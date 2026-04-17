"""
tests/test_memory.py — Stage 2 Memory 模块完整测试

运行：
    cd d:/agent-one
    pytest tests/test_memory.py -v
    pytest tests/test_memory.py -v --tb=short   # 失败时只打印简短 traceback
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

# ──────────────────────────────────────────────
# 依赖检查（faiss / sentence-transformers 缺失时跳过集成测试）
# ──────────────────────────────────────────────

try:
    import faiss  # noqa: F401
    import sentence_transformers  # noqa: F401
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

requires_deps = pytest.mark.skipif(
    not HAS_DEPS,
    reason="faiss 或 sentence-transformers 未安装",
)

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _patch_and_reset(m, data_dir: Path) -> None:
    """把 memory 模块的所有路径重定向到临时目录，并清空全局状态。"""
    m.DATA_DIR = data_dir
    m.DB_PATH = data_dir / "threads.db"
    m.MEMORY_INDEX_PATH = data_dir / "memory.faiss"
    m.MEMORY_IDS_PATH = data_dir / "memory_ids.pkl"
    m._initialized = False
    m._index = None
    m._memory_ids = []


@pytest.fixture()
def mem(tmp_path):
    """每个测试获得独立路径 + 干净全局状态的 memory 模块。"""
    import memory as m
    _patch_and_reset(m, tmp_path)
    yield m
    _patch_and_reset(m, tmp_path)  # 测试结束后还原，防止污染下一个测试


# ──────────────────────────────────────────────
# 样本数据
# ──────────────────────────────────────────────

TESLA_ANSWER = """
特斯拉2024年第一季度营收213亿美元，同比下降8.7%。这是近年来首次出现同比下滑。

主要压力来自两个方面：一是持续降价侵蚀毛利率，二是市场竞争加剧，尤其是来自比亚迪的压力。

尽管如此，特斯拉的Cybertruck交付量在本季度显著提升，弥补了Model S/X的销量下滑。

展望未来，马斯克表示将在2025年发布更低价格的入门级车型，以扩大市场覆盖范围。
"""

BYD_ANSWER = """
比亚迪2024年实现全年销量302万辆，同比增长41%，首次超越特斯拉成为全球电动车销冠。

比亚迪的核心优势在于垂直整合能力：自研电池、自研芯片、自建供应链，使其成本控制远优于竞争对手。

