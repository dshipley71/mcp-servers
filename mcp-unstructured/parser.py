import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from pdfminer.high_level import extract_text as pdfminer_extract_text

from unstructured.partition.auto import partition
from unstructured.chunking.basic import chunk_elements
from unstructured.chunking.title import chunk_by_title
from unstructured.cleaners.core import (
    clean,
    clean_bullets,
    clean_dashes,
    clean_non_ascii_chars,
    clean_ordered_bullets,
    clean_postfix,
    clean_prefix,
    clean_trailing_punctuation,
    group_broken_paragraphs,
    remove_punctuation,
    replace_unicode_quotes,
)

ALLOWED_ROOT = Path(os.getenv("ALLOWED_ROOT", ".")).expanduser().resolve()

SLOW_PATH_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".heic"
}

FAST_PATH_EXTENSIONS = {
    ".txt", ".md", ".html", ".htm", ".xml", ".json", ".csv", ".eml",
    ".docx", ".pptx", ".xlsx", ".odt", ".rtf", ".tsv"
}

SCANNED_PDF_POLICY = os.getenv("SCANNED_PDF_POLICY", "hi_res").strip().lower()
HI_RES_MODEL_NAME = os.getenv("UNSTRUCTURED_HI_RES_MODEL_NAME", "").strip() or None
OCR_AGENT = os.getenv("OCR_AGENT", "").strip() or None


def validate_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()

    if not p.exists():
        raise ValueError(f"File does not exist: {path}")
    if not p.is_file():
        raise ValueError("Path must be a file")
    if ALLOWED_ROOT not in p.parents and p != ALLOWED_ROOT:
        raise ValueError("Access denied: path outside allowed root")
    return p


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def detect_pdf_text_layer(path: Path, max_pages: int = 3, min_chars: int = 20) -> Tuple[bool, str]:
    try:
        text = pdfminer_extract_text(str(path), maxpages=max_pages) or ""
        meaningful = "".join(ch for ch in text if not ch.isspace())
        if len(meaningful) >= min_chars:
            return True, "digital"
        return False, "scanned"
    except Exception:
        return False, "scanned"


def infer_route(path: Path) -> Tuple[str, Optional[str]]:
    suffix = path.suffix.lower()

    if suffix in FAST_PATH_EXTENSIONS:
        return "fast", None

    if suffix in SLOW_PATH_EXTENSIONS:
        if suffix == ".pdf":
            has_text_layer, pdf_kind = detect_pdf_text_layer(path)
            if has_text_layer:
                return "fast", pdf_kind
            if SCANNED_PDF_POLICY == "ocr_only":
                return "ocr_only", pdf_kind
            return "slow", pdf_kind
        return "slow", None

    return "auto", None


def resolve_strategy(path: Path, route: str) -> Optional[str]:
    suffix = path.suffix.lower()

    if suffix != ".pdf" and suffix not in SLOW_PATH_EXTENSIONS:
        return None

    if route == "fast":
        return "fast"
    if route == "slow":
        return "hi_res"
    if route == "ocr_only":
        return "ocr_only"
    return "auto"


def build_partition_kwargs(
    path: Path,
    route: str,
    ocr_languages: Optional[List[str]] = None,
    hi_res_model_name: Optional[str] = None,
    ocr_agent: Optional[str] = None,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"filename": str(path)}
    strategy = resolve_strategy(path, route)
    if strategy is not None:
        kwargs["strategy"] = strategy

    effective_model_name = (hi_res_model_name or HI_RES_MODEL_NAME or "").strip() or None
    if effective_model_name and strategy == "hi_res":
        kwargs["hi_res_model_name"] = effective_model_name

    if ocr_languages:
        kwargs["languages"] = ocr_languages

    effective_ocr_agent = (ocr_agent or OCR_AGENT or "").strip() or None
    if effective_ocr_agent:
        kwargs["ocr_agent"] = effective_ocr_agent

    return kwargs


