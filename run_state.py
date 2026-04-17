"""
Serializable run-state models for Stage D.

These models define graph-level state only. They intentionally do not embed
runtime-only objects such as report.CitationRegistry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field


def source_key_for_url(url: str) -> str:
    """
    Normalize a web URL into a stable source key.

    Rules:
    - drop fragment
    - drop query params whose key starts with ``utm_`` (case-insensitive)
    - strip trailing slash from non-root paths
    - lowercase scheme and host
    """
    text = str(url or "").strip()
    if not text:
        raise ValueError("url is required")

    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"expected absolute URL, got: {url!r}")

    path = parsed.path or ""
    if path not in ("", "/"):
        path = path.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    query = urlencode(filtered_query, doseq=True)

    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            query,
            "",
        )
    )


def source_key_for_file(file_path: str | Path) -> str:
    """
    Normalize a local file path into a stable file:// source key.

    Rules:
    - resolve to an absolute path without requiring the file to exist
    - normalize path separators
    - emit a file URI-like key
    """
    text = str(file_path or "").strip()
    if not text:
        raise ValueError("file_path is required")

    normalized = Path(text).expanduser().resolve(strict=False).as_posix()
    if normalized.startswith("/"):
        return f"file://{normalized}"
    return f"file:///{normalized}"


def source_key_for_rag_chunk(collection: str, doc_name: str) -> str:
    """
    Normalize a RAG chunk identity into a stable rag:// source key.

    Format:
    - rag://{collection}/{doc_name}
    """
    collection_name = str(collection or "").strip()
    document_name = str(doc_name or "").strip()
    if not collection_name:
        raise ValueError("collection is required")
    if not document_name:
        raise ValueError("doc_name is required")

    return (
        f"rag://{quote(collection_name, safe='')}/"
        f"{quote(document_name, safe='')}"
    )


def make_source_key(
    *,
    url: str = "",
    file_path: str | Path | None = None,
    rag_collection: str = "",
    rag_doc_name: str = "",
) -> str:
    """
    Build a stable source_key from exactly one supported source type.
    """
    has_url = bool(str(url or "").strip())
    has_file = file_path is not None and bool(str(file_path).strip())
    has_rag = bool(str(rag_collection or "").strip()) or bool(str(rag_doc_name or "").strip())

    selected = int(has_url) + int(has_file) + int(has_rag)
    if selected != 1:
        raise ValueError("provide exactly one of: url, file_path, or rag_collection+rag_doc_name")

    if has_url:
        return source_key_for_url(url)
    if has_file:
        return source_key_for_file(file_path)
    return source_key_for_rag_chunk(rag_collection, rag_doc_name)


class ObservationRecord(BaseModel):
    content: str
    tool: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    source_keys: list[str] = Field(default_factory=list)


class SourceRecord(BaseModel):
    source_key: str
    url: str
    title: str = ""
    snippet: str = ""
    source_type: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactRecord(BaseModel):
    artifact_id: str
    kind: str
    title: str = ""
    content: str
    created_by: str
    created_at: int


class CheckpointRecord(BaseModel):
    checkpoint_id: str
    run_id: str
    node_id: str
    status: str
    snapshot_ref: str
    created_at: int


class NodeResult(BaseModel):
    node_id: str
    node_type: str
    status: str = "pending"
    summary: str = ""
    observations: list[ObservationRecord] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
    started_at: int | None = None
    finished_at: int | None = None


class RunState(BaseModel):
    run_id: str
    thread_id: str
    question: str
    route_kind: str
    status: str = "running"
    current_node: str = ""
    node_order: list[str] = Field(default_factory=list)
    node_results: dict[str, NodeResult] = Field(default_factory=dict)
    source_catalog: dict[str, SourceRecord] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    checkpoints: list[CheckpointRecord] = Field(default_factory=list)
    created_at: int
    updated_at: int


__all__ = [
    "ArtifactRecord",
    "CheckpointRecord",
    "NodeResult",
    "ObservationRecord",
    "RunState",
    "SourceRecord",
    "make_source_key",
    "source_key_for_file",
    "source_key_for_rag_chunk",
    "source_key_for_url",
]
