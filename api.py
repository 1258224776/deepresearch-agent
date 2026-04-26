"""
DeepResearch Agent - FastAPI backend v2.0.

Endpoints are split into two groups:
  - /api/*: modern SSE research APIs with persistent threads for the Next.js frontend
  - legacy: backward-compatible paths such as /health, /skills, /skills/route-preview, and /run
"""


from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import queue
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import memory
import run_store
from config import ENGINE_PRESETS, PROVIDERS, load_secret
from agent_loop import run_agent
from agent_planner import run_planner_agent
from graph_runner import create_run_state, resume_static_graph, run_static_graph
from runtime_adapters import parse_uploaded_document
from run_state import ArtifactRecord, CheckpointRecord, NodeResult, RunState
from skills import BUILTIN_SKILL_REGISTRY
from skills.adapters import get_search_provider_catalog, get_search_provider_order, search_results_with_trace
from skills.config import get_enabled_skill_names, get_skill_state_map, set_skill_enabled
from skills.profiles import (
    DEFAULT_SKILL_PROFILE,
    get_profile_allowlist,
    get_profile_metadata_list,
    get_skill_profiles,
)
from skills.router import preview_route
from skills.stats import get_skill_stats_map, init_skill_stats

logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

DB_PATH = Path(__file__).parent / "data" / "threads.db"
DEFAULT_THREAD_TITLE = "New chat"
THREAD_TITLE_LIMIT = 40
THREAD_PREVIEW_LIMIT = 120
THREAD_SEARCH_CONTENT_LIMIT = 500
THREAD_SEARCH_THOUGHT_LIMIT = 150
THREAD_SEARCH_OBSERVATION_LIMIT = 300
THREAD_SEARCH_SNIPPET_LIMIT = 150
CHAT_HISTORY_TURNS = 8
AUTO_THREAD_TITLES = {
    DEFAULT_THREAD_TITLE,
    "New chat",
    "\u65b0\u5efa\u5bf9\u8bdd",
}
CHAT_SYSTEM_PROMPT = (
    "You are the DeepResearch chat assistant. Continue the existing thread naturally. "
    "Use the prior conversation when it matters, stay concise, and answer directly."
)
API_ALLOWED_ORIGINS_RAW = os.getenv(
    "API_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001",
)
API_ACCESS_KEY = (os.getenv("DEEPRESEARCH_API_KEY", "") or os.getenv("API_KEY", "")).strip()