海外扩张是比亚迪2025年的核心战略，重点市场包括东南亚、欧洲和拉丁美洲。
"""


# ══════════════════════════════════════════════
# 1. 纯函数单元测试（无 IO，无模型）
# ══════════════════════════════════════════════

class TestChunkTitle:
    def test_extracts_first_chinese_sentence(self, mem):
        chunk = "特斯拉2024年毛利率下降。这主要是因为降价。"
        assert mem._chunk_title(chunk) == "特斯拉2024年毛利率下降"

    def test_extracts_first_english_sentence(self, mem):
        chunk = "Tesla revenue fell in 2024. Mainly due to price cuts."
        assert mem._chunk_title(chunk) == "Tesla revenue fell in 2024"

    def test_truncates_to_limit(self, mem):
        chunk = "A" * 100 + "。rest"
        result = mem._chunk_title(chunk, limit=10)
        assert len(result) <= 10

    def test_fallback_when_no_sentence_boundary(self, mem):
        chunk = "NoBoundary"
        result = mem._chunk_title(chunk, limit=5)
        assert len(result) <= 5

    def test_newline_as_boundary(self, mem):
        chunk = "第一行内容\n第二行内容"
        result = mem._chunk_title(chunk)
        assert "第二行" not in result


class TestNormalizeText:
    def test_strips_extra_whitespace(self, mem):
        assert mem._normalize_text("  hello   world  ") == "hello world"

    def test_handles_none(self, mem):
        assert mem._normalize_text(None) == ""

    def test_collapses_newlines(self, mem):
        assert mem._normalize_text("line1\n\nline2") == "line1 line2"

    def test_handles_numbers(self, mem):
        assert mem._normalize_text(42) == "42"


class TestSplitAnswerIntoMemoryItems:
    def test_returns_list(self, mem):
        items = mem._split_answer_into_memory_items(TESLA_ANSWER)
        assert isinstance(items, list)

    def test_non_empty_for_valid_input(self, mem):
        items = mem._split_answer_into_memory_items(TESLA_ANSWER)
        assert len(items) > 0

    def test_filters_short_items(self, mem):
        items = mem._split_answer_into_memory_items("短。")
        assert items == []

    def test_filters_empty_string(self, mem):
        items = mem._split_answer_into_memory_items("")
        assert items == []

    def test_respects_max_facts_limit(self, mem):
        # 生成一个很长的 answer，验证不超过 MEMORY_MAX_FACTS 条
        long_answer = "\n\n".join(
            [f"这是第{i}段内容，包含足够多的文字以通过最小长度过滤器，用于验证上限逻辑是否生效。" * 3
             for i in range(20)]
        )
        items = mem._split_answer_into_memory_items(long_answer)
        assert len(items) <= mem.MEMORY_MAX_FACTS

    def test_each_item_meets_min_length(self, mem):
        items = mem._split_answer_into_memory_items(TESLA_ANSWER)
        for item in items:
            assert len(item) >= mem.MEMORY_ITEM_MIN_LEN


class TestFormatMemoryContext:
    def test_returns_empty_for_no_hits(self, mem):
        assert mem.format_memory_context([]) == ""

    def test_contains_header(self, mem):
        hits = [{"content": "特斯拉毛利率下降", "created_at": int(time.time() * 1000),
                 "metadata": {"thread_title": "财报"}, "thread_id": "t1"}]
        result = mem.format_memory_context(hits)
        assert "Relevant Prior Research" in result

    def test_contains_thread_title(self, mem):
        hits = [{"content": "特斯拉毛利率下降", "created_at": int(time.time() * 1000),
                 "metadata": {"thread_title": "特斯拉财报"}, "thread_id": "t1"}]
        result = mem.format_memory_context(hits)
        assert "特斯拉财报" in result

    def test_contains_content(self, mem):
        hits = [{"content": "特斯拉毛利率下降", "created_at": int(time.time() * 1000),
                 "metadata": {"thread_title": "T"}, "thread_id": "t1"}]
        result = mem.format_memory_context(hits)
        assert "特斯拉毛利率下降" in result

    def test_truncates_long_content(self, mem):
        long_content = "X" * 500
        hits = [{"content": long_content, "created_at": int(time.time() * 1000),
                 "metadata": {"thread_title": "T"}, "thread_id": "t1"}]
        result = mem.format_memory_context(hits, item_limit=50)
        # 结果里不应出现超过 item_limit 长度的连续 X
        assert "X" * 51 not in result

    def test_fallback_to_thread_id_when_no_title(self, mem):
        hits = [{"content": "内容", "created_at": int(time.time() * 1000),
                 "metadata": {}, "thread_id": "my-thread-id"}]
        result = mem.format_memory_context(hits)
        assert "my-thread-id" in result

    def test_multiple_hits_numbered(self, mem):
        ts = int(time.time() * 1000)
        hits = [
            {"content": "内容一", "created_at": ts, "metadata": {"thread_title": "T"}, "thread_id": "t1"},
            {"content": "内容二", "created_at": ts, "metadata": {"thread_title": "T"}, "thread_id": "t2"},
        ]
        result = mem.format_memory_context(hits)
        assert "Memory 1" in result
        assert "Memory 2" in result


# ══════════════════════════════════════════════
# 2. 集成测试（需要 faiss + sentence-transformers）
# ══════════════════════════════════════════════

@requires_deps
class TestInitMemory:
    def test_creates_memory_entries_table(self, mem):
        mem.init_memory()
        conn = sqlite3.connect(str(mem.DB_PATH))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "memory_entries" in tables

    def test_creates_indexes(self, mem):
        mem.init_memory()
        conn = sqlite3.connect(str(mem.DB_PATH))
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        conn.close()
        assert "idx_memory_thread_created" in indexes
        assert "idx_memory_mode_created" in indexes

    def test_sets_initialized_flag(self, mem):
        assert not mem._initialized
        mem.init_memory()
        assert mem._initialized

    def test_idempotent_double_call(self, mem):
        mem.init_memory()
        mem.init_memory()  # 不应报错，不应重复建表
        assert mem._initialized

    def test_is_memory_ready_false_before_data(self, mem):
        mem.init_memory()
        # 空库，index 为 None
        assert not mem.is_memory_ready()


@requires_deps
class TestAddResearchMemory:
    def test_writes_rows_to_sqlite(self, mem):
        mem.init_memory()
        count = mem.add_research_memory(
            thread_id="t1", thread_title="特斯拉财报",
            question="特斯拉2024年财务状况", answer=TESLA_ANSWER,
            mode="research", source_message_ts=int(time.time() * 1000),
        )
        assert count > 0
        conn = sqlite3.connect(str(mem.DB_PATH))
        rows = conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
        conn.close()
        assert rows == count

    def test_updates_faiss_index(self, mem):
        mem.init_memory()
        count = mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        assert mem._index is not None
        assert mem._index.ntotal == count
        assert len(mem._memory_ids) == count

    def test_is_memory_ready_after_add(self, mem):
        mem.init_memory()
        mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        assert mem.is_memory_ready()

    def test_dedup_same_thread_same_content(self, mem):
        mem.init_memory()
        ts = int(time.time() * 1000)
        kwargs = dict(thread_id="t1", thread_title="T", question="Q",
                      answer=TESLA_ANSWER, mode="research", source_message_ts=ts)
        c1 = mem.add_research_memory(**kwargs)
        c2 = mem.add_research_memory(**kwargs)
        assert c1 > 0
        assert c2 == 0  # 完全重复，跳过

    def test_dedup_different_threads_not_deduped(self, mem):
        """不同 thread 的相同内容不应被去重"""
        mem.init_memory()
        ts = int(time.time() * 1000)
        c1 = mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research", source_message_ts=ts,
        )
        c2 = mem.add_research_memory(
            thread_id="t2", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research", source_message_ts=ts,
        )
        assert c1 > 0
        assert c2 > 0  # 不同 thread，允许写入

    def test_empty_answer_returns_zero(self, mem):
        mem.init_memory()
        count = mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer="", mode="research", source_message_ts=int(time.time() * 1000),
        )
        assert count == 0

    def test_too_short_answer_returns_zero(self, mem):
        mem.init_memory()
        count = mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer="太短了。", mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        assert count == 0

    def test_metadata_stored_correctly(self, mem):
        mem.init_memory()
        mem.add_research_memory(
            thread_id="t1", thread_title="特斯拉财报",
            question="特斯拉Q1财务", answer=TESLA_ANSWER,
            mode="research", source_message_ts=int(time.time() * 1000),
        )
        conn = sqlite3.connect(str(mem.DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT metadata FROM memory_entries LIMIT 1").fetchone()
        conn.close()
        meta = json.loads(row["metadata"])
        assert meta["question"] == "特斯拉Q1财务"
        assert meta["thread_title"] == "特斯拉财报"
        assert meta["kind"] == "fact"
        assert "position" in meta

    def test_title_non_empty(self, mem):
        mem.init_memory()
        mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        conn = sqlite3.connect(str(mem.DB_PATH))
        rows = conn.execute("SELECT title FROM memory_entries").fetchall()
        conn.close()
        for row in rows:
            assert row[0] and len(row[0]) > 0


@requires_deps
class TestSearchMemory:
    def _setup_both(self, mem):
        mem.init_memory()
        ts = int(time.time() * 1000)
        mem.add_research_memory(
            thread_id="t-tesla", thread_title="特斯拉财报",
            question="特斯拉2024年财务", answer=TESLA_ANSWER,
            mode="research", source_message_ts=ts,
        )
        mem.add_research_memory(
            thread_id="t-byd", thread_title="比亚迪分析",
            question="比亚迪2024年销量", answer=BYD_ANSWER,
            mode="research", source_message_ts=ts,
        )

    def test_returns_list(self, mem):
        self._setup_both(mem)
        hits = mem.search_memory("特斯拉营收")
        assert isinstance(hits, list)

    def test_returns_relevant_result(self, mem):
        self._setup_both(mem)
        hits = mem.search_memory("特斯拉毛利率下降", top_k=3)
        assert len(hits) > 0
        top_contents = " ".join(h["content"] for h in hits[:2])
        assert "特斯拉" in top_contents

    def test_chinese_query_matches_chinese_content(self, mem):
        self._setup_both(mem)
        hits = mem.search_memory("比亚迪垂直整合优势", top_k=3)
        assert len(hits) > 0
        # top hit 应与比亚迪相关
        assert any("比亚迪" in h["content"] for h in hits[:2])

    def test_empty_when_no_data(self, mem):
        mem.init_memory()
        hits = mem.search_memory("特斯拉")
        assert hits == []

    def test_empty_for_blank_query(self, mem):
        self._setup_both(mem)
        assert mem.search_memory("") == []
        assert mem.search_memory("   ") == []

    def test_respects_top_k(self, mem):
        self._setup_both(mem)
        hits = mem.search_memory("电动车市场竞争", top_k=2)
        assert len(hits) <= 2

    def test_mode_filter_research(self, mem):
        mem.init_memory()
        ts = int(time.time() * 1000)
        mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research", source_message_ts=ts,
        )
        hits = mem.search_memory("特斯拉", mode="research")
        assert len(hits) > 0

    def test_mode_filter_excludes_wrong_mode(self, mem):
        mem.init_memory()
        ts = int(time.time() * 1000)
        mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research", source_message_ts=ts,
        )
        hits = mem.search_memory("特斯拉", mode="planner")
        assert len(hits) == 0  # 数据是 research 模式，planner 过滤后为空

    def test_score_is_float(self, mem):
        self._setup_both(mem)
        hits = mem.search_memory("特斯拉营收")
        for hit in hits:
            assert isinstance(hit["score"], float)

    def test_score_within_cosine_range(self, mem):
        self._setup_both(mem)
        hits = mem.search_memory("特斯拉营收")
        for hit in hits:
            assert -1.0 - 1e-6 <= hit["score"] <= 1.0 + 1e-6

    def test_result_has_required_fields(self, mem):
        self._setup_both(mem)
        hits = mem.search_memory("特斯拉")
        required = {"id", "thread_id", "kind", "title", "content", "mode",
                    "created_at", "score", "metadata"}
        for hit in hits:
            assert required.issubset(hit.keys())


@requires_deps
class TestPersistence:
    def test_survives_state_reset(self, mem):
        """写入后模拟进程重启，重新 init，搜索仍可命中。"""
        mem.init_memory()
        mem.add_research_memory(
            thread_id="t1", thread_title="特斯拉", question="特斯拉",
            answer=TESLA_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        initial_count = len(mem._memory_ids)
        assert initial_count > 0

        # 模拟进程重启
        mem._initialized = False
        mem._index = None
        mem._memory_ids = []

        mem.init_memory()

        assert len(mem._memory_ids) == initial_count
        hits = mem.search_memory("特斯拉营收下滑")
        assert len(hits) > 0

    def test_faiss_file_written_to_disk(self, mem):
        mem.init_memory()
        mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        assert mem.MEMORY_INDEX_PATH.exists()
        assert mem.MEMORY_IDS_PATH.exists()

    def test_rebuild_from_sqlite_when_faiss_deleted(self, mem):
        """删除 FAISS 文件后，init_memory 应从 SQLite 重建索引。"""
        mem.init_memory()
        mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        initial_count = len(mem._memory_ids)

        # 删除 FAISS 文件
        mem.MEMORY_INDEX_PATH.unlink(missing_ok=True)
        mem.MEMORY_IDS_PATH.unlink(missing_ok=True)

        # 重置状态
        mem._initialized = False
        mem._index = None
        mem._memory_ids = []

        mem.init_memory()  # 应触发重建

        assert len(mem._memory_ids) == initial_count
        hits = mem.search_memory("特斯拉")
        assert len(hits) > 0

    def test_atomic_write_no_corrupt_on_save(self, mem):
        """写入使用 tmp → replace，不会留下 .tmp 文件。"""
        mem.init_memory()
        mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        tmp_faiss = mem.MEMORY_INDEX_PATH.with_suffix(".faiss.tmp")
        tmp_pkl = mem.MEMORY_IDS_PATH.with_suffix(".pkl.tmp")
        assert not tmp_faiss.exists()
        assert not tmp_pkl.exists()


@requires_deps
class TestRebuildIndex:
    def test_rebuild_empty_db_returns_zero(self, mem):
        mem.init_memory()
        count = mem.rebuild_memory_index()
        assert count == 0
        assert mem._index is None

    def test_rebuild_matches_sqlite_row_count(self, mem):
        mem.init_memory()
        written = mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        rebuilt = mem.rebuild_memory_index()
        assert rebuilt == written
        assert mem._index.ntotal == rebuilt
        assert len(mem._memory_ids) == rebuilt

    def test_rebuild_ids_consistent_with_index(self, mem):
        """重建后 _memory_ids 数量应与 FAISS ntotal 一致。"""
        mem.init_memory()
        mem.add_research_memory(
            thread_id="t1", thread_title="T", question="Q",
            answer=TESLA_ANSWER + BYD_ANSWER, mode="research",
            source_message_ts=int(time.time() * 1000),
        )
        mem.rebuild_memory_index()
        assert mem._index.ntotal == len(mem._memory_ids)
