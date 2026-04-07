# MCP Unstructured v7.4.1 (Reorganized)

This package preserves the original v7.4 server behavior while reorganizing the code into a package-friendly directory structure.

## Directory layout

```text
mcp_unstructured_v7_4_reorg/
├── README.md
├── requirements.txt
├── mcp.toml
├── pyproject.toml
├── notebooks/
│   └── colab_test.ipynb
├── src/
│   └── mcp_unstructured/
│       ├── __init__.py
│       ├── parser.py
│       ├── server.py
│       └── tools.py
└── tests/
    └── client_test.py
```

## Preserved behavior

- Keeps the original `http.server` based server
- Keeps the original `parse_file` and `health` tool contract
- Keeps `ALLOWED_ROOT`
- Keeps the original Colab-centered workflow
- Keeps targeted `unstructured` extras for PDF / DOCX / PPTX / XLSX support

## Tool schema

The package includes `src/mcp_unstructured/tools.py` with JSON-RPC-style tool metadata for:

- `parse_file`
- `health`

## Colab notes

1. Upload or clone this repo into `/content`.
2. Run `notebooks/colab_test.ipynb`.
3. Restart the runtime after the install cell.
4. Continue with the remaining cells.

## System packages

```bash
apt-get update -y
apt-get install -y poppler-utils tesseract-ocr libmagic-dev
```
