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
- `--separator-blank-rows N`: Split one sheet into multiple tables when there are N consecutive blank rows (default: 1)
- `--trim-empty-cols`: Trim trailing empty columns per detected table

## Behavior
- Values are read directly from the sheet XML:
  - Shared strings (`xl/sharedStrings.xml`), inline strings, booleans are supported
  - Numbers/dates are not formatted; raw values are used
- Each detected table becomes a Word table preceded by a title paragraph: `Sheet: <name>`
- Tables are separated by page breaks, so each table starts on a new page

## Example

```bash
python xlsx_to_docx_xml.py sample.xlsx sample.docx --separator-blank-rows 2 --trim-empty-cols
```

Open `sample.docx` in Word or LibreOffice to view the converted tables.