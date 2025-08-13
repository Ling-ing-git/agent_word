# -*- coding: utf-8 -*-
# 用法:
#   pip install lxml Pillow
#   python replace_docx_text_and_images_notranscode.py in.docx mapping.json -o out.docx
#
# 映射示例 mapping.json:
# {
#   "猫娘": "Catgirl",
#   "图斑": "Patch",
#   "image1": "/abs/path/new1.png",          # 推荐绝对路径
#   "image2.jpg": "/abs/path/new2.webp"      # 非支持格式 -> 自动转成原格式（jpg）
# }
#
# 规则（图片）：
# - 默认不转码：
#   * 若新图片扩展名 与 原包内目标扩展名相同：直接替换二进制
#   * 若不同：若新扩展是 Word 支持的 -> 改包结构（重命名 word/media/*.ext + 更新 .rels Target + 更新 [Content_Types].xml）
# - 若新图片扩展 Word 不支持：自动转码为“原目标扩展名”对应的格式（仅该处转码）
# - 显示尺寸：等比缩放；不超过原 wp:extent@cx/cy；不放大；不变形；同步 pic:spPr/a:xfrm/a:ext

import sys, json, re, difflib, os, io
from typing import Optional, List, Dict, Tuple, Set
from zipfile import ZipFile
from lxml import etree
from PIL import Image

NS = {
    "w":   "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "mc":  "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wp":  "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a":   "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS  = "http://schemas.openxmlformats.org/package/2006/content-types"
EMU_PER_PX = 9525  # 96dpi 近似

TEXT_PARTS = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
)

# Word 常见可显示格式 & ContentType
SUPPORTED_IMAGE_CT = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".bmp":  "image/bmp",
    ".tif":  "image/tiff",
    ".tiff": "image/tiff",
    ".emf":  "image/x-emf",
    ".wmf":  "image/x-wmf",
}
UNSUPPORTED_HINT = {".webp": "多数 Word 版本不支持 WebP；将自动转为原格式"}

def _ln(tag: Optional[str]) -> str:
    if not isinstance(tag, str): return ""
    return tag.split("}", 1)[1] if "}" in tag else tag

def _in_fallback(node: etree._Element) -> bool:
    for a in node.iterancestors():
        if _ln(a.tag) == "Fallback":
            return True
    return False

def _is_deleted_or_field(node: etree._Element) -> bool:
    ln = _ln(node.tag)
    if ln in ("del", "delText", "instrText", "moveFrom"): return True
    for a in node.iterancestors():
        if _ln(a.tag) in ("del", "moveFrom"): return True
    return False

def _is_hidden_run(node: etree._Element) -> bool:
    for a in node.iterancestors():
        if _ln(a.tag) == "r":
            if a.find(".//w:rPr/w:vanish", namespaces=NS) is not None:
                return True
            break
    return False

def _nearest(node: etree._Element, names: Tuple[str, ...]) -> Optional[etree._Element]:
    for a in node.iterancestors():
        if _ln(a.tag) in names:
            return a
    return None

def _nearest_para(node: etree._Element) -> Optional[etree._Element]:
    return _nearest(node, ("p",))

def _nearest_container(node: etree._Element) -> Optional[etree._Element]:
    return _nearest(node, ("hyperlink", "p"))

def _xml_space_preserve(t_elem: etree._Element, text: str):
    if text.startswith(" ") or text.endswith(" "):
        t_elem.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    elif "{http://www.w3.org/XML/1998/namespace}space" in t_elem.attrib and text.strip() == text:
        del t_elem.attrib["{http://www.w3.org/XML/1998/namespace}space"]

def _clone_r_with_text(src_r: etree._Element, repl_text: str) -> etree._Element:
    new_r = etree.Element(src_r.tag, nsmap=src_r.nsmap)
    rpr = src_r.find("./w:rPr", namespaces=NS)
    if rpr is not None:
        new_r.append(etree.fromstring(etree.tostring(rpr)))
    t = etree.Element("{%s}t" % NS["w"])
    t.text = repl_text
    _xml_space_preserve(t, repl_text)
    new_r.append(t)
    return new_r

