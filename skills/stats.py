from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "threads.db"


def _ensure_skill_stats_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_usage_stats (
            skill_name         TEXT PRIMARY KEY,
            call_count         INTEGER NOT NULL DEFAULT 0,
            success_count      INTEGER NOT NULL DEFAULT 0,
            failure_count      INTEGER NOT NULL DEFAULT 0,
            total_duration_ms  INTEGER NOT NULL DEFAULT 0,
            last_used_at       INTEGER NOT NULL DEFAULT 0,
            last_status        TEXT NOT NULL DEFAULT '',
            last_error         TEXT NOT NULL DEFAULT ''
        )
        """
    )


def init_skill_stats(db_path: str | Path = DB_PATH) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        _ensure_skill_stats_schema(conn)
        conn.commit()
    finally:
        conn.close()


def record_skill_call(
    skill_name: str,
    *,
    success: bool,
    duration_ms: int = 0,
    error: str = "",
    db_path: str | Path = DB_PATH,
) -> None:
    record_skill_calls(
        [
            {
                "skill_name": skill_name,
                "success": success,
                "duration_ms": duration_ms,
                "error": error,
            }
        ],
        db_path=db_path,
    )


def record_skill_calls(
    entries: list[dict[str, Any]],
    *,
    db_path: str | Path = DB_PATH,
) -> None:
    normalized_entries: list[tuple[str, int, int, int, int, str, str]] = []
    for entry in entries:
        normalized_name = str(entry.get("skill_name") or "").strip()
        if not normalized_name:
            continue
        success = bool(entry.get("success"))
        normalized_entries.append(
            (
                normalized_name,
                1 if success else 0,
                0 if success else 1,
                max(0, int(entry.get("duration_ms", 0) or 0)),
                int(time.time() * 1000),
                "success" if success else "failure",
                str(entry.get("error") or "")[:500],
            )
        )

    if not normalized_entries:
        return

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        _ensure_skill_stats_schema(conn)
        conn.executemany(
            """
            INSERT INTO skill_usage_stats (
                skill_name,
                call_count,
                success_count,
                failure_count,
                total_duration_ms,
                last_used_at,
                last_status,
                last_error
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_name) DO UPDATE SET
                call_count = call_count + 1,
                success_count = success_count + excluded.success_count,
                failure_count = failure_count + excluded.failure_count,
                total_duration_ms = total_duration_ms + excluded.total_duration_ms,
                last_used_at = excluded.last_used_at,
                last_status = excluded.last_status,
                last_error = excluded.last_error
            """,
            normalized_entries,
        )
        conn.commit()
    finally:
        conn.close()


def get_skill_stats_map(
    skill_names: list[str] | None = None,
    db_path: str | Path = DB_PATH,
) -> dict[str, dict[str, Any]]:
    path = Path(db_path)
    if not path.exists():
        return {
            name: {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_duration_ms": 0,
                "average_duration_ms": 0.0,
                "last_used_at": 0,
                "last_status": "",
                "last_error": "",
            }
            for name in (skill_names or [])
        }

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        _ensure_skill_stats_schema(conn)
        if skill_names:
            placeholders = ",".join("?" for _ in skill_names)
            rows = conn.execute(
                f"SELECT * FROM skill_usage_stats WHERE skill_name IN ({placeholders})",
                skill_names,
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM skill_usage_stats").fetchall()
    finally:
        conn.close()

    stats_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        call_count = int(row["call_count"] or 0)
        total_duration_ms = int(row["total_duration_ms"] or 0)
        stats_map[str(row["skill_name"])] = {
            "call_count": call_count,
            "success_count": int(row["success_count"] or 0),
            "failure_count": int(row["failure_count"] or 0),
            "total_duration_ms": total_duration_ms,
            "average_duration_ms": float(total_duration_ms / call_count) if call_count else 0.0,
            "last_used_at": int(row["last_used_at"] or 0),
            "last_status": str(row["last_status"] or ""),
            "last_error": str(row["last_error"] or ""),
        }

    for name in skill_names or []:
        stats_map.setdefault(
            name,
            {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_duration_ms": 0,
                "average_duration_ms": 0.0,
                "last_used_at": 0,
                "last_status": "",
                "last_error": "",
            },
        )

    return stats_map