def extract_page_number(obj: Any) -> Optional[int]:
    metadata = getattr(obj, "metadata", None)
    if metadata is None:
        return None
    value = getattr(metadata, "page_number", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_coords(obj: Any) -> Optional[Dict[str, Any]]:
    metadata = getattr(obj, "metadata", None)
    if metadata is None:
        return None

    coords = getattr(metadata, "coordinates", None)
    if not coords:
        return None

    points = getattr(coords, "points", None)
    system = getattr(coords, "system", None)

    serialized_points = None
    if points:
        serialized_points = []
        for point in points:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                serialized_points.append([point[0], point[1]])
            else:
                x = getattr(point, "x", None)
                y = getattr(point, "y", None)
                if x is not None and y is not None:
                    serialized_points.append([x, y])

    return {
        "points": serialized_points,
        "system": str(system) if system is not None else None,
    }


def serialize_element(element: Any, include_coordinates: bool = False) -> Dict[str, Any]:
    metadata = getattr(element, "metadata", None)
    data = {
        "element_type": type(element).__name__,
        "text": getattr(element, "text", "") or "",
        "page_number": extract_page_number(element),
        "element_id": getattr(element, "id", None),
        "filename": getattr(metadata, "filename", None) if metadata else None,
        "last_modified": str(getattr(metadata, "last_modified", None)) if metadata else None,
    }
    if include_coordinates:
        data["coordinates"] = extract_coords(element)
    return data


def apply_cleaning_pipeline(text: str, cleaning_config: Optional[Dict[str, Any]] = None) -> str:
    if not text:
        return ""

    cfg = cleaning_config or {}

    # Base wrapper
    if cfg.get("use_clean", True):
        text = clean(
            text,
            extra_whitespace=cfg.get("extra_whitespace", True),
            bullets=cfg.get("bullets", False),
            dashes=cfg.get("dashes", False),
            trailing_punctuation=cfg.get("trailing_punctuation", False),
            lowercase=cfg.get("lowercase", False),
        )

    # Explicit utilities
    if cfg.get("group_broken_paragraphs", True):
        text = group_broken_paragraphs(text)

    if cfg.get("replace_unicode_quotes", True):
        text = replace_unicode_quotes(text)

    if cfg.get("clean_bullets", False):
        text = clean_bullets(text)

    if cfg.get("clean_dashes", False):
        text = clean_dashes(text)

    if cfg.get("clean_ordered_bullets", False):
        text = clean_ordered_bullets(text)

    if cfg.get("clean_non_ascii_chars", False):
        text = clean_non_ascii_chars(text)

    if cfg.get("clean_trailing_punctuation", False):
        text = clean_trailing_punctuation(text)

    if cfg.get("remove_punctuation", False):
        text = remove_punctuation(text)

    prefix_regex = cfg.get("clean_prefix_regex")
    if prefix_regex:
        text = clean_prefix(text, prefix_regex)

    postfix_regex = cfg.get("clean_postfix_regex")
    if postfix_regex:
        text = clean_postfix(text, postfix_regex)

    return text.strip()


def chunk_partitioned_elements(
    elements: List[Any],
    chunking_strategy: str,
    max_characters: int,
    new_after_n_chars: int,
    overlap: int,
    combine_text_under_n_chars: int = 0,
    multipage_sections: bool = True,
) -> List[Any]:
    if chunking_strategy == "basic":
        return chunk_elements(
            elements,
            max_characters=max_characters,
            new_after_n_chars=new_after_n_chars,
            overlap=overlap,
        )

    if chunking_strategy == "by_title":
        kwargs: Dict[str, Any] = {
            "max_characters": max_characters,
            "new_after_n_chars": new_after_n_chars,
            "overlap": overlap,
            "combine_text_under_n_chars": combine_text_under_n_chars,
            "multipage_sections": multipage_sections,
        }
        return chunk_by_title(elements, **kwargs)

    raise ValueError("Invalid chunking_strategy: must be one of ['basic', 'by_title']")


def partition_file(
    path: str,
    route: str = "auto",
    ocr_languages: Optional[List[str]] = None,
    hi_res_model_name: Optional[str] = None,
    ocr_agent: Optional[str] = None,
    include_coordinates: bool = False,
) -> Dict[str, Any]:
    valid_routes = {"auto", "fast", "slow", "ocr_only"}
    if route not in valid_routes:
        raise ValueError("Invalid route: must be one of ['auto', 'fast', 'slow', 'ocr_only']")

    p = validate_path(path)

    detected_pdf_kind: Optional[str] = None
    if route == "auto":
        effective_route, detected_pdf_kind = infer_route(p)
    else:
        effective_route = route
        if is_pdf(p):
            _, detected_pdf_kind = detect_pdf_text_layer(p)

    partition_kwargs = build_partition_kwargs(
        p,
        route=effective_route,
        ocr_languages=ocr_languages,
        hi_res_model_name=hi_res_model_name,
        ocr_agent=ocr_agent,
    )

    try:
        elements = partition(**partition_kwargs)
    except Exception as e:
        raise RuntimeError(f"Partition failed: {type(e).__name__}: {e}") from e

    return {
        "elements": [serialize_element(el, include_coordinates=include_coordinates) for el in elements],
        "metadata": {
            "filename": p.name,
            "source_path": str(p),
            "num_elements": len(elements),
            "route_requested": route,
            "route_used": effective_route,
            "pdf_kind": detected_pdf_kind,
            "scanned_pdf_policy": SCANNED_PDF_POLICY,
            "hi_res_model_name_requested": hi_res_model_name,
            "hi_res_model_name_used": partition_kwargs.get("hi_res_model_name"),
            "ocr_agent_requested": ocr_agent,
            "ocr_agent_used": partition_kwargs.get("ocr_agent"),
            "partition_kwargs": partition_kwargs,
        },
        "_raw_elements": elements,
    }


def parse_file(
    path: str,
    route: str = "auto",
    max_characters: int = 1000,
    new_after_n_chars: int = 1000,
    overlap: int = 0,
    ocr_languages: Optional[List[str]] = None,
    hi_res_model_name: Optional[str] = None,
    ocr_agent: Optional[str] = None,
    include_coordinates: bool = False,
    return_elements: bool = False,
    cleaning_config: Optional[Dict[str, Any]] = None,
    chunking_strategy: str = "basic",
    combine_text_under_n_chars: int = 0,
    multipage_sections: bool = True,
) -> Dict[str, Any]:
    partition_result = partition_file(
        path=path,
        route=route,
        ocr_languages=ocr_languages,
        hi_res_model_name=hi_res_model_name,
        ocr_agent=ocr_agent,
        include_coordinates=include_coordinates,
    )

    raw_elements = partition_result.pop("_raw_elements")

    try:
        chunks = chunk_partitioned_elements(
            raw_elements,
            chunking_strategy=chunking_strategy,
            max_characters=max_characters,
            new_after_n_chars=new_after_n_chars,
            overlap=overlap,
            combine_text_under_n_chars=combine_text_under_n_chars,
            multipage_sections=multipage_sections,
        )
    except Exception as e:
        raise RuntimeError(f"Chunking failed: {type(e).__name__}: {e}") from e

    p = validate_path(path)
    chunk_list = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        text = apply_cleaning_pipeline(getattr(chunk, "text", "") or "", cleaning_config=cleaning_config)
        page_number = extract_page_number(chunk)

        chunk_item = {
            "text": text,
            "source_path": str(p),
            "filename": p.name,
            "chunk_index": i,
            "total_chunks": total,
            "page_number": page_number,
        }

        if include_coordinates:
            chunk_item["coordinates"] = extract_coords(chunk)

        chunk_list.append(chunk_item)

    full_text = "\n\n".join(c["text"] for c in chunk_list if c["text"])

    result = {
        "text": full_text,
        "chunks": chunk_list,
        "metadata": {
            **partition_result["metadata"],
            "num_chunks": total,
            "chunking_strategy": chunking_strategy,
            "cleaning_config": cleaning_config or {},
        },
    }

    if return_elements:
        result["elements"] = partition_result["elements"]

    return result
