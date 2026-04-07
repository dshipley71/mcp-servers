# Minimal Local Unstructured MCP Server

This project provides a deterministic local parser server built on open-source Unstructured only.

## Added capabilities
- `parse_file` tool
- `partition` tool for raw element output
- configurable cleaning pipeline using Unstructured cleaners
- `basic` and `by_title` chunking strategies
- optional coordinate passthrough
- PDF scanned vs digital pre-check before route selection
- optional hi-res model and OCR-agent overrides

## Tools

### parse_file
Inputs:
- `path`
- `route`: `auto`, `fast`, `slow`, `ocr_only`
- `chunking_strategy`: `basic`, `by_title`
- `cleaning_config`: dict of cleaner options
- `return_elements`: include serialized raw partitioned elements
- `include_coordinates`
- `ocr_languages`
- `hi_res_model_name`
- `ocr_agent`

### partition
Returns raw serialized Unstructured elements without chunking.

## Cleaning options
`cleaning_config` supports:
- `use_clean`
- `extra_whitespace`
- `bullets`
- `dashes`
- `trailing_punctuation`
- `lowercase`
- `group_broken_paragraphs`
- `replace_unicode_quotes`
- `clean_bullets`
- `clean_dashes`
- `clean_ordered_bullets`
- `clean_non_ascii_chars`
- `clean_trailing_punctuation`
- `remove_punctuation`
- `clean_prefix_regex`
- `clean_postfix_regex`

## Environment variables
- `ALLOWED_ROOT`
- `SCANNED_PDF_POLICY`: `hi_res` or `ocr_only`
- `UNSTRUCTURED_HI_RES_MODEL_NAME`
- `OCR_AGENT`

## Colab / Ubuntu system packages
```bash
apt-get update -y
apt-get install -y poppler-utils tesseract-ocr libmagic-dev
```
