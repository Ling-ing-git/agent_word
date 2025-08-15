# XLSX → DOCX (XML-based) Converter

This tool converts an Excel `.xlsx` to a Word `.docx` by parsing and generating raw Office Open XML (OOXML). It does not rely on third-party libraries.

## Usage

```bash
python xlsx_to_docx_xml.py input.xlsx output.docx
```

### Options
- `--sheets SHEET1 SHEET2`: Only include specific sheet names (default: all sheets)
- `--max-rows N`: Limit rows per sheet
- `--max-cols N`: Limit columns per sheet

## Notes
- Values are read directly from the sheet XML:
  - Shared strings (`xl/sharedStrings.xml`), inline strings, booleans are supported
  - Numbers/dates are not formatted; raw values are used
- The generated Word document is a minimal OOXML package with:
  - `[Content_Types].xml`
  - `_rels/.rels`
  - `word/document.xml`
- Each sheet becomes a Word table preceded by a title paragraph: `Sheet: <name>`

## Example

```bash
python xlsx_to_docx_xml.py sample.xlsx sample.docx
```

Open `sample.docx` in Word or LibreOffice to view the converted tables.