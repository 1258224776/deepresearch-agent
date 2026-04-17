from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("fastapi")
pytest.importorskip("aiosqlite")
TestClient = pytest.importorskip("fastapi.testclient").TestClient


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        event_name = ""
        data: dict = {}
        for line in chunk.splitlines():
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:].strip())
        if event_name:
            events.append({"event": event_name, "data": data})
    return events


def _wait_for_run_status(client: TestClient, run_id: str, expected: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] == expected:
            return last_payload
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not reach {expected}: {last_payload}")


def _fake_embed_texts(texts: list[str]) -> np.ndarray:
    keywords = [
        "tesla",
        "byd",
        "planner",
        "research",
        "特斯拉",
        "比亚迪",
        "财报",
        "毛利率",
        "营收",
        "销量",
        "规划",
        "研究",
    ]
    vectors: list[np.ndarray] = []
    for text in texts:
        raw = str(text or "")
        lowered = raw.lower()
        values = [float(lowered.count(token.lower())) for token in keywords[:4]]
        values.extend(float(raw.count(token)) for token in keywords[4:])
        if not any(values):
            checksum = sum(ord(ch) for ch in raw)
            values = [1.0, float((checksum % 13) + 1), float((len(raw) % 7) + 1)]
        vector = np.array(values, dtype="float32")
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        vectors.append(vector)
    return np.vstack(vectors).astype("float32")


