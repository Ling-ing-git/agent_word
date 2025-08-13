# -*- coding: utf-8 -*-
# 功能：
# - 按文档顺序导出“块列表”：paragraph / textbox / table / image / shape
# - 图片：输出关系 rId 对应的目标文件名（name）、完整包内路径（file）、描述（desc）、尺寸（cx/cy）
# - 颜色块：识别 DrawingML 形状填充色/描边色（hex）
# - 处理文本框嵌套，排除 mc:Fallback，避免 VML 回退重复
#
# 依赖：pip install lxml
# 用法：python export_blocks_images_shapes.py input.docx > out.json

import sys, json, os
from zipfile import ZipFile
from lxml import etree
from typing import Optional, List, Dict

NS = {
    "w":   "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "mc":  "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wp":  "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a":   "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}

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
    if ln in ("del", "delText", "instrText", "moveFrom"):
        return True
    for a in node.iterancestors():
        if _ln(a.tag) in ("del", "moveFrom"):
            return True
    return False

def _is_hidden_run(node: etree._Element) -> bool:
    for a in node.iterancestors():
        if _ln(a.tag) == "r":
            if a.find(".//w:rPr/w:vanish", namespaces=NS) is not None:
                return True
            break
    return False

def _nearest_para(node: etree._Element) -> Optional[etree._Element]:
    for a in node.iterancestors():
        if _ln(a.tag) == "p":
            return a
    return None

def _iter_para_units(p: etree._Element):
    # 仅产出“属于当前段落 p 自身”的文本单元
    for node in p.iter():
        if _is_deleted_or_field(node) or _in_fallback(node) or _is_hidden_run(node):
            continue
        if _nearest_para(node) is not p:
            continue
        ln = _ln(node.tag)
        if ln == "t" and node.text:
            yield node.text
        elif ln in ("br", "cr"):
            yield "\n"
        elif ln == "tab":
            yield "\t"

def _paragraph_text(p: etree._Element) -> str:
    return "".join(_iter_para_units(p))

def _read_xml(z: ZipFile, name: str) -> Optional[etree._Element]:
    try:
        return etree.fromstring(z.read(name))
    except (KeyError, etree.XMLSyntaxError, OSError, ValueError):
        return None

def _build_rel_map(z: ZipFile, rels_path: str) -> Dict[str, str]:
    """
    构建关系映射：rId -> Target（如 'media/image1.png'）
    传入示例：'word/_rels/document.xml.rels'
    """
    rel_map: Dict[str, str] = {}
    rels = _read_xml(z, rels_path)
    if rels is None:
        return rel_map
    for rel in rels.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
        rid = rel.get("Id")
        target = rel.get("Target")
        rtype = rel.get("Type")
        # 仅保留非超链接（主要用于图片）
        if rtype == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink":
            continue
        if rid and target:
            # 规范里 Target 是相对路径；这里直接记录相对路径
            rel_map[rid] = target
    return rel_map

# 新增：构建超链接关系映射 rId -> {target, mode}

def _build_hyperlink_rel_map(z: ZipFile, rels_path: str) -> Dict[str, Dict[str, Optional[str]]]:
    hyper_map: Dict[str, Dict[str, Optional[str]]] = {}
    rels = _read_xml(z, rels_path)
    if rels is None:
        return hyper_map
    for rel in rels.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
        rid = rel.get("Id")
        rtype = rel.get("Type")
        if rtype != "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink":
            continue
        target = rel.get("Target")
        mode = rel.get("TargetMode")  # External / Internal
        if rid and target:
            hyper_map[rid] = {"target": target, "mode": mode}
    return hyper_map

def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1] if "/" in path else path

def _color_hex_from_solidFill(node: etree._Element) -> Optional[str]:
    # a:solidFill/a:srgbClr @val -> '#RRGGBB'
    srgb = node.find(".//a:solidFill/a:srgbClr", namespaces=NS)
    if srgb is not None and srgb.get("val"):
        val = srgb.get("val").upper()
        if not val.startswith("#"):
            val = "#" + val
        return val
    return None

