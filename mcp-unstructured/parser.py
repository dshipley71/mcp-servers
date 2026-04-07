import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from pdfminer.high_level import extract_text as pdfminer_extract_text

from unstructured.partition.auto import partition
from unstructured.chunking.basic import chunk_elements
from unstructured.chunking.title import chunk_by_title
from unstructured.cleaners.core import (
    clean,
    group_broken_paragraphs,
    replace_unicode_quotes,
)

SLOW_PATH_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".heic"
}

FAST_PATH_EXTENSIONS = {
    ".txt", ".md", ".html", ".htm", ".xml", ".json", ".csv", ".eml",
    ".docx", ".pptx", ".xlsx", ".odt", ".rtf", ".tsv"
}

def get_allowed_root() -> Path:
    return Path(os.getenv("ALLOWED_ROOT", ".")).expanduser().resolve()

def get_scanned_pdf_policy() -> str:
    return os.getenv("SCANNED_PDF_POLICY", "ocr_only")

def validate_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    root = get_allowed_root()
    if not p.exists(): raise ValueError("File not found")
    if not p.is_file(): raise ValueError("Not a file")
    if root not in p.parents and p != root:
        raise ValueError("Access denied")
    return p

def detect_pdf_text_layer(path: Path):
    try:
        txt = pdfminer_extract_text(str(path), maxpages=2) or ""
        return len(txt.strip()) > 20
    except:
        return False

def infer_route(path: Path):
    if path.suffix.lower() == ".pdf":
        return "fast" if detect_pdf_text_layer(path) else get_scanned_pdf_policy()
    if path.suffix.lower() in FAST_PATH_EXTENSIONS:
        return "fast"
    return "slow"

def resolve_strategy(route):
    if route == "fast": return "fast"
    if route == "slow": return "hi_res"
    if route == "ocr_only": return "ocr_only"
    return "auto"

def apply_clean(text):
    text = clean(text)
    text = group_broken_paragraphs(text)
    text = replace_unicode_quotes(text)
    return text.strip()

def chunk_safe(elements, strategy):
    try:
        if strategy == "by_title":
            return chunk_by_title(elements)
        return chunk_elements(elements)
    except:
        return chunk_elements(elements)

def safe_partition(path, route):
    strategies = [route, "ocr_only", "fast"]
    last_err = None
    for r in strategies:
        try:
            return partition(filename=str(path), strategy=resolve_strategy(r)), r
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Partition failed after fallback: {last_err}")

def parse_file(path, route="auto", chunking_strategy="basic"):
    p = validate_path(path)
    route = infer_route(p) if route == "auto" else route

    elements, used_route = safe_partition(p, route)

    chunks = chunk_safe(elements, chunking_strategy)
    out = []

    for i, c in enumerate(chunks):
        out.append({
            "text": apply_clean(getattr(c, "text", "")),
            "source_path": str(p),
            "filename": p.name,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "page_number": getattr(getattr(c, "metadata", None), "page_number", None)
        })

    return {
        "text": "\n\n".join([c["text"] for c in out]),
        "chunks": out,
        "metadata": {
            "route_used": used_route,
            "num_chunks": len(out)
        }
    }

def health():
    import numpy
    return {
        "status": "ok",
        "numpy_version": numpy.__version__
    }