def _build_fake_run_state(
    *,
    thread_id: str,
    question: str,
    run_id: str = "run-123",
    status: str = "done",
    route_kind: str = "direct_research",
) -> object:
    from run_state import (
        ArtifactRecord,
        CheckpointRecord,
        NodeResult,
        ObservationRecord,
        RunState,
        SourceRecord,
    )

    now = int(time.time() * 1000)
    source_key = "https://example.com/tesla"
    return RunState(
        run_id=run_id,
        thread_id=thread_id,
        question=question,
        route_kind=route_kind,
        status=status,
        current_node="reporter" if status == "done" else "researcher",
        node_order=["coordinator", "researcher", "reporter"],
        node_results={
            "coordinator": NodeResult(
                node_id="coordinator",
                node_type="coordinator",
                status="done",
                summary=f"Resolved route: {route_kind}",
                started_at=now,
                finished_at=now,
            ),
            "researcher": NodeResult(
                node_id="researcher",
                node_type="researcher",
                status="done" if status == "done" else "running",
                summary="Tesla margin fell in 2024.",
                observations=[
                    ObservationRecord(
                        content="Found earnings coverage.",
                        tool="search_web",
                        args={"q": question},
                        source_keys=[source_key],
                    )
                ],
                source_keys=[source_key],
                started_at=now,
                finished_at=now if status == "done" else None,
            ),
            "reporter": NodeResult(
                node_id="reporter",
                node_type="reporter",
                status="done" if status == "done" else "pending",
                summary="Tesla margin fell in 2024." if status == "done" else "",
                artifacts=["final_report"] if status == "done" else [],
                started_at=now if status == "done" else None,
                finished_at=now if status == "done" else None,
            ),
        },
        source_catalog={
            source_key: SourceRecord(
                source_key=source_key,
                url="https://example.com/tesla",
                title="Tesla earnings",
                snippet="Revenue fell.",
                source_type="web",
            )
        },
        artifacts={
            "final_report": ArtifactRecord(
                artifact_id="final_report",
                kind="report",
                title="Final report",
                content="Tesla margin fell in 2024.",
                created_by="reporter",
                created_at=now,
            )
        }
        if status == "done"
        else {},
        context={"engine": "", "max_steps": 8, "use_planner": route_kind == "planned_research"},
        checkpoints=[
            CheckpointRecord(
                checkpoint_id=f"cp-{run_id}-1",
                run_id=run_id,
                node_id="coordinator",
                status="done",
                snapshot_ref=f"inline://runs/{run_id}/nodes/coordinator/1",
                created_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch):
    import api
    import memory

    data_dir = Path("D:/agent-one/tests/.tmp") / f"case-{uuid4().hex}"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "threads.db"

    monkeypatch.setattr(api, "DB_PATH", db_path)
    monkeypatch.setattr(memory, "DATA_DIR", data_dir)
    monkeypatch.setattr(memory, "DB_PATH", db_path)
    monkeypatch.setattr(memory, "MEMORY_INDEX_PATH", data_dir / "memory.faiss")
    monkeypatch.setattr(memory, "MEMORY_IDS_PATH", data_dir / "memory_ids.pkl")
    monkeypatch.setattr(memory, "_initialized", False)
    monkeypatch.setattr(memory, "_index", None)
    monkeypatch.setattr(memory, "_memory_ids", [])
    monkeypatch.setattr(memory, "_embed_texts", _fake_embed_texts)

    with TestClient(api.app) as client:
        yield client, api, memory

    memory._initialized = False
    memory._index = None
    memory._memory_ids = []
    shutil.rmtree(data_dir, ignore_errors=True)


def test_thread_crud_roundtrip(api_client):
    client, _, _ = api_client

    created = client.post("/api/threads", json={"title": "New chat"})
    assert created.status_code == 200
    thread = created.json()
    thread_id = thread["id"]

    listed = client.get("/api/threads?limit=10")
    assert listed.status_code == 200
    assert any(item["id"] == thread_id for item in listed.json())

    renamed = client.patch(f"/api/threads/{thread_id}", json={"title": "Tesla memo"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Tesla memo"

    detail = client.get(f"/api/threads/{thread_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["title"] == "Tesla memo"
    assert payload["messages"] == []


def test_chat_stream_persists_messages(api_client, monkeypatch: pytest.MonkeyPatch):
    client, _, _ = api_client
    thread_id = client.post("/api/threads", json={"title": "New chat"}).json()["id"]

    import agent

    monkeypatch.setattr(agent, "ai_generate_role", lambda *args, **kwargs: "hello back")

    response = client.post(
        f"/api/threads/{thread_id}/chat",
        json={"content": "hi", "engine": ""},
    )
    assert response.status_code == 200

    events = _parse_sse(response.text)
    assert [item["event"] for item in events][:2] == ["message_start", "text_delta"]
    assert events[-2]["event"] == "message_done"
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["content"] == "hello back"

    detail = client.get(f"/api/threads/{thread_id}").json()
    assert [msg["role"] for msg in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][-1]["content"] == "hello back"


def test_research_stream_returns_steps_and_memory_hits(api_client, monkeypatch: pytest.MonkeyPatch):
    client, api, _ = api_client
    thread_id = client.post("/api/threads", json={"title": "New chat"}).json()["id"]

    async def _noop_persist(**kwargs):
        return None

    def fake_run_agent(**kwargs):
        progress = kwargs.get("progress_callback")
        if progress:
            progress("mock progress")
        return {
            "answer": "Tesla margin fell in 2024.",
            "steps": [
                {
                    "thought": "Need the latest earnings.",
                    "tool": "search_web",
                    "args": {"q": "Tesla 2024 earnings"},
                    "observation": "Found earnings coverage.",
                    "sources": [
                        {
                            "url": "https://example.com/tesla",
                            "title": "Tesla earnings",
                            "snippet": "Revenue fell.",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "observations": [
                {
                    "content": "Found earnings coverage.",
                    "tool": "search_web",
                    "args": {"q": "Tesla 2024 earnings"},
                    "sources": [
                        {
                            "url": "https://example.com/tesla",
                            "title": "Tesla earnings",
                            "snippet": "Revenue fell.",
                        }
                    ],
                    "cite_ids": [1],
                }
            ],
            "memory_hits": [
                {
                    "id": "m1",
                    "thread_id": thread_id,
                    "source_message_ts": 0,
                    "kind": "fact",
                    "title": "Tesla margin",
                    "content": "Tesla margin was under pressure.",
                    "mode": "research",
                    "created_at": int(time.time() * 1000),
                    "semantic_score": 0.91,
                    "rank_score": 1.09,
                    "metadata": {"thread_title": "Old Tesla"},
                }
            ],
            "memory_hit_count": 1,
            "step_count": 1,
        }

    monkeypatch.setattr(api, "_persist_memory_after_research", _noop_persist)
    monkeypatch.setattr(api, "run_agent", fake_run_agent)

    response = client.post(
        f"/api/threads/{thread_id}/research",
        json={
            "content": "Analyze Tesla 2024 earnings",
            "engine": "",
            "max_steps": 6,
            "skill_profile": "react_default",
            "use_planner": False,
        },
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    event_types = [item["event"] for item in events]
    assert "progress" in event_types
    assert "step" in event_types
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["memory_hit_count"] == 1
    assert events[-1]["data"]["memory_hits"][0]["title"] == "Tesla margin"

    detail = client.get(f"/api/threads/{thread_id}").json()
    assert detail["messages"][-1]["mode"] == "research"
    assert detail["messages"][-1]["content"] == "Tesla margin fell in 2024."


def test_planner_run_alias_works(api_client, monkeypatch: pytest.MonkeyPatch):
    client, api, _ = api_client
    thread_id = client.post("/api/threads", json={"title": "New chat"}).json()["id"]

    async def _noop_persist(**kwargs):
        return None

    def fake_run_planner_agent(**kwargs):
        progress = kwargs.get("progress_callback")
        if progress:
            progress("识别主问题类型…")
            progress("规划研究方向，拆解子问题…")
        return {
            "answer": "Planner answer.",
            "plan": {
                "reasoning": "Need two sub-questions.",
                "sub_questions": ["Q1", "Q2"],
            },
            "sub_results": [
                {
                    "question": "Q1",
                    "answer": "Sub answer 1",
                    "observations": [
                        {
                            "content": "Observation 1",
                            "tool": "search_web",
                            "args": {},
                            "sources": [],
                            "cite_ids": [],
                        }
                    ],
                    "steps": [],
                    "references": [],
                }
            ],
            "memory_hits": [],
            "memory_hit_count": 0,
            "question_type": "comparison",
            "total_steps": 1,
        }

    monkeypatch.setattr(api, "_persist_memory_after_research", _noop_persist)
    monkeypatch.setattr(api, "run_planner_agent", fake_run_planner_agent)

    response = client.post(
        f"/api/threads/{thread_id}/run",
        json={
            "content": "Compare Tesla and BYD",
            "engine": "",
            "max_steps": 6,
            "skill_profile": "planner",
            "use_planner": True,
        },
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["answer"] == "Planner answer."

    detail = client.get(f"/api/threads/{thread_id}").json()
    assert detail["messages"][-1]["mode"] == "planner"


def test_memory_search_and_delete_cascade(api_client):
    client, _, memory = api_client
    thread = client.post("/api/threads", json={"title": "Tesla thread"}).json()
    thread_id = thread["id"]

    inserted = memory.add_research_memory(
        thread_id=thread_id,
        thread_title="Tesla thread",
        question="Tesla 2024 earnings",
        answer=(
            "Tesla revenue fell in 2024 due to price cuts and margin pressure. "
            "Gross margin remained under pressure as competition intensified. "
            "The company still expects lower-cost models to expand market coverage."
        ),
        mode="research",
        source_message_ts=int(time.time() * 1000),
    )
    assert inserted > 0

    search_response = client.get("/api/memory/search?q=Tesla margin&limit=3")
    assert search_response.status_code == 200
    hits = search_response.json()
    assert hits
    assert hits[0]["thread_id"] == thread_id
    assert "semantic_score" in hits[0]
    assert "rank_score" in hits[0]

    stats_before = client.get("/api/memory/stats").json()
    assert stats_before["entry_count"] > 0

    rebuilt = client.post("/api/memory/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["rebuilt"] >= 1

    deleted = client.delete(f"/api/threads/{thread_id}")
    assert deleted.status_code == 200

    stats_after = client.get("/api/memory/stats").json()
    assert stats_after["entry_count"] == 0

    search_after = client.get("/api/memory/search?q=Tesla margin&limit=3").json()
    assert search_after == []


def test_api_key_auth_is_optional_and_applies_only_to_api_routes(api_client, monkeypatch: pytest.MonkeyPatch):
    client, api, _ = api_client

    monkeypatch.setattr(api, "API_ACCESS_KEY", "secret-key")

    unauthorized = client.get("/api/threads")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["detail"] == "invalid api key"

    health = client.get("/health")
    assert health.status_code == 200

    authorized = client.get("/api/threads", headers={"X-API-Key": "secret-key"})
    assert authorized.status_code == 200


def test_skill_catalog_returns_all_skills(
    api_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    client, api, _ = api_client
    import skills.config as skill_config
    from skills.stats import record_skill_call

    config_path = tmp_path / "skills_config.yaml"
    monkeypatch.setattr(skill_config, "get_skills_config_path", lambda: config_path)
    record_skill_call("search", success=True, duration_ms=12, db_path=api.DB_PATH)

    response = client.get("/skills")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total_skills"] > 0
    assert payload["enabled_skills"] <= payload["total_skills"]
    assert payload["categories"]
    assert payload["profiles"]
    assert all("stats" in item and "call_count" in item["stats"] for item in payload["skills"])

    search_skill = next(item for item in payload["skills"] if item["name"] == "search")
    assert search_skill["stats"]["call_count"] >= 1
    assert "SEARCH_PROVIDERS" in search_skill["env_hints"]


def test_patch_skill_toggles_enabled_state(
    api_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    client, _, _ = api_client
    import skills.config as skill_config

    config_path = tmp_path / "skills_config.yaml"
    monkeypatch.setattr(skill_config, "get_skills_config_path", lambda: config_path)

    disabled = client.patch("/skills/search", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["name"] == "search"
    assert disabled.json()["enabled"] is False

    listed_after_disable = client.get("/skills")
    assert listed_after_disable.status_code == 200
    disabled_search = next(
        item for item in listed_after_disable.json()["skills"] if item["name"] == "search"
    )
    assert disabled_search["enabled"] is False

    enabled = client.patch("/skills/search", json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    listed_after_enable = client.get("/skills")
    assert listed_after_enable.status_code == 200
    enabled_search = next(
        item for item in listed_after_enable.json()["skills"] if item["name"] == "search"
    )
    assert enabled_search["enabled"] is True


def test_graph_run_endpoints_persist_and_expose_state(api_client, monkeypatch: pytest.MonkeyPatch):
    client, api, _ = api_client
    thread_id = client.post("/api/threads", json={"title": "Graph thread"}).json()["id"]

    def fake_run_static_graph(**kwargs):
        state = kwargs["state"]
        return _build_fake_run_state(
            thread_id=state.thread_id,
            question=state.question,
            run_id=state.run_id,
            route_kind="direct_research",
        )

    monkeypatch.setattr(api, "run_static_graph", fake_run_static_graph)

    created = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "Analyze Tesla", "engine": "", "max_steps": 8, "use_planner": False},
    )
    assert created.status_code == 200
    run_payload = created.json()
    assert run_payload["status"] == "running"
    assert run_payload["question"] == "Analyze Tesla"
    run_id = run_payload["run_id"]

    detail_payload = _wait_for_run_status(client, run_id, "done")
    assert detail_payload["artifacts"]["final_report"]["content"] == "Tesla margin fell in 2024."

    listed = client.get(f"/api/threads/{thread_id}/runs")
    assert listed.status_code == 200
    summaries = listed.json()
    assert summaries[0]["run_id"] == run_id

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["node_results"]["researcher"]["summary"] == "Tesla margin fell in 2024."

    nodes = client.get(f"/api/runs/{run_id}/nodes")
    assert nodes.status_code == 200
    assert [item["node_id"] for item in nodes.json()] == ["coordinator", "researcher", "reporter"]

    artifacts = client.get(f"/api/runs/{run_id}/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json()[0]["artifact_id"] == "final_report"

    checkpoints = client.get(f"/api/runs/{run_id}/checkpoints")
    assert checkpoints.status_code == 200
    assert checkpoints.json()[0]["node_id"] == "coordinator"


def test_graph_run_resume_reuses_run_id(api_client, monkeypatch: pytest.MonkeyPatch):
    client, api, _ = api_client
    import run_store

    thread_id = client.post("/api/threads", json={"title": "Resume thread"}).json()["id"]
    pending = _build_fake_run_state(
        thread_id=thread_id,
        question="Resume Tesla run",
        run_id="run-resume-1",
        status="running",
        route_kind="planned_research",
    )
    run_store.save_run_state(api.DB_PATH, pending)

    monkeypatch.setattr(
        api,
        "resume_static_graph",
        lambda state, **kwargs: _build_fake_run_state(
            thread_id=state.thread_id,
            question=state.question,
            run_id=state.run_id,
            status="done",
            route_kind="planned_research",
        ),
    )

    resumed = client.post("/api/runs/run-resume-1/resume")
    assert resumed.status_code == 200
    payload = resumed.json()
    assert payload["run_id"] == "run-resume-1"
    assert payload["status"] == "running"
    assert payload["route_kind"] == "planned_research"

    detail_payload = _wait_for_run_status(client, "run-resume-1", "done")
    assert detail_payload["status"] == "done"


def test_graph_run_background_failure_marks_failed(api_client, monkeypatch: pytest.MonkeyPatch):
    client, api, _ = api_client
    thread_id = client.post("/api/threads", json={"title": "Failure thread"}).json()["id"]

    def fake_run_static_graph(**kwargs):
        state = kwargs["state"]
        state.current_node = "researcher"
        raise RuntimeError("background boom")

    monkeypatch.setattr(api, "run_static_graph", fake_run_static_graph)

    created = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "Fail this run", "engine": "", "max_steps": 8, "use_planner": False},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    detail_payload = _wait_for_run_status(client, run_id, "failed")
    assert detail_payload["context"]["error"] == "background boom"
    assert detail_payload["current_node"] == "researcher"


def test_graph_run_events_stream_snapshots(api_client, monkeypatch: pytest.MonkeyPatch):
    client, api, _ = api_client
    thread_id = client.post("/api/threads", json={"title": "SSE thread"}).json()["id"]
    release_run = threading.Event()

    def fake_run_static_graph(**kwargs):
        state = kwargs["state"]
        release_run.wait(timeout=1.0)
        return _build_fake_run_state(
            thread_id=state.thread_id,
            question=state.question,
            run_id=state.run_id,
            status="done",
            route_kind="direct_research",
        )

    monkeypatch.setattr(api, "run_static_graph", fake_run_static_graph)

    created = client.post(
        f"/api/threads/{thread_id}/runs",
        json={"content": "Stream this run", "engine": "", "max_steps": 8, "use_planner": False},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.status_code == 200
        release_run.set()

        chunks: list[str] = []
        for text in response.iter_text():
            chunks.append(text)
            parsed = _parse_sse("".join(chunks))
            if any(
                item["event"] == "snapshot" and item["data"].get("status") == "done"
                for item in parsed
            ):
                break

    events = _parse_sse("".join(chunks))
    snapshot_events = [item for item in events if item["event"] == "snapshot"]
    assert snapshot_events
    assert snapshot_events[0]["data"]["state"]["run_id"] == run_id
    assert any(item["data"]["status"] == "done" for item in snapshot_events)