def _shape_colors_from_spPr(spPr: etree._Element) -> Dict[str, Optional[str]]:
    return {
        "fill": _color_hex_from_solidFill(spPr),
        "stroke": _color_hex_from_solidFill(spPr.find(".//a:ln", namespaces=NS)) if spPr is not None else None,
    }

def _extent_from_inline_or_anchor(drawing: etree._Element) -> Dict[str, Optional[int]]:
    # 从 wp:inline/wp:anchor 读尺寸（EMU）
    inline = drawing.find(".//wp:inline", namespaces=NS)
    anchor = drawing.find(".//wp:anchor", namespaces=NS)
    holder = inline if inline is not None else anchor
    if holder is not None:
        ext = holder.find(".//wp:extent", namespaces=NS)
        if ext is not None:
            try:
                return {"cx": int(ext.get("cx")), "cy": int(ext.get("cy"))}
            except (TypeError, ValueError):
                pass
    return {"cx": None, "cy": None}

def _drawables_in_paragraph(p: etree._Element, rel_map: Dict[str, str]) -> List[Dict]:
    """
    提取段落内（属于该段落自身）的图片与颜色形状，按出现顺序返回块：
    - image：通过 a:blip@r:embed -> rId -> rel_map -> Target -> basename
    - shape：通过 wps:wsp/wps:spPr 下的 a:solidFill/a:srgbClr 识别填充与描边
    """
    blocks: List[Dict] = []
    # 遍历该段落内出现的 w:drawing（过滤 Fallback；只取最近祖先段落为 p）
    for drawing in p.xpath(".//w:drawing[not(ancestor::mc:Fallback)]", namespaces=NS):
        if _nearest_para(drawing) is not p:
            continue

        # 1) 图片：a:blip@r:embed
        blip = drawing.find(".//a:blip", namespaces=NS)
        if blip is not None:
            rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            if rid and rid in rel_map:
                target = rel_map[rid]                   # e.g. 'media/image1.png'
                name = _basename(target)               # 'image1.png'
                # 描述信息（非必须）
                docPr = drawing.find(".//wp:docPr", namespaces=NS)
                #desc = docPr.get("descr") if docPr is not None else None
                size = _extent_from_inline_or_anchor(drawing)
                blocks.append({
                    "type": "image",
                    "name": name,
                    "relId": rid,
                    "file": f"word/{target}" if not target.startswith("/") else target,
                    #"desc": desc,
                    "size": size,
                })
                continue  # 一个 drawing 若是图片，就不当作 shape 处理

        # 2) 颜色形状：wps:wsp/wps:spPr
        spPr = drawing.find(".//wps:wsp/wps:spPr", namespaces=NS)
        if spPr is not None:
            colors = _shape_colors_from_spPr(spPr)
            if colors["fill"] or colors["stroke"]:
                blocks.append({
                    "type": "shape",
                    **colors
                })
                continue

        # 3) 有些配图的轮廓在 pic:spPr 上（一般是图片边框或裁剪形状）
        pic_spPr = drawing.find(".//pic:spPr", namespaces=NS)
        if pic_spPr is not None:
            colors = _shape_colors_from_spPr(pic_spPr)
            if colors["fill"] or colors["stroke"]:
                blocks.append({
                    "type": "shape",
                    **colors
                })
                continue

    return blocks

# 新增：提取段落内的超链接块

def _hyperlinks_in_paragraph(p: etree._Element, hyper_map: Dict[str, Dict[str, Optional[str]]]) -> List[Dict]:
    blocks: List[Dict] = []
    for h in p.xpath(".//w:hyperlink[not(ancestor::mc:Fallback)]", namespaces=NS):
        if _nearest_para(h) is not p:
            continue
        # 采集该超链接内的可见文本
        parts: List[str] = []
        for node in h.iter():
            if _is_deleted_or_field(node) or _in_fallback(node) or _is_hidden_run(node):
                continue
            ln = _ln(node.tag)
            if ln == "t" and node.text:
                parts.append(node.text)
            elif ln in ("br", "cr"):
                parts.append("\n")
            elif ln == "tab":
                parts.append("\t")
        link_text = "".join(parts)
        if not link_text:
            continue
        rid = h.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        anchor = h.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}anchor")
        tooltip = h.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tooltip")
        if rid and rid in hyper_map:
            target = hyper_map[rid].get("target")
            mode = (hyper_map[rid].get("mode") or "").lower()
            if mode == "external":
                blk = {"type": "hyperlink", "text": link_text, "url": target, "relId": rid, "external": True}
                if tooltip:
                    blk["tooltip"] = tooltip
                blocks.append(blk)
            else:
                # 内部链接，可能 target 形如 '#Bookmark'
                anchor_name = anchor
                if not anchor_name and target:
                    anchor_name = target[1:] if target.startswith("#") else target
                blk = {"type": "hyperlink", "text": link_text, "anchor": anchor_name, "relId": rid, "external": False}
                if tooltip:
                    blk["tooltip"] = tooltip
                blocks.append(blk)
        elif anchor:
            blk = {"type": "hyperlink", "text": link_text, "anchor": anchor, "external": False}
            if tooltip:
                blk["tooltip"] = tooltip
            blocks.append(blk)
        # 若既无 rid 也无 anchor，忽略
    return blocks

