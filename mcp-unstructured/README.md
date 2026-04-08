# MCP Unstructured v7.5

This patch keeps the original lightweight HTTP MCP server shape and removes the dependency pattern
that was pulling `unstructured-inference` back into the environment through `unstructured[...]` extras.

## What changed
- removes `unstructured[pdf,docx,pptx,xlsx]` from `requirements.txt`
- uses a lighter explicit dependency list instead of broad extras
- keeps the existing local `parse_file` flow
- adds an **optional VLM mode toggle**
- VLM mode is **off by default**
- VLM mode uses the hosted Unstructured API only when explicitly enabled

## Why this is safer for Colab
- avoids broad extras that can trigger slow dependency backtracking
- keeps the default install focused on local parsing
- keeps VLM separate from the base local environment

## Requirements
```txt
numpy==1.26.4
unstructured
pdfminer.six
requests
python-docx
python-pptx
openpyxl
pypdf
pdf2image
pytesseract
unstructured-pytesseract
```

## Local mode
Local mode is the default:

```json
{"tool":"parse_file","path":"/content/sample.pdf","route":"auto","chunking_strategy":"basic"}
```

## Optional VLM mode
To enable VLM mode, set these environment variables first:

```bash
export UNSTRUCTURED_API_URL="https://<your-endpoint>"
export UNSTRUCTURED_API_KEY="<your-api-key>"
export UNSTRUCTURED_VLM_PROVIDER="openai"
export UNSTRUCTURED_VLM_MODEL="gpt-4o"
```

Then call:

```json
{
  "tool":"parse_file",
  "path":"/content/sample.pdf",
  "vlm_mode":true,
  "vlm_model_provider":"openai",
  "vlm_model":"gpt-4o"
}
```

## System packages
```bash
apt-get update -y
apt-get install -y poppler-utils tesseract-ocr libmagic-dev
```


## Standardized Project Layout

```text
mcp-unstructured/
├── mcp.toml
├── pyproject.toml
├── README.md
├── requirements.txt
├── src/
│   └── mcp_unstructured/
│       ├── __init__.py
│       ├── parser.py
│       └── server.py
├── tests/
│   └── client_test.py
├── notebooks/
│   └── colab_test.ipynb
└── scripts/
    └── run_server.py
```
