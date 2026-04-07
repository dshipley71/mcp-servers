# MCP Unstructured v7.1

This version removes `unstructured-inference` and also replaces `unstructured[all-docs]`
with a leaner non-inference dependency set to reduce install time.

Includes:
- local Unstructured parsing only
- no `hi_res` / inference dependency in requirements
- no `all-docs` extra in requirements
- fallback partition strategies limited to `ocr_only`, `fast`, and `auto`
- health endpoint
- numpy pin fix

## Colab notes
1. Run the install cell.
2. Restart the runtime.
3. Run the remaining cells.

## Why installs are faster
`unstructured[all-docs]` pulls in a very large dependency tree, including
`unstructured-inference`, Whisper, Google Vision, and many extra document/image packages.
This version avoids that.