def _extract_blocks_from_container(container: etree._Element, rel_map: Dict[str, str], hyper_map: Dict[str, Dict[str, Optional[str]]]) -> List[Dict]:
    """
    从容器（w:body / w:txbxContent / w:tc）按顺序抽取块：
    - 段落：paragraph + 段落中的 drawables（image/shape）+ 段落中的文本框（textbox，递归）+ 段落中的超链接（hyperlink）
    - 表格：table.rows[row][col] = 块数组（递归）
    """
    blocks: List[Dict] = []
    for child in container:
        if not isinstance(child.tag, str):
            continue
        if _in_fallback(child):
            continue

        tag = _ln(child.tag)

        if tag == "p":
            text = _paragraph_text(child)
            if text:
                blocks.append({"type": "paragraph", "text": text})

            # 段落内的图片/形状（按出现顺序追加）
            drawables = _drawables_in_paragraph(child, rel_map)
            blocks.extend(drawables)

            # 段落内的文本框 -> 独立 textbox 块（children 递归）
            for txbx in child.xpath(".//wps:txbx[not(ancestor::mc:Fallback)]", namespaces=NS):
                content = txbx.find(".//w:txbxContent", namespaces=NS)
                if content is None:
                    continue
                children = _extract_blocks_from_container(content, rel_map, hyper_map)
                if children:
                    blocks.append({"type": "textbox", "children": children})

            # 段落内的超链接（按出现顺序追加）
            hyperlinks = _hyperlinks_in_paragraph(child, hyper_map)
            blocks.extend(hyperlinks)

        elif tag == "tbl":
            rows: List[List[List[Dict]]] = []
            for tr in child.xpath("./w:tr[not(ancestor::mc:Fallback)]", namespaces=NS):
                row_cells: List[List[Dict]] = []
                for tc in tr.xpath("./w:tc", namespaces=NS):
                    cell_blocks = _extract_blocks_from_container(tc, rel_map, hyper_map)
                    row_cells.append(cell_blocks)
                rows.append(row_cells)
            if rows:
                blocks.append({"type": "table", "rows": rows})

    return blocks

def export_document_blocks(docx_path: str) -> List[Dict]:
    try:
        with ZipFile(docx_path) as z:
            # 构建主文档关系映射（图片 rId -> media 路径；超链接 rId -> target/mode）
            rels_path = "word/_rels/document.xml.rels"
            rel_map = _build_rel_map(z, rels_path)
            hyper_map = _build_hyperlink_rel_map(z, rels_path)

            root = _read_xml(z, "word/document.xml")
            if root is None:
                return []
            body = root.find(".//w:body", namespaces=NS)
            if body is None:
                return []
            return _extract_blocks_from_container(body, rel_map, hyper_map)
    except FileNotFoundError:
        # 文件不存在
        return []
    except Exception:
        # 其他异常（包括 BadZipFile 等），返回空
        return []

if __name__ == "__main__":
    try:
        docx_path = sys.argv[1]
    except IndexError:
        sys.stderr.write("Usage: python word_scan.py <input.docx>\n")
        sys.exit(2)
    try:
        blocks = export_document_blocks(docx_path)
        sys.stdout.write(json.dumps(blocks, ensure_ascii=False, indent=2))
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)