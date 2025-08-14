#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
import zipfile
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def read_xml_from_docx(docx_path: str, inner_path: str) -> Optional[ET.Element]:
	"""Read an internal XML part from a .docx (zip) and parse as ElementTree Element."""
	with zipfile.ZipFile(docx_path, "r") as zf:
		try:
			data = zf.read(inner_path)
			return ET.fromstring(data)
		except KeyError:
			return None


def get_text_from_paragraph(paragraph: ET.Element) -> str:
	"""Concatenate plain text from a <w:p> by joining all <w:t> contents in order."""
	texts: List[str] = []
	for run in paragraph.findall("w:r", NS):
		for child in list(run):
			if child.tag == f"{{{W_NS}}}t":
				texts.append(child.text or "")
	return "".join(texts)


def paragraph_has_page_break_before(paragraph: ET.Element, style_page_break_before: Dict[str, bool]) -> bool:
	"""Return True if this paragraph enforces a page break before it.

	Signals:
	- <w:pPr><w:pageBreakBefore/>
	- Style has pageBreakBefore (resolved from styles.xml)
	"""
	ppr = paragraph.find("w:pPr", NS)
	if ppr is not None:
		if ppr.find("w:pageBreakBefore", NS) is not None:
			return True
		pstyle = ppr.find("w:pStyle", NS)
		if pstyle is not None:
			style_id = pstyle.get(f"{{{W_NS}}}val")
			if style_id and style_page_break_before.get(style_id, False):
				return True
	return False


def paragraph_contains_any_page_break(paragraph: ET.Element) -> bool:
	"""Detect if <w:p> contains any <w:br w:type="page"/> anywhere in its runs."""
	for run in paragraph.findall("w:r", NS):
		for child in list(run):
			if child.tag == f"{{{W_NS}}}br" and (child.get(f"{{{W_NS}}}type") == "page"):
				return True
	return False


def paragraph_ends_with_page_break(paragraph: ET.Element) -> bool:
	"""Detect if a paragraph ends with an explicit page break (and nothing substantive after it)."""
	last_event: Optional[str] = None
	for run in paragraph.findall("w:r", NS):
		for child in list(run):
			if child.tag == f"{{{W_NS}}}br" and (child.get(f"{{{W_NS}}}type") == "page"):
				last_event = "br"
			elif child.tag == f"{{{W_NS}}}t":
				text_val = (child.text or "").strip()
				if text_val:
					last_event = "text"
			else:
				# Other content counts as content after break
				last_event = "other"
	return last_event == "br"


def paragraph_has_section_break_next_page(paragraph: ET.Element) -> bool:
	"""Detect if <w:pPr><w:sectPr><w:type w:val="nextPage"/> triggers a section page break."""
	ppr = paragraph.find("w:pPr", NS)
	if ppr is None:
		return False
	sect_pr = ppr.find("w:sectPr", NS)
	if sect_pr is None:
		return False
	sect_type = sect_pr.find("w:type", NS)
	if sect_type is None:
		# A sectPr without w:type is commonly a section end; Word typically treats as continuous unless specified.
		return False
	return sect_type.get(f"{{{W_NS}}}val") in {"nextPage", "oddPage", "evenPage"}


def build_style_page_break_before_map(styles_root: Optional[ET.Element]) -> Dict[str, bool]:
	"""Return a map of styleId -> has pageBreakBefore (resolving basedOn chain)."""
	if styles_root is None:
		return {}

	# Collect raw styles
	style_nodes = styles_root.findall("w:style", NS)
	raw: Dict[str, Tuple[bool, Optional[str]]] = {}
	for s in style_nodes:
		style_id = s.get(f"{{{W_NS}}}styleId")
		if not style_id:
			continue
		ppr = s.find("w:pPr", NS)
		has_pbb = False
		if ppr is not None and ppr.find("w:pageBreakBefore", NS) is not None:
			has_pbb = True
		based_on = s.find("w:basedOn", NS)
		based_on_val = based_on.get(f"{{{W_NS}}}val") if based_on is not None else None
		raw[style_id] = (has_pbb, based_on_val)

	# Resolve inheritance
	resolved: Dict[str, bool] = {}

	def resolve(style_id: str, visited: Optional[set] = None) -> bool:
		if style_id in resolved:
			return resolved[style_id]
		if style_id not in raw:
			resolved[style_id] = False
			return False
		if visited is None:
			visited = set()
		if style_id in visited:
			resolved[style_id] = False
			return False
		visited.add(style_id)
		has_pbb, parent_id = raw[style_id]
		if has_pbb:
			resolved[style_id] = True
			return True
		parent_has = resolve(parent_id, visited) if parent_id else False
		resolved[style_id] = parent_has
		return parent_has

	for sid in raw.keys():
		resolve(sid)
	return resolved


