import os
from pathlib import Path
from typing import Dict

from pdfminer.high_level import extract_text as pdfminer_extract_text

from unstructured.partition.auto import partition
from unstructured.chunking.basic import chunk_elements
from unstructured.chunking.title import chunk_by_title
from unstructured.cleaners.core import (
    clean,
    group_broken_paragraphs,
    replace_unicode_quotes,
)

FAST_PATH_EXTENSIONS = {
    ".txt", ".md", ".html", ".htm", ".xml", ".json", ".csv", ".eml",
    ".docx", ".pptx", ".xlsx", ".odt", ".rtf", ".tsv", ".pdf"
}


def get_allowed_root() -> Path:
    return Path(os.getenv("ALLOWED_ROOT", ".")).expanduser().resolve()


def validate_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    root = get_allowed_root()
    if not p.exists():
        raise ValueError(f"File not found: {path}")
    if not p.is_file():
        raise ValueError(f"Not a file: {path}")
    if root not in p.parents and p != root:
        raise ValueError("Access denied")
    return p


def detect_pdf_text_layer(path: Path) -> bool:
    try:
        txt = pdfminer_extract_text(str(path), maxpages=2) or ""
        return len("".join(ch for ch in txt if not ch.isspace())) > 20
    except Exception:
        return False


def infer_route(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "fast" if detect_pdf_text_layer(path) else "ocr_only"
    if suffix in FAST_PATH_EXTENSIONS:
        return "fast"
    return "auto"


def resolve_strategy(route: str) -> str:
    if route == "fast":
        return "fast"
    if route == "ocr_only":
        return "ocr_only"
    return "auto"


def apply_clean(text: str) -> str:
    text = clean(text)
    text = group_broken_paragraphs(text)
    text = replace_unicode_quotes(text)
    return text.strip()


def chunk_safe(elements, strategy: str):
    try:
        if strategy == "by_title":
            return chunk_by_title(elements)
        return chunk_elements(elements)
    except Exception:
        return chunk_elements(elements)


def safe_partition(path: Path, route: str):
    strategies = []
    for candidate in [route, "ocr_only", "fast", "auto"]:
        if candidate not in strategies:
            strategies.append(candidate)

    last_err = None
    for r in strategies:
        try:
            elements = partition(filename=str(path), strategy=resolve_strategy(r))
            return elements, r
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Partition failed after fallback: {type(last_err).__name__}: {last_err}")


def parse_file(path: str, route: str = "auto", chunking_strategy: str = "basic") -> Dict:
    p = validate_path(path)
    effective_route = infer_route(p) if route == "auto" else route

    elements, used_route = safe_partition(p, effective_route)
    chunks = chunk_safe(elements, chunking_strategy)

    out = []
    total = len(chunks)
    for i, c in enumerate(chunks):
        out.append({
            "text": apply_clean(getattr(c, "text", "") or ""),
            "source_path": str(p),
            "filename": p.name,
            "chunk_index": i,
            "total_chunks": total,
            "page_number": getattr(getattr(c, "metadata", None), "page_number", None)
        })

    return {
        "text": "\n\n".join(c["text"] for c in out if c["text"]),
        "chunks": out,
        "metadata": {
            "route_requested": route,
            "route_used": used_route,
            "num_chunks": len(out),
            "inference_enabled": False
        }
    }


def health():
    import numpy
    return {
        "status": "ok",
        "numpy_version": numpy.__version__,
        "inference_enabled": False
    }
