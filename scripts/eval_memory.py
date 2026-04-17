from __future__ import annotations

import importlib
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import memory  # noqa: E402


DB_PATH = ROOT / "data" / "threads.db"
RESEARCH_THREAD_ID = f"eval-research-{uuid.uuid4().hex[:8]}"
PLANNER_THREAD_ID = f"eval-planner-{uuid.uuid4().hex[:8]}"


@dataclass
class EvalResult:
    name: str
    passed: bool
    details: str


def _cleanup_threads(thread_ids: list[str]) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            f"DELETE FROM memory_entries WHERE thread_id IN ({','.join('?' for _ in thread_ids)})",
            thread_ids,
        )
        conn.commit()
    finally:
        conn.close()
    memory.rebuild_memory_index()


def _db_count_for_thread(thread_id: str) -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM memory_entries WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _run_write_eval() -> EvalResult:
    written = memory.add_research_memory(
        thread_id=RESEARCH_THREAD_ID,
        thread_title="Eval Research Thread",
        question="特斯拉 2024 财报",
        answer=(
            "特斯拉2024年的盈利能力承压，主要受降价策略影响。"
            "毛利率下降，但储能业务增长明显。"
            "公司在自动驾驶投入上继续加码，资本开支保持高位。"
        ),
        mode="research",
        source_message_ts=int(time.time() * 1000),
    )
    row_count = _db_count_for_thread(RESEARCH_THREAD_ID)
    passed = written > 0 and row_count > 0
    return EvalResult(
        name="第一次研究写入",
        passed=passed,
        details=f"written={written}, db_rows={row_count}",
    )


def _run_search_eval() -> EvalResult:
    hits = memory.search_memory(
        "特斯拉 盈利能力 降价 毛利率",
        top_k=3,
        preferred_thread_id=RESEARCH_THREAD_ID,
    )
    top = hits[0] if hits else {}
    semantic_score = float(top.get("semantic_score", 0.0)) if hits else 0.0
    rank_score = float(top.get("rank_score", 0.0)) if hits else 0.0
    content = str(top.get("content", "")) if hits else ""
    passed = bool(hits) and ("降价" in content or "盈利能力" in content) and rank_score >= semantic_score
    return EvalResult(
        name="相关问题检索",
        passed=passed,
        details=(
            f"hit_count={len(hits)}, "
            f"top_semantic={semantic_score:.4f}, "
            f"top_rank={rank_score:.4f}"
        ),
    )


def _run_restart_eval() -> EvalResult:
    stats_before = memory.get_memory_stats()
    reloaded = importlib.reload(memory)
    reloaded.init_memory()
    hits = reloaded.search_memory("特斯拉 盈利能力 降价", top_k=3)
    stats_after = reloaded.get_memory_stats()
    passed = (
        bool(hits)
        and stats_before["entry_count"] == stats_after["entry_count"]
        and stats_before["faiss_count"] == stats_after["faiss_count"]
    )
    return EvalResult(
        name="重启进程恢复",
        passed=passed,
        details=(
            f"before_entries={stats_before['entry_count']}, "
            f"after_entries={stats_after['entry_count']}, "
            f"after_hits={len(hits)}"
        ),
    )


def _run_planner_eval() -> EvalResult:
    written = memory.add_research_memory(
        thread_id=PLANNER_THREAD_ID,
        thread_title="Eval Planner Thread",
        question="比较 OpenAI 和 Anthropic 的 API 策略",
        answer=(
            "规划型调研显示，OpenAI 的平台策略更偏通用工作台，"
            "Anthropic 更强调安全性和企业级协作。"
            "两者在开发者生态和工具调用设计上路径不同。"
        ),
        mode="planner",
        source_message_ts=int(time.time() * 1000),
    )
    hits = memory.search_memory("Anthropic 企业级 协作 安全性", top_k=5)
    planner_hits = [hit for hit in hits if hit.get("mode") == "planner"]
    passed = written > 0 and bool(planner_hits)
    top_mode = planner_hits[0]["mode"] if planner_hits else "none"
    return EvalResult(
        name="Planner 记忆召回",
        passed=passed,
        details=f"written={written}, hit_count={len(hits)}, planner_hits={len(planner_hits)}, top_mode={top_mode}",
    )


def main() -> int:
    print("== Memory Eval ==")
    print(f"DB: {DB_PATH}")
    print(f"Index: {memory.MEMORY_INDEX_PATH}")
    print("")

    memory.init_memory()
    _cleanup_threads([RESEARCH_THREAD_ID, PLANNER_THREAD_ID])

    try:
        results = [
            _run_write_eval(),
            _run_search_eval(),
            _run_restart_eval(),
            _run_planner_eval(),
        ]
    finally:
        _cleanup_threads([RESEARCH_THREAD_ID, PLANNER_THREAD_ID])

    passed = sum(1 for item in results if item.passed)
    for item in results:
        status = "PASS" if item.passed else "FAIL"
        print(f"[{status}] {item.name}: {item.details}")

    print("")
    print(f"Summary: {passed}/{len(results)} scenarios passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
