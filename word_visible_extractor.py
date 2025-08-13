import json
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


# Constants
EMU_PER_INCH = 914400
EMU_PER_PX_AT_96_DPI = 9525
TWIPS_PER_POINT = 20
TWIPS_PER_PX_AT_96_DPI = 15


# Utilities

def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _attr_val(elem: ET.Element, local_attr: str) -> Optional[str]:
    for k, v in elem.attrib.items():
        if _local_name(k) == local_attr:
            return v
    return None

# Added: CN size/font helpers
CN_SIZE_NAME_MAP: List[Tuple[float, str]] = [
    (42.0, "初号"), (36.0, "小初"), (26.0, "一号"), (24.0, "小一"), (22.0, "二号"),
    (18.0, "小二"), (16.0, "三号"), (15.0, "小三"), (14.0, "四号"), (12.0, "小四"),
    (10.5, "五号"), (9.0, "小五"), (7.5, "六号"), (6.5, "小六"), (5.5, "七号"), (5.0, "八号"),
]

CN_FONT_ALIASES: Dict[str, str] = {
    "SimSun": "宋体",
    "NSimSun": "新宋体",
    "KaiTi": "楷体",
    "FangSong": "仿宋",
    "SimHei": "黑体",
    "Microsoft YaHei": "微软雅黑",
    "Microsoft YaHei UI": "微软雅黑",
    "Songti SC": "宋体",
    "Heiti SC": "黑体",
}


def pt_to_cn_size_name(point_size: Optional[float], tolerance: float = 0.3) -> Optional[str]:
    if point_size is None:
        return None
    best: Tuple[float, Optional[str]] = (1e9, None)
    for pt, name in CN_SIZE_NAME_MAP:
        diff = abs(point_size - pt)
        if diff < best[0]:
            best = (diff, name)
    if best[0] <= tolerance:
        return best[1]
    return None


def localize_font_name(font_name: Optional[str]) -> Optional[str]:
    if not font_name:
        return None
    return CN_FONT_ALIASES.get(font_name, font_name)


def build_style_display(rs: "RunStyle") -> List[str]:
    display_parts: List[str] = []
    size_name = pt_to_cn_size_name(rs.font_size_pt)
    if size_name:
        display_parts.append(size_name)
    font = rs.font_family_east_asia or rs.font_family_ascii or rs.font_family_cs
    font_disp = localize_font_name(font)
    if font_disp:
        display_parts.append(font_disp)
    return display_parts


def build_style_summary_cn(rs: "RunStyle") -> Optional[str]:
    parts = build_style_display(rs)
    return "，".join(parts) if parts else None


# Styles parsing and resolution
@dataclass
class RunStyle:
    font_family_ascii: Optional[str] = None
    font_family_east_asia: Optional[str] = None
    font_family_cs: Optional[str] = None
    font_size_pt: Optional[float] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[str] = None
    color_rgb: Optional[str] = None  # like FF0000
    highlight: Optional[str] = None
    strike: Optional[bool] = None

    def merge(self, overlay: "RunStyle") -> "RunStyle":
        result = RunStyle(
            font_family_ascii=overlay.font_family_ascii or self.font_family_ascii,
            font_family_east_asia=overlay.font_family_east_asia or self.font_family_east_asia,
            font_family_cs=overlay.font_family_cs or self.font_family_cs,
            font_size_pt=overlay.font_size_pt if overlay.font_size_pt is not None else self.font_size_pt,
            bold=overlay.bold if overlay.bold is not None else self.bold,
            italic=overlay.italic if overlay.italic is not None else self.italic,
            underline=overlay.underline or self.underline,
            color_rgb=overlay.color_rgb or self.color_rgb,
            highlight=overlay.highlight or self.highlight,
            strike=overlay.strike if overlay.strike is not None else self.strike,
        )
        return result

    def to_summary_str(self) -> Optional[str]:
        parts: List[str] = []
        if self.font_size_pt:
            parts.append(f"{self.font_size_pt:g}pt")
        # Prefer east asia font for CJK
        font = self.font_family_east_asia or self.font_family_ascii or self.font_family_cs
        if font:
            parts.append(font)
        if not parts:
            return None
        return ", ".join(parts)

    def to_json(self) -> Dict[str, Any]:
        return {
            "fontFamily": self.font_family_east_asia or self.font_family_ascii or self.font_family_cs,
            "fontFamilyAscii": self.font_family_ascii,
            "fontFamilyEastAsia": self.font_family_east_asia,
            "fontFamilyComplex": self.font_family_cs,
            "fontSizePt": self.font_size_pt,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "color": f"#{self.color_rgb}" if self.color_rgb and not self.color_rgb.startswith("#") else self.color_rgb,
            "highlight": self.highlight,
            "strike": self.strike,
        }