def _remove_run_if_empty(r: etree._Element):
    ts = r.findall(".//w:t", namespaces=NS)
    if not ts:
        parent = r.getparent()
        if parent is not None:
            parent.remove(r)
        return
    only_text = "".join((t.text or "") for t in ts)
    if only_text == "":
        parent = r.getparent()
        if parent is not None:
            parent.remove(r)

def _iter_visible_text_nodes_in_para(p: etree._Element):
    for t in p.xpath(".//w:t", namespaces=NS):
        if _is_deleted_or_field(t) or _in_fallback(t) or _is_hidden_run(t):
            continue
        if _nearest_para(t) is not p:
            continue
        r = _nearest(t, ("r",))
        if r is None:
            continue
        container = _nearest_container(t) or p
        yield {"t": t, "r": r, "container": container, "text": t.text or ""}

def _replace_once_in_container(paragraph: etree._Element, atoms: List[Dict], start: int, end: int, repl: str) -> bool:
    covered = [a for a in atoms if not (a["end"] <= start or a["start"] >= end)]
    if not covered:
        return False
    container = covered[0]["container"]
    if any(a["container"] is not container for a in covered):
        return False
    first = covered[0]
    last = covered[-1]
    f_keep = max(0, start - first["start"])
    l_drop_after = max(0, last["end"] - end)
    f_text = first["t"].text or ""
    first_before = f_text[:f_keep]
    first["t"].text = first_before
    _xml_space_preserve(first["t"], first_before)
    for mid in covered:
        if mid is first or mid is last:
            continue
        mid["t"].text = ""
        _xml_space_preserve(mid["t"], "")
    if last is not first:
        l_text = last["t"].text or ""
        last_after = l_text[len(l_text) - l_drop_after:] if l_drop_after > 0 else ""
        last["t"].text = last_after
        _xml_space_preserve(last["t"], last_after)
    new_r = _clone_r_with_text(first["r"], repl)
    parent = first["r"].getparent()
    idx = parent.index(first["r"])
    parent.insert(idx + 1, new_r)
    for mid in covered:
        _remove_run_if_empty(mid["r"])
    return True

def _replace_in_paragraph(p: etree._Element, mapping: Dict[str, str]) -> Dict[str, Dict[str, int]]:
    stats: Dict[str, Dict[str, int]] = {k: {"replaced": 0, "skippedCrossContainer": 0} for k in mapping.keys()}

    def build_atoms():
        atoms = []
        pos = 0
        for a in _iter_visible_text_nodes_in_para(p):
            txt = a["text"]
            if not txt:
                continue
            start = pos
            end = pos + len(txt)
            atoms.append({**a, "start": start, "end": end})
            pos = end
        full = "".join(a["text"] for a in atoms)
        return atoms, full

    for key, repl in mapping.items():
        if not key:
            continue
        search_pos = 0
        while True:
            atoms, full = build_atoms()
            if search_pos > len(full):
                break
            idx = full.find(key, search_pos)
            if idx < 0:
                break
            ok = _replace_once_in_container(p, atoms, idx, idx + len(key), repl)
            if ok:
                stats[key]["replaced"] += 1
                search_pos = idx + len(repl)
            else:
                stats[key]["skippedCrossContainer"] += 1
                search_pos = idx + 1
    return stats

def _extract_blocks_and_replace(container: etree._Element, text_map: Dict[str, str]) -> Dict[str, Dict[str, int]]:
    agg_stats: Dict[str, Dict[str, int]] = {k: {"replaced": 0, "skippedCrossContainer": 0} for k in text_map.keys()}
    for child in container:
        if not isinstance(child.tag, str):
            continue
        if _in_fallback(child):
            continue
        tag = _ln(child.tag)
        if tag == "p":
            s = _replace_in_paragraph(child, text_map)
            for k in agg_stats:
                agg_stats[k]["replaced"] += s[k]["replaced"]
                agg_stats[k]["skippedCrossContainer"] += s[k]["skippedCrossContainer"]
            for txbx in child.xpath(".//wps:txbx[not(ancestor::mc:Fallback)]", namespaces=NS):
                content = txbx.find(".//w:txbxContent", namespaces=NS)
                if content is not None:
                    ss = _extract_blocks_and_replace(content, text_map)
                    for k in agg_stats:
                        agg_stats[k]["replaced"] += ss[k]["replaced"]
                        agg_stats[k]["skippedCrossContainer"] += ss[k]["skippedCrossContainer"]
        elif tag == "tbl":
            for tr in child.xpath("./w:tr[not(ancestor::mc:Fallback)]", namespaces=NS):
                for tc in tr.xpath("./w:tc", namespaces=NS):
                    ss = _extract_blocks_and_replace(tc, text_map)
                    for k in agg_stats:
                        agg_stats[k]["replaced"] += ss[k]["replaced"]
                        agg_stats[k]["skippedCrossContainer"] += ss[k]["skippedCrossContainer"]
    return agg_stats