def extract_table_element_as_xml(tbl_elem: ET.Element, is_nested: bool, independent_page: bool) -> ET.Element:
	"""Create a simplified <table> XML element from a <w:tbl>."""
	table_el = ET.Element("table")
	table_el.set("nested", "true" if is_nested else "false")
	table_el.set("independentPage", "true" if independent_page else "false")

	for tr in tbl_elem.findall("w:tr", NS):
		tr_el = ET.SubElement(table_el, "tr")
		for tc in tr.findall("w:tc", NS):
			tc_el = ET.SubElement(tr_el, "tc")
			# Gather plain text paragraphs inside the cell (ignore deeper nested tables here)
			for child in list(tc):
				if child.tag == f"{{{W_NS}}}p":
					p_text = get_text_from_paragraph(child)
					p_el = ET.SubElement(tc_el, "p")
					p_el.text = p_text
	return table_el


class WordToXmlConverter:
	"""Convert .docx (OOXML) to custom XML with page segmentation and nested-table isolation."""

	def __init__(self, docx_path: str, isolation_rule: str = "before") -> None:
		self.docx_path = docx_path
		self.isolation_rule = isolation_rule  # one of: "any", "before", "both"
		self.document_root: Optional[ET.Element] = None
		self.styles_root: Optional[ET.Element] = None
		self.style_page_break_before: Dict[str, bool] = {}

	def load(self) -> None:
		self.document_root = read_xml_from_docx(self.docx_path, "word/document.xml")
		self.styles_root = read_xml_from_docx(self.docx_path, "word/styles.xml")
		self.style_page_break_before = build_style_page_break_before_map(self.styles_root)
		if self.document_root is None:
			raise RuntimeError("word/document.xml not found in the .docx file")

	def convert(self) -> ET.Element:
		if self.document_root is None:
			raise RuntimeError("Document not loaded")

		out_root = ET.Element("document")
		pages_el = ET.SubElement(out_root, "pages")

		current_page_el = self._new_page(pages_el, 1)
		page_index = 1

		body = self.document_root.find("w:body", NS)
		if body is None:
			return out_root

		# Process body children in order
		children = list(body)
		pending_break = False  # indicates a page break should be applied before processing the next block

		idx = 0
		while idx < len(children):
			child = children[idx]
			tag = child.tag

			# Apply pending break
			if pending_break:
				page_index += 1
				current_page_el = self._new_page(pages_el, page_index)
				pending_break = False

			if tag == f"{{{W_NS}}}p":
				# Break before paragraph?
				if paragraph_has_page_break_before(child, self.style_page_break_before):
					page_index += 1
					current_page_el = self._new_page(pages_el, page_index)
				# Emit paragraph
				p_el = ET.SubElement(current_page_el, "p")
				p_el.text = get_text_from_paragraph(child)
				# Determine breaks after paragraph
				if paragraph_ends_with_page_break(child) or paragraph_has_section_break_next_page(child):
					pending_break = True
				else:
					pending_break = False
				idx += 1
				continue

			if tag == f"{{{W_NS}}}tbl":
				# Top-level table encountered. We will process its children and detect nested tables within cells.
				idx, current_page_el, page_index, pending_break = self._process_table_into_pages(
					current_page_el,
					children,
					idx,
					pages_el,
					page_index,
					pending_break,
				)
				continue

			# Other nodes (e.g., sectPr directly under body) - just skip
			idx += 1

		return out_root

	def _assign_loop_state(self, new_idx: int, new_page_el: ET.Element, new_page_index: int, new_pending_break: bool) -> Tuple[int, ET.Element, int, bool]:
		# Helper (legacy) retained for compatibility if needed elsewhere
		return new_idx, new_page_el, new_page_index, new_pending_break

	def _process_table_into_pages(
		self,
		current_page_el: ET.Element,
		siblings: List[ET.Element],
		idx: int,
		pages_el: ET.Element,
		page_index: int,
		pending_break: bool,
	) -> Tuple[int, ET.Element, int, bool]:
		# Determine next sibling paragraph for lookahead break
		next_sibling = siblings[idx + 1] if (idx + 1) < len(siblings) else None
		next_is_break_before = False
		if next_sibling is not None and next_sibling.tag == f"{{{W_NS}}}p":
			next_is_break_before = paragraph_has_page_break_before(next_sibling, self.style_page_break_before)

		# For a top-level table, we will iterate its content and detect nested tables inside its cells
		tbl_elem = siblings[idx]

		# Apply pending break before placing this top-level table
		if pending_break:
			page_index += 1
			current_page_el = self._new_page(pages_el, page_index)
			pending_break = False

		# Place the top-level table itself on the current page
		# But we also need to inspect for nested tables inside its cells and decide whether they require page isolation.
		# We will emit a simplified representation of the top-level table structure (text only), and separately lift nested tables
		# out as independent pages if they match the isolation rule.

		# First, collect nested tables inside this top-level table with their parent cells and sibling context
		nested_tables_info: List[Tuple[ET.Element, ET.Element]] = []  # (nested_tbl, parent_tc)
		for tr in tbl_elem.findall("w:tr", NS):
			for tc in tr.findall("w:tc", NS):
				for inner in list(tc):
					if inner.tag == f"{{{W_NS}}}tbl":
						nested_tables_info.append((inner, tc))

		# Emit the top-level table skeleton (without nested tables' contents to avoid duplication)
		toplevel_table_el = ET.SubElement(current_page_el, "table")
		toplevel_table_el.set("nested", "false")
		toplevel_table_el.set("independentPage", "false")
		for tr in tbl_elem.findall("w:tr", NS):
			tr_el = ET.SubElement(toplevel_table_el, "tr")
			for tc in tr.findall("w:tc", NS):
				tc_el = ET.SubElement(tr_el, "tc")
				for child in list(tc):
					if child.tag == f"{{{W_NS}}}p":
						p_text = get_text_from_paragraph(child)
						p_el = ET.SubElement(tc_el, "p")
						p_el.text = p_text
					# Skip nested tables here; they will be processed separately

		# Now evaluate nested tables for isolation
		for nested_tbl, parent_tc in nested_tables_info:
			# Determine explicit page-break signals around this nested table inside its cell
			parent_children = list(parent_tc)
			pos = parent_children.index(nested_tbl)

			prev_p_end_break = False
			if pos - 1 >= 0 and parent_children[pos - 1].tag == f"{{{W_NS}}}p":
				prev_p = parent_children[pos - 1]
				prev_p_end_break = paragraph_ends_with_page_break(prev_p) or paragraph_has_section_break_next_page(prev_p)

			next_break_before = False
			if pos + 1 < len(parent_children) and parent_children[pos + 1].tag == f"{{{W_NS}}}p":
				next_p = parent_children[pos + 1]
				next_break_before = paragraph_has_page_break_before(next_p, self.style_page_break_before)

			independent = self._decide_nested_table_independence(prev_p_end_break, next_break_before)

			if independent:
				# Start a new page for this nested table
				page_index += 1
				current_page_el = self._new_page(pages_el, page_index)
				t_el = extract_table_element_as_xml(nested_tbl, is_nested=True, independent_page=True)
				current_page_el.append(t_el)
				# End the page after the nested table to keep it isolated
				page_index += 1
				current_page_el = self._new_page(pages_el, page_index)
			else:
				# Keep nested table inline on the current page (under the top-level table context)
				t_el = extract_table_element_as_xml(nested_tbl, is_nested=True, independent_page=False)
				current_page_el.append(t_el)

		# After handling this top-level table, consider a break because next sibling paragraph may have break-before
		pending_break = next_is_break_before

		# Advance the sibling index by one (we fully handled this table) and return new loop state
		return idx + 1, current_page_el, page_index, pending_break

	def _decide_nested_table_independence(self, prev_p_end_break: bool, next_break_before: bool) -> bool:
		if self.isolation_rule == "both":
			return prev_p_end_break and next_break_before
		if self.isolation_rule == "before":
			return prev_p_end_break
		# "any"
		return prev_p_end_break or next_break_before

	def _new_page(self, pages_el: ET.Element, index: int) -> ET.Element:
		page_el = ET.SubElement(pages_el, "page")
		page_el.set("index", str(index))
		return page_el


