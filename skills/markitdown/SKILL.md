---
name: markitdown
description: "Trigger: convert to markdown, convertir a markdown, markitdown, extract text from docx/xlsx/pptx/pdf/epub, document conversion. Convert documents and media to Markdown via the markitdown CLI."
license: Apache-2.0
metadata:
  author: "pablontiv"
  version: "1.0"
  upstream-repository: "https://github.com/microsoft/markitdown"
  adaptation-status: "unofficial"
---

# markitdown — document-to-Markdown conversion

This is an unofficial handbook adaptation for the Microsoft MarkItDown CLI, not an official Microsoft Agent Skill.

## Activation Contract

Activate when the user asks to convert a file to Markdown, extract text/structure from Office documents (DOCX, XLSX, PPTX), EPUB, HTML, or batch-convert documents. Also when a task needs a Markdown artifact derived from a binary document.

## Hard Rules

- Use the `markitdown` CLI (installed via pipx with `[all]` extras). Never re-install; if missing, report it.
- For PDFs and images that only need READING (not a .md artifact), prefer the native Read tool — it renders them directly.
- Output artifacts go next to the source file or where the user says; temp output goes to the scratchpad.
- Do not pass secrets or `.age`-encrypted files through markitdown.

## Decision Gates

| Situation | Action |
|---|---|
| Need to read a PDF/image content only | Read tool (native) |
| Need a .md file from PDF/DOCX/XLSX/PPTX/EPUB/HTML | `markitdown <file> -o <file>.md` |
| Batch conversion | `fd -e docx -e pdf . <dir> -x markitdown {} -o {.}.md` |
| Piped content | `cat file | markitdown` (stdin, format auto-detected via magika) |
| XLSX with several sheets | markitdown emits one table per sheet — verify all sheets landed |

## Execution Steps

1. Confirm the source file exists and its extension is supported (pdf, docx, xlsx, xls, pptx, epub, html, csv, json, xml, zip, images, audio).
2. Run `markitdown <input> -o <output>.md` (omit `-o` to capture stdout).
3. Inspect the output: check headings/tables survived; warn the user about lossy areas (embedded charts, images without OCR text).
4. Deliver the path of the generated file.

## Output Contract

Return: path of the generated .md file(s) plus a one-line note of any lossy conversion (dropped images, charts, formulas).

## References

- `references/formats.md` — supported formats and per-format caveats.
