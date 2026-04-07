import os
from pathlib import Path
from typing import Dict, Any

from unstructured.partition.auto import partition
from unstructured.chunking.basic import chunk_elements
from unstructured.cleaners.core import (
    group_broken_paragraphs,
    replace_unicode_quotes,
)

ALLOWED_ROOT = Path(os.getenv("ALLOWED_ROOT", ".")).resolve()


def validate_path(path: str) -> Path:
    p = Path(path).resolve()

    if not p.exists():
        raise ValueError(f"File does not exist: {path}")

    if not str(p).startswith(str(ALLOWED_ROOT)):
        raise ValueError("Access denied: path outside allowed root")

    if not p.is_file():
        raise ValueError("Path must be a file")

    return p


def clean_text(text: str) -> str:
    text = text.strip()
    text = replace_unicode_quotes(text)
    text = group_broken_paragraphs(text)
    return text


def parse_file(path: str) -> Dict[str, Any]:
    p = validate_path(path)

    elements = partition(filename=str(p))

    chunks = chunk_elements(
        elements,
        max_characters=1000,
        new_after_n_chars=1000,
        overlap=0,
    )

    chunk_list = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        text = clean_text(chunk.text)

        metadata = getattr(chunk, "metadata", None)
        page_number = getattr(metadata, "page_number", None) if metadata else None

        chunk_list.append({
            "text": text,
            "source_path": str(p),
            "filename": p.name,
            "chunk_index": i,
            "total_chunks": total,
            "page_number": page_number
        })

    full_text = "\n\n".join([c["text"] for c in chunk_list])

    return {
        "text": full_text,
        "chunks": chunk_list,
        "metadata": {
            "filename": p.name,
            "source_path": str(p),
            "num_chunks": total
        }
    }
