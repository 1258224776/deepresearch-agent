from __future__ import annotations

import time


def test_set_skill_enabled_persists_to_yaml(tmp_path, monkeypatch):
    from skills import config as skills_config

    config_path = tmp_path / "skills_config.yaml"
    monkeypatch.setattr(skills_config, "get_skills_config_path", lambda: config_path)

    skills_config.save_skills_config(
        {
            "skills": {
                "search": {"enabled": True},
            },
            "profiles": {"react_default": {"allow": ["search"]}},
        }
    )

    skills_config.set_skill_enabled("search", False)
    loaded = skills_config.load_skills_config()

    assert loaded["skills"]["search"]["enabled"] is False
    assert "react_default" in loaded["profiles"]


def test_skill_stats_accumulate_counts_and_duration(tmp_path):
    from skills.stats import get_skill_stats_map, init_skill_stats, record_skill_call

    db_path = tmp_path / "threads.db"
    init_skill_stats(db_path)

    record_skill_call("search", success=True, duration_ms=120, db_path=db_path)
    record_skill_call("search", success=False, duration_ms=80, error="boom", db_path=db_path)

    stats_map = get_skill_stats_map(["search", "scrape"], db_path=db_path)

    assert stats_map["search"]["call_count"] == 2
    assert stats_map["search"]["success_count"] == 1
    assert stats_map["search"]["failure_count"] == 1
    assert stats_map["search"]["total_duration_ms"] == 200
    assert stats_map["search"]["average_duration_ms"] == 100.0
    assert stats_map["search"]["last_status"] == "failure"
    assert stats_map["search"]["last_error"] == "boom"

    assert stats_map["scrape"]["call_count"] == 0
    assert stats_map["scrape"]["last_used_at"] == 0


def test_append_tool_metric_skips_finish(monkeypatch):
    import agent_loop

    tool_metrics: list[dict[str, object]] = []

    agent_loop._append_tool_metric(
        tool_metrics,
        agent_loop.FINISH_TOOL_NAME,
        success=True,
        started_at=time.perf_counter(),
    )

    assert tool_metrics == []


def test_flush_tool_metrics_records_success(monkeypatch):
    import agent_loop

    captured: dict[str, object] = {"entries": None}

    def fake_record_skill_calls(entries):
        captured["entries"] = entries

    monkeypatch.setattr(agent_loop, "record_skill_calls", fake_record_skill_calls)

    tool_metrics: list[dict[str, object]] = []
    agent_loop._append_tool_metric(
        tool_metrics,
        "search",
        success=True,
        started_at=time.perf_counter(),
    )
    agent_loop._flush_tool_metrics(tool_metrics)

    assert captured["entries"] is not None
    assert len(captured["entries"]) == 1
    assert captured["entries"][0]["skill_name"] == "search"
    assert captured["entries"][0]["success"] is True
    assert captured["entries"][0]["duration_ms"] >= 0
    assert captured["entries"][0]["error"] == ""
