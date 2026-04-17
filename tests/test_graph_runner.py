from __future__ import annotations

import json

import pytest

from agent_planner import ResearchPlan
from report import QuestionType
from run_state import NodeResult, ObservationRecord, RunState, SourceRecord


def test_run_static_graph_direct_route(monkeypatch):
    import graph_runner

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)

    def fake_run_agent(**kwargs):
        return {
            "answer": "Draft answer",
            "observations": [
                {
                    "content": "Observation from direct research",
                    "tool": "search_web",
                    "args": {"q": "example"},
                    "sources": [
                        {
                            "url": "https://Example.com/path/?utm_source=ads&b=1#frag",
                            "title": "Example",
                            "snippet": "Example snippet",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "FINAL REPORT")

    state = graph_runner.run_static_graph(
        question="Direct question",
        thread_id="thread-1",
        use_planner=False,
    )

    assert state.route_kind == "direct_research"
    assert state.node_order == ["coordinator", "researcher", "reporter"]
    assert state.status == "done"
    assert "researcher" in state.node_results
    assert state.artifacts["final_report"].content == "FINAL REPORT"
    assert "https://example.com/path?b=1" in state.source_catalog


def test_run_static_graph_planned_route(monkeypatch):
    import graph_runner

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)
    monkeypatch.setattr(graph_runner, "search_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        graph_runner,
        "_plan_research",
        lambda question, engine="": ResearchPlan(
            reasoning="Need two sub-questions.",
            sub_questions=["Sub 1", "Sub 2"],
        ),
    )

    def fake_run_agent(**kwargs):
        question = kwargs["question"]
        if question.rstrip().endswith("Sub 1"):
            source = {
                "url": "https://Example.com/one/?utm_campaign=x",
                "title": "One",
                "snippet": "One snippet",
            }
            answer = "Answer for sub 1"
        else:
            source = {
                "url": "file:///D:/docs/two.md",
                "title": "Two",
                "snippet": "Two snippet",
            }
            answer = "Answer for sub 2"
        return {
            "answer": answer,
            "observations": [
                {
                    "content": answer,
                    "tool": "search_web",
                    "args": {"q": question},
                    "sources": [source],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "PLANNED FINAL REPORT")

    state = graph_runner.run_static_graph(
        question="Planned question",
        thread_id="thread-2",
        use_planner=True,
    )

    assert state.route_kind == "planned_research"
    assert state.node_order == [
        "coordinator",
        "planner",
        "researcher:1",
        "researcher:2",
        "reporter",
    ]
    assert state.context["sub_questions"] == ["Sub 1", "Sub 2"]
    assert state.artifacts["plan"].kind == "plan"
    assert state.artifacts["final_report"].content == "PLANNED FINAL REPORT"
    assert "https://example.com/one" in state.source_catalog
    assert "file:///D:/docs/two.md" in state.source_catalog
    assert state.node_results["researcher:1"].status == "done"
    assert state.node_results["researcher:2"].status == "done"


def test_run_static_graph_direct_route_retries_financial_questions(monkeypatch):
    import graph_runner

    snapshots: list[RunState] = []
    attempts = {"count": 0}

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.FINANCIAL)

    def fake_run_agent(**kwargs):
        attempts["count"] += 1
        if attempts["count"] < 3:
            return {
                "answer": "",
                "observations": [],
                "error": f"temporary failure {attempts['count']}",
            }
        return {
            "answer": "Recovered answer",
            "observations": [
                {
                    "content": "Recovered answer",
                    "tool": "search_web",
                    "args": {"q": kwargs["question"]},
                    "sources": [
                        {
                            "url": "https://example.com/recovered",
                            "title": "Recovered",
                            "snippet": "Recovered snippet",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "FINAL REPORT")

    state = graph_runner.run_static_graph(
        question="Financial question",
        thread_id="thread-retry-financial",
        use_planner=False,
        persist_callback=lambda current: snapshots.append(current.model_copy(deep=True)),
    )

    assert attempts["count"] == 3
    assert state.status == "done"
    assert state.node_results["researcher"].status == "done"
    assert state.context["researcher_retry_counts"]["researcher"] == 2
    assert any(
        snapshot.node_results.get("researcher") is not None
        and snapshot.node_results["researcher"].status == "failed"
        and snapshot.status == "running"
        for snapshot in snapshots
    )


def test_run_static_graph_planned_route_runs_researcher_wave_concurrently(monkeypatch):
    import threading

    import graph_runner

    snapshots: list[RunState] = []
    barrier = threading.Barrier(2)

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)
    monkeypatch.setattr(graph_runner, "search_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        graph_runner,
        "_plan_research",
        lambda question, engine="": ResearchPlan(
            reasoning="Run both sub-questions in parallel.",
            sub_questions=["Sub 1", "Sub 2"],
        ),
    )

    def fake_run_agent(**kwargs):
        question = kwargs["question"]
        barrier.wait(timeout=1.5)
        if question.rstrip().endswith("Sub 1"):
            source = {
                "url": "https://example.com/one",
                "title": "One",
                "snippet": "One snippet",
            }
            answer = "Answer for sub 1"
        else:
            source = {
                "url": "https://example.com/two",
                "title": "Two",
                "snippet": "Two snippet",
            }
            answer = "Answer for sub 2"
        return {
            "answer": answer,
            "observations": [
                {
                    "content": answer,
                    "tool": "search_web",
                    "args": {"q": question},
                    "sources": [source],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "PLANNED FINAL REPORT")

    state = graph_runner.run_static_graph(
        question="Planned question",
        thread_id="thread-2-concurrent",
        use_planner=True,
        persist_callback=lambda current: snapshots.append(current.model_copy(deep=True)),
    )

    assert state.context["research_batches"] == [["researcher:1", "researcher:2"]]
    assert any(
        snapshot.node_results.get("researcher:1") is not None
        and snapshot.node_results["researcher:1"].status == "running"
        and snapshot.node_results.get("researcher:2") is not None
        and snapshot.node_results["researcher:2"].status == "running"
        for snapshot in snapshots
    )
    assert state.node_results["researcher:1"].status == "done"
    assert state.node_results["researcher:2"].status == "done"


def test_run_static_graph_direct_route_exhausts_retry_budget(monkeypatch):
    import graph_runner

    snapshots: list[RunState] = []
    attempts = {"count": 0}

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)

    def fake_run_agent(**kwargs):
        attempts["count"] += 1
        raise RuntimeError("permanent failure")

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "FINAL REPORT")

    with pytest.raises(RuntimeError, match="permanent failure"):
        graph_runner.run_static_graph(
            question="Direct question",
            thread_id="thread-retry-fail",
            use_planner=False,
            persist_callback=lambda current: snapshots.append(current.model_copy(deep=True)),
        )

    assert attempts["count"] == 2
    assert snapshots[-1].status == "failed"
    assert snapshots[-1].node_results["researcher"].status == "failed"
    assert snapshots[-1].context["researcher_retry_counts"]["researcher"] == 2


def test_run_static_graph_persist_callback_tracks_running_nodes(monkeypatch):
    import graph_runner

    snapshots: list[RunState] = []

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)

    def fake_run_agent(**kwargs):
        return {
            "answer": "Draft answer",
            "observations": [
                {
                    "content": "Observation from direct research",
                    "tool": "search_web",
                    "args": {"q": kwargs["question"]},
                    "sources": [
                        {
                            "url": "https://example.com/path",
                            "title": "Example",
                            "snippet": "Example snippet",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "FINAL REPORT")

    state = graph_runner.run_static_graph(
        question="Direct question",
        thread_id="thread-persist",
        use_planner=False,
        persist_callback=lambda current: snapshots.append(current.model_copy(deep=True)),
    )

    assert state.status == "done"
    assert any(snapshot.current_node == "coordinator" and snapshot.node_results["coordinator"].status == "running" for snapshot in snapshots)
    assert any(snapshot.current_node == "researcher" and snapshot.node_results["researcher"].status == "running" for snapshot in snapshots)
    assert any(snapshot.current_node == "reporter" and snapshot.node_results["reporter"].status == "running" for snapshot in snapshots)
    assert snapshots[-1].status == "done"
    assert snapshots[-1].current_node == "reporter"


def test_resume_static_graph_skips_completed_nodes(monkeypatch):
    import graph_runner

    now = 1_700_000_000_000
    state = RunState(
        run_id="run-resume-graph",
        thread_id="thread-3",
        question="Planned resume question",
        route_kind="planned_research",
        status="running",
        current_node="researcher:2",
        node_order=["coordinator", "planner", "researcher:1", "researcher:2", "reporter"],
        node_results={
            "coordinator": NodeResult(
                node_id="coordinator",
                node_type="coordinator",
                status="done",
                summary="Resolved route: planned_research",
                started_at=now,
                finished_at=now,
            ),
            "planner": NodeResult(
                node_id="planner",
                node_type="planner",
                status="done",
                summary="Need two sub-questions.",
                artifacts=["plan"],
                started_at=now,
                finished_at=now,
            ),
            "researcher:1": NodeResult(
                node_id="researcher:1",
                node_type="researcher",
                status="done",
                summary="Answer for sub 1",
                observations=[
                    ObservationRecord(
                        content="Answer for sub 1",
                        tool="search_web",
                        args={"q": "Sub 1"},
                        source_keys=["https://example.com/one"],
                    )
                ],
                source_keys=["https://example.com/one"],
                started_at=now,
                finished_at=now,
            ),
            "researcher:2": NodeResult(
                node_id="researcher:2",
                node_type="researcher",
                status="failed",
                summary="",
                error="network issue",
                started_at=now,
            ),
        },
        source_catalog={
            "https://example.com/one": SourceRecord(
                source_key="https://example.com/one",
                url="https://example.com/one",
                title="One",
                snippet="One snippet",
                source_type="web",
            )
        },
        artifacts={},
        context={
            "question_type": "research",
            "planner_memory_context": "",
            "sub_questions": ["Sub 1", "Sub 2"],
            "sub_questions_by_node": {
                "researcher:1": "Sub 1",
                "researcher:2": "Sub 2",
            },
        },
        checkpoints=[],
        created_at=now,
        updated_at=now,
    )

    monkeypatch.setattr(graph_runner.CoordinatorNode, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("coordinator should be skipped")))
    monkeypatch.setattr(graph_runner.PlannerNode, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("planner should be skipped")))

    def fake_run_agent(**kwargs):
        question = kwargs["question"]
        assert question.rstrip().endswith("Sub 2")
        return {
            "answer": "Answer for sub 2",
            "observations": [
                {
                    "content": "Answer for sub 2",
                    "tool": "search_web",
                    "args": {"q": question},
                    "sources": [
                        {
                            "url": "file:///D:/docs/two.md",
                            "title": "Two",
                            "snippet": "Two snippet",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "RESUMED FINAL REPORT")

    resumed = graph_runner.resume_static_graph(state, engine="", max_steps=8, preferred_thread_id="thread-3")

    assert resumed.run_id == "run-resume-graph"
    assert resumed.node_results["planner"].status == "done"
    assert resumed.node_results["researcher:1"].status == "done"
    assert resumed.node_results["researcher:2"].status == "done"
    assert resumed.node_results["researcher:2"].summary == "Answer for sub 2"
    assert resumed.node_results["reporter"].status == "done"
    assert resumed.artifacts["final_report"].content == "RESUMED FINAL REPORT"


def test_run_static_graph_direct_route_uses_memory_and_writes_back(monkeypatch):
    import graph_runner

    captured: dict[str, object] = {}
    memory_hits = [
        {
            "id": "mem-1",
            "thread_id": "thread-direct",
            "title": "Prior finding",
            "content": "Tesla margin compression was already identified in prior research.",
            "created_at": 1_700_000_000_000,
            "metadata": {
                "thread_title": "Tesla thread",
                "question": "What changed last quarter?",
            },
            "semantic_score": 0.82,
            "rank_score": 0.98,
        }
    ]

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)

    def fake_search_memory(query, top_k=3, mode=None, preferred_thread_id=None):
        captured["search_call"] = {
            "query": query,
            "top_k": top_k,
            "mode": mode,
            "preferred_thread_id": preferred_thread_id,
        }
        return memory_hits

    monkeypatch.setattr(graph_runner, "search_memory", fake_search_memory)
    monkeypatch.setattr(graph_runner, "format_memory_context", lambda hits: "MEMORY CONTEXT")

    def fake_run_agent(**kwargs):
        captured["memory_context"] = kwargs.get("memory_context")
        return {
            "answer": "Draft answer",
            "observations": [
                {
                    "content": "Observation from direct research",
                    "tool": "search_web",
                    "args": {"q": kwargs["question"]},
                    "sources": [
                        {
                            "url": "https://example.com/direct",
                            "title": "Direct source",
                            "snippet": "Direct snippet",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "FINAL REPORT")
    monkeypatch.setattr(
        graph_runner,
        "extract_research_memory_items",
        lambda answer, max_items=5: ["Conclusion 1", "Conclusion 2", "Conclusion 3"],
    )

    def fake_add_research_memory(**kwargs):
        captured["memory_write"] = kwargs
        return len(kwargs["items"])

    monkeypatch.setattr(graph_runner, "add_research_memory", fake_add_research_memory)

    state = graph_runner.run_static_graph(
        question="Direct question",
        thread_id="thread-direct",
        use_planner=False,
    )

    assert captured["search_call"] == {
        "query": "Direct question",
        "top_k": 3,
        "mode": None,
        "preferred_thread_id": "thread-direct",
    }
    assert captured["memory_context"] == "MEMORY CONTEXT"
    assert state.context["run_memory_context"] == "MEMORY CONTEXT"
    assert state.context["memory_hit_count"] == 1
    assert state.context["memory_written_count"] == 3
    assert state.node_results["coordinator"].artifacts == ["memory_hits"]
    assert state.node_results["reporter"].artifacts == ["final_report", "memory_writeback"]

    hits_artifact = json.loads(state.artifacts["memory_hits"].content)
    assert hits_artifact["count"] == 1
    assert hits_artifact["items"][0]["thread_title"] == "Tesla thread"

    write_artifact = json.loads(state.artifacts["memory_writeback"].content)
    assert write_artifact["item_count"] == 3
    assert write_artifact["written_count"] == 3
    assert write_artifact["artifact_id"] == "final_report"

    memory_write = captured["memory_write"]
    assert memory_write["thread_id"] == "thread-direct"
    assert memory_write["mode"] == "research"
    assert memory_write["items"] == ["Conclusion 1", "Conclusion 2", "Conclusion 3"]
    assert memory_write["source_message_ts"] == state.context["final_message_ts"]
    assert memory_write["metadata_extra"]["run_id"] == state.run_id
    assert memory_write["metadata_extra"]["artifact_id"] == "final_report"


def test_run_static_graph_planned_route_reuses_coordinator_memory_hits(monkeypatch):
    import graph_runner

    search_calls: list[tuple[str, str | None]] = []
    researcher_memory_contexts: list[str | None] = []

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)

    def fake_search_memory(query, top_k=3, mode=None, preferred_thread_id=None):
        search_calls.append((query, preferred_thread_id))
        return [
            {
                "id": "mem-1",
                "thread_id": "thread-planned",
                "title": "Prior finding",
                "content": "Previous research already covered the market share trend.",
                "created_at": 1_700_000_000_000,
                "metadata": {"thread_title": "Planned thread"},
                "semantic_score": 0.8,
                "rank_score": 0.96,
            }
        ]

    monkeypatch.setattr(graph_runner, "search_memory", fake_search_memory)
    monkeypatch.setattr(graph_runner, "format_memory_context", lambda hits: "PLANNER MEMORY CONTEXT")
    monkeypatch.setattr(
        graph_runner,
        "_plan_research",
        lambda question, engine="": ResearchPlan(
            reasoning="Break the task into two parts.",
            sub_questions=["Sub 1", "Sub 2"],
        ),
    )

    def fake_run_agent(**kwargs):
        researcher_memory_contexts.append(kwargs.get("memory_context"))
        return {
            "answer": f"Answer for {kwargs['question']}",
            "observations": [
                {
                    "content": f"Answer for {kwargs['question']}",
                    "tool": "search_web",
                    "args": {"q": kwargs["question"]},
                    "sources": [
                        {
                            "url": f"https://example.com/{len(researcher_memory_contexts)}",
                            "title": "Example",
                            "snippet": "Example snippet",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "PLANNED FINAL REPORT")
    monkeypatch.setattr(graph_runner, "extract_research_memory_items", lambda answer, max_items=5: ["Conclusion"])
    monkeypatch.setattr(graph_runner, "add_research_memory", lambda **kwargs: len(kwargs["items"]))

    state = graph_runner.run_static_graph(
        question="Planned question",
        thread_id="thread-planned",
        use_planner=True,
    )

    assert search_calls == [("Planned question", "thread-planned")]
    assert researcher_memory_contexts == ["PLANNER MEMORY CONTEXT", "PLANNER MEMORY CONTEXT"]
    assert state.context["planner_memory_context"] == "PLANNER MEMORY CONTEXT"
    assert state.node_results["planner"].artifacts == ["plan"]
    assert "memory_hits" in state.artifacts


def test_run_static_graph_memory_write_failure_does_not_fail_run(monkeypatch):
    import graph_runner

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)
    monkeypatch.setattr(graph_runner, "search_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(graph_runner, "format_memory_context", lambda hits: "")
    monkeypatch.setattr(
        graph_runner,
        "run_agent",
        lambda **kwargs: {
            "answer": "Draft answer",
            "observations": [],
            "error": None,
        },
    )
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "FINAL REPORT")
    monkeypatch.setattr(graph_runner, "extract_research_memory_items", lambda answer, max_items=5: ["Conclusion"])
    monkeypatch.setattr(
        graph_runner,
        "add_research_memory",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("memory store unavailable")),
    )

    state = graph_runner.run_static_graph(
        question="Direct question",
        thread_id="thread-memory-failure",
        use_planner=False,
    )

    assert state.status == "done"
    assert state.context["memory_written_count"] == 0
    assert state.context["memory_writeback_error"] == "memory store unavailable"
    write_artifact = json.loads(state.artifacts["memory_writeback"].content)
    assert write_artifact["error"] == "memory store unavailable"


def test_run_static_graph_direct_route_empty_memory_searches_once(monkeypatch):
    import graph_runner

    calls = {"search": 0}

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.RESEARCH)

    def fake_search_memory(*args, **kwargs):
        calls["search"] += 1
        return []

    monkeypatch.setattr(graph_runner, "search_memory", fake_search_memory)
    monkeypatch.setattr(graph_runner, "format_memory_context", lambda hits: "")
    monkeypatch.setattr(
        graph_runner,
        "run_agent",
        lambda **kwargs: {
            "answer": "Draft answer",
            "observations": [],
            "error": None,
        },
    )
    monkeypatch.setattr(graph_runner, "compose_report", lambda *args, **kwargs: "FINAL REPORT")
    monkeypatch.setattr(graph_runner, "extract_research_memory_items", lambda answer, max_items=5: ["Conclusion"])
    monkeypatch.setattr(graph_runner, "add_research_memory", lambda **kwargs: len(kwargs["items"]))

    state = graph_runner.run_static_graph(
        question="Direct question",
        thread_id="thread-empty-memory",
        use_planner=False,
    )

    assert state.status == "done"
    assert state.context["memory_search_done"] is True
    assert state.context["memory_hits"] == []
    assert calls["search"] == 1


def test_run_static_graph_code_route_runs_coder_node(monkeypatch):
    import graph_runner
    from sandbox_runner import SandboxArtifactResult, SandboxExecutionResult

    captured: dict[str, object] = {}

    monkeypatch.setattr(graph_runner, "classify_question", lambda question, engine="": QuestionType.TREND)
    monkeypatch.setattr(graph_runner, "search_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(graph_runner, "format_memory_context", lambda hits: "")

    def fake_run_agent(**kwargs):
        return {
            "answer": "Tesla revenue climbed from 2020 to 2024.",
            "observations": [
                {
                    "content": "Revenue data points: 2020=31.5, 2021=53.8, 2022=81.5, 2023=96.8, 2024=97.7",
                    "tool": "search_web",
                    "args": {"q": kwargs["question"]},
                    "sources": [
                        {
                            "url": "https://example.com/tesla-revenue",
                            "title": "Tesla revenue history",
                            "snippet": "Annual revenue points by year.",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(graph_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(
        graph_runner,
        "_generate_coder_plan",
        lambda state, engine="": graph_runner.CoderPlan(
            summary="Create a revenue trend chart.",
            python_code="print('sandbox ready')",
        ),
    )
    monkeypatch.setattr(
        graph_runner,
        "run_coder_sandbox",
        lambda **kwargs: SandboxExecutionResult(
            summary="The generated chart shows steady revenue growth through 2024.",
            artifacts=[
                SandboxArtifactResult(
                    artifact_id="code_analysis",
                    kind="text_markdown",
                    title="Code analysis",
                    content="# Revenue trend\n\nTesla revenue rose strongly over the period.",
                ),
                SandboxArtifactResult(
                    artifact_id="code_chart",
                    kind="image_png",
                    title="Revenue chart",
                    content="data:image/png;base64,ZmFrZQ==",
                ),
            ],
        ),
    )

    def fake_compose_report(question, observations, registry, **kwargs):
        captured["observations"] = observations
        return "CODE FINAL REPORT"

    monkeypatch.setattr(graph_runner, "compose_report", fake_compose_report)
    monkeypatch.setattr(graph_runner, "extract_research_memory_items", lambda answer, max_items=5: ["Conclusion"])
    monkeypatch.setattr(graph_runner, "add_research_memory", lambda **kwargs: len(kwargs["items"]))

    state = graph_runner.run_static_graph(
        question="Plot Tesla revenue trend as a chart",
        thread_id="thread-code",
        use_planner=False,
    )

    assert state.route_kind == "code_research"
    assert state.node_order == ["coordinator", "researcher", "coder", "reporter"]
    assert state.node_results["coder"].status == "done"
    assert state.node_results["coder"].artifacts == ["coder_script", "code_analysis", "code_chart"]
    assert state.artifacts["coder_script"].kind == "code_python"
    assert state.artifacts["code_analysis"].kind == "text_markdown"
    assert state.artifacts["code_chart"].kind == "image_png"
    assert any(observation.tool == "python_sandbox" for observation in captured["observations"])