def _collect_vocab(root: etree._Element) -> List[str]:
    words = set()
    for t in root.xpath(".//w:t[not(ancestor::mc:Fallback)]", namespaces=NS):
        if _is_deleted_or_field(t) or _is_hidden_run(t):
            continue
        s = (t.text or "").strip()
        if not s:
            continue
        words.add(s)
        for w in re.split(r"\s+", s):
            if w:
                words.add(w)
    return list(words)

def _list_header_footer_parts(z: ZipFile) -> List[str]:
    names = []
    for info in z.infolist():
        fn = info.filename
        if fn.startswith("word/header") and fn.endswith(".xml"):
            names.append(fn)
        elif fn.startswith("word/footer") and fn.endswith(".xml"):
            names.append(fn)
    return names

def _rels_path_for_part(part_path: str) -> str:
    d, base = part_path.rsplit("/", 1)
    return f"{d}/_rels/{base}.rels"

def _build_rel_map_from_bytes(rels_bytes: bytes) -> Dict[str, str]:
    root = etree.fromstring(rels_bytes)
    m = {}
    for rel in root.findall(f".//{{{REL_NS}}}Relationship"):
        rid = rel.get("Id"); tgt = rel.get("Target")
        if rid and tgt:
            m[rid] = tgt
    return m

def _reverse_media_targets(rel_map: Dict[str, str]) -> Dict[str, Set[str]]:
    rev: Dict[str, Set[str]] = {}
    for rid, tgt in rel_map.items():
        if tgt.startswith("media/"):
            base = tgt.split("/")[-1]
            rev.setdefault(base, set()).add(rid)
    return rev

def _get_img_px(path: str) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.width, im.height

def _extent_from_drawing(drawing: etree._Element) -> Optional[Tuple[etree._Element, int, int]]:
    holder = drawing.find(".//wp:inline", namespaces=NS) or drawing.find(".//wp:anchor", namespaces=NS)
    if holder is None:
        return None
    ext = holder.find(".//wp:extent", namespaces=NS)
    if ext is None:
        return None
    try:
        cx = int(ext.get("cx")); cy = int(ext.get("cy"))
        return ext, cx, cy
    except (TypeError, ValueError):
        return None

def _set_pic_extents(drawing: etree._Element, new_cx: int, new_cy: int):
    holder = drawing.find(".//wp:inline", namespaces=NS) or drawing.find(".//wp:anchor", namespaces=NS)
    if holder is not None:
        ext = holder.find(".//wp:extent", namespaces=NS)
        if ext is not None:
            ext.set("cx", str(int(new_cx))); ext.set("cy", str(int(new_cy)))
    for path in (".//pic:spPr/a:xfrm/a:ext", ".//wps:wsp/wps:spPr/a:xfrm/a:ext"):
        e = drawing.find(path, namespaces=NS)
        if e is not None:
            e.set("cx", str(int(new_cx))); e.set("cy", str(int(new_cy)))

def _scale_fit(emu_w: int, emu_h: int, box_w: int, box_h: int) -> Tuple[int, int]:
    # 约束：不放大（展示面积不大于原图）；且至少有一条边等于“原图展示大小”或等于盒子限制边
    # - 若原图两边都不超过盒子：直接用原图尺寸（不放大；两边都等于“原图展示大小”）
    # - 若需要缩小以适配盒子：选取限制边等于盒子对应边，另一边按比例四舍五入
    if emu_w <= 0 or emu_h <= 0 or box_w <= 0 or box_h <= 0:
        return emu_w, emu_h
    # 不放大：原图本身已经小于等于盒子
    if emu_w <= box_w and emu_h <= box_h:
        return emu_w, emu_h
    # 需要缩小：保证至少有一条边等于盒子边
    ratio_w = box_w / emu_w
    ratio_h = box_h / emu_h
    if ratio_w <= ratio_h:
        new_w = box_w
        new_h = int(round(emu_h * ratio_w))
    else:
        new_h = box_h
        new_w = int(round(emu_w * ratio_h))
    # 保险起见不超过盒子
    if new_w > box_w:
        new_w = box_w
    if new_h > box_h:
        new_h = box_h
    return int(new_w), int(new_h)

