"""
SQLite persistence helpers for Stage D graph runs.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from run_state import (
    ArtifactRecord,
    CheckpointRecord,
    NodeResult,
    ObservationRecord,
    RunState,
    SourceRecord,
)


def init_run_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            run_id        TEXT PRIMARY KEY,
            thread_id     TEXT NOT NULL,
            question      TEXT NOT NULL,
            route_kind    TEXT NOT NULL DEFAULT '',
            status        TEXT NOT NULL DEFAULT 'running',
            current_node  TEXT NOT NULL DEFAULT '',
            node_order    TEXT NOT NULL DEFAULT '[]',
            context_json  TEXT NOT NULL DEFAULT '{}',
            created_at    INTEGER NOT NULL,
            updated_at    INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_run_nodes (
            run_id             TEXT NOT NULL,
            node_id            TEXT NOT NULL,
            node_index         INTEGER NOT NULL DEFAULT 0,
            node_type          TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'pending',
            summary            TEXT NOT NULL DEFAULT '',
            observations_json  TEXT NOT NULL DEFAULT '[]',
            source_keys_json   TEXT NOT NULL DEFAULT '[]',
            artifacts_json     TEXT NOT NULL DEFAULT '[]',
            error              TEXT,
            started_at         INTEGER,
            finished_at        INTEGER,
            PRIMARY KEY (run_id, node_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_run_sources (
            run_id         TEXT NOT NULL,
            source_key     TEXT NOT NULL,
            url            TEXT NOT NULL,
            title          TEXT NOT NULL DEFAULT '',
            snippet        TEXT NOT NULL DEFAULT '',
            source_type    TEXT NOT NULL DEFAULT '',
            metadata_json  TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, source_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_run_artifacts (
            run_id       TEXT NOT NULL,
            artifact_id  TEXT NOT NULL,
            kind         TEXT NOT NULL,
            title        TEXT NOT NULL DEFAULT '',
            content      TEXT NOT NULL,
            created_by   TEXT NOT NULL,
            created_at   INTEGER NOT NULL,
            PRIMARY KEY (run_id, artifact_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_run_checkpoints (
            run_id         TEXT NOT NULL,
            checkpoint_id  TEXT NOT NULL,
            checkpoint_idx INTEGER NOT NULL DEFAULT 0,
            node_id        TEXT NOT NULL,
            status         TEXT NOT NULL,
            snapshot_ref   TEXT NOT NULL,
            created_at     INTEGER NOT NULL,
            PRIMARY KEY (run_id, checkpoint_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_thread_updated ON agent_runs(thread_id, updated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_run_nodes_run_idx ON agent_run_nodes(run_id, node_index ASC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_run_artifacts_run_created ON agent_run_artifacts(run_id, created_at ASC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_run_checkpoints_run_idx ON agent_run_checkpoints(run_id, checkpoint_idx ASC)"
    )


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    init_run_schema(conn)
    return conn


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def save_run_state(db_path: str | Path, state: RunState) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO agent_runs (
                run_id, thread_id, question, route_kind, status, current_node,
                node_order, context_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                thread_id = excluded.thread_id,
                question = excluded.question,
                route_kind = excluded.route_kind,
                status = excluded.status,
                current_node = excluded.current_node,
                node_order = excluded.node_order,
                context_json = excluded.context_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                state.run_id,
                state.thread_id,
                state.question,
                state.route_kind,
                state.status,
                state.current_node,
                _json_dumps(list(state.node_order)),
                _json_dumps(dict(state.context)),
                state.created_at,
                state.updated_at,
            ),
        )

        conn.execute("DELETE FROM agent_run_nodes WHERE run_id = ?", (state.run_id,))
        conn.execute("DELETE FROM agent_run_sources WHERE run_id = ?", (state.run_id,))
        conn.execute("DELETE FROM agent_run_artifacts WHERE run_id = ?", (state.run_id,))
        conn.execute("DELETE FROM agent_run_checkpoints WHERE run_id = ?", (state.run_id,))

        ordered_node_ids = list(dict.fromkeys(list(state.node_order) + list(state.node_results.keys())))
        for index, node_id in enumerate(ordered_node_ids):
            result = state.node_results.get(node_id)
            if result is None:
                continue
            conn.execute(
                """
                INSERT INTO agent_run_nodes (
                    run_id, node_id, node_index, node_type, status, summary,
                    observations_json, source_keys_json, artifacts_json,
                    error, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.run_id,
                    result.node_id,
                    index,
                    result.node_type,
                    result.status,
                    result.summary,
                    _json_dumps([item.model_dump() for item in result.observations]),
                    _json_dumps(list(result.source_keys)),
                    _json_dumps(list(result.artifacts)),
                    result.error,
                    result.started_at,
                    result.finished_at,
                ),
            )

        for source in state.source_catalog.values():
            conn.execute(
                """
                INSERT INTO agent_run_sources (
                    run_id, source_key, url, title, snippet, source_type, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.run_id,
                    source.source_key,
                    source.url,
                    source.title,
                    source.snippet,
                    source.source_type,
                    _json_dumps(dict(source.metadata)),
                ),
            )

        for artifact in state.artifacts.values():
            conn.execute(
                """
                INSERT INTO agent_run_artifacts (
                    run_id, artifact_id, kind, title, content, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.run_id,
                    artifact.artifact_id,
                    artifact.kind,
                    artifact.title,
                    artifact.content,
                    artifact.created_by,
                    artifact.created_at,
                ),
            )

        for index, checkpoint in enumerate(state.checkpoints):
            conn.execute(
                """
                INSERT INTO agent_run_checkpoints (
                    run_id, checkpoint_id, checkpoint_idx, node_id, status, snapshot_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.run_id,
                    checkpoint.checkpoint_id,
                    index,
                    checkpoint.node_id,
                    checkpoint.status,
                    checkpoint.snapshot_ref,
                    checkpoint.created_at,
                ),
            )

        conn.commit()
    finally:
        conn.close()


def _load_node_results(conn: sqlite3.Connection, run_id: str) -> dict[str, NodeResult]:
    rows = conn.execute(
        """
        SELECT *
        FROM agent_run_nodes
        WHERE run_id = ?
        ORDER BY node_index ASC
        """,
        (run_id,),
    ).fetchall()
    results: dict[str, NodeResult] = {}
    for row in rows:
        observations = [
            ObservationRecord(**item)
            for item in json.loads(row["observations_json"] or "[]")
        ]
        result = NodeResult(
            node_id=row["node_id"],
            node_type=row["node_type"],
            status=row["status"],
            summary=row["summary"] or "",
            observations=observations,
            source_keys=[str(item) for item in json.loads(row["source_keys_json"] or "[]")],
            artifacts=[str(item) for item in json.loads(row["artifacts_json"] or "[]")],
            error=row["error"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
        results[result.node_id] = result
    return results


def _load_sources(conn: sqlite3.Connection, run_id: str) -> dict[str, SourceRecord]:
    rows = conn.execute(
        """
        SELECT *
        FROM agent_run_sources
        WHERE run_id = ?
        ORDER BY source_key ASC
        """,
        (run_id,),
    ).fetchall()
    return {
        row["source_key"]: SourceRecord(
            source_key=row["source_key"],
            url=row["url"],
            title=row["title"] or "",
            snippet=row["snippet"] or "",
            source_type=row["source_type"] or "",
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
        for row in rows
    }


def _load_artifacts(conn: sqlite3.Connection, run_id: str) -> dict[str, ArtifactRecord]:
    rows = conn.execute(
        """
        SELECT *
        FROM agent_run_artifacts
        WHERE run_id = ?
        ORDER BY created_at ASC, artifact_id ASC
        """,
        (run_id,),
    ).fetchall()
    return {
        row["artifact_id"]: ArtifactRecord(
            artifact_id=row["artifact_id"],
            kind=row["kind"],
            title=row["title"] or "",
            content=row["content"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )
        for row in rows
    }


def _load_checkpoints(conn: sqlite3.Connection, run_id: str) -> list[CheckpointRecord]:
    rows = conn.execute(
        """
        SELECT *
        FROM agent_run_checkpoints
        WHERE run_id = ?
        ORDER BY checkpoint_idx ASC
        """,
        (run_id,),
    ).fetchall()
    return [
        CheckpointRecord(
            checkpoint_id=row["checkpoint_id"],
            run_id=run_id,
            node_id=row["node_id"],
            status=row["status"],
            snapshot_ref=row["snapshot_ref"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_run_state(db_path: str | Path, run_id: str) -> RunState | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM agent_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if not row:
            return None

        return RunState(
            run_id=row["run_id"],
            thread_id=row["thread_id"],
            question=row["question"],
            route_kind=row["route_kind"] or "",
            status=row["status"],
            current_node=row["current_node"] or "",
            node_order=[str(item) for item in json.loads(row["node_order"] or "[]")],
            node_results=_load_node_results(conn, run_id),
            source_catalog=_load_sources(conn, run_id),
            artifacts=_load_artifacts(conn, run_id),
            context=json.loads(row["context_json"] or "{}"),
            checkpoints=_load_checkpoints(conn, run_id),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    finally:
        conn.close()


def list_thread_runs(db_path: str | Path, thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT run_id, thread_id, question, route_kind, status, current_node, created_at, updated_at
            FROM agent_runs
            WHERE thread_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (thread_id, max(1, min(limit, 100))),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_run_nodes(db_path: str | Path, run_id: str) -> list[NodeResult]:
    conn = _connect(db_path)
    try:
        return list(_load_node_results(conn, run_id).values())
    finally:
        conn.close()


def list_run_artifacts(db_path: str | Path, run_id: str) -> list[ArtifactRecord]:
    conn = _connect(db_path)
    try:
        return list(_load_artifacts(conn, run_id).values())
    finally:
        conn.close()


def list_run_checkpoints(db_path: str | Path, run_id: str) -> list[CheckpointRecord]:
    conn = _connect(db_path)
    try:
        return _load_checkpoints(conn, run_id)
    finally:
        conn.close()


def delete_thread_runs(db_path: str | Path, thread_id: str) -> int:
    conn = _connect(db_path)
    try:
        run_rows = conn.execute(
            "SELECT run_id FROM agent_runs WHERE thread_id = ?",
            (thread_id,),
        ).fetchall()
        run_ids = [str(row["run_id"]) for row in run_rows]
        if not run_ids:
            return 0

        placeholders = ",".join("?" for _ in run_ids)
        conn.execute(f"DELETE FROM agent_run_nodes WHERE run_id IN ({placeholders})", run_ids)
        conn.execute(f"DELETE FROM agent_run_sources WHERE run_id IN ({placeholders})", run_ids)
        conn.execute(f"DELETE FROM agent_run_artifacts WHERE run_id IN ({placeholders})", run_ids)
        conn.execute(f"DELETE FROM agent_run_checkpoints WHERE run_id IN ({placeholders})", run_ids)
        cur = conn.execute(f"DELETE FROM agent_runs WHERE run_id IN ({placeholders})", run_ids)
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


__all__ = [
    "delete_thread_runs",
    "get_run_state",
    "init_run_schema",
    "list_run_artifacts",
    "list_run_checkpoints",
    "list_run_nodes",
    "list_thread_runs",
    "save_run_state",
]
