TOOLS = [
    {
        "name": "parse_file",
        "description": "Parse a local file with Unstructured and return combined text, chunks, and metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to a local file under ALLOWED_ROOT."},
                "route": {"type": "string", "enum": ["auto", "fast", "ocr_only"], "default": "auto"},
                "chunking_strategy": {"type": "string", "enum": ["basic", "by_title"], "default": "basic"}
            },
            "required": ["path"],
            "additionalProperties": False
        }
    },
    {
        "name": "health",
        "description": "Return server health information and runtime metadata.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    }
]
