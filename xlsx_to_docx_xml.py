#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Convert XLSX to DOCX using raw Office Open XML (OOXML).
- Reads sheet names and cell values from .xlsx (ZIP) via XML
- Builds a minimal .docx (ZIP) with word/document.xml created via XML
- No third-party dependencies

Usage:
  python xlsx_to_docx_xml.py input.xlsx output.docx

Optional flags:
  --sheets SHEET1 SHEET2     Only include specified sheet names (default: all)
  --max-rows N               Limit rows per sheet (default: no limit)
  --max-cols N               Limit columns per sheet (default: auto)
  --separator-blank-rows N   Split tables by N consecutive empty rows (default: 1)
  --trim-empty-cols          Trim trailing empty columns per table (default: off)

Note:
- Numbers/dates are not formatted; values are taken as-is from the XML
- Shared strings and inline strings are supported
- Rich text runs are concatenated
- Tables are split by blank-row separators and each table starts on a new page
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

# Namespaces
NS_SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_REL_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_XML = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("w", NS_W)
ET.register_namespace("r", NS_REL_OFFICE)


def column_letters_to_index(column_letters: str) -> int:
    """Convert Excel column letters (e.g., 'A', 'AA') to 0-based index."""
    result = 0
    for ch in column_letters.upper():
        if not ('A' <= ch <= 'Z'):
            continue
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result - 1


def parse_cell_reference(cell_ref: str) -> Tuple[int, int]:
    """Parse a cell reference like 'B3' into (row_index_0based, col_index_0based)."""
    match = re.match(r"^([A-Za-z]+)(\d+)$", cell_ref)
    if not match:
        return 0, 0
    col_letters, row_str = match.groups()
    col_idx = column_letters_to_index(col_letters)
    row_idx = int(row_str) - 1
    return row_idx, col_idx


def read_zip_xml(zf: zipfile.ZipFile, path: str) -> Optional[ET.Element]:
    try:
        with zf.open(path) as fp:
            data = fp.read()
        return ET.fromstring(data)
    except KeyError:
        return None


def extract_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    shared: List[str] = []
    root = read_zip_xml(zf, "xl/sharedStrings.xml")
    if root is None:
        return shared
    for si in root.findall(f".//{{{NS_SS}}}si"):
        # Concatenate all text within <si>, including rich text runs
        text_parts: List[str] = []
        for node in si.iter():
            if node.tag == f"{{{NS_SS}}}t" and node.text is not None:
                text_parts.append(node.text)
        shared.append("".join(text_parts))
    return shared


