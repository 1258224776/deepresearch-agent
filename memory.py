from __future__ import annotations

import json
import logging
import pickle
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from rag import chunk_text, _get_model

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "threads.db"
MEMORY_INDEX_PATH = DATA_DIR / "memory.faiss"
MEMORY_IDS_PATH = DATA_DIR / "memory_ids.pkl"

MEMORY_KIND_FACT = "fact"
MEMORY_CHUNK_SIZE = 220
MEMORY_CHUNK_OVERLAP = 40
MEMORY_ITEM_MIN_LEN = 40
MEMORY_MAX_FACTS = 8
MEMORY_CONTEXT_TOP_K = 3
MEMORY_CONTEXT_ITEM_LIMIT = 220
MEMORY_TITLE_LIMIT = 60
THREAD_SCORE_BOOST = 1.2

_state_lock = threading.Lock()
_initialized = False
_index = None
_memory_ids: list[str] = []


def _ensure_memory_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_entries (
            id                TEXT PRIMARY KEY,
            thread_id         TEXT NOT NULL,
            source_message_ts INTEGER NOT NULL,
            kind              TEXT NOT NULL,
            title             TEXT NOT NULL DEFAULT '',
            content           TEXT NOT NULL,
            mode              TEXT NOT NULL DEFAULT 'research',
            created_at        INTEGER NOT NULL,
            metadata          TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_thread_created
        ON memory_entries(thread_id, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_mode_created
        ON memory_entries(mode, created_at DESC)
        """
    )


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _chunk_title(chunk: str, limit: int = MEMORY_TITLE_LIMIT) -> str:
    first = re.split(r"[。！？.!?\n]", chunk.strip())[0].strip()
    candidate = first or chunk[:limit]
    return candidate[:limit]


def _split_answer_into_memory_items(answer: str) -> list[str]:
    chunks = chunk_text(answer, chunk_size=MEMORY_CHUNK_SIZE, overlap=MEMORY_CHUNK_OVERLAP)
    if not chunks:
        single = _normalize_text(answer)
        return [single] if len(single) >= MEMORY_ITEM_MIN_LEN else []

    items: list[str] = []
    for chunk in chunks:
        normalized = _normalize_text(chunk)
        if len(normalized) < MEMORY_ITEM_MIN_LEN:
            continue
        items.append(normalized)
        if len(items) >= MEMORY_MAX_FACTS:
            break
    return items


def _embed_texts(texts: list[str]) -> np.ndarray:
    model = _get_model()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return np.array(embeddings, dtype="float32")


def _atomic_pickle_dump(path: Path, value: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as handle:
        pickle.dump(value, handle)
    tmp_path.replace(path)


def _atomic_write_index(path: Path, index) -> None:
    import faiss

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    faiss.write_index(index, str(tmp_path))
    tmp_path.replace(path)


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _persist_state_locked() -> None:
    if _index is None or not _memory_ids:
        _remove_file(MEMORY_INDEX_PATH)
        _atomic_pickle_dump(MEMORY_IDS_PATH, [])
        return
    _atomic_write_index(MEMORY_INDEX_PATH, _index)
    _atomic_pickle_dump(MEMORY_IDS_PATH, list(_memory_ids))


def _load_state_locked() -> None:
    global _index, _memory_ids
    if not MEMORY_INDEX_PATH.exists() or not MEMORY_IDS_PATH.exists():
        _index = None
        _memory_ids = []
        return

    import faiss

    _index = faiss.read_index(str(MEMORY_INDEX_PATH))
    with MEMORY_IDS_PATH.open("rb") as handle:
        loaded_ids = pickle.load(handle)
    _memory_ids = [str(item) for item in loaded_ids]


def _rebuild_memory_index_locked(conn: sqlite3.Connection) -> int:
    global _index, _memory_ids
    rows = conn.execute(
        """
        SELECT id, content
        FROM memory_entries
        WHERE kind = ?
        ORDER BY created_at ASC, id ASC
        """,
        (MEMORY_KIND_FACT,),
    ).fetchall()

    if not rows:
        _index = None
        _memory_ids = []
        _persist_state_locked()
        return 0

    texts = [str(row[1]) for row in rows]
    embeddings = _embed_texts(texts)

    import faiss

    index = faiss.IndexFlatIP(int(embeddings.shape[1]))
    index.add(embeddings)
    _index = index
    _memory_ids = [str(row[0]) for row in rows]
    _persist_state_locked()
    return len(_memory_ids)


def init_memory() -> None:
    global _initialized, _index, _memory_ids
    DATA_DIR.mkdir(exist_ok=True)

    with _state_lock:
        if _initialized:
            return

        conn = sqlite3.connect(str(DB_PATH))
        try:
            _ensure_memory_schema(conn)
            conn.commit()

            try:
                _load_state_locked()
            except Exception:
                logger.exception("Failed to load persisted memory state, rebuilding index")
                _index = None
                _memory_ids = []

            row_count = conn.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE kind = ?",
                (MEMORY_KIND_FACT,),
            ).fetchone()[0]
            index_count = 0 if _index is None else int(_index.ntotal)
            if index_count != len(_memory_ids) or index_count != row_count:
                _rebuild_memory_index_locked(conn)
        finally:
            conn.close()

        _initialized = True


def is_memory_ready() -> bool:
    if not _initialized:
        init_memory()
    return _index is not None and bool(_memory_ids)


def add_research_memory(
    *,
    thread_id: str,
    thread_title: str,
    question: str,
    answer: str,
    mode: str,
    source_message_ts: int,
) -> int:
    if not _initialized:
        init_memory()

    items = _split_answer_into_memory_items(answer)
    if not items:
        return 0

    with _state_lock:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            _ensure_memory_schema(conn)
            existing_rows = conn.execute(
                """
                SELECT content
                FROM memory_entries
                WHERE thread_id = ? AND kind = ?
                """,
                (thread_id, MEMORY_KIND_FACT),
            ).fetchall()
            existing = {_normalize_text(row[0]) for row in existing_rows}
            seen = set(existing)
            now = int(time.time() * 1000)

            prepared: list[tuple[str, str, int, str, str, str, str, int, str]] = []
            fact_texts: list[str] = []
            for position, content in enumerate(items, 1):
                normalized = _normalize_text(content)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                entry_id = str(uuid.uuid4())
                metadata = {
                    "question": question,
                    "thread_title": thread_title,
                    "kind": MEMORY_KIND_FACT,
                    "position": position,
                }
                prepared.append(
                    (
                        entry_id,
                        thread_id,
                        int(source_message_ts),
                        MEMORY_KIND_FACT,
                        _chunk_title(normalized),
                        normalized,
                        mode or "research",
                        now,
                        json.dumps(metadata, ensure_ascii=False),
                    )
                )
                fact_texts.append(normalized)

            if not prepared:
                return 0

            embeddings = _embed_texts(fact_texts)
            conn.executemany(
                """
                INSERT INTO memory_entries (
                    id, thread_id, source_message_ts, kind, title,
                    content, mode, created_at, metadata
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                prepared,
            )
            conn.commit()

            try:
                global _index, _memory_ids
                if _index is None:
                    import faiss

                    _index = faiss.IndexFlatIP(int(embeddings.shape[1]))
                _index.add(embeddings)
                _memory_ids.extend(entry_id for entry_id, *_ in prepared)
                _persist_state_locked()
            except Exception:
                logger.exception("Memory state became inconsistent after insert, rebuilding index")
                _rebuild_memory_index_locked(conn)

            return len(prepared)
        finally:
            conn.close()


def search_memory(
    query: str,
    top_k: int = MEMORY_CONTEXT_TOP_K,
    mode: str | None = None,
    preferred_thread_id: str | None = None,
) -> list[dict[str, Any]]:
    if not _initialized:
        init_memory()
    if _index is None or not _memory_ids:
        return []

    query_text = _normalize_text(query)
    if not query_text:
        return []

    with _state_lock:
        embeddings = _embed_texts([query_text])
        candidate_k = min(max(top_k * 8, top_k), len(_memory_ids))
        scores, indices = _index.search(embeddings, candidate_k)
        candidate_ids: list[tuple[str, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(_memory_ids):
                continue
            candidate_ids.append((_memory_ids[idx], float(score)))

    if not candidate_ids:
        return []

    id_order = [item_id for item_id, _ in candidate_ids]
    score_map = {item_id: score for item_id, score in candidate_ids}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in id_order)
        sql = (
            "SELECT id, thread_id, source_message_ts, kind, title, content, mode, created_at, metadata "
            f"FROM memory_entries WHERE id IN ({placeholders})"
        )
        rows = conn.execute(sql, id_order).fetchall()
    finally:
        conn.close()

    row_map = {str(row["id"]): row for row in rows}
    hits: list[dict[str, Any]] = []
    for item_id in id_order:
        row = row_map.get(item_id)
        if row is None:
            continue
        if mode and row["mode"] != mode:
            continue
        metadata = json.loads(row["metadata"] or "{}")
        semantic_score = score_map.get(item_id, 0.0)
        rank_score = semantic_score
        if preferred_thread_id and str(row["thread_id"]) == preferred_thread_id:
            rank_score *= THREAD_SCORE_BOOST
        hits.append(
            {
                "id": row["id"],
                "thread_id": row["thread_id"],
                "source_message_ts": row["source_message_ts"],
                "kind": row["kind"],
                "title": row["title"],
                "content": row["content"],
                "mode": row["mode"],
                "created_at": row["created_at"],
                "metadata": metadata,
                "score": semantic_score,
                "semantic_score": semantic_score,
                "rank_score": rank_score,
            }
        )
    hits.sort(
        key=lambda item: (
            float(item.get("rank_score", 0.0)),
            int(item.get("created_at", 0)),
        ),
        reverse=True,
    )
    return hits[:top_k]


def format_memory_context(hits: list[dict[str, Any]], item_limit: int = MEMORY_CONTEXT_ITEM_LIMIT) -> str:
    if not hits:
        return ""

    lines = ["## Relevant Prior Research"]
    for index, hit in enumerate(hits, 1):
        created_at = int(hit.get("created_at") or 0)
        date_str = time.strftime("%Y-%m-%d", time.localtime(created_at / 1000)) if created_at else "unknown"
        metadata = hit.get("metadata") or {}
        thread_title = metadata.get("thread_title") or hit.get("thread_id") or "unknown"
        content = _normalize_text(hit.get("content", ""))[:item_limit]
        lines.append(f"[Memory {index} | {date_str} | thread: {thread_title}]")
        lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()


def rebuild_memory_index() -> int:
    if not _initialized:
        init_memory()

    with _state_lock:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            _ensure_memory_schema(conn)
            return _rebuild_memory_index_locked(conn)
        finally:
            conn.close()


def get_memory_stats() -> dict[str, Any]:
    if not _initialized:
        init_memory()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        _ensure_memory_schema(conn)
        total_entries = int(conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0])
        fact_entries = int(
            conn.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE kind = ?",
                (MEMORY_KIND_FACT,),
            ).fetchone()[0]
        )
        last_created_at = conn.execute(
            "SELECT MAX(created_at) FROM memory_entries"
        ).fetchone()[0]
    finally:
        conn.close()

    with _state_lock:
        faiss_count = 0 if _index is None else int(_index.ntotal)
        id_count = len(_memory_ids)

    return {
        "ready": is_memory_ready(),
        "entry_count": total_entries,
        "fact_count": fact_entries,
        "faiss_count": faiss_count,
        "id_count": id_count,
        "last_created_at": int(last_created_at or 0),
    }