@dataclass
class StyleDef:
    style_id: str
    style_type: str  # paragraph/character
    name: Optional[str]
    rpr: RunStyle = field(default_factory=RunStyle)


@dataclass
class StylesResolver:
    default_run: RunStyle = field(default_factory=RunStyle)
    styles: Dict[str, StyleDef] = field(default_factory=dict)

    @staticmethod
    def from_styles_xml(xml_bytes: Optional[bytes]) -> "StylesResolver":
        if not xml_bytes:
            return StylesResolver()
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return StylesResolver()

        resolver = StylesResolver()
        # docDefaults
        for dd in root.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}docDefaults'):
            for rp in dd.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPrDefault'):
                rpr = rp.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr')
                if rpr is not None:
                    resolver.default_run = _parse_rpr(rpr)

        # individual styles
        for s in root.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}style'):
            style_id = _attr_val(s, 'styleId') or ''
            style_type = _attr_val(s, 'type') or ''
            name_elem = s.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name')
            name_val = _attr_val(name_elem, 'val') if name_elem is not None else None
            rpr_elem = s.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr')
            rpr = _parse_rpr(rpr_elem) if rpr_elem is not None else RunStyle()
            resolver.styles[style_id] = StyleDef(style_id=style_id, style_type=style_type, name=name_val, rpr=rpr)

        return resolver

    def resolve_run_style(self, r_elem: Optional[ET.Element], p_elem: Optional[ET.Element]) -> RunStyle:
        result = self.default_run

        # Paragraph style contributes run defaults
        p_style_id = None
        if p_elem is not None:
            pPr = p_elem.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr')
            if pPr is not None:
                pStyle = pPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pStyle')
                if pStyle is not None:
                    p_style_id = _attr_val(pStyle, 'val')
                    if p_style_id and p_style_id in self.styles:
                        result = result.merge(self.styles[p_style_id].rpr)

        # Character style on run
        if r_elem is not None:
            rPr = r_elem.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr')
            if rPr is not None:
                rStyle = rPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rStyle')
                if rStyle is not None:
                    r_style_id = _attr_val(rStyle, 'val')
                    if r_style_id and r_style_id in self.styles:
                        result = result.merge(self.styles[r_style_id].rpr)
                # Direct formatting
                direct = _parse_rpr(rPr)
                result = result.merge(direct)
        return result

    def get_paragraph_style_name(self, p_elem: ET.Element) -> Optional[str]:
        pPr = p_elem.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr')
        if pPr is None:
            return None
        pStyle = pPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pStyle')
        if pStyle is None:
            return None
        sid = _attr_val(pStyle, 'val')
        if not sid:
            return None
        sd = self.styles.get(sid)
        return sd.name if sd and sd.name else sid


def _parse_rpr(rpr: Optional[ET.Element]) -> RunStyle:
    if rpr is None:
        return RunStyle()
    rs = RunStyle()
    rFonts = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts')
    if rFonts is not None:
        rs.font_family_ascii = _attr_val(rFonts, 'ascii')
        rs.font_family_east_asia = _attr_val(rFonts, 'eastAsia')
        rs.font_family_cs = _attr_val(rFonts, 'cs')
    sz = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sz')
    if sz is not None:
        val = _attr_val(sz, 'val')
        if val and val.isdigit():
            rs.font_size_pt = int(val) / 2.0
    b = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}b')
    if b is not None:
        rs.bold = True
    i = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}i')
    if i is not None:
        rs.italic = True
    u = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}u')
    if u is not None:
        rs.underline = _attr_val(u, 'val') or 'single'
    color = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}color')
    if color is not None:
        rs.color_rgb = _attr_val(color, 'val')
    hl = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}highlight')
    if hl is not None:
        rs.highlight = _attr_val(hl, 'val')
    strike = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}strike')
    if strike is not None:
        rs.strike = True
    dstrike = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}dstrike')
    if dstrike is not None:
        rs.strike = True
    return rs