def extract_workbook_sheets(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
    """Return list of (sheet_name, target_path) relative to xl/ ..."""
    workbook = read_zip_xml(zf, "xl/workbook.xml")
    rels = read_zip_xml(zf, "xl/_rels/workbook.xml.rels")
    if workbook is None or rels is None:
        raise ValueError("Invalid XLSX: missing workbook.xml or workbook.xml.rels")

    # Map relationship Id -> Target
    id_to_target: Dict[str, str] = {}
    for rel in rels.findall(f".//{{{NS_REL}}}Relationship"):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target:
            if not target.startswith("/"):
                target = f"xl/{target}" if not target.startswith("xl/") else target
            id_to_target[rel_id] = target

    sheets: List[Tuple[str, str]] = []
    for sheet in workbook.findall(f".//{{{NS_SS}}}sheet"):
        name = sheet.attrib.get("name", "Sheet")
        rel_id = sheet.attrib.get(f"{{{NS_REL_OFFICE}}}id")
        if rel_id and rel_id in id_to_target:
            target_path = id_to_target[rel_id]
            sheets.append((name, target_path))
    return sheets


def extract_sheet_grid(
    zf: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: List[str],
    max_rows: Optional[int] = None,
    max_cols: Optional[int] = None,
) -> List[List[str]]:
    sheet = read_zip_xml(zf, sheet_path)
    if sheet is None:
        return []

    rows_map: Dict[int, Dict[int, str]] = {}
    max_col_index = -1
    last_row_index = -1

    for row in sheet.findall(f".//{{{NS_SS}}}row"):
        # Row index may be absent; derive from first cell if needed
        for cell in row.findall(f".//{{{NS_SS}}}c"):
            cell_ref = cell.attrib.get("r")
            if not cell_ref:
                continue
            row_idx, col_idx = parse_cell_reference(cell_ref)

            cell_type = cell.attrib.get("t")
            text_value: str = ""

            if cell_type == "s":
                v = cell.find(f"{{{NS_SS}}}v")
                if v is not None and v.text is not None:
                    try:
                        idx = int(v.text)
                        text_value = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
                    except ValueError:
                        text_value = v.text
            elif cell_type == "inlineStr":
                is_el = cell.find(f"{{{NS_SS}}}is")
                if is_el is not None:
                    parts: List[str] = []
                    for node in is_el.iter():
                        if node.tag == f"{{{NS_SS}}}t" and node.text is not None:
                            parts.append(node.text)
                    text_value = "".join(parts)
            elif cell_type == "b":
                v = cell.find(f"{{{NS_SS}}}v")
                text_value = "TRUE" if (v is not None and v.text == "1") else "FALSE"
            else:
                v = cell.find(f"{{{NS_SS}}}v")
                if v is not None and v.text is not None:
                    text_value = v.text
                else:
                    text_value = ""

            if max_cols is not None and col_idx >= max_cols:
                continue

            if row_idx not in rows_map:
                rows_map[row_idx] = {}
            rows_map[row_idx][col_idx] = text_value
            if col_idx > max_col_index:
                max_col_index = col_idx
            if row_idx > last_row_index:
                last_row_index = row_idx

            if max_rows is not None and row_idx + 1 >= max_rows:
                # Still consume row for padding, but skip further cells beyond limit
                continue

    if max_cols is not None and max_col_index >= 0:
        max_col_index = min(max_col_index, max_cols - 1)

    # Build dense grid including blank (missing) rows
    grid: List[List[str]] = []
    if last_row_index >= 0 and max_col_index >= -1:
        last_dense_row = last_row_index
        if max_rows is not None:
            last_dense_row = min(last_dense_row, max_rows - 1)
        if max_col_index < 0:
            # No cells at all; return empty grid
            return []
        for row_idx in range(0, last_dense_row + 1):
            row_dict = rows_map.get(row_idx, {})
            row_list = [row_dict.get(col_idx, "") for col_idx in range(max_col_index + 1)]
            grid.append(row_list)

    return grid


def is_empty_row(row: List[str]) -> bool:
    return all((cell is None or cell == "") for cell in row)


def trim_trailing_empty_columns(grid: List[List[str]]) -> List[List[str]]:
    if not grid:
        return grid
    last_non_empty_col = -1
    for row in grid:
        for col_idx, val in enumerate(row):
            if val is not None and val != "":
                if col_idx > last_non_empty_col:
                    last_non_empty_col = col_idx
    if last_non_empty_col == -1:
        return [[""]]
    trimmed: List[List[str]] = []
    for row in grid:
        trimmed.append(row[: last_non_empty_col + 1])
    return trimmed


def split_grid_into_tables(grid: List[List[str]], min_blank_rows_between: int = 1) -> List[List[List[str]]]:
    if not grid:
        return []
    tables: List[List[List[str]]] = []
    current: List[List[str]] = []
    blank_run = 0

    for row in grid:
        if is_empty_row(row):
            blank_run += 1
            current.append(row)
            continue
        # Non-empty row
        if blank_run >= min_blank_rows_between and current:
            # Cut off the separator rows from current
            if min_blank_rows_between > 0:
                current = current[:-blank_run]
            # Trim leading/trailing empty rows
            while current and is_empty_row(current[0]):
                current.pop(0)
            while current and is_empty_row(current[-1]):
                current.pop()
            if current:
                tables.append(current)
            current = []
        blank_run = 0
        current.append(row)

    # Finalize last segment
    if current:
        if blank_run >= min_blank_rows_between and min_blank_rows_between > 0:
            current = current[:-blank_run]
        while current and is_empty_row(current[0]):
            current.pop(0)
        while current and is_empty_row(current[-1]):
            current.pop()
        if current:
            tables.append(current)

    return tables


def build_word_paragraph(text: str) -> ET.Element:
    p = ET.Element(f"{{{NS_W}}}p")
    r = ET.SubElement(p, f"{{{NS_W}}}r")
    # Split on newlines, inserting w:br between runs
    parts = text.split("\n")
    for idx, part in enumerate(parts):
        t = ET.SubElement(r, f"{{{NS_W}}}t")
        t.set(f"{{{NS_XML}}}space", "preserve")
        t.text = part
        if idx < len(parts) - 1:
            ET.SubElement(r, f"{{{NS_W}}}br")
    return p


def build_page_break_paragraph() -> ET.Element:
    p = ET.Element(f"{{{NS_W}}}p")
    r = ET.SubElement(p, f"{{{NS_W}}}r")
    br = ET.SubElement(r, f"{{{NS_W}}}br")
    br.set(f"{{{NS_W}}}type", "page")
    return p


def build_word_table(grid: List[List[str]]) -> ET.Element:
    tbl = ET.Element(f"{{{NS_W}}}tbl")

    # Optional basic table properties for borders could be added here if desired
    # Ensure at least one empty row with one empty cell if grid is empty
    effective_grid = grid if grid else [[""]]

    for row_values in effective_grid:
        tr = ET.SubElement(tbl, f"{{{NS_W}}}tr")
        if not row_values:
            row_values = [""]
        for cell_text in row_values:
            tc = ET.SubElement(tr, f"{{{NS_W}}}tc")
            p = build_word_paragraph(cell_text if cell_text is not None else "")
            tc.append(p)
    return tbl


def build_word_document_xml(sheets: List[Tuple[str, List[List[str]]]]) -> bytes:
    root = ET.Element(f"{{{NS_W}}}document")
    body = ET.SubElement(root, f"{{{NS_W}}}body")

    for idx, (sheet_name, grid) in enumerate(sheets):
        # Sheet title paragraph
        title_p = build_word_paragraph(f"Sheet: {sheet_name}")
        body.append(title_p)

        # Table for the sheet (or table segment)
        tbl = build_word_table(grid)
        body.append(tbl)

        # Page break between tables (not after the last one)
        if idx < len(sheets) - 1:
            body.append(build_page_break_paragraph())

    # Section properties (required end element in a valid Word doc)
    sectPr = ET.SubElement(body, f"{{{NS_W}}}sectPr")
    pgSz = ET.SubElement(sectPr, f"{{{NS_W}}}pgSz")
    pgSz.set(f"{{{NS_W}}}w", "11906")  # A4 width in twips
    pgSz.set(f"{{{NS_W}}}h", "16838")  # A4 height in twips

    pgMar = ET.SubElement(sectPr, f"{{{NS_W}}}pgMar")
    pgMar.set(f"{{{NS_W}}}top", "1440")
    pgMar.set(f"{{{NS_W}}}right", "1440")
    pgMar.set(f"{{{NS_W}}}bottom", "1440")
    pgMar.set(f"{{{NS_W}}}left", "1440")
    pgMar.set(f"{{{NS_W}}}header", "708")
    pgMar.set(f"{{{NS_W}}}footer", "708")
    pgMar.set(f"{{{NS_W}}}gutter", "0")

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True)
    return xml_bytes


