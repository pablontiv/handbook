# markitdown — supported formats and caveats

Source: https://github.com/microsoft/markitdown (v0.1.x, installed via `pipx install 'markitdown[all]'`).

| Format | Notes |
|---|---|
| PDF | Text extraction via pdfminer.six; no OCR of scanned pages by default. Layout tables may flatten. |
| DOCX | mammoth-based; headings, lists, tables preserved. Tracked changes are ignored. |
| XLSX / XLS | One Markdown table per sheet (openpyxl / xlrd). Formulas come out as values. |
| PPTX | Slide-by-slide text plus notes; charts render as placeholders. |
| EPUB | Chapter text with headings. |
| HTML | markdownify-based; scripts/styles stripped. |
| CSV / JSON / XML | Rendered as table / fenced block. |
| Images | EXIF metadata + optional LLM-generated description (needs `--use-docintel` or LLM client; not configured locally — expect metadata only). |
| Audio (wav/mp3) | Speech transcription via speech_recognition; slow, network-dependent. |
| ZIP | Iterates contents and concatenates conversions. |
| YouTube URL | Fetches transcript when available. |

## Known caveats

- Scanned PDFs produce empty/garbage output — no OCR pipeline locally; tell the user instead of retrying.
- Complex XLSX (merged cells, pivot tables) flattens; verify column alignment.
- `markitdown` reads stdin when no filename is given; format detection uses magika.
- Plugins exist (`--use-plugins`) but none are installed.
