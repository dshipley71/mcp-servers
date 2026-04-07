# MCP Unstructured v7

This version removes `unstructured-inference` from the MCP server package.

Includes:
- local Unstructured parsing only
- no `hi_res` / inference dependency in requirements
- fallback partition strategies limited to `ocr_only`, `fast`, and `auto`
- health endpoint
- numpy pin fix

## Colab notes
1. Run the install cell.
2. Restart the runtime.
3. Run the remaining cells.
