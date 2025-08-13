import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, Iterable, List, Optional, Tuple


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _extract_w_namespace(root: ET.Element) -> Optional[str]:
    if root.tag.startswith("{"):
        return root.tag.split("}", 1)[0][1:]
    return None


def _gather_text_tokens(element: ET.Element) -> List[str]:
    tokens: List[str] = []
    stack: List[ET.Element] = [element]

    while stack:
        node = stack.pop()
        name = _local_name(node.tag)

        # Skip deleted content and field instruction text
        if name in {"del", "instrText"}:
            continue

        if name == "t":
            if node.text:
                tokens.append(node.text)
            # No need to descend further; w:t has no meaningful children for text
            continue

        if name in {"tab"}:
            tokens.append("\t")
            continue

        if name in {"br", "cr"}:
            tokens.append("\n")
            continue

        if name == "sym":
            # Best-effort decode of symbol character
            # The visible glyph depends on font; w:char is hex of Unicode code point or Private Use
            char_hex: Optional[str] = None
            for attr_key, attr_val in node.attrib.items():
                if _local_name(attr_key) == "char":
                    char_hex = attr_val
                    break
            if char_hex:
                try:
                    tokens.append(chr(int(char_hex, 16)))
                except Exception:
                    pass
            continue

        if name == "noBreakHyphen":
            tokens.append("\u2011")
            continue

        if name == "softHyphen":
            tokens.append("\u00AD")
            continue

        # Depth-first traversal (children processed before siblings for natural order)
        # We push children in reverse so leftmost child is processed first when popping
        children = list(node)
        for child in reversed(children):
            # Skip any subtree explicitly marked as deletion
            if _local_name(child.tag) == "del":
                continue
            stack.append(child)

    return tokens


def _extract_paragraph_text(paragraph: ET.Element) -> str:
    tokens = _gather_text_tokens(paragraph)
    # Normalize: collapse multiple newlines produced by consecutive br/cr
    text = "".join(tokens)
    return text


def _extract_texts_from_part_xml(xml_bytes: bytes) -> List[str]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    w_ns = _extract_w_namespace(root) or "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    p_xpath = f".//{{{w_ns}}}p"

    paragraphs: List[str] = []
    for p in root.findall(p_xpath):
        para_text = _extract_paragraph_text(p)
        if para_text.strip():
            paragraphs.append(para_text)
    return paragraphs


def extract_texts_by_part(
    docx_path: str,
    include_headers: bool = True,
    include_footers: bool = True,
    include_footnotes: bool = True,
    include_endnotes: bool = True,
    include_comments: bool = False,
) -> Dict[str, List[str]]:
    """
    Extract visible text paragraphs from a .docx, grouped by part path.

    - Skips deleted revisions (w:del) and field instruction text (w:instrText)
    - Includes paragraphs from body, tables, textboxes (w:txbxContent), etc.
    - Optionally includes headers/footers/footnotes/endnotes/comments

    Returns a mapping of part path (e.g., "word/document.xml") to list of paragraph strings.
    """
    parts_to_consider: List[str] = []

    with zipfile.ZipFile(docx_path, "r") as zf:
        namelist = set(zf.namelist())

        # Main document
        if "word/document.xml" in namelist:
            parts_to_consider.append("word/document.xml")

        # Headers and footers
        if include_headers:
            parts_to_consider.extend(sorted([n for n in namelist if n.startswith("word/header") and n.endswith(".xml")]))
        if include_footers:
            parts_to_consider.extend(sorted([n for n in namelist if n.startswith("word/footer") and n.endswith(".xml")]))

        # Footnotes and endnotes
        if include_footnotes and "word/footnotes.xml" in namelist:
            parts_to_consider.append("word/footnotes.xml")
        if include_endnotes and "word/endnotes.xml" in namelist:
            parts_to_consider.append("word/endnotes.xml")

        # Comments (non-visible in document body, optional)
        if include_comments and "word/comments.xml" in namelist:
            parts_to_consider.append("word/comments.xml")

        results: Dict[str, List[str]] = {}
        for part in parts_to_consider:
            try:
                xml_bytes = zf.read(part)
            except KeyError:
                continue
            results[part] = _extract_texts_from_part_xml(xml_bytes)

    return results


def extract_texts_from_docx(
    docx_path: str,
    include_headers: bool = True,
    include_footers: bool = True,
    include_footnotes: bool = True,
    include_endnotes: bool = True,
    include_comments: bool = False,
) -> List[str]:
    """
    Extract visible text from a .docx and return a flat list of paragraph strings.

    See extract_texts_by_part for inclusion details.
    """
    by_part = extract_texts_by_part(
        docx_path,
        include_headers=include_headers,
        include_footers=include_footers,
        include_footnotes=include_footnotes,
        include_endnotes=include_endnotes,
        include_comments=include_comments,
    )
    paragraphs: List[str] = []
    for _, texts in by_part.items():
        paragraphs.extend(texts)
    return paragraphs


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Extract visible text from a .docx (WordprocessingML)")
    parser.add_argument("docx_path", help="Path to the .docx file")
    parser.add_argument("--no-headers", action="store_true", help="Exclude headers")
    parser.add_argument("--no-footers", action="store_true", help="Exclude footers")
    parser.add_argument("--no-footnotes", action="store_true", help="Exclude footnotes")
    parser.add_argument("--no-endnotes", action="store_true", help="Exclude endnotes")
    parser.add_argument("--include-comments", action="store_true", help="Include comments (not visible in body)")
    parser.add_argument("--by-part", action="store_true", help="Group output by part path")

    args = parser.parse_args()

    if args.by_part:
        grouped = extract_texts_by_part(
            args.docx_path,
            include_headers=not args.no_headers,
            include_footers=not args.no_footers,
            include_footnotes=not args.no_footnotes,
            include_endnotes=not args.no_endnotes,
            include_comments=args.include_comments,
        )
        for part, texts in grouped.items():
            print(f"[{part}]")
            for line in texts:
                print(line)
            print()
    else:
        lines = extract_texts_from_docx(
            args.docx_path,
            include_headers=not args.no_headers,
            include_footers=not args.no_footers,
            include_footnotes=not args.no_footnotes,
            include_endnotes=not args.no_endnotes,
            include_comments=args.include_comments,
        )
        for line in lines:
            print(line)