# Numbering support
@dataclass
class LvlDef:
    ilvl: int
    num_fmt: str  # decimal, lowerRoman, bullet, etc.
    lvl_text: Optional[str]  # e.g., "%1."
    start: int = 1


@dataclass
class NumberingResolver:
    num_to_abs: Dict[str, str] = field(default_factory=dict)
    abs_to_lvls: Dict[str, Dict[int, LvlDef]] = field(default_factory=dict)
    num_lvl_overrides: Dict[Tuple[str, int], int] = field(default_factory=dict)
    counters: Dict[str, Dict[int, int]] = field(default_factory=dict)  # numId -> ilvl -> counter

    @staticmethod
    def from_numbering_xml(xml_bytes: Optional[bytes]) -> "NumberingResolver":
        if not xml_bytes:
            return NumberingResolver()
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return NumberingResolver()
        nr = NumberingResolver()
        # numId -> abstractNumId and lvlOverrides
        for num in root.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}num'):
            num_id = _attr_val(num, 'numId')
            if not num_id:
                continue
            an = num.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}abstractNumId')
            if an is not None:
                nr.num_to_abs[num_id] = _attr_val(an, 'val') or ''
            for lo in num.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}lvlOverride'):
                ilvl_str = _attr_val(lo, 'ilvl')
                if ilvl_str and ilvl_str.isdigit():
                    ilvl = int(ilvl_str)
                    so = lo.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}startOverride')
                    if so is not None:
                        val = _attr_val(so, 'val')
                        if val and val.isdigit():
                            nr.num_lvl_overrides[(num_id, ilvl)] = int(val)
        # abstract levels
        for an in root.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}abstractNum'):
            an_id = _attr_val(an, 'abstractNumId') or ''
            lvl_map: Dict[int, LvlDef] = {}
            for lvl in an.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}lvl'):
                ilvl_str = _attr_val(lvl, 'ilvl')
                if not ilvl_str or not ilvl_str.isdigit():
                    continue
                ilvl = int(ilvl_str)
                num_fmt_elem = lvl.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numFmt')
                num_fmt = _attr_val(num_fmt_elem, 'val') if num_fmt_elem is not None else 'decimal'
                lvl_text_elem = lvl.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}lvlText')
                lvl_text = _attr_val(lvl_text_elem, 'val') if lvl_text_elem is not None else None
                start_elem = lvl.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}start')
                start_val = 1
                if start_elem is not None:
                    s = _attr_val(start_elem, 'val')
                    if s and s.isdigit():
                        start_val = int(s)
                lvl_map[ilvl] = LvlDef(ilvl=ilvl, num_fmt=num_fmt or 'decimal', lvl_text=lvl_text, start=start_val)
            nr.abs_to_lvls[an_id] = lvl_map
        return nr

    def _init_counters_if_needed(self, num_id: str) -> None:
        if num_id not in self.counters:
            self.counters[num_id] = {}

    def next_label(self, num_id: str, ilvl: int) -> Optional[str]:
        if num_id not in self.num_to_abs:
            return None
        abs_id = self.num_to_abs[num_id]
        lvl_map = self.abs_to_lvls.get(abs_id)
        if not lvl_map:
            return None
        lvl_def = lvl_map.get(ilvl)
        if not lvl_def:
            return None
        # Initialize counters up to ilvl
        self._init_counters_if_needed(num_id)
        for i in list(self.counters[num_id].keys()):
            if i > ilvl:
                # deeper levels reset when moving up
                self.counters[num_id].pop(i, None)
        # ensure parents exist
        for i in range(0, ilvl + 1):
            if i not in self.counters[num_id]:
                start_val = self.num_lvl_overrides.get((num_id, i), lvl_map.get(i, lvl_def).start if lvl_map.get(i) else 1)
                self.counters[num_id][i] = start_val - 1
        # increment current level
        self.counters[num_id][ilvl] += 1
        # build text using lvlText with placeholders %1..%9
        values = {i + 1: self._format_number(self.counters[num_id].get(i, 1), lvl_map.get(i)) for i in range(0, 9)}
        if lvl_def.lvl_text:
            text = lvl_def.lvl_text
            for k, v in values.items():
                text = text.replace(f"%{k}", v)
            return text
        # fallback
        return self._format_number(self.counters[num_id][ilvl], lvl_def)

    def _format_number(self, value: int, lvl_def: Optional[LvlDef]) -> str:
        fmt = (lvl_def.num_fmt if lvl_def else 'decimal').lower()
        if fmt == 'decimal':
            return str(value)
        if fmt == 'lowerletter':
            return _to_alpha(value, upper=False)
        if fmt == 'upperletter':
            return _to_alpha(value, upper=True)
        if fmt == 'lowerroman':
            return _to_roman(value).lower()
        if fmt == 'upperroman':
            return _to_roman(value)
        if fmt == 'bullet':
            return '•'
        # default
        return str(value)