def _ensure_content_type_default(file_map: Dict[str, bytes], ext: str):
    ext = ext.lower().lstrip(".")
    ct_path = "[Content_Types].xml"
    root = etree.fromstring(file_map[ct_path])
    has = root.find(f".//{{{CT_NS}}}Default[@Extension='{ext}']")
    if has is None:
        ct = SUPPORTED_IMAGE_CT.get("." + ext)
        if ct:
            el = etree.Element(f"{{{CT_NS}}}Default", Extension=ext, ContentType=ct)
            root.append(el)
            file_map[ct_path] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

def replace_docx(in_path: str, mapping: Dict[str, str], out_path: str) -> Dict:
    # 拆分文本/图片映射
    text_map: Dict[str, str] = {}
    image_map: Dict[str, str] = {}
    for k, v in mapping.items():
        key = str(k)
        val = "" if v is None else str(v)
        if re.fullmatch(r"image\d+(\.[A-Za-z0-9]+)?", key) and os.path.exists(val):
            image_map[key] = os.path.abspath(val)
        else:
            text_map[key] = val

    # 读原包
    with ZipFile(in_path) as zin:
        file_map = {i.filename: zin.read(i.filename) for i in zin.infolist()}
    parts = set(TEXT_PARTS)
    with ZipFile(in_path) as zin:
        parts.update(_list_header_footer_parts(zin))

    # 文本替换
    total_text_stats = {k: {"replaced": 0, "skippedCrossContainer": 0} for k in text_map.keys()}
    vocab_all: List[str] = []

    for name in parts:
        data = file_map.get(name)
        if not data:
            continue
        root = etree.fromstring(data)
        vocab_all.extend(_collect_vocab(root))
        body = root.find(".//w:body", namespaces=NS)
        container = body if body is not None else root
        stats = _extract_blocks_and_replace(container, text_map)
        for k in total_text_stats:
            total_text_stats[k]["replaced"] += stats[k]["replaced"]
            total_text_stats[k]["skippedCrossContainer"] += stats[k]["skippedCrossContainer"]
        file_map[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

    # 构建 rId->Target（以及 basename->rIds）映射（基于当前包）
    part_rel_bytes: Dict[str, bytes] = {}
    part_rel_roots: Dict[str, etree._Element] = {}
    part_rel_maps: Dict[str, Dict[str, str]] = {}
    part_rev_media: Dict[str, Dict[str, Set[str]]] = {}
    for name in parts:
        rels_path = _rels_path_for_part(name)
        b = file_map.get(rels_path)
        if not b:
            part_rel_maps[name] = {}
            part_rev_media[name] = {}
            continue
        part_rel_bytes[name] = b
        root = etree.fromstring(b)
        part_rel_roots[name] = root
        rel_map = _build_rel_map_from_bytes(b)
        part_rel_maps[name] = rel_map
        part_rev_media[name] = _reverse_media_targets(rel_map)

    # 命中：imageKey -> set(word/media/basename)
    image_hits: Dict[str, Set[str]] = {k: set() for k in image_map.keys()}
    for name in parts:
        rev = part_rev_media.get(name, {})
        for key in image_map.keys():
            key_lower = key.lower()
            for base, rids in rev.items():
                base_lower = base.lower()
                if base_lower == key_lower or os.path.splitext(base_lower)[0] == os.path.splitext(key_lower)[0]:
                    image_hits[key].add(f"word/media/{base}")

    # 图片替换 & 包结构调整（不转码优先，必要时自动转）
    image_report: Dict[str, Dict] = {k: {"foundTargets": [], "replaced": False, "renamed": [], "autoTranscoded": [], "instancesAdjusted": 0, "errors": ""} for k in image_map.keys()}

    # 先执行“媒体重命名+内容写入”
    for key, img_path in image_map.items():
        targets = sorted(image_hits.get(key, set()))
        image_report[key]["foundTargets"] = targets
        if not targets:
            image_report[key]["errors"] = "no matching media found by basename"
            continue

        new_ext = os.path.splitext(img_path)[1].lower()
        new_supported = new_ext in SUPPORTED_IMAGE_CT

        for target in targets:
            base_dir, old_base = target.rsplit("/", 1)
            old_ext = os.path.splitext(old_base)[1].lower()

            # 选择策略
            if new_ext == old_ext:
                # 1) 同扩展：不转码，直接替换二进制
                with open(img_path, "rb") as f:
                    file_map[target] = f.read()
                image_report[key]["replaced"] = True

            elif new_supported:
                # 2) 新扩展 Word 支持：不转码，改包结构（重命名 + 更新 .rels + 更新 Content_Types）
                new_base = os.path.splitext(old_base)[0] + new_ext
                new_target = f"{base_dir}/{new_base}"
                # 避免重名冲突
                if new_target in file_map and new_target != target:
                    stem = os.path.splitext(old_base)[0]
                    i = 1
                    while f"{base_dir}/{stem}_{i}{new_ext}" in file_map:
                        i += 1
                    new_base = f"{stem}_{i}{new_ext}"
                    new_target = f"{base_dir}/{new_base}"

                # 写入新图片
                with open(img_path, "rb") as f:
                    file_map[new_target] = f.read()
                # 删除旧媒体
                if target in file_map:
                    del file_map[target]

                # 更新所有部件 .rels 里指向 old_base 的 Relationship.Target
                for pname in parts:
                    rel_root = part_rel_roots.get(pname)
                    if rel_root is None:
                        continue
                    changed = False
                    for rel in rel_root.findall(f".//{{{REL_NS}}}Relationship"):
                        tgt = rel.get("Target")
                        if tgt == f"media/{old_base}":
                            rel.set("Target", f"media/{new_base}")
                            changed = True
                    if changed:
                        file_map[_rels_path_for_part(pname)] = etree.tostring(rel_root, xml_declaration=True, encoding="UTF-8", standalone="yes")

                # 确保 Content_Types 有该扩展
                _ensure_content_type_default(file_map, new_ext)

                image_report[key]["replaced"] = True
                image_report[key]["renamed"].append({"from": old_base, "to": new_base})

            else:
                # 3) 新扩展 Word 不支持：自动转码为原扩展对应格式（仅该处转码）
                hint = UNSUPPORTED_HINT.get(new_ext, "")
                try:
                    with Image.open(img_path) as im:
                        buf = io.BytesIO()
                        if old_ext in (".jpg", ".jpeg"):
                            im.save(buf, format="JPEG", quality=92)
                        elif old_ext == ".png":
                            im.save(buf, format="PNG")
                        elif old_ext in (".tif", ".tiff"):
                            im.save(buf, format="TIFF")
                        elif old_ext == ".gif":
                            im.save(buf, format="GIF")
                        elif old_ext == ".bmp":
                            im.save(buf, format="BMP")
                        else:
                            # 兜底：转成 PNG 并把包结构改为 .png（因为旧扩展可能本身也不常用）
                            base_dir, old_base = target.rsplit("/", 1)
                            stem = os.path.splitext(old_base)[0]
                            new_base = stem + ".png"
                            new_target = f"{base_dir}/{new_base}"
                            if new_target in file_map and new_target != target:
                                i = 1
                                while f"{base_dir}/{stem}_{i}.png" in file_map:
                                    i += 1
                                new_base = f"{stem}_{i}.png"
                                new_target = f"{base_dir}/{new_base}"
                            im.save(buf, format="PNG")
                            # 改包结构到 PNG
                            file_map[new_target] = buf.getvalue()
                            if target in file_map:
                                del file_map[target]
                            for pname in parts:
                                rel_root = part_rel_roots.get(pname)
                                if rel_root is None:
                                    continue
                                changed = False
                                for rel in rel_root.findall(f".//{{{REL_NS}}}Relationship"):
                                    tgt = rel.get("Target")
                                    if tgt == f"media/{old_base}":
                                        rel.set("Target", f"media/{new_base}")
                                        changed = True
                                if changed:
                                    file_map[_rels_path_for_part(pname)] = etree.tostring(rel_root, xml_declaration=True, encoding="UTF-8", standalone="yes")
                            _ensure_content_type_default(file_map, ".png")
                            image_report[key]["replaced"] = True
                            image_report[key]["autoTranscoded"].append({"fromExt": new_ext, "to": new_base, "hint": hint})
                            continue

                        # 直接覆盖旧 target
                        file_map[target] = buf.getvalue()
                        image_report[key]["replaced"] = True
                        image_report[key]["autoTranscoded"].append({"fromExt": new_ext, "to": old_base, "hint": hint})
                except Exception as e:
                    image_report[key]["errors"] = f"autotranscode failed: {e}"

    # 尺寸调整（按实例 wp:extent，等比、不超过原框、不放大）
    img_px_cache: Dict[str, Tuple[int, int]] = {}
    for name in parts:
        data = file_map.get(name)
        if not data:
            continue
        root = etree.fromstring(data)
        # 更新后的 .rels
        rel_bytes = file_map.get(_rels_path_for_part(name))
        rel_map = _build_rel_map_from_bytes(rel_bytes) if rel_bytes else {}
        changed = False

        # 建 rid -> hit-keys（哪些 imageKey 影响此 rid）
        base_to_keys: Dict[str, List[str]] = {}
        for k, ts in image_hits.items():
            for t in ts:
                base_to_keys.setdefault(os.path.basename(t), []).append(k)
        rid_to_keys: Dict[str, List[str]] = {}
        for rid, tgt in rel_map.items():
            if tgt.startswith("media/"):
                base = tgt.split("/")[-1]
                if base in base_to_keys:
                    rid_to_keys[rid] = base_to_keys[base]

        for drawing in root.xpath(".//w:drawing[not(ancestor::mc:Fallback)]", namespaces=NS):
            blip = drawing.find(".//a:blip", namespaces=NS)
            if blip is None:
                continue
            rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            if not rid or rid not in rid_to_keys:
                continue
            # 取该 rid 对应的第一个 imageKey 的路径
            key = rid_to_keys[rid][0]
            img_path = image_map.get(key)
            if not img_path:
                continue
            try:
                if img_path not in img_px_cache:
                    with Image.open(img_path) as im:
                        img_px_cache[img_path] = (im.width, im.height)
                px_w, px_h = img_px_cache[img_path]
                emu_w = int(px_w * EMU_PER_PX); emu_h = int(px_h * EMU_PER_PX)
            except Exception:
                continue

            ext_info = _extent_from_drawing(drawing)
            if not ext_info:
                # 无 extent，直接设置为实际像素（不放大则同等）
                _set_pic_extents(drawing, emu_w, emu_h)
                # 记一次调整在所有相关 key 上
                for k in rid_to_keys[rid]:
                    image_report[k]["instancesAdjusted"] += 1
                changed = True
                continue

            _, box_w, box_h = ext_info
            new_w, new_h = _scale_fit(emu_w, emu_h, box_w, box_h)
            _set_pic_extents(drawing, new_w, new_h)
            for k in rid_to_keys[rid]:
                image_report[k]["instancesAdjusted"] += 1
            changed = True

        if changed:
            file_map[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

    # 写出新 docx
    with ZipFile(out_path, "w") as zout:
        for fn, bytes_ in file_map.items():
            zout.writestr(fn, bytes_)

    # 文本未命中 & DidYouMean
    vocab_all = list(set(vocab_all))
    failures = []
    did = {}
    for k, st in total_text_stats.items():
        if st["replaced"] == 0:
            failures.append(k)
            did[k] = difflib.get_close_matches(k, vocab_all, n=3, cutoff=0.6)

    return {
        "textStats": total_text_stats,
        "textFailures": failures,
        "didYouMean": did,
        "imageReport": image_report
    }

if __name__ == "__main__":
    in_docx = 'example.docx'
    mapping_json = 'mapping.json'
    out_docx = 'out.docx'
    with open(mapping_json, "r", encoding="utf-8") as f:
        mapping = json.load(f)
        if not isinstance(mapping, dict):
            print("ERROR: mapping.json must be an object like {\"old\":\"new\", \"image1\":\"/path/img.png\"}", file=sys.stderr)
            sys.exit(2)
    report = replace_docx(in_docx, mapping, out_docx)
    print(json.dumps(report, ensure_ascii=False, indent=2))