def convert_docx_to_custom_xml(input_docx: str, output_xml: str, isolation_rule: str = "before") -> None:
	converter = WordToXmlConverter(input_docx, isolation_rule=isolation_rule)
	converter.load()
	root_el = converter.convert()
	# Write pretty without external libs (ElementTree does not pretty print by default)
	# We'll write a rough compact XML; users can pretty-print later if needed.
	tree = ET.ElementTree(root_el)
	tree.write(output_xml, encoding="utf-8", xml_declaration=True)


def main(argv: Optional[List[str]] = None) -> int:
	parser = argparse.ArgumentParser(description="Convert .docx to custom XML with page segmentation and nested-table isolation.")
	parser.add_argument("input", help="Path to input .docx file")
	parser.add_argument("output", help="Path to output .xml file")
	parser.add_argument(
		"--isolation",
		choices=["any", "before", "both"],
		default="before",
		help=(
			"Rule to decide a nested table is an independent page: "
			"'before' (default) requires previous paragraph ends with a page break; "
			"'both' requires both previous-end-break and next paragraph break-before; "
			"'any' if either side signals a break."
		),
	)
	args = parser.parse_args(argv)
	try:
		convert_docx_to_custom_xml(args.input, args.output, isolation_rule=args.isolation)
	except Exception as exc:
		print(f"Error: {exc}", file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())