def _to_alpha(n: int, upper: bool) -> str:
    if n <= 0:
        return ''
    result = ''
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr((ord('A') if upper else ord('a')) + rem) + result
    return result


def _to_roman(n: int) -> str:
    vals = [
        (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
        (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
        (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')
    ]
    result = ''
    for v, s in vals:
        while n >= v:
            result += s
            n -= v
    return result


# Relationships
@dataclass
class Relationship:
    r_id: str
    r_type: str
    target: str
    target_mode: Optional[str]


def _read_part_relationships(zf: zipfile.ZipFile, part_path: str) -> Dict[str, Relationship]:
    rels_path = part_path.replace('word/', 'word/_rels/').replace('.xml', '.xml.rels')
    rels: Dict[str, Relationship] = {}
    try:
        xml_bytes = zf.read(rels_path)
    except KeyError:
        return rels
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return rels
    for rel in root.findall('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
        rid = _attr_val(rel, 'Id') or ''
        rtype = _attr_val(rel, 'Type') or ''
        target = _attr_val(rel, 'Target') or ''
        tmode = _attr_val(rel, 'TargetMode')
        rels[rid] = Relationship(r_id=rid, r_type=rtype, target=target, target_mode=tmode)
    return rels


# Core extraction
@dataclass
class VisibleItem:
    type: str  # text | table | image | hyperlink
    data: Dict[str, Any]


def _extract_text_runs(p: ET.Element, styles: StylesResolver, numbering: NumberingResolver) -> List[VisibleItem]:
    items: List[VisibleItem] = []

    # Determine numbering label if any
    pPr = p.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr')
    list_label: Optional[str] = None
    if pPr is not None:
        numPr = pPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr')
        if numPr is not None:
            numId_elem = numPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numId')
            ilvl_elem = numPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ilvl')
            num_id = _attr_val(numId_elem, 'val') if numId_elem is not None else None
            ilvl_val = _attr_val(ilvl_elem, 'val') if ilvl_elem is not None else '0'
            if num_id and ilvl_val and ilvl_val.isdigit():
                list_label = numbering.next_label(num_id, int(ilvl_val))

    # Iterate children to preserve run order; also handle hyperlinks
    for child in list(p):
        lname = _local_name(child.tag)
        if lname == 'r':
            text = _collect_text_from_run(child)
            if text:
                rstyle = styles.resolve_run_style(child, p)
                item = VisibleItem(
                    type='text',
                    data={
                        'text': text,
                        'style': build_style_display(rstyle),
                        'styleSummaryCn': build_style_summary_cn(rstyle),
                        'styleRaw': rstyle.to_json(),
                        'styleSummary': rstyle.to_summary_str(),
                    },
                )
                if list_label:
                    item.data['listLabel'] = list_label
                    list_label = None  # only show once at paragraph start
                # Paragraph style name
                ps_name = styles.get_paragraph_style_name(p)
                if ps_name:
                    item.data['paragraphStyle'] = ps_name
                items.append(item)
        elif lname == 'hyperlink':
            rid = _attr_val(child, 'id') or _attr_val(child, 'r:id')
            if rid:
                link_text = _collect_text_from_runs(child)
                if link_text:
                    rstyle = styles.resolve_run_style(None, p)
                    items.append(
                        VisibleItem(
                            type='hyperlink',
                            data={
                                'text': link_text,
                                'rId': rid,
                                'style': build_style_display(rstyle),
                                'styleSummaryCn': build_style_summary_cn(rstyle),
                                'styleRaw': rstyle.to_json(),
                                'styleSummary': rstyle.to_summary_str(),
                            },
                        )
                    )
        elif lname == 'drawing':
            # drawings may carry images or textboxes; handled in outer walker to attach rels
            pass
        elif lname == 'fldSimple' or lname == 'smartTag':
            # recurse for runs inside
            for sub in child:
                if _local_name(sub.tag) == 'r':
                    text = _collect_text_from_run(sub)
                    if text:
                        rstyle = styles.resolve_run_style(sub, p)
                        items.append(VisibleItem(type='text', data={'text': text, 'style': build_style_display(rstyle), 'styleSummaryCn': build_style_summary_cn(rstyle), 'styleRaw': rstyle.to_json(), 'styleSummary': rstyle.to_summary_str()}))
        # ignore other nodes

    return items


def _collect_text_from_runs(parent: ET.Element) -> str:
    parts: List[str] = []
    for r in parent.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r'):
        t = _collect_text_from_run(r)
        if t:
            parts.append(t)
    return ''.join(parts)


def _collect_text_from_run(r: ET.Element) -> str:
    parts: List[str] = []
    for node in r.iter():
        lname = _local_name(node.tag)
        if lname == 't':
            if node.text:
                parts.append(node.text)
        elif lname in {'tab'}:
            parts.append('\t')
        elif lname in {'br', 'cr'}:
            parts.append('\n')
        elif lname == 'sym':
            char_hex = _attr_val(node, 'char')
            if char_hex:
                try:
                    parts.append(chr(int(char_hex, 16)))
                except Exception:
                    pass
        elif lname == 'instrText' or lname == 'del':
            # skip field codes and deleted content
            continue
    return ''.join(parts)


def _extract_textbox_paragraphs(node: ET.Element) -> List[str]:
    texts: List[str] = []
    for txbx in node.iter():
        if _local_name(txbx.tag) == 'txbxContent':
            for p in txbx.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                txt = _collect_text_from_runs(p)
                if txt.strip():
                    texts.append(txt)
    return texts


def _extract_images_from_paragraph(p: ET.Element, rels: Dict[str, Relationship]) -> List[VisibleItem]:
    items: List[VisibleItem] = []
    for drawing in p.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing'):
        # Find extent
        cx = cy = None
        # Try wp:extent
        for el in drawing.iter():
            lname = _local_name(el.tag)
            if lname == 'extent':
                cx_attr = _attr_val(el, 'cx')
                cy_attr = _attr_val(el, 'cy')
                if cx_attr and cy_attr and cx is None and cy is None:
                    try:
                        cx = int(cx_attr)
                        cy = int(cy_attr)
                    except Exception:
                        pass
            if lname == 'ext' and (cx is None or cy is None):
                cx_attr = _attr_val(el, 'cx')
                cy_attr = _attr_val(el, 'cy')
                if cx_attr and cy_attr:
                    try:
                        cx = int(cx_attr)
                        cy = int(cy_attr)
                    except Exception:
                        pass
        # Find blip with r:embed
        embed_rid = None
        for el in drawing.iter():
            if _local_name(el.tag) == 'blip':
                rid = _attr_val(el, 'embed') or _attr_val(el, 'r:embed')
                if rid:
                    embed_rid = rid
                    break
        if embed_rid and embed_rid in rels:
            rel = rels[embed_rid]
            if 'image' in rel.r_type:
                # Resolve size to px as well
                width_px = cx / EMU_PER_PX_AT_96_DPI if cx else None
                height_px = cy / EMU_PER_PX_AT_96_DPI if cy else None
                items.append(
                    VisibleItem(
                        type='image',
                        data={
                            'image': rel.target if rel.target_mode == 'External' else f"word/{rel.target}" if not rel.target.startswith('word/') else rel.target,
                            'size': {'cx': cx, 'cy': cy},
                            'sizePx': {'width': width_px, 'height': height_px},
                            'sizeEmu': {'cx': cx, 'cy': cy},
                        },
                    )
                )
    return items


def _extract_table(tbl: ET.Element, styles: StylesResolver, numbering: NumberingResolver) -> VisibleItem:
    # Table width info
    tblW_twips: Optional[int] = None
    tblW_type: Optional[str] = None
    tblPr = tbl.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblPr')
    if tblPr is not None:
        tblW = tblPr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblW')
        if tblW is not None:
            val = _attr_val(tblW, 'val')
            typ = _attr_val(tblW, 'type')
            if val and val.isdigit():
                tblW_twips = int(val)
            tblW_type = typ

    rows: List[List[str]] = []
    for tr in tbl.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tr'):
        row_texts: List[str] = []
        for tc in tr.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc'):
            cell_paras: List[str] = []
            for p in tc.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                text = _collect_text_from_runs(p)
                if text:
                    cell_paras.append(text)
            row_texts.append("\n".join(cell_paras))
        if row_texts:
            rows.append(row_texts)

    size_obj: Dict[str, Any] = {}
    if tblW_twips is not None:
        size_obj['tblWidthTwips'] = tblW_twips
        size_obj['tblWidthPxApprox'] = tblW_twips / TWIPS_PER_PX_AT_96_DPI
    if tblW_type:
        size_obj['tblWidthType'] = tblW_type

    return VisibleItem(type='table', data={'table': rows, 'size': size_obj})


def extract_visible_content(docx_path: str, include_headers: bool = True, include_footers: bool = True,
                            include_footnotes: bool = True, include_endnotes: bool = True) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    with zipfile.ZipFile(docx_path, 'r') as zf:
        namelist = set(zf.namelist())

        # Load styles and numbering
        styles_xml = zf.read('word/styles.xml') if 'word/styles.xml' in namelist else None
        numbering_xml = zf.read('word/numbering.xml') if 'word/numbering.xml' in namelist else None
        styles = StylesResolver.from_styles_xml(styles_xml)
        numbering = NumberingResolver.from_numbering_xml(numbering_xml)

        parts: List[str] = []
        if 'word/document.xml' in namelist:
            parts.append('word/document.xml')
        if include_headers:
            parts += sorted(p for p in namelist if p.startswith('word/header') and p.endswith('.xml'))
        if include_footers:
            parts += sorted(p for p in namelist if p.startswith('word/footer') and p.endswith('.xml'))
        if include_footnotes and 'word/footnotes.xml' in namelist:
            parts.append('word/footnotes.xml')
        if include_endnotes and 'word/endnotes.xml' in namelist:
            parts.append('word/endnotes.xml')

        # Traverse each part in order
        for part in parts:
            try:
                root = ET.fromstring(zf.read(part))
            except ET.ParseError:
                continue
            rels = _read_part_relationships(zf, part)

            body = root.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body')
            top_level = list(body) if body is not None else list(root)
            for node in top_level:
                lname = _local_name(node.tag)
                if lname == 'p':
                    # text runs
                    for item in _extract_text_runs(node, styles, numbering):
                        # resolve hyperlink URLs where applicable
                        if item.type == 'hyperlink':
                            rid = item.data.get('rId')
                            if rid and rid in rels and 'hyperlink' in rels[rid].r_type:
                                target = rels[rid].target
                                if rels[rid].target_mode == 'External':
                                    item.data['url'] = target
                                else:
                                    # internal bookmark
                                    item.data['bookmark'] = target
                                item.data.pop('rId', None)
                        items.append({'type': item.type, **item.data})
                    # images inside paragraph
                    for img in _extract_images_from_paragraph(node, rels):
                        items.append({'type': img.type, **img.data})
                    # textboxes
                    tbx_texts = _extract_textbox_paragraphs(node)
                    for t in tbx_texts:
                        items.append({'type': 'text', 'text': t})
                elif lname == 'tbl':
                    tbl_item = _extract_table(node, styles, numbering)
                    items.append({'type': tbl_item.type, **tbl_item.data})
                # ignore other top-level nodes

    return items


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Extract all user-visible content (text with styles, tables, images) from a .docx.')
    parser.add_argument('docx_path', help='Path to the .docx file')
    parser.add_argument('--no-headers', action='store_true')
    parser.add_argument('--no-footers', action='store_true')
    parser.add_argument('--no-footnotes', action='store_true')
    parser.add_argument('--no-endnotes', action='store_true')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON')

    args = parser.parse_args()

    result = extract_visible_content(
        args.docx_path,
        include_headers=not args.no_headers,
        include_footers=not args.no_footers,
        include_footnotes=not args.no_footnotes,
        include_endnotes=not args.no_endnotes,
    )
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))

# Single function API

def scan_docx_to_json(docx_path: str, pretty: bool = False) -> str:
    items = extract_visible_content(
        docx_path,
        include_headers=True,
        include_footers=True,
        include_footnotes=True,
        include_endnotes=True,
    )
    return json.dumps(items, ensure_ascii=False, indent=2 if pretty else None)