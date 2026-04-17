from __future__ import annotations

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