def build_content_types_xml() -> bytes:
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
        "</Types>"
    )
    return xml.encode("utf-8")


def build_root_rels_xml() -> bytes:
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>"
        "</Relationships>"
    )
    return xml.encode("utf-8")


def write_docx(document_xml: bytes, out_path: str) -> None:
    with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", build_content_types_xml())
        zf.writestr("_rels/.rels", build_root_rels_xml())
        zf.writestr("word/document.xml", document_xml)


def xlsx_to_docx(
    xlsx_path: str,
    docx_path: str,
    only_sheets: Optional[List[str]] = None,
    max_rows: Optional[int] = None,
    max_cols: Optional[int] = None,
    separator_blank_rows: int = 1,
    trim_empty_cols: bool = False,
) -> None:
    with zipfile.ZipFile(xlsx_path, "r") as zf:
        shared = extract_shared_strings(zf)
        sheets_info = extract_workbook_sheets(zf)

        prepared: List[Tuple[str, List[List[str]]]] = []
        for sheet_name, sheet_target in sheets_info:
            if only_sheets and sheet_name not in only_sheets:
                continue
            grid = extract_sheet_grid(
                zf,
                sheet_target,
                shared,
                max_rows=max_rows,
                max_cols=max_cols,
            )
            tables = split_grid_into_tables(grid, min_blank_rows_between=separator_blank_rows)
            if not tables:
                prepared.append((sheet_name, []))
            else:
                for t in tables:
                    if trim_empty_cols:
                        t = trim_trailing_empty_columns(t)
                    prepared.append((sheet_name, t))

    document_xml = build_word_document_xml(prepared)
    write_docx(document_xml, docx_path)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert XLSX to DOCX using raw OOXML (no third-party libs)")
    parser.add_argument("input_xlsx", help="Path to input .xlsx file")
    parser.add_argument("output_docx", help="Path to output .docx file")
    parser.add_argument("--sheets", nargs="*", default=None, help="Only include these sheet names")
    parser.add_argument("--max-rows", type=int, default=None, help="Limit number of rows per sheet")
    parser.add_argument("--max-cols", type=int, default=None, help="Limit number of columns per sheet")
    parser.add_argument("--separator-blank-rows", type=int, default=1, help="Split tables by N consecutive empty rows")
    parser.add_argument("--trim-empty-cols", action="store_true", help="Trim trailing empty columns per table")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        xlsx_to_docx(
            args.input_xlsx,
            args.output_docx,
            only_sheets=args.sheets,
            max_rows=args.max_rows,
            max_cols=args.max_cols,
            separator_blank_rows=args.separator_blank_rows,
            trim_empty_cols=args.trim_empty_cols,
        )
    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())