def _parse_allowed_origins(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if text == "*":
        return ["*"]
    return [item.strip() for item in text.split(",") if item.strip()]


API_ALLOWED_ORIGINS = _parse_allowed_origins(API_ALLOWED_ORIGINS_RAW)
_graph_run_tasks: dict[str, asyncio.Task[None]] = {}
_run_event_subscribers: dict[str, set[queue.Queue[dict[str, Any]]]] = {}
_run_event_lock = threading.Lock()
TERMINAL_RUN_STATUSES = {"done", "failed"}
RUN_EVENT_KEEPALIVE_SECONDS = 15.0
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENT_COUNT = 5
SUPPORTED_UPLOAD_EXTENSIONS = {
    "pdf", "docx", "txt", "md", "csv",
    "py", "js", "jsx", "ts", "tsx", "json",
    "yaml", "yml", "html", "css", "sql", "sh", "xml",
}
ATTACHMENT_PROMPT_CHAR_LIMIT = 32000
ATTACHMENT_PREVIEW_CHAR_LIMIT = 240


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    memory.init_memory()
    init_skill_stats(DB_PATH)
    yield

# ----------------------------------------------------------------------
# App
# ----------------------------------------------------------------------

app = FastAPI(
    title="DeepResearch Agent API",
    version="2.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=API_ALLOWED_ORIGINS or [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_and_request_log_middleware(request: Request, call_next):
    started_at = time.perf_counter()
    path = request.url.path
    method = request.method

    if API_ACCESS_KEY and path.startswith("/api/"):
        supplied = request.headers.get("X-API-Key", "").strip()
        if supplied != API_ACCESS_KEY:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.warning("%s %s -> 401 in %.1fms", method, path, duration_ms)
            return JSONResponse(status_code=401, content={"detail": "invalid api key"})

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.exception("%s %s -> 500 in %.1fms", method, path, duration_ms)
        raise

    duration_ms = (time.perf_counter() - started_at) * 1000
    logger.info("%s %s -> %s in %.1fms", method, path, response.status_code, duration_ms)
    return response

def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _trim_text(value: Any, limit: int) -> str:
    text = _normalize_text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _message_content(message: dict[str, Any]) -> str:
    return _normalize_text(message.get("content", ""))


def _thread_preview(messages: list[dict[str, Any]]) -> str:
    assistant_messages = [
        message
        for message in messages
        if message.get("role") == "assistant" and _message_content(message)
    ]
    target = assistant_messages[-1] if assistant_messages else next(
        (message for message in reversed(messages) if _message_content(message)),
        None,
    )
    if target:
        return _trim_text(_message_content(target), THREAD_PREVIEW_LIMIT)
    return ""


def _thread_message_count(messages: list[dict[str, Any]]) -> int:
    return sum(1 for msg in messages if _message_content(msg))


def _thread_last_mode(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("mode"):
            return str(message["mode"])
    return "chat"


def _thread_total_step_count(messages: list[dict[str, Any]]) -> int:
    return sum(len(message.get("steps") or []) for message in messages)


def _thread_search_body(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        content = _message_content(message)
        if content:
            parts.append(content[:THREAD_SEARCH_CONTENT_LIMIT])

        for step in message.get("steps") or []:
            thought = _normalize_text(step.get("thought", ""))
            observation = _normalize_text(step.get("observation", ""))
            if thought:
                parts.append(thought[:THREAD_SEARCH_THOUGHT_LIMIT])
            if observation:
                parts.append(observation[:THREAD_SEARCH_OBSERVATION_LIMIT])

        for reference in message.get("references") or []:
            ref_title = _normalize_text(reference.get("title", ""))
            ref_snippet = _normalize_text(reference.get("snippet", ""))
            if ref_title:
                parts.append(ref_title)
            if ref_snippet:
                parts.append(ref_snippet[:THREAD_SEARCH_SNIPPET_LIMIT])

    return " ".join(part for part in parts if part)


def _rebuild_thread_derived_fields(messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "preview": _thread_preview(messages),
        "message_count": _thread_message_count(messages),
        "last_mode": _thread_last_mode(messages),
        "total_step_count": _thread_total_step_count(messages),
        "search_body": _thread_search_body(messages),
    }


def _thread_title_from_first_user_message(messages: list[dict[str, Any]]) -> str | None:
    if not messages:
        return None
    first = messages[0]
    if first.get("role") != "user":
        return None
    content = _message_content(first)
    if not content:
        return None
    return _trim_text(content, THREAD_TITLE_LIMIT)


def _sanitize_fts_query(q: str) -> str:
    clean = q.replace('"', "").replace("'", "").strip()
    clean = " ".join(clean.split())
    return f'"{clean}"' if clean else ""


def _thread_uses_auto_title(title: str) -> bool:
    return _normalize_text(title) in AUTO_THREAD_TITLES


def _run_mode_from_flag(use_planner: bool) -> str:
    return "planner" if use_planner else "research"


def _run_mode_from_state(state: RunState) -> str:
    return _run_mode_from_flag(bool(state.context.get("use_planner", state.route_kind == "planned_research")))


def _run_final_message_content(state: RunState) -> str:
    final_report = state.artifacts.get("final_report")
    if final_report and final_report.content.strip():
        return final_report.content

    reporter = state.node_results.get("reporter")
    if reporter and reporter.summary.strip():
        return reporter.summary

    error = str(state.context.get("error", "") or "").strip()
    if error:
        return f"Run failed: {error}"

    return ""


def _serialize_thread_summary(
    tid: str,
    title: str,
    created_at: int,
    updated_at: int,
    messages: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    preview: str | None = None,
    message_count: int | None = None,
    last_mode: str | None = None,
    total_step_count: int | None = None,
    score: float | None = None,
    matched_by: str | None = None,
) -> dict[str, Any]:
    safe_messages = messages or []
    return {
        "id": tid,
        "title": title,
        "created_at": created_at,
        "updated_at": updated_at,
        "preview": preview if preview is not None else _thread_preview(safe_messages),
        "message_count": (
            int(message_count)
            if message_count is not None
            else _thread_message_count(safe_messages)
        ),
        "last_mode": last_mode if last_mode is not None else _thread_last_mode(safe_messages),
        "total_step_count": (
            int(total_step_count)
            if total_step_count is not None
            else _thread_total_step_count(safe_messages)
        ),
        "metadata": metadata or {},
        "score": score,
        "matched_by": matched_by,
    }


def _build_chat_prompt(history: list[dict[str, Any]], latest_user_message: str) -> str:
    relevant = [msg for msg in history if msg.get("role") in {"user", "assistant"} and _message_content(msg)]
    recent = relevant[-CHAT_HISTORY_TURNS:]
    if not recent:
        return latest_user_message
    lines: list[str] = ["Conversation so far:"]
    for msg in recent:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {_message_content(msg)}")
    lines.append("")
    lines.append("Latest user message:")
    lines.append(latest_user_message)
    return "\n".join(lines)


def _sse_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _ensure_thread_columns(conn: sqlite3.Connection) -> bool:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(threads)").fetchall()
    }
    required_columns = {
        "preview": "TEXT NOT NULL DEFAULT ''",
        "message_count": "INTEGER NOT NULL DEFAULT 0",
        "last_mode": "TEXT NOT NULL DEFAULT 'chat'",
        "total_step_count": "INTEGER NOT NULL DEFAULT 0",
    }
    changed = False
    for column, ddl in required_columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE threads ADD COLUMN {column} {ddl}")
            changed = True
    return changed


def _sync_thread_index_sqlite(
    conn: sqlite3.Connection,
    tid: str,
    title: str,
    body: str,
) -> None:
    conn.execute("DELETE FROM threads_fts WHERE thread_id = ?", (tid,))
    conn.execute(
        "INSERT INTO threads_fts (thread_id, title, body) VALUES (?, ?, ?)",
        (tid, title, body),
    )


async def _sync_thread_index_async(
    db: aiosqlite.Connection,
    tid: str,
    title: str,
    body: str,
) -> None:
    await db.execute("DELETE FROM threads_fts WHERE thread_id = ?", (tid,))
    await db.execute(
        "INSERT INTO threads_fts (thread_id, title, body) VALUES (?, ?, ?)",
        (tid, title, body),
    )


def _rebuild_all_fts(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM threads_fts")
    rows = conn.execute("SELECT id, title, messages FROM threads").fetchall()
    for tid, title, messages_raw in rows:
        messages = json.loads(messages_raw or "[]")
        derived = _rebuild_thread_derived_fields(messages)
        conn.execute(
            """
            UPDATE threads
            SET preview = ?, message_count = ?, last_mode = ?, total_step_count = ?
            WHERE id = ?
            """,
            (
                derived["preview"],
                derived["message_count"],
                derived["last_mode"],
                derived["total_step_count"],
                tid,
            ),
        )
        _sync_thread_index_sqlite(conn, tid, title, derived["search_body"])


def _ensure_attachment_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id           TEXT PRIMARY KEY,
            filename     TEXT NOT NULL,
            content_type TEXT NOT NULL DEFAULT '',
            size_bytes   INTEGER NOT NULL DEFAULT 0,
            parsed_text  TEXT NOT NULL DEFAULT '',
            created_at   INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attachments_created_at
        ON attachments(created_at DESC)
        """
    )


def _serialize_attachment_record(
    item: sqlite3.Row | aiosqlite.Row | dict[str, Any],
    *,
    include_text: bool = False,
) -> dict[str, Any]:
    data = dict(item)
    payload = {
        "id": data["id"],
        "filename": data["filename"],
        "content_type": data.get("content_type") or "",
        "size_bytes": int(data.get("size_bytes") or 0),
        "created_at": int(data.get("created_at") or 0),
    }
    if include_text:
        payload["parsed_text"] = str(data.get("parsed_text") or "")
    return payload


def _normalize_attachment_ids(raw_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        attachment_id = str(raw_id or "").strip()
        if not attachment_id or attachment_id in seen:
            continue
        seen.add(attachment_id)
        normalized.append(attachment_id)
    if len(normalized) > MAX_ATTACHMENT_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"attachments exceed limit {MAX_ATTACHMENT_COUNT}",
        )
    return normalized


def _attachment_prompt_block(attachments: list[dict[str, Any]]) -> str:
    if not attachments:
        return ""

    remaining = ATTACHMENT_PROMPT_CHAR_LIMIT
    sections = ["## Uploaded attachments"]
    for index, attachment in enumerate(attachments, 1):
        parsed_text = str(attachment.get("parsed_text") or "").strip()
        if not parsed_text:
            continue
        if remaining <= 0:
            break
        excerpt = parsed_text[:remaining]
        sections.append(f"### Attachment {index}: {attachment.get('filename') or f'file-{index}'}")
        sections.append(excerpt)
        remaining -= len(excerpt)
    return "\n\n".join(sections) if len(sections) > 1 else ""


def _content_with_attachment_context(content: str, attachments: list[dict[str, Any]]) -> str:
    attachment_block = _attachment_prompt_block(attachments)
    if not attachment_block:
        return content
    return f"{content}\n\n{attachment_block}"

# ----------------------------------------------------------------------
# DB helpers
# ----------------------------------------------------------------------


# legacy duplicate DB helpers removed; active implementations are defined below


async def _db_create_thread(title: str = DEFAULT_THREAD_TITLE) -> dict[str, Any]:
    tid = str(uuid.uuid4())
    now = int(time.time() * 1000)
    clean_title = (title or "").strip() or DEFAULT_THREAD_TITLE
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            INSERT INTO threads (
                id, title, created_at, updated_at, messages, metadata,
                preview, message_count, last_mode, total_step_count
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (tid, clean_title, now, now, "[]", "{}", "", 0, "chat", 0),
        )
        await _sync_thread_index_async(db, tid, clean_title, "")
        await db.commit()
    return _serialize_thread_summary(
        tid=tid,
        title=clean_title,
        created_at=now,
        updated_at=now,
        preview="",
        message_count=0,
        last_mode="chat",
        total_step_count=0,
        metadata={},
    )


async def _db_list_threads(limit: int = 50) -> list[dict[str, Any]]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                id, title, created_at, updated_at, metadata,
                preview, message_count, last_mode, total_step_count
            FROM threads
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        results.append(
            _serialize_thread_summary(
                tid=data["id"],
                title=data["title"],
                created_at=data["created_at"],
                updated_at=data["updated_at"],
                metadata=json.loads(data.get("metadata") or "{}"),
                preview=data.get("preview") or "",
                message_count=data.get("message_count") or 0,
                last_mode=data.get("last_mode") or "chat",
                total_step_count=data.get("total_step_count") or 0,
            )
        )
    return results


async def _db_get_thread(tid: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM threads WHERE id=?", (tid,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    data = dict(row)
    messages = json.loads(data.get("messages") or "[]")
    data["messages"] = messages
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    data["preview"] = data.get("preview") or _thread_preview(messages)
    data["message_count"] = int(data.get("message_count") or _thread_message_count(messages))
    data["last_mode"] = data.get("last_mode") or _thread_last_mode(messages)
    data["total_step_count"] = int(
        data.get("total_step_count") or _thread_total_step_count(messages)
    )
    return data


async def _db_append_message(tid: str, message: dict[str, Any]) -> None:
    now = int(time.time() * 1000)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT title, messages FROM threads WHERE id=?", (tid,)) as cur:
            row = await cur.fetchone()
        if not row:
            return
        current_title = row["title"] or DEFAULT_THREAD_TITLE
        messages = json.loads(row["messages"] or "[]")
        messages.append(message)
        derived = _rebuild_thread_derived_fields(messages)
        next_title = current_title
        auto_title = _thread_title_from_first_user_message(messages)
        if auto_title and _thread_uses_auto_title(current_title):
            next_title = auto_title
        await db.execute(
            """
            UPDATE threads
            SET
                title = ?,
                updated_at = ?,
                messages = ?,
                preview = ?,
                message_count = ?,
                last_mode = ?,
                total_step_count = ?
            WHERE id = ?
            """,
            (
                next_title,
                now,
                json.dumps(messages, ensure_ascii=False),
                derived["preview"],
                derived["message_count"],
                derived["last_mode"],
                derived["total_step_count"],
                tid,
            ),
        )
        await _sync_thread_index_async(db, tid, next_title, derived["search_body"])
        await db.commit()


async def _db_delete_thread(tid: str) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM threads_fts WHERE thread_id=?", (tid,))
        mem_cur = await db.execute("DELETE FROM memory_entries WHERE thread_id=?", (tid,))
        cur = await db.execute("DELETE FROM threads WHERE id=?", (tid,))
        await db.commit()
        deleted = cur.rowcount > 0
        deleted_memory = mem_cur.rowcount > 0
    if deleted:
        try:
            await asyncio.to_thread(run_store.delete_thread_runs, DB_PATH, tid)
        except Exception:
            logger.exception("Failed to delete graph runs for thread %s", tid)
    if deleted and deleted_memory:
        try:
            await asyncio.to_thread(memory.rebuild_memory_index)
        except Exception:
            logger.exception("Failed to rebuild memory index after deleting thread %s", tid)
    return deleted


async def _db_create_attachment(
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    parsed_text: str,
) -> dict[str, Any]:
    attachment_id = uuid.uuid4().hex
    created_at = int(time.time() * 1000)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            INSERT INTO attachments (
                id, filename, content_type, size_bytes, parsed_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                attachment_id,
                filename,
                content_type,
                int(size_bytes),
                parsed_text,
                created_at,
            ),
        )
        await db.commit()
    return {
        "id": attachment_id,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": int(size_bytes),
        "parsed_text": parsed_text,
        "created_at": created_at,
    }


async def _db_get_attachments(attachment_ids: list[str]) -> list[dict[str, Any]]:
    if not attachment_ids:
        return []
    placeholders = ",".join("?" for _ in attachment_ids)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT id, filename, content_type, size_bytes, parsed_text, created_at
            FROM attachments
            WHERE id IN ({placeholders})
            """,
            attachment_ids,
        ) as cur:
            rows = await cur.fetchall()
    by_id = {row["id"]: _serialize_attachment_record(row, include_text=True) for row in rows}
    return [by_id[attachment_id] for attachment_id in attachment_ids if attachment_id in by_id]


async def _resolve_attachments(attachment_ids: list[str]) -> list[dict[str, Any]]:
    normalized_ids = _normalize_attachment_ids(attachment_ids)
    if not normalized_ids:
        return []
    attachments = await _db_get_attachments(normalized_ids)
    if len(attachments) != len(normalized_ids):
        resolved_ids = {attachment["id"] for attachment in attachments}
        missing = [attachment_id for attachment_id in normalized_ids if attachment_id not in resolved_ids]
        raise HTTPException(status_code=400, detail=f"unknown attachments: {missing}")
    return attachments


async def _db_update_title(tid: str, title: str) -> None:
    clean_title = (title or "").strip() or DEFAULT_THREAD_TITLE
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT messages FROM threads WHERE id=?", (tid,)) as cur:
            row = await cur.fetchone()
        if not row:
            return
        messages = json.loads(row["messages"] or "[]")
        derived = _rebuild_thread_derived_fields(messages)
        await db.execute(
            "UPDATE threads SET title=?, updated_at=? WHERE id=?",
            (clean_title, int(time.time() * 1000), tid),
        )
        await _sync_thread_index_async(db, tid, clean_title, derived["search_body"])
        await db.commit()


async def _db_search_threads(
    q: str,
    from_ts: int | None,
    to_ts: int | None,
    mode: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    limit_val = max(1, min(limit, 100))
    query = (q or "").strip()
    mode_val = (mode or "").strip() or None

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        if not query:
            async with db.execute(
                """
                SELECT
                    id, title, created_at, updated_at, metadata,
                    preview, message_count, last_mode, total_step_count
                FROM threads
                WHERE (? IS NULL OR updated_at >= ?)
                  AND (? IS NULL OR updated_at <= ?)
                  AND (? IS NULL OR last_mode = ?)
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (from_ts, from_ts, to_ts, to_ts, mode_val, mode_val, limit_val),
            ) as cur:
                rows = await cur.fetchall()
            parsed_rows = [(dict(row), None, "recent") for row in rows]
        elif len(query) < 3:
            like_value = f"%{query}%"
            async with db.execute(
                """
                SELECT
                    id, title, created_at, updated_at, metadata,
                    preview, message_count, last_mode, total_step_count
                FROM threads
                WHERE (? IS NULL OR updated_at >= ?)
                  AND (? IS NULL OR updated_at <= ?)
                  AND (? IS NULL OR last_mode = ?)
                  AND (
                    title LIKE ?
                    OR preview LIKE ?
                    OR messages LIKE ?
                  )
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (
                    from_ts,
                    from_ts,
                    to_ts,
                    to_ts,
                    mode_val,
                    mode_val,
                    like_value,
                    like_value,
                    like_value,
                    limit_val,
                ),
            ) as cur:
                rows = await cur.fetchall()
            parsed_rows = [(dict(row), None, "like") for row in rows]
        else:
            fts_query = _sanitize_fts_query(query)
            async with db.execute(
                """
                SELECT
                    t.id, t.title, t.created_at, t.updated_at, t.metadata,
                    t.preview, t.message_count, t.last_mode, t.total_step_count,
                    bm25(threads_fts) AS score
                FROM threads_fts
                JOIN threads t ON t.id = threads_fts.thread_id
                WHERE threads_fts MATCH ?
                  AND (? IS NULL OR t.updated_at >= ?)
                  AND (? IS NULL OR t.updated_at <= ?)
                  AND (? IS NULL OR t.last_mode = ?)
                ORDER BY score, t.updated_at DESC
                LIMIT ?
                """,
                (
                    fts_query,
                    from_ts,
                    from_ts,
                    to_ts,
                    to_ts,
                    mode_val,
                    mode_val,
                    limit_val,
                ),
            ) as cur:
                rows = await cur.fetchall()
            parsed_rows = [(dict(row), row["score"], "fts") for row in rows]

    results: list[dict[str, Any]] = []
    for data, raw_score, matched_by in parsed_rows:
        results.append(
            _serialize_thread_summary(
                tid=data["id"],
                title=data["title"],
                created_at=data["created_at"],
                updated_at=data["updated_at"],
                metadata=json.loads(data.get("metadata") or "{}"),
                preview=data.get("preview") or "",
                message_count=data.get("message_count") or 0,
                last_mode=data.get("last_mode") or "chat",
                total_step_count=data.get("total_step_count") or 0,
                score=(-float(raw_score)) if raw_score is not None else None,
                matched_by=matched_by,
            )
        )
    return results


def _init_db() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    run_store.init_run_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL DEFAULT 'New chat',
            created_at  INTEGER NOT NULL,
            updated_at  INTEGER NOT NULL,
            messages    TEXT NOT NULL DEFAULT '[]',
            metadata    TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    columns_changed = _ensure_thread_columns(conn)
    _ensure_attachment_schema(conn)
    fts_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='threads_fts'"
    ).fetchone()
    fts_sql = (fts_sql_row[0] or "").lower() if fts_sql_row else ""
    if not fts_sql_row or "tokenize = 'trigram'" not in fts_sql:
        conn.execute("DROP TABLE IF EXISTS threads_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE threads_fts USING fts5(
                thread_id UNINDEXED,
                title,
                body,
                tokenize = 'trigram'
            )
            """
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_threads_updated_at ON threads(updated_at DESC)"
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_threads_last_mode_updated_at
        ON threads(last_mode, updated_at DESC)
        """
    )
    fts_count = conn.execute("SELECT COUNT(*) FROM threads_fts").fetchone()[0]
    thread_count = conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
    if columns_changed or fts_count < thread_count:
        _rebuild_all_fts(conn)
    conn.commit()
    conn.close()

# ----------------------------------------------------------------------
# SSE helpers
# ----------------------------------------------------------------------


def _sse(event: str, data: dict) -> str:
    """Format one SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _serialize_step(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "thought": step.get("thought", ""),
        "tool": step.get("tool", ""),
        "args": step.get("args", {}),
        "observation": step.get("observation", ""),
        "sources": step.get("sources", []),
        "cite_ids": step.get("cite_ids", []),
        "error_type": step.get("error_type"),
    }


def _planner_steps(result: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for item in result.get("sub_results", []) or []:
        cite_ids: list[int] = []
        sources: list[dict[str, Any]] = []
        for obs in item.get("observations", []) or []:
            cite_ids.extend(obs.get("cite_ids", []) or [])
            sources.extend(obs.get("sources", []) or [])
        steps.append(
            {
                "thought": item.get("sub_q", ""),
                "tool": "planner_subtask",
                "args": {},
                "observation": item.get("answer", ""),
                "sources": sources,
                "cite_ids": sorted(set(cite_ids)),
                "error_type": item.get("error"),
            }
        )
    return steps


def _result_observations(result: dict[str, Any], use_planner: bool) -> list[dict[str, Any]]:
    if not use_planner:
        return result.get("observations", []) or []
    observations: list[dict[str, Any]] = []
    for item in result.get("sub_results", []) or []:
        observations.extend(item.get("observations", []) or [])
    return observations


def _result_steps(result: dict[str, Any], use_planner: bool) -> list[dict[str, Any]]:
    if not use_planner:
        return result.get("steps", []) or []
    return _planner_steps(result)


async def _persist_memory_after_research(
    *,
    thread_id: str,
    question: str,
    answer: str,
    mode: str,
    source_message_ts: int,
) -> None:
    if not answer.strip():
        return
    try:
        thread = await _db_get_thread(thread_id)
        thread_title = (thread or {}).get("title", DEFAULT_THREAD_TITLE)
        await asyncio.to_thread(
            memory.add_research_memory,
            thread_id=thread_id,
            thread_title=thread_title,
            question=question,
            answer=answer,
            mode=mode,
            source_message_ts=source_message_ts,
        )
    except Exception:
        logger.exception("Failed to persist research memory for thread %s", thread_id)


async def _run_research_stream(
    question: str,
    engine: str,
    max_steps: int,
    skill_profile: str,
    use_planner: bool,
    preferred_thread_id: str,
    queue: asyncio.Queue,
) -> None:
    """Run the research agent in a worker thread and stream progress into the queue."""

    def on_progress(msg: str) -> None:
        queue.put_nowait({"type": "progress", "text": msg})

    def on_step(step: dict) -> None:
        queue.put_nowait({"type": "step", **step})

    try:
        if use_planner:
            result = await asyncio.to_thread(
                run_planner_agent,
                question=question,
                engine=engine,
                progress_callback=on_progress,
                preferred_thread_id=preferred_thread_id,
            )
        else:
            result = await asyncio.to_thread(
                run_agent,
                question=question,
                engine=engine,
                max_steps=max_steps,
                skill_profile=skill_profile,
                progress_callback=on_progress,
                preferred_thread_id=preferred_thread_id,
            )
        # Re-emit step events after the agent finishes so SSE clients can replay the trace.
        for step in result.get("steps", []):
            on_step(step)
        queue.put_nowait({"type": "done", "result": result})
    except Exception as exc:
        queue.put_nowait({"type": "error", "message": str(exc)})

# ----------------------------------------------------------------------
# Modern /api endpoints
# ----------------------------------------------------------------------


# ---------- Thread CRUD ----------

class ThreadCreateRequest(BaseModel):
    title: str = DEFAULT_THREAD_TITLE


class ThreadPatchRequest(BaseModel):
    title: str


class AttachmentInfo(BaseModel):
    id: str
    filename: str
    content_type: str = ""
    size_bytes: int = 0
    created_at: int


class AttachmentUploadRequest(BaseModel):
    filename: str
    content_type: str = ""
    data_base64: str = Field(..., description="Base64 encoded file contents")


class AttachmentUploadResponse(AttachmentInfo):
    text_preview: str = ""


class GraphRunRequest(BaseModel):
    content: str = Field(..., description="Research question")
    engine: str = ""
    max_steps: int = Field(default=8, ge=3, le=15)
    use_planner: bool = False
    attachments: list[str] = Field(default_factory=list)


class RunSummaryInfo(BaseModel):
    run_id: str
    thread_id: str
    question: str
    route_kind: str = ""
    status: str = ""
    current_node: str = ""
    created_at: int
    updated_at: int


class SearchProviderInfo(BaseModel):
    name: str
    enabled: bool = False
    configured: bool = False
    requested: bool = False
    env_hints: list[str] = Field(default_factory=list)


class SearchProviderCatalogResponse(BaseModel):
    active_order: list[str] = Field(default_factory=list)
    providers: list[SearchProviderInfo] = Field(default_factory=list)


class EnginePresetInfo(BaseModel):
    name: str
    roles: list[str] = Field(default_factory=list)


class EngineProviderInfo(BaseModel):
    name: str
    model: str = ""
    configured: bool = False


class EngineCatalogResponse(BaseModel):
    presets: list[EnginePresetInfo] = Field(default_factory=list)
    providers: list[EngineProviderInfo] = Field(default_factory=list)


class SearchProviderAttemptInfo(BaseModel):
    provider: str
    configured: bool = False
    status: str = ""
    result_count: int = 0
    added_count: int = 0
    error: str = ""


class SearchProviderSummaryInfo(BaseModel):
    provider: str
    count: int = 0


class SearchDiagnosticsResultInfo(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    domain: str = ""
    provider: str = ""


class SearchDiagnosticsResponse(BaseModel):
    query: str
    active_order: list[str] = Field(default_factory=list)
    attempts: list[SearchProviderAttemptInfo] = Field(default_factory=list)
    provider_summary: list[SearchProviderSummaryInfo] = Field(default_factory=list)
    results: list[SearchDiagnosticsResultInfo] = Field(default_factory=list)


@app.post("/api/threads", summary="Create thread")
async def create_thread(body: ThreadCreateRequest) -> dict:
    return await _db_create_thread(body.title)


@app.post("/api/uploads", response_model=AttachmentUploadResponse, summary="Upload and parse one attachment")
async def upload_attachment(body: AttachmentUploadRequest) -> AttachmentUploadResponse:
    filename = Path(body.filename or "").name.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported attachment type: {ext or 'unknown'}",
        )

    try:
        file_bytes = base64.b64decode(body.data_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid attachment payload") from exc

    if not file_bytes:
        raise HTTPException(status_code=400, detail="attachment cannot be empty")
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"attachment exceeds {MAX_UPLOAD_SIZE_BYTES} bytes",
        )

    parsed_text = str(
        await asyncio.to_thread(parse_uploaded_document, file_bytes, filename)
    ).strip()
    if not parsed_text:
        raise HTTPException(status_code=422, detail="attachment could not be parsed")

    attachment = await _db_create_attachment(
        filename=filename,
        content_type=(body.content_type or "").strip(),
        size_bytes=len(file_bytes),
        parsed_text=parsed_text,
    )
    return AttachmentUploadResponse(
        **_serialize_attachment_record(attachment),
        text_preview=parsed_text[:ATTACHMENT_PREVIEW_CHAR_LIMIT],
    )


@app.get("/api/threads", summary="List recent threads")
async def list_threads(limit: int = 50) -> list[dict]:
    return await _db_list_threads(limit)


# legacy route decorator removed during Stage 1 search upgrade
@app.get("/api/threads/search", summary="Search threads")
async def search_threads(
    q: str = "",
    from_ts: int | None = Query(None, alias="from"),
    to_ts: int | None = Query(None, alias="to"),
    mode: str | None = None,
    limit: int = 20,
) -> list[dict]:
    return await _db_search_threads(
        q=q,
        from_ts=from_ts,
        to_ts=to_ts,
        mode=mode,
        limit=limit,
    )


@app.get("/api/threads/{thread_id}", summary="Get thread details")
async def get_thread(thread_id: str) -> dict:
    thread = await _db_get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="thread not found")
    return thread


@app.patch("/api/threads/{thread_id}", summary="Rename thread")
async def patch_thread(thread_id: str, body: ThreadPatchRequest) -> dict:
    thread = await _db_get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="thread not found")
    await _db_update_title(thread_id, body.title)
    return {"id": thread_id, "title": body.title}


@app.delete("/api/threads/{thread_id}", summary="Delete thread")
async def delete_thread(thread_id: str) -> dict:
    ok = await _db_delete_thread(thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"deleted": thread_id}


def _run_summary_from_state(state: RunState) -> RunSummaryInfo:
    return RunSummaryInfo(
        run_id=state.run_id,
        thread_id=state.thread_id,
        question=state.question,
        route_kind=state.route_kind,
        status=state.status,
        current_node=state.current_node,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def _run_snapshot_event(state: RunState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "status": state.status,
        "ts": state.updated_at,
        "state": state.model_dump(mode="json"),
    }


def _publish_run_event(run_id: str, event: dict[str, Any]) -> None:
    with _run_event_lock:
        subscribers = tuple(_run_event_subscribers.get(run_id, ()))

    for subscriber in subscribers:
        subscriber.put_nowait(event)


def _publish_run_snapshot(state: RunState) -> None:
    _publish_run_event(state.run_id, _run_snapshot_event(state))


def _register_run_event_subscriber(run_id: str) -> queue.Queue[dict[str, Any]]:
    subscriber: queue.Queue[dict[str, Any]] = queue.Queue()
    with _run_event_lock:
        _run_event_subscribers.setdefault(run_id, set()).add(subscriber)
    return subscriber


def _unregister_run_event_subscriber(run_id: str, subscriber: queue.Queue[dict[str, Any]]) -> None:
    with _run_event_lock:
        subscribers = _run_event_subscribers.get(run_id)
        if not subscribers:
            return
        subscribers.discard(subscriber)
        if not subscribers:
            _run_event_subscribers.pop(run_id, None)


def _encode_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _get_run_or_404(run_id: str) -> RunState:
    state = await asyncio.to_thread(run_store.get_run_state, DB_PATH, run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    return state


def _track_graph_run_task(run_id: str, task: asyncio.Task[None]) -> None:
    _graph_run_tasks[run_id] = task
    task.add_done_callback(lambda _: _graph_run_tasks.pop(run_id, None))


async def _run_graph_in_background(
    state: RunState,
    *,
    engine: str,
    max_steps: int,
    use_planner: bool,
    preferred_thread_id: str,
) -> None:
    worker_state = state.model_copy(deep=True)

    def persist(snapshot: RunState) -> None:
        persisted = snapshot.model_copy(deep=True)
        run_store.save_run_state(DB_PATH, persisted)
        _publish_run_snapshot(persisted)

    try:
        final_state = await asyncio.to_thread(
            run_static_graph,
            state=worker_state,
            engine=engine,
            use_planner=use_planner,
            max_steps=max_steps,
            preferred_thread_id=preferred_thread_id,
            persist_callback=persist,
        )
        persisted_final = final_state.model_copy(deep=True)
        await asyncio.to_thread(run_store.save_run_state, DB_PATH, persisted_final)
        _publish_run_snapshot(persisted_final)
        final_content = _run_final_message_content(final_state)
        if final_content:
            message_ts = int(final_state.context.get("final_message_ts") or time.time() * 1000)
            await _db_append_message(
                final_state.thread_id,
                {
                    "role": "assistant",
                    "content": final_content,
                    "mode": _run_mode_from_state(final_state),
                    "run_id": final_state.run_id,
                    "ts": message_ts,
                },
            )
    except Exception as exc:
        error = str(exc)
        worker_state.status = "failed"
        worker_state.updated_at = int(time.time() * 1000)
        worker_state.context["error"] = error
        current = worker_state.current_node
        if current:
            existing = worker_state.node_results.get(current)
            if existing is not None:
                existing.status = "failed"
                existing.error = error
                existing.finished_at = existing.finished_at or worker_state.updated_at
        failed_state = worker_state.model_copy(deep=True)
        await asyncio.to_thread(run_store.save_run_state, DB_PATH, failed_state)
        _publish_run_snapshot(failed_state)
        await _db_append_message(
            worker_state.thread_id,
            {
                "role": "assistant",
                "content": _run_final_message_content(worker_state),
                "mode": _run_mode_from_state(worker_state),
                "run_id": worker_state.run_id,
                "ts": int(time.time() * 1000),
            },
        )
        logger.exception("Graph run %s failed", worker_state.run_id)


async def _resume_graph_in_background(
    state: RunState,
    *,
    engine: str,
    max_steps: int,
    use_planner: bool,
    preferred_thread_id: str,
) -> None:
    worker_state = state.model_copy(deep=True)

    def persist(snapshot: RunState) -> None:
        persisted = snapshot.model_copy(deep=True)
        run_store.save_run_state(DB_PATH, persisted)
        _publish_run_snapshot(persisted)

    try:
        final_state = await asyncio.to_thread(
            resume_static_graph,
            worker_state,
            engine=engine,
            max_steps=max_steps,
            preferred_thread_id=preferred_thread_id,
            use_planner=use_planner,
            persist_callback=persist,
        )
        persisted_final = final_state.model_copy(deep=True)
        await asyncio.to_thread(run_store.save_run_state, DB_PATH, persisted_final)
        _publish_run_snapshot(persisted_final)
    except Exception as exc:
        error = str(exc)
        worker_state.status = "failed"
        worker_state.updated_at = int(time.time() * 1000)
        worker_state.context["error"] = error
        current = worker_state.current_node
        if current:
            existing = worker_state.node_results.get(current)
            if existing is not None:
                existing.status = "failed"
                existing.error = error
                existing.finished_at = existing.finished_at or worker_state.updated_at
        failed_state = worker_state.model_copy(deep=True)
        await asyncio.to_thread(run_store.save_run_state, DB_PATH, failed_state)
        _publish_run_snapshot(failed_state)
        logger.exception("Graph run resume %s failed", worker_state.run_id)


@app.get("/api/threads/{thread_id}/runs", response_model=list[RunSummaryInfo], summary="List graph runs for a thread")
async def list_thread_runs(thread_id: str, limit: int = 50) -> list[RunSummaryInfo]:
    thread = await _db_get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="thread not found")
    rows = await asyncio.to_thread(run_store.list_thread_runs, DB_PATH, thread_id, limit)
    return [RunSummaryInfo(**row) for row in rows]


@app.post("/api/threads/{thread_id}/runs", response_model=RunState, summary="Create and execute a persisted graph run")
async def create_graph_run(thread_id: str, body: GraphRunRequest) -> RunState:
    thread = await _db_get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="thread not found")

    question = body.content.strip()
    if not question:
        raise HTTPException(status_code=400, detail="content cannot be empty")
    attachments = await _resolve_attachments(body.attachments)
    attachment_refs = [_serialize_attachment_record(item) for item in attachments]
    attachment_prompt = _attachment_prompt_block(attachments)

    route_kind = "planned_research" if body.use_planner else "direct_research"
    state = create_run_state(
        question=question,
        thread_id=thread_id,
        route_kind=route_kind,
    )
    state.context["engine"] = body.engine
    state.context["max_steps"] = body.max_steps
    state.context["use_planner"] = body.use_planner
    state.context["thread_title"] = str(thread.get("title") or DEFAULT_THREAD_TITLE)
    if attachment_refs:
        state.context["uploaded_attachments"] = attachment_refs
    if attachment_prompt:
        state.context["uploaded_attachment_prompt"] = attachment_prompt
    state.updated_at = int(time.time() * 1000)

    user_message = {
        "role": "user",
        "content": question,
        "mode": _run_mode_from_flag(body.use_planner),
        "run_id": state.run_id,
        "ts": int(time.time() * 1000),
    }
    if attachment_refs:
        user_message["attachments"] = attachment_refs
    await _db_append_message(thread_id, user_message)
    await asyncio.to_thread(run_store.save_run_state, DB_PATH, state)
    task = asyncio.create_task(
        _run_graph_in_background(
            state,
            engine=body.engine,
            max_steps=body.max_steps,
            use_planner=body.use_planner,
            preferred_thread_id=thread_id,
        )
    )
    _track_graph_run_task(state.run_id, task)
    return state


@app.get("/api/runs/{run_id}", response_model=RunState, summary="Get persisted graph run details")
async def get_graph_run(run_id: str) -> RunState:
    return await _get_run_or_404(run_id)


@app.get("/api/runs/{run_id}/events", summary="Stream persisted graph run snapshots")
async def stream_graph_run_events(run_id: str, request: Request) -> StreamingResponse:
    await _get_run_or_404(run_id)
    subscriber = _register_run_event_subscriber(run_id)
    current_state = await _get_run_or_404(run_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            initial_event = _run_snapshot_event(current_state)
            yield _encode_sse("snapshot", initial_event)
            if current_state.status in TERMINAL_RUN_STATUSES:
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.to_thread(
                        subscriber.get,
                        True,
                        RUN_EVENT_KEEPALIVE_SECONDS,
                    )
                except queue.Empty:
                    yield _encode_sse("ping", {})
                    continue

                yield _encode_sse("snapshot", event)
                if event.get("status") in TERMINAL_RUN_STATUSES:
                    return
        finally:
            _unregister_run_event_subscriber(run_id, subscriber)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/runs/{run_id}/resume", response_model=RunState, summary="Resume or re-run a persisted graph run")
async def resume_graph_run(run_id: str) -> RunState:
    existing = await _get_run_or_404(run_id)
    if existing.status == "done" or run_id in _graph_run_tasks:
        return existing

    engine = str(existing.context.get("engine", "") or "")
    max_steps = int(existing.context.get("max_steps", 8) or 8)
    use_planner = bool(existing.context.get("use_planner", existing.route_kind == "planned_research"))
    state = existing.model_copy(deep=True)
    state.status = "running"
    state.updated_at = int(time.time() * 1000)
    state.context["engine"] = engine
    state.context["max_steps"] = max_steps
    state.context["use_planner"] = use_planner
    state.context.pop("error", None)

    await asyncio.to_thread(run_store.save_run_state, DB_PATH, state)
    task = asyncio.create_task(
        _resume_graph_in_background(
            state,
            engine=engine,
            max_steps=max_steps,
            use_planner=use_planner,
            preferred_thread_id=existing.thread_id,
        )
    )
    _track_graph_run_task(state.run_id, task)
    return state


@app.get("/api/runs/{run_id}/nodes", response_model=list[NodeResult], summary="List persisted node results for a run")
async def list_graph_run_nodes(run_id: str) -> list[NodeResult]:
    await _get_run_or_404(run_id)
    return await asyncio.to_thread(run_store.list_run_nodes, DB_PATH, run_id)


@app.get("/api/runs/{run_id}/artifacts", response_model=list[ArtifactRecord], summary="List persisted artifacts for a run")
async def list_graph_run_artifacts(run_id: str) -> list[ArtifactRecord]:
    await _get_run_or_404(run_id)
    return await asyncio.to_thread(run_store.list_run_artifacts, DB_PATH, run_id)


@app.get("/api/runs/{run_id}/checkpoints", response_model=list[CheckpointRecord], summary="List persisted checkpoints for a run")
async def list_graph_run_checkpoints(run_id: str) -> list[CheckpointRecord]:
    await _get_run_or_404(run_id)
    return await asyncio.to_thread(run_store.list_run_checkpoints, DB_PATH, run_id)


@app.get("/api/memory/search", summary="Search persisted research memory")
async def search_memory_endpoint(
    q: str,
    limit: int = 10,
    mode: str | None = None,
    thread_id: str | None = None,
) -> list[dict]:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="q cannot be empty")
    top_k = max(1, min(limit, 50))
    return await asyncio.to_thread(
        memory.search_memory,
        query,
        top_k,
        mode,
        thread_id,
    )


@app.post("/api/memory/rebuild", summary="Rebuild the persistent memory index")
async def rebuild_memory_endpoint() -> dict:
    count = await asyncio.to_thread(memory.rebuild_memory_index)
    return {"rebuilt": count}


@app.get("/api/memory/stats", summary="Show memory index stats")
async def memory_stats_endpoint() -> dict:
    stats = await asyncio.to_thread(memory.get_memory_stats)
    return stats


@app.get("/api/search/providers", response_model=SearchProviderCatalogResponse, summary="List search providers")
def list_search_providers() -> SearchProviderCatalogResponse:
    return SearchProviderCatalogResponse(
        active_order=get_search_provider_order(),
        providers=[SearchProviderInfo(**item) for item in get_search_provider_catalog()],
    )


@app.get("/api/ai/engines", response_model=EngineCatalogResponse, summary="List selectable AI engine presets and providers")
def list_ai_engines() -> EngineCatalogResponse:
    presets = [
        EnginePresetInfo(
            name=name,
            roles=[role for role, order in preset.items() if role in {"orchestrator", "worker", "analyst"} and order],
        )
        for name, preset in ENGINE_PRESETS.items()
    ]
    providers = [
        EngineProviderInfo(
            name=name,
            model=str(cfg.get("model", "")),
            configured=bool(load_secret(str(cfg.get("env", "")).strip())),
        )
        for name, cfg in PROVIDERS.items()
    ]
    return EngineCatalogResponse(presets=presets, providers=providers)


@app.get(
    "/api/search/diagnostics",
    response_model=SearchDiagnosticsResponse,
    summary="Run a provider-level search diagnostics query",
)
def search_diagnostics(
    q: str,
    max_results: int = 5,
    timelimit: str = "",
) -> SearchDiagnosticsResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="q cannot be empty")
    payload = search_results_with_trace(
        query,
        max_results=max(1, min(max_results, 10)),
        timelimit=timelimit.strip(),
    )
    return SearchDiagnosticsResponse(
        query=payload["query"],
        active_order=payload["active_order"],
        attempts=[SearchProviderAttemptInfo(**item) for item in payload["attempts"]],
        provider_summary=[SearchProviderSummaryInfo(**item) for item in payload["provider_summary"]],
        results=[SearchDiagnosticsResultInfo(**item) for item in payload["results"]],
    )


# ---------- Chat streaming ----------


class ChatRequest(BaseModel):
    content: str = Field(..., description="User message content")
    engine: str = ""
    attachments: list[str] = Field(default_factory=list)


@app.post("/api/threads/{thread_id}/chat", summary="Stream chat response")
async def chat_stream(thread_id: str, body: ChatRequest, request: Request):
    thread = await _db_get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="thread not found")

    prompt_text = body.content.strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="content cannot be empty")
    attachments = await _resolve_attachments(body.attachments)
    attachment_refs = [_serialize_attachment_record(item) for item in attachments]
    prompt_text_with_attachments = _content_with_attachment_context(prompt_text, attachments)

    user_msg = {"role": "user", "content": prompt_text, "ts": int(time.time() * 1000)}
    if attachment_refs:
        user_msg["attachments"] = attachment_refs
    await _db_append_message(thread_id, user_msg)

    from agent import ai_generate_role

    async def generator() -> AsyncIterator[str]:
        yield _sse("message_start", {"role": "user", "content": prompt_text})
        try:
            prompt = _build_chat_prompt(thread.get("messages", []), prompt_text_with_attachments)
            answer = await asyncio.to_thread(
                ai_generate_role,
                prompt,
                CHAT_SYSTEM_PROMPT,
                engine=body.engine,
            )
            chunk_size = 80
            for i in range(0, len(answer), chunk_size):
                if await request.is_disconnected():
                    return
                yield _sse("text_delta", {"delta": answer[i : i + chunk_size]})
                await asyncio.sleep(0.02)
            assistant_msg = {"role": "assistant", "content": answer, "ts": int(time.time() * 1000)}
            await _db_append_message(thread_id, assistant_msg)
            yield _sse("message_done", {"content": answer})
            yield _sse("done", {"thread_id": thread_id, "content": answer})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return _sse_response(generator())




# ---------- Research锛圧eAct/Planner锛屾祦寮忔楠わ級 ----------

class ResearchRequest(BaseModel):
    content: str = Field(..., description="Research question")
    engine: str = ""
    max_steps: int = Field(default=8, ge=3, le=15)
    skill_profile: str = DEFAULT_SKILL_PROFILE
    use_planner: bool = False
    attachments: list[str] = Field(default_factory=list)


@app.post("/api/threads/{thread_id}/research", summary="Stream research run")
async def research_stream(thread_id: str, body: ResearchRequest, request: Request):
    return await _thread_run_stream(thread_id, body, request)


async def _thread_run_stream(thread_id: str, body: ResearchRequest, request: Request):
    thread = await _db_get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="thread not found")

    question = body.content.strip()
    if not question:
        raise HTTPException(status_code=400, detail="content cannot be empty")
    profile_name = _validate_profile_name(body.skill_profile.strip() or DEFAULT_SKILL_PROFILE)
    attachments = await _resolve_attachments(body.attachments)
    attachment_refs = [_serialize_attachment_record(item) for item in attachments]
    effective_question = _content_with_attachment_context(question, attachments)

    user_msg = {
        "role": "user",
        "content": question,
        "mode": "planner" if body.use_planner else "research",
        "ts": int(time.time() * 1000),
    }
    if attachment_refs:
        user_msg["attachments"] = attachment_refs
    await _db_append_message(thread_id, user_msg)

    async def generator() -> AsyncIterator[str]:
        yield _sse("message_start", {"role": "user", "content": question})

        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            _run_research_stream(
                question=effective_question,
                engine=body.engine,
                max_steps=body.max_steps,
                skill_profile=profile_name,
                use_planner=body.use_planner,
                preferred_thread_id=thread_id,
                queue=queue,
            )
        )

        emitted_steps = 0
        try:
            while True:
                if await request.is_disconnected():
                    task.cancel()
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    yield _sse("ping", {})
                    continue

                etype = event.get("type")
                if etype == "progress":
                    yield _sse("progress", {"text": event["text"]})
                    continue

                if etype == "step":
                    emitted_steps += 1
                    yield _sse("step", _serialize_step(event))
                    continue

                if etype == "done":
                    result = event["result"]
                    steps = _result_steps(result, body.use_planner)
                    observations = _result_observations(result, body.use_planner)
                    references, references_md = _build_references(observations)
                    answer = result.get("answer", "")
                    if emitted_steps == 0:
                        for step in steps:
                            yield _sse("step", _serialize_step(step))

                    assistant_msg = {
                        "role": "assistant",
                        "content": answer,
                        "mode": "planner" if body.use_planner else "research",
                        "steps": steps,
                        "references": [ref.model_dump() for ref in references],
                        "ts": int(time.time() * 1000),
                    }
                    await _db_append_message(thread_id, assistant_msg)
                    if answer.strip() and not result.get("error"):
                        asyncio.create_task(
                            _persist_memory_after_research(
                                thread_id=thread_id,
                                question=question,
                                answer=answer,
                                mode="planner" if body.use_planner else "research",
                                source_message_ts=assistant_msg["ts"],
                            )
                        )
                    step_count = result.get("step_count", result.get("total_steps", len(steps)))
                    error = result.get("error")
                    memory_hits = result.get("memory_hits", []) or []
                    memory_hit_count = int(result.get("memory_hit_count", len(memory_hits)))
                    yield _sse("message_done", {"content": answer, "step_count": step_count, "error": error})
                    yield _sse(
                        "done",
                        {
                            "thread_id": thread_id,
                            "answer": answer,
                            "step_count": step_count,
                            "memory_hits": memory_hits,
                            "memory_hit_count": memory_hit_count,
                            "refs": [ref.model_dump() for ref in references],
                            "references_md": references_md,
                            "error": error,
                        },
                    )
                    return

                if etype == "error":
                    yield _sse("error", {"message": event["message"]})
                    return
        finally:
            if not task.done():
                task.cancel()
        return

    return _sse_response(generator())

# ----------------------------------------------------------------------
# Legacy endpoints (backward compatibility)
# ----------------------------------------------------------------------

@app.post("/api/threads/{thread_id}/run", summary="Run agent workflow for a thread")
async def run_thread(thread_id: str, body: ResearchRequest, request: Request):
    return await _thread_run_stream(thread_id, body, request)


class RunRequest(BaseModel):
    question: str = Field(..., description="Research question")
    engine: str = Field(default="")
    max_steps: int = Field(default=8, ge=3, le=15)
    skill_profile: str = Field(default="api_safe")
    attachments: list[str] = Field(default_factory=list)


class SourceInfo(BaseModel):
    url: str = ""
    title: str = ""
    snippet: str = ""


class StepInfo(BaseModel):
    thought: str = ""
    tool: str = ""
    args: dict = Field(default_factory=dict)
    observation: str = ""
    sources: list[SourceInfo] = Field(default_factory=list)
    cite_ids: list[int] = Field(default_factory=list)
    error_type: str | None = None


class ObservationInfo(BaseModel):
    content: str = ""
    sources: list[SourceInfo] = Field(default_factory=list)
    tool: str = ""
    args: dict = Field(default_factory=dict)
    cite_ids: list[int] = Field(default_factory=list)


class ReferenceInfo(BaseModel):
    cite_id: int
    url: str
    title: str = ""
    snippet: str = ""


class MemoryHitInfo(BaseModel):
    id: str
    thread_id: str
    source_message_ts: int = 0
    kind: str = ""
    title: str = ""
    content: str = ""
    mode: str = ""
    created_at: int = 0
    semantic_score: float = 0.0
    rank_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    answer: str
    steps: list[StepInfo] = Field(default_factory=list)
    observations: list[ObservationInfo] = Field(default_factory=list)
    references: list[ReferenceInfo] = Field(default_factory=list)
    references_md: str = ""
    memory_hits: list[MemoryHitInfo] = Field(default_factory=list)
    memory_hit_count: int = 0
    skill_profile: str = DEFAULT_SKILL_PROFILE
    step_count: int
    error: str | None = None


class MemoryStatsResponse(BaseModel):
    ready: bool
    entry_count: int
    fact_count: int
    faiss_count: int
    id_count: int
    last_created_at: int


class SkillInfo(BaseModel):
    name: str
    description: str
    category: str
    required_args: list[str] = Field(default_factory=list)
    optional_args: list[str] = Field(default_factory=list)
    args_desc: dict[str, str] = Field(default_factory=dict)
    returns_sources: bool = True
    enabled: bool = True
    configured: bool = True
    env_hints: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class SkillStatePatchRequest(BaseModel):
    enabled: bool


class SkillProfileInfo(BaseModel):
    name: str
    description: str = ""
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_count: int = 0


class SkillCatalogResponse(BaseModel):
    total_skills: int
    enabled_skills: int
    categories: list[str] = Field(default_factory=list)
    profiles: list[SkillProfileInfo] = Field(default_factory=list)
    skills: list[SkillInfo] = Field(default_factory=list)


class RoutePreviewRequest(BaseModel):
    question: str
    engine: str = ""
    skill_profile: str = DEFAULT_SKILL_PROFILE


class RoutePreviewResponse(BaseModel):
    question: str
    question_type: str
    skill_profile: str
    allowed_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    discouraged_skills: list[str] = Field(default_factory=list)
    starter: str = ""
    reasons: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)


_SEARCH_SKILL_ENV_HINT_NAMES = {
    "search",
    "search_company",
    "search_docs",
    "search_multi",
    "search_news",
    "search_recent",
    "search_site",
}


def _search_skill_env_hints() -> list[str]:
    hints = ["SEARCH_PROVIDERS"]
    seen = set(hints)
    for provider in get_search_provider_catalog():
        for hint in provider.get("env_hints", []) or []:
            normalized_hint = str(hint or "").strip()
            if not normalized_hint or normalized_hint in seen:
                continue
            seen.add(normalized_hint)
            hints.append(normalized_hint)
    return hints


def _build_references(observations: list[dict]) -> tuple[list[ReferenceInfo], str]:
    ref_map: dict[int, ReferenceInfo] = {}
    for obs in observations:
        sources = obs.get("sources", []) or []
        cite_ids = obs.get("cite_ids", []) or []
        for idx, source in enumerate(sources):
            cite_id = cite_ids[idx] if idx < len(cite_ids) else None
            url = source.get("url", "")
            if not cite_id or not url or cite_id in ref_map:
                continue
            ref_map[cite_id] = ReferenceInfo(
                cite_id=cite_id, url=url,
                title=source.get("title", ""), snippet=source.get("snippet", ""),
            )
    references = [ref_map[k] for k in sorted(ref_map)]
    if not references:
        return [], ""
    refs_md = "## References\n\n" + "\n".join(
        f"{r.cite_id}. [{r.title or r.url}]({r.url})" for r in references
    )
    return references, refs_md


def _skill_runtime_metadata(skill_name: str) -> dict[str, Any]:
    normalized_name = str(skill_name or "").strip()
    if normalized_name == "rag_retrieve":
        configured = bool(os.getenv("DEER_RAG_URL", "").strip())
        if not configured:
            try:
                import rag

                configured = bool(rag.is_ready())
            except Exception:
                configured = False
        return {
            "configured": configured,
            "env_hints": [] if configured else ["DEER_RAG_URL"],
        }
    if normalized_name in _SEARCH_SKILL_ENV_HINT_NAMES:
        return {
            "configured": True,
            "env_hints": _search_skill_env_hints(),
        }

    return {
        "configured": True,
        "env_hints": [],
    }


def _build_skill_catalog() -> SkillCatalogResponse:
    skill_names = BUILTIN_SKILL_REGISTRY.names()
    enabled_map = get_skill_state_map(skill_names)
    stats_map = get_skill_stats_map(skill_names, DB_PATH)
    skills_raw = BUILTIN_SKILL_REGISTRY.as_metadata_list(enabled_map=enabled_map)
    enriched_skills: list[dict[str, Any]] = []
    for item in skills_raw:
        runtime = _skill_runtime_metadata(item["name"])
        enriched = dict(item)
        enriched.update(runtime)
        enriched["stats"] = stats_map.get(item["name"], {})
        enriched_skills.append(enriched)
    return SkillCatalogResponse(
        total_skills=len(enriched_skills),
        enabled_skills=sum(1 for s in enriched_skills if s["enabled"]),
        categories=sorted({s["category"] for s in enriched_skills}),
        profiles=[SkillProfileInfo(**p) for p in get_profile_metadata_list([s["name"] for s in enriched_skills if s["enabled"]])],
        skills=[SkillInfo(**s) for s in enriched_skills],
    )


def _validate_profile_name(name: str) -> str:
    available = get_skill_profiles(BUILTIN_SKILL_REGISTRY.names())
    if name not in available:
        raise HTTPException(status_code=400, detail=f"unknown skill_profile: {name}. available: {sorted(available)}")
    return name


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/skills", response_model=SkillCatalogResponse)
def list_skills() -> SkillCatalogResponse:
    return _build_skill_catalog()


@app.patch("/skills/{skill_name}", response_model=SkillInfo)
def patch_skill(skill_name: str, body: SkillStatePatchRequest) -> SkillInfo:
    normalized_name = skill_name.strip()
    if not BUILTIN_SKILL_REGISTRY.has(normalized_name):
        raise HTTPException(status_code=404, detail="skill not found")
    set_skill_enabled(normalized_name, body.enabled)
    catalog = _build_skill_catalog()
    for item in catalog.skills:
        if item.name == normalized_name:
            return item
    raise HTTPException(status_code=500, detail="updated skill not found in catalog")


@app.post("/skills/route-preview", response_model=RoutePreviewResponse)
def route_preview_endpoint(req: RoutePreviewRequest) -> RoutePreviewResponse:
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    profile_name = _validate_profile_name(req.skill_profile.strip() or DEFAULT_SKILL_PROFILE)
    enabled_skills = get_enabled_skill_names(BUILTIN_SKILL_REGISTRY.names())
    resolved, profile_skills = get_profile_allowlist(profile_name, enabled_skills)
    decision = preview_route(q, profile_skills, engine=req.engine, profile_name=resolved)
    return RoutePreviewResponse(
        question=q, question_type=decision.qtype.value, skill_profile=resolved,
        allowed_skills=decision.allowed, preferred_skills=decision.preferred,
        discouraged_skills=decision.discouraged, starter=decision.starter,
        reasons=decision.reasons, signals=decision.signals,
    )


@app.post("/run", response_model=RunResponse)
async def run_sync(req: RunRequest) -> RunResponse:
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    profile_name = _validate_profile_name(req.skill_profile.strip() or DEFAULT_SKILL_PROFILE)
    attachments = await _resolve_attachments(req.attachments)
    result = run_agent(
        question=_content_with_attachment_context(q, attachments),
        engine=req.engine,
        max_steps=req.max_steps,
        skill_profile=profile_name,
    )
    observations_raw = result.get("observations", [])
    references, references_md = _build_references(observations_raw)
    return RunResponse(
        answer=result.get("answer", ""),
        steps=[StepInfo(**{k: s.get(k, StepInfo.__fields__[k].default) for k in StepInfo.__fields__}) for s in result.get("steps", [])],
        observations=[ObservationInfo(**{k: o.get(k, ObservationInfo.__fields__[k].default) for k in ObservationInfo.__fields__}) for o in observations_raw],
        references=references, references_md=references_md,
        memory_hits=result.get("memory_hits", []),
        memory_hit_count=int(result.get("memory_hit_count", len(result.get("memory_hits", [])))),
        skill_profile=result.get("skill_profile", DEFAULT_SKILL_PROFILE),
        step_count=result.get("step_count", 0), error=result.get("error"),
    )
