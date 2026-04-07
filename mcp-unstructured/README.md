# MCP Unstructured v7.4

This version restores PDF support while keeping the environment leaner than `unstructured[all-docs]`.

## What changed
- keeps `unstructured-inference` out of the MCP server package
- replaces base `unstructured` with targeted extras:
  - `unstructured[pdf,docx,pptx,xlsx]`
- keeps the non-inference MCP server flow
- keeps notebook formatting fixed

## Requirements
```txt
numpy==1.26.4
unstructured[pdf,docx,pptx,xlsx]
pdfminer.six
requests
```

## Colab notes
1. Run the install cell.
2. Restart the runtime.
3. Run the remaining cells.

## System packages
```bash
apt-get update -y
apt-get install -y poppler-utils tesseract-ocr libmagic-dev
```
