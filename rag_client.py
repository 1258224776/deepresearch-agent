"""
rag_client.py — thin HTTP client for the deer-rag microservice.

Set DEER_RAG_URL (and optionally DEER_RAG_DEFAULT_COLLECTION) to enable
remote RAG.  All conversations share a single collection (Phase 1).
Per-thread isolation is deferred to Phase 2.

When DEER_RAG_URL is unset or the service is unreachable every public
function returns a safe empty value so callers can fall back to the local
in-memory rag.py without any special-casing.

Collection resolution:
  resolve_collection_id(name)   — used by ingest; creates the collection if
                                  it does not exist yet.
  _find_collection_id(name)     — used by query; looks up only, never creates.
                                  Returns None when the collection is missing
                                  so the caller can fall back immediately.
"""

from __future__ import annotations

import logging
import os

import httpx

from report import Source

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0       # seconds — retrieve / ingest calls
_BUILD_TIMEOUT = 60.0  # seconds — /indexes/build can be slow on large collections


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _base() -> str:
    return os.getenv("DEER_RAG_URL", "").rstrip("/")


def _default_collection() -> str:
    return os.getenv("DEER_RAG_DEFAULT_COLLECTION", "default")


def _list_collections() -> list[dict]:
    """Return the raw items list from GET /collections, or [] on failure."""
    try:
        resp = httpx.get(f"{_base()}/collections", timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Public: availability check
# ──────────────────────────────────────────────────────────────────────────────

def is_available() -> bool:
    """Return True when DEER_RAG_URL is set and /health responds 200."""
    url = _base()
    if not url:
        return False
    try:
        resp = httpx.get(f"{url}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Collection management — two distinct operations
# ──────────────────────────────────────────────────────────────────────────────

def _find_collection_id(name: str) -> str | None:
    """
    Look up a collection by name.  Returns the UUID or None if not found.
    Never creates a collection — safe to call on the query path.
    """
    for col in _list_collections():
        if col.get("name") == name:
            return col["id"]
    return None


def resolve_collection_id(name: str) -> str | None:
    """
    Return the UUID for a collection, creating it if it does not exist yet.
    Intended for the ingest path only — never call this from query().
    Returns None on network / HTTP failure.
    """
    url = _base()
    existing = _find_collection_id(name)
    if existing:
        return existing

    try:
        resp = httpx.post(
            f"{url}/collections",
            json={
                "name": name,
                "description": "agent-one auto-created collection",
                "domain": "research",
                "metadata": {},
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except Exception:
        logger.exception("deer-rag: failed to create collection %r", name)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Public: query
# ──────────────────────────────────────────────────────────────────────────────

def build_indexes(collection: str) -> bool:
    """
    Rebuild indexes for an existing collection.

    Returns False when the collection does not exist or the build request fails.
    This helper never creates collections; callers should ingest first.
    """
    url = _base()
    collection_id = _find_collection_id(collection)
    if not collection_id:
        return False

    try:
        resp = httpx.post(
            f"{url}/indexes/build",
            json={"collection_id": collection_id},
            timeout=_BUILD_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("deer-rag: build_indexes failed for collection %r", collection)
        return False


def query(
    collection: str,
    text: str,
    *,
    top_k: int = 5,
    strategy: str = "hybrid",
    rerank: bool = True,
    token_budget: int = 3000,
) -> tuple[str, list[Source]]:
    """
    Retrieve relevant chunks from deer-rag and return a (context, sources) pair.

    Flow:
      _find_collection_id → /retrieve → /context/assemble (plain profile)

    Uses _find_collection_id (never creates) so an empty / missing collection
    simply returns ("", []) and the caller falls back to local rag.py.

    Evidence is rendered in the same bracket format as local rag_retrieve so
    the LLM sees a consistent style regardless of which backend served it.
    """
    url = _base()

    # Look up only — do NOT create the collection here.
    collection_id = _find_collection_id(collection)
    if not collection_id:
        return "", []

    try:
        # 1. Retrieve candidates
        r_resp = httpx.post(
            f"{url}/retrieve",
            json={
                "query": text,
                "collection_id": collection_id,
                "top_k": top_k,
                "strategy": strategy,
                "rerank": rerank,
                # fetch 3× candidates so the reranker has enough to work with
                "candidate_k": top_k * 3,
            },
            timeout=_TIMEOUT,
        )
        r_resp.raise_for_status()
        evidence: list[dict] = r_resp.json().get("results", [])
        if not evidence:
            return "", []

        # 2. Assemble with token budget.
        #    reserve=0 so the full token_budget is available for evidence
        #    (TokenBudget.available = total - reserve).
        per_ev = min(600, token_budget // max(len(evidence), 1))
        a_resp = httpx.post(
            f"{url}/context/assemble",
            json={
                "evidence": evidence,
                "budget": {
                    "total": token_budget,
                    "reserve": 0,
                    "per_evidence": per_ev,
                },
                # Use "plain" not "agent" — deer-rag's agent profile uses
                # [E1]-style markers that conflict with agent-one's [1] system.
                "profile": "plain",
                "merge_adjacent": True,
                "compression_mode": "none",
            },
            timeout=_TIMEOUT,
        )
        a_resp.raise_for_status()
        selected: list[dict] = a_resp.json().get("selected", [])
        if not selected:
            return "", []

        # 3. Render in agent-one's local bracket format (matches rag_retrieve.py)
        parts: list[str] = []
        sources: list[Source] = []
        for idx, item in enumerate(selected, 1):
            title = item.get("title") or "未知文档"
            source_uri = item.get("source") or ""
            score = item.get("rerank_score") or item.get("score") or 0.0
            snippet = item.get("snippet", "")
            parts.append(
                f"【本地文档片段 {idx}｜来源：{title}｜相关度：{score:.2f}】\n{snippet}"
            )
            sources.append(Source(
                url=source_uri if source_uri else f"file://{title}",
                title=title,
                snippet=snippet[:200],
            ))

        return "\n\n".join(parts), sources

    except Exception:
        logger.exception("deer-rag: query failed for collection %r", collection)
        return "", []


# ──────────────────────────────────────────────────────────────────────────────
# Public: ingestion  (these are the only callers of resolve_collection_id)
# ──────────────────────────────────────────────────────────────────────────────

def ingest_text(
    collection: str,
    content: str,
    doc_name: str,
    *,
    source_uri: str = "",
    rebuild: bool = True,
) -> bool:
    """
    Ingest plain text into deer-rag, then optionally rebuild indexes.
    Creates the collection if it does not exist yet.
    Returns True on success, False (with a logged warning) on failure.
    """
    url = _base()
    collection_id = resolve_collection_id(collection)
    if not collection_id:
        return False

    try:
        r = httpx.post(
            f"{url}/ingest/text",
            json={
                "collection_id": collection_id,
                "title": doc_name,
                "text": content,
                "source_uri": source_uri or doc_name,
                "source_type": "text",
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()

        if rebuild:
            b = httpx.post(
                f"{url}/indexes/build",
                json={"collection_id": collection_id},
                timeout=_BUILD_TIMEOUT,
            )
            b.raise_for_status()
        return True

    except Exception:
        logger.exception(
            "deer-rag: ingest_text failed for %r in collection %r", doc_name, collection
        )
        return False


def ingest_url(
    collection: str,
    target_url: str,
    *,
    title: str = "",
    rebuild: bool = True,
) -> bool:
    """
    Ask deer-rag to fetch a URL, ingest its content, then optionally rebuild indexes.
    Creates the collection if it does not exist yet.
    Returns True on success, False (with a logged warning) on failure.

    Note: /indexes/build is a full-collection rebuild.  Call this only when
    you are ready to make new content searchable — not on every scrape.
    """
    url = _base()
    collection_id = resolve_collection_id(collection)
    if not collection_id:
        return False

    try:
        r = httpx.post(
            f"{url}/ingest/web",
            json={
                "collection_id": collection_id,
                "url": target_url,
                "title": title or target_url,
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()

        if rebuild:
            b = httpx.post(
                f"{url}/indexes/build",
                json={"collection_id": collection_id},
                timeout=_BUILD_TIMEOUT,
            )
            b.raise_for_status()
        return True

    except Exception:
        logger.exception(
            "deer-rag: ingest_url failed for %r in collection %r", target_url, collection
        )
        return False
