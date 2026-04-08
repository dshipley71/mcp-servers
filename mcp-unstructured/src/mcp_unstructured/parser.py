import os
from pathlib import Path
from typing import Dict, List

import requests
from pdfminer.high_level import extract_text as pdfminer_extract_text

from unstructured.partition.auto import partition
from unstructured.chunking.basic import chunk_elements
from unstructured.chunking.title import chunk_by_title
from unstructured.cleaners.core import clean, group_broken_paragraphs, replace_unicode_quotes


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


def _normalize_api_elements(elements: List[dict], path: Path) -> Dict:
    out = []
    total = len(elements)
    for i, el in enumerate(elements):
        metadata = el.get("metadata", {}) or {}
        text = apply_clean(el.get("text", "") or "")
        out.append({
            "text": text,
            "source_path": str(path),
            "filename": path.name,
            "chunk_index": i,
            "total_chunks": total,
            "page_number": metadata.get("page_number"),
            "element_type": el.get("type"),
        })

    return {
        "text": "\n\n".join(c["text"] for c in out if c["text"]),
        "chunks": out,
    }


def _parse_file_vlm(
    path: Path,
    route: str,
    chunking_strategy: str,
    vlm_model_provider: str | None = None,
    vlm_model: str | None = None,
) -> Dict:
    api_url = os.getenv("UNSTRUCTURED_API_URL")
    api_key = os.getenv("UNSTRUCTURED_API_KEY")

    if not api_url or not api_key:
        raise ValueError(
            "VLM mode requires UNSTRUCTURED_API_URL and UNSTRUCTURED_API_KEY to be set."
        )

    provider = vlm_model_provider or os.getenv("UNSTRUCTURED_VLM_PROVIDER", "openai")
    model = vlm_model or os.getenv("UNSTRUCTURED_VLM_MODEL", "gpt-4o")

    with open(path, "rb") as f:
        files = {"files": (path.name, f, "application/octet-stream")}
        data = {
            "strategy": "vlm",
            "vlm_model_provider": provider,
            "vlm_model": model,
        }
        if chunking_strategy and chunking_strategy != "basic":
            data["chunking_strategy"] = chunking_strategy

        response = requests.post(
            api_url,
            headers={"unstructured-api-key": api_key},
            files=files,
            data=data,
            timeout=600,
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"VLM partition request failed: HTTP {response.status_code}: {response.text[:1000]}"
        )

    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected VLM response format: expected a JSON list of elements.")

    normalized = _normalize_api_elements(payload, path)
    normalized["metadata"] = {
        "route_requested": route,
        "route_used": "vlm",
        "num_chunks": len(normalized["chunks"]),
        "inference_enabled": False,
        "vlm_mode": True,
        "vlm_model_provider": provider,
        "vlm_model": model,
        "vlm_transport": "unstructured_api",
    }
    return normalized


def parse_file(
    path: str,
    route: str = "auto",
    chunking_strategy: str = "basic",
    vlm_mode: bool = False,
    vlm_model_provider: str | None = None,
    vlm_model: str | None = None,
) -> Dict:
    p = validate_path(path)

    if vlm_mode:
        return _parse_file_vlm(
            path=p,
            route=route,
            chunking_strategy=chunking_strategy,
            vlm_model_provider=vlm_model_provider,
            vlm_model=vlm_model,
        )

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
            "inference_enabled": False,
            "vlm_mode": False
        }
    }


def health():
    import numpy
    return {
        "status": "ok",
        "numpy_version": numpy.__version__,
        "inference_enabled": False,
        "vlm_available_via_api": bool(
            os.getenv("UNSTRUCTURED_API_URL") and os.getenv("UNSTRUCTURED_API_KEY")
        ),
        "default_vlm_provider": os.getenv("UNSTRUCTURED_VLM_PROVIDER", "openai"),
        "default_vlm_model": os.getenv("UNSTRUCTURED_VLM_MODEL", "gpt-4o"),
    }
