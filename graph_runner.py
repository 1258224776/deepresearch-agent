"""
Static graph runner for Stage D v1.

This module wraps the existing research stack into a graph-shaped execution
model with serializable run state. The first version intentionally uses a
fixed topology and project-local orchestration instead of a dynamic scheduler.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import json
import time
import uuid
from typing import Callable
from urllib.parse import unquote, urlsplit

from agent_loop import run_agent
from agent_planner import _plan_research
from memory import format_memory_context, search_memory
from report import CitationRegistry, Observation, QuestionType, Source, classify_question, compose_report
from run_state import (
    ArtifactRecord,
    CheckpointRecord,
    NodeResult,
    ObservationRecord,
    RunState,
    SourceRecord,
    source_key_for_file,
    source_key_for_rag_chunk,
    source_key_for_url,
)

ProgressCallback = Callable[[str], None]
PersistCallback = Callable[[RunState], None]
ResearcherExecutionResult = tuple[NodeResult, dict[str, SourceRecord]]

COORDINATOR_NODE_ID = "coordinator"
PLANNER_NODE_ID = "planner"
REPORTER_NODE_ID = "reporter"
FINAL_REPORT_ARTIFACT_ID = "final_report"
PLAN_ARTIFACT_ID = "plan"
COMPLETED_NODE_STATUSES = {"done", "skipped"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback:
        progress_callback(message)


def _source_key_from_source_url(source_url: str) -> str:
    text = str(source_url or "").strip()
    if not text:
        raise ValueError("source url is required")

    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()

    if scheme in ("http", "https"):
        return source_key_for_url(text)

    if scheme == "file":
        raw_path = unquote(parsed.path or "")
        if raw_path.startswith("/") and len(raw_path) >= 4 and raw_path[2] == ":":
            raw_path = raw_path[1:]
        if parsed.netloc:
            raw_path = f"//{parsed.netloc}{raw_path}"
        return source_key_for_file(raw_path)

    if scheme == "rag":
        collection = parsed.netloc
        doc_name = unquote(parsed.path.lstrip("/"))
        return source_key_for_rag_chunk(collection, doc_name)

    return text.rstrip("/")


def _source_type_from_url(source_url: str) -> str:
    scheme = urlsplit(str(source_url or "").strip()).scheme.lower()
    if scheme in ("http", "https"):
        return "web"
    if scheme == "file":
        return "file"
    if scheme == "rag":
        return "rag"
    return "api" if scheme else ""


def _checkpoint_ref(state: RunState, node_id: str) -> str:
    return f"inline://runs/{state.run_id}/nodes/{node_id}/{len(state.checkpoints) + 1}"


def _append_checkpoint(state: RunState, node_id: str, status: str) -> None:
    checkpoint = CheckpointRecord(
        checkpoint_id=uuid.uuid4().hex,
        run_id=state.run_id,
        node_id=node_id,
        status=status,
        snapshot_ref=_checkpoint_ref(state, node_id),
        created_at=_now_ms(),
    )
    state.checkpoints.append(checkpoint)
    state.updated_at = checkpoint.created_at


def _set_node_result(state: RunState, result: NodeResult) -> None:
    state.node_results[result.node_id] = result
    state.current_node = result.node_id
    state.updated_at = _now_ms()


def _persist_state(state: RunState, persist_callback: PersistCallback | None = None) -> None:
    if persist_callback:
        persist_callback(state)


def _mark_node_running(state: RunState, *, node_id: str, node_type: str) -> None:
    now = _now_ms()
    state.node_results[node_id] = NodeResult(
        node_id=node_id,
        node_type=node_type,
        status="running",
        started_at=now,
    )
    state.current_node = node_id
    state.status = "running"
    state.updated_at = now


def _mark_node_failed(
    state: RunState,
    *,
    node_id: str,
    error: str,
    terminal: bool = True,
    result: NodeResult | None = None,
    source_catalog: dict[str, SourceRecord] | None = None,
) -> None:
    now = result.finished_at or _now_ms() if result is not None else _now_ms()
    if source_catalog:
        _merge_source_catalog(state.source_catalog, source_catalog)

    existing = result.model_copy(deep=True) if result is not None else state.node_results.get(node_id)
    if existing is None:
        existing = NodeResult(node_id=node_id, node_type="", status="failed")
    existing.status = "failed"
    existing.error = error
    existing.finished_at = existing.finished_at or now
    state.node_results[node_id] = existing
    state.current_node = node_id
    state.status = "failed" if terminal else "running"
    state.updated_at = now


def _merge_source_catalog(
    target_catalog: dict[str, SourceRecord],
    source_catalog: dict[str, SourceRecord],
) -> None:
    for source_key, source_record in source_catalog.items():
        existing = target_catalog.get(source_key)
        if existing is None:
            target_catalog[source_key] = source_record
            continue
        if not existing.title and source_record.title:
            existing.title = source_record.title
        if not existing.snippet and source_record.snippet:
            existing.snippet = source_record.snippet
        if not existing.source_type and source_record.source_type:
            existing.source_type = source_record.source_type


def _source_records_from_sources(sources: list[Source]) -> tuple[list[str], dict[str, SourceRecord]]:
    source_keys: list[str] = []
    source_catalog: dict[str, SourceRecord] = {}
    for source in sources:
        if not source.url:
            continue
        key = _source_key_from_source_url(source.url)
        source_keys.append(key)
        existing = source_catalog.get(key)
        if existing is None:
            source_catalog[key] = SourceRecord(
                source_key=key,
                url=source.url,
                title=source.title,
                snippet=source.snippet,
                source_type=_source_type_from_url(source.url),
                metadata={},
            )
            continue
        if not existing.title and source.title:
            existing.title = source.title
        if not existing.snippet and source.snippet:
            existing.snippet = source.snippet
    return source_keys, source_catalog


def _observation_record_from_observation(
    observation: Observation,
) -> tuple[ObservationRecord, dict[str, SourceRecord]]:
    source_keys, source_catalog = _source_records_from_sources(list(observation.sources))
    return ObservationRecord(
        content=observation.content,
        tool=observation.tool,
        args=dict(observation.args),
        source_keys=source_keys,
    ), source_catalog


def _question_type_from_state(state: RunState) -> QuestionType | None:
    raw = str(state.context.get("question_type", "") or "").strip().lower()
    if not raw:
        return None
    try:
        return QuestionType(raw)
    except ValueError:
        return None


def _researcher_retry_budget(question_type: QuestionType | None) -> int:
    if question_type in {QuestionType.FINANCIAL, QuestionType.COMPARE}:
        return 2
    return 1


def _record_researcher_retry_count(state: RunState, node_id: str, retry_count: int) -> None:
    retry_counts = state.context.get("researcher_retry_counts")
    if not isinstance(retry_counts, dict):
        retry_counts = {}
        state.context["researcher_retry_counts"] = retry_counts
    retry_counts[node_id] = retry_count


def _completed_researcher_nodes(state: RunState) -> list[NodeResult]:
    ordered: list[NodeResult] = []
    for node_id in state.node_order:
        result = state.node_results.get(node_id)
        if result and result.node_type == "researcher" and result.status == "done":
            ordered.append(result)
    return ordered


def _planner_findings_context(state: RunState) -> str:
    sub_questions = state.context.get("sub_questions_by_node", {})
    if not isinstance(sub_questions, dict):
        sub_questions = {}

    lines: list[str] = []
    for result in _completed_researcher_nodes(state):
        sub_q = str(sub_questions.get(result.node_id, result.node_id)).strip()
        summary = str(result.summary or "").strip()
        if not sub_q or not summary:
            continue
        snippet = summary[:400]
        if len(summary) > 400:
            snippet += " ..."
        lines.append(f"### {sub_q}")
        lines.append(snippet)
        lines.append("")
    if not lines:
        return ""
    return "## Completed sub-question findings\n\n" + "\n".join(lines).strip()


def _researcher_node_batches(state: RunState) -> list[list[str]]:
    sub_questions = state.context.get("sub_questions_by_node", {})
    if not isinstance(sub_questions, dict):
        sub_questions = {}

    ordered_researcher_nodes = [node_id for node_id in state.node_order if node_id in sub_questions]
    raw_batches = state.context.get("research_batches", [])

    parsed_batches: list[list[str]] = []
    seen: set[str] = set()
    if isinstance(raw_batches, list):
        for raw_batch in raw_batches:
            if not isinstance(raw_batch, list):
                continue
            batch: list[str] = []
            for raw_node_id in raw_batch:
                node_id = str(raw_node_id or "").strip()
                if not node_id or node_id in seen or node_id not in sub_questions:
                    continue
                seen.add(node_id)
                batch.append(node_id)
            if batch:
                parsed_batches.append(batch)

    missing_nodes = [node_id for node_id in ordered_researcher_nodes if node_id not in seen]
    if parsed_batches:
        parsed_batches.extend([[node_id] for node_id in missing_nodes])
        return parsed_batches

    return [[node_id] for node_id in ordered_researcher_nodes]


def _collect_observations_for_report(state: RunState) -> list[Observation]:
    observations: list[Observation] = []

    for node in _completed_researcher_nodes(state):
        for record in node.observations:
            sources: list[Source] = []
            for source_key in record.source_keys:
                source_record = state.source_catalog.get(source_key)
                if not source_record:
                    continue
                sources.append(
                    Source(
                        url=source_record.url,
                        title=source_record.title,
                        snippet=source_record.snippet,
                    )
                )
            observations.append(
                Observation(
                    content=record.content,
                    tool=record.tool,
                    args=dict(record.args),
                    sources=sources,
                    cite_ids=[],
                )
            )

    return observations


def _node_is_completed(state: RunState, node_id: str) -> bool:
    result = state.node_results.get(node_id)
    return result is not None and result.status in COMPLETED_NODE_STATUSES


def _run_node(
    state: RunState,
    *,
    node_id: str,
    node_type: str,
    runner,
    progress_callback: ProgressCallback | None = None,
    persist_callback: PersistCallback | None = None,
) -> None:
    _mark_node_running(state, node_id=node_id, node_type=node_type)
    _persist_state(state, persist_callback)
    try:
        runner.run(state, progress_callback)
    except Exception as exc:
        _mark_node_failed(state, node_id=node_id, error=str(exc))
        _persist_state(state, persist_callback)
        raise
    _persist_state(state, persist_callback)


def _merge_researcher_result(
    state: RunState,
    *,
    node_result: NodeResult,
    source_catalog: dict[str, SourceRecord],
) -> None:
    _merge_source_catalog(state.source_catalog, source_catalog)
    _set_node_result(state, node_result)
    _append_checkpoint(state, node_result.node_id, node_result.status)


class CoordinatorNode:
    node_id = COORDINATOR_NODE_ID
    node_type = "coordinator"

    def __init__(self, *, use_planner: bool, engine: str) -> None:
        self._use_planner = use_planner
        self._engine = engine

    def run(self, state: RunState, progress_callback: ProgressCallback | None = None) -> None:
        started_at = _now_ms()
        route_kind = "planned_research" if self._use_planner else "direct_research"
        qtype = classify_question(state.question, self._engine)

        state.route_kind = route_kind
        state.node_order = [COORDINATOR_NODE_ID]
        state.context["question_type"] = qtype.value

        if self._use_planner:
            state.node_order.extend([PLANNER_NODE_ID, REPORTER_NODE_ID])
        else:
            state.node_order.extend(["researcher", REPORTER_NODE_ID])

        _emit(progress_callback, f"graph route -> {route_kind}")
        result = NodeResult(
            node_id=self.node_id,
            node_type=self.node_type,
            status="done",
            summary=f"Resolved route: {route_kind}",
            started_at=started_at,
            finished_at=_now_ms(),
        )
        _set_node_result(state, result)
        _append_checkpoint(state, self.node_id, result.status)


class PlannerNode:
    node_id = PLANNER_NODE_ID
    node_type = "planner"

    def __init__(self, *, engine: str, preferred_thread_id: str | None = None) -> None:
        self._engine = engine
        self._preferred_thread_id = preferred_thread_id

    def run(self, state: RunState, progress_callback: ProgressCallback | None = None) -> None:
        started_at = _now_ms()
        _emit(progress_callback, "planner -> building plan")

        memory_hits = search_memory(
            state.question,
            top_k=3,
            preferred_thread_id=self._preferred_thread_id,
        )
        memory_context = format_memory_context(memory_hits)
        planning_question = state.question
        if memory_context:
            planning_question = f"{memory_context}\n\n## Current research task\n{state.question}"

        plan = _plan_research(planning_question, self._engine)
        state.context["planner_memory_context"] = memory_context
        state.context["memory_hits"] = memory_hits
        state.context["memory_hit_count"] = len(memory_hits)
        state.context["plan_reasoning"] = plan.reasoning
        state.context["sub_questions"] = list(plan.sub_questions)

        sub_question_map: dict[str, str] = {}
        reporter_index = state.node_order.index(REPORTER_NODE_ID)
        new_researcher_ids: list[str] = []
        for index, sub_q in enumerate(plan.sub_questions, 1):
            node_id = f"researcher:{index}"
            new_researcher_ids.append(node_id)
            sub_question_map[node_id] = sub_q
        state.context["sub_questions_by_node"] = sub_question_map
        state.context["research_batches"] = [list(new_researcher_ids)] if new_researcher_ids else []
        state.node_order = (
            state.node_order[:reporter_index]
            + new_researcher_ids
            + state.node_order[reporter_index:]
        )

        artifact = ArtifactRecord(
            artifact_id=PLAN_ARTIFACT_ID,
            kind="plan",
            title="Research plan",
            content=json.dumps(plan.model_dump(), ensure_ascii=False),
            created_by=self.node_id,
            created_at=_now_ms(),
        )
        state.artifacts[artifact.artifact_id] = artifact

        result = NodeResult(
            node_id=self.node_id,
            node_type=self.node_type,
            status="done",
            summary=plan.reasoning,
            artifacts=[artifact.artifact_id],
            started_at=started_at,
            finished_at=_now_ms(),
        )
        _set_node_result(state, result)
        _append_checkpoint(state, self.node_id, result.status)


class ResearcherNode:
    node_type = "researcher"

    def __init__(
        self,
        *,
        node_id: str,
        engine: str,
        max_steps: int,
        max_retries: int = 1,
        preferred_thread_id: str | None = None,
        skill_profile: str = "react_default",
    ) -> None:
        self.node_id = node_id
        self._engine = engine
        self._max_steps = max_steps
        self.max_retries = max(0, int(max_retries))
        self._preferred_thread_id = preferred_thread_id
        self._skill_profile = skill_profile

    def _resolve_question(self, state: RunState) -> tuple[str, str]:
        sub_questions = state.context.get("sub_questions_by_node", {})
        sub_q = str(sub_questions.get(self.node_id, "")).strip()
        planner_context = str(state.context.get("planner_memory_context", "") or "").strip()
        findings_context = _planner_findings_context(state)

        question = sub_q
        if findings_context:
            question = f"{findings_context}\n\n## Current sub-question\n{sub_q}"
        return question, planner_context

    def build_request(self, state: RunState) -> tuple[str, str | None, QuestionType | None]:
        if self.node_id == "researcher":
            question = state.question
            memory_context = None
        else:
            question, memory_context = self._resolve_question(state)

        return question, memory_context, _question_type_from_state(state)

    def run_isolated(
        self,
        *,
        question: str,
        memory_context: str | None,
        question_type: QuestionType | None,
        progress_callback: ProgressCallback | None = None,
    ) -> ResearcherExecutionResult:
        started_at = _now_ms()
        _emit(progress_callback, f"{self.node_id} -> researching")

        result = run_agent(
            question=question,
            engine=self._engine,
            max_steps=self._max_steps,
            progress_callback=progress_callback,
            compose=False,
            question_type=question_type,
            skill_profile=self._skill_profile,
            memory_context=memory_context,
            preferred_thread_id=self._preferred_thread_id,
        )

        local_sources: dict[str, SourceRecord] = {}
        observations = [
            _observation_record_from_observation(Observation(**item))
            for item in result.get("observations", [])
        ]
        observation_records: list[ObservationRecord] = []
        for observation_record, source_catalog in observations:
            observation_records.append(observation_record)
            _merge_source_catalog(local_sources, source_catalog)
        source_keys = sorted({key for item in observation_records for key in item.source_keys})
        node_result = NodeResult(
            node_id=self.node_id,
            node_type=self.node_type,
            status="failed" if result.get("error") else "done",
            summary=str(result.get("answer", "") or "").strip(),
            observations=observation_records,
            source_keys=source_keys,
            error=result.get("error"),
            started_at=started_at,
            finished_at=_now_ms(),
        )
        return node_result, local_sources

    def run(self, state: RunState, progress_callback: ProgressCallback | None = None) -> None:
        question, memory_context, question_type = self.build_request(state)
        node_result, local_sources = self.run_isolated(
            question=question,
            memory_context=memory_context,
            question_type=question_type,
            progress_callback=progress_callback,
        )
        _merge_researcher_result(
            state,
            node_result=node_result,
            source_catalog=local_sources,
        )


def _run_researcher_wave(
    state: RunState,
    *,
    researchers: list[ResearcherNode],
    progress_callback: ProgressCallback | None = None,
    persist_callback: PersistCallback | None = None,
) -> None:
    if not researchers:
        return

    requests: dict[str, tuple[str, str | None, QuestionType | None]] = {}
    researcher_map = {researcher.node_id: researcher for researcher in researchers}
    pending_node_ids = list(researcher_map)
    attempts: dict[str, int] = {node_id: 0 for node_id in researcher_map}

    for researcher in researchers:
        requests[researcher.node_id] = researcher.build_request(state)

    first_exception: Exception | None = None
    first_failed_node_id: str | None = None

    while pending_node_ids:
        current_wave = [researcher_map[node_id] for node_id in pending_node_ids]
        pending_node_ids = []

        for researcher in current_wave:
            if attempts[researcher.node_id] > 0:
                _emit(
                    progress_callback,
                    f"{researcher.node_id} -> retrying ({attempts[researcher.node_id]}/{researcher.max_retries})",
                )
            _mark_node_running(state, node_id=researcher.node_id, node_type=researcher.node_type)
            _persist_state(state, persist_callback)

        with ThreadPoolExecutor(max_workers=max(1, len(current_wave))) as executor:
            future_to_node_id: dict[Future[ResearcherExecutionResult], str] = {}
            for researcher in current_wave:
                question, memory_context, question_type = requests[researcher.node_id]
                worker_progress = None
                if progress_callback:
                    worker_progress = lambda message, node_id=researcher.node_id: _emit(progress_callback, f"[{node_id}] {message}")
                future = executor.submit(
                    researcher.run_isolated,
                    question=question,
                    memory_context=memory_context,
                    question_type=question_type,
                    progress_callback=worker_progress,
                )
                future_to_node_id[future] = researcher.node_id

            for future in as_completed(future_to_node_id):
                node_id = future_to_node_id[future]
                researcher = researcher_map[node_id]

                try:
                    node_result, source_catalog = future.result()
                except Exception as exc:
                    attempts[node_id] += 1
                    _record_researcher_retry_count(state, node_id, attempts[node_id])
                    terminal = attempts[node_id] > researcher.max_retries
                    _mark_node_failed(
                        state,
                        node_id=node_id,
                        error=str(exc),
                        terminal=terminal,
                    )
                    _append_checkpoint(state, node_id, "failed")
                    _persist_state(state, persist_callback)
                    if terminal:
                        if first_exception is None:
                            first_exception = exc
                            first_failed_node_id = node_id
                    else:
                        pending_node_ids.append(node_id)
                        _emit(progress_callback, f"{node_id} -> retry scheduled after error: {exc}")
                    continue

                if node_result.status == "failed":
                    error_text = str(node_result.error or f"{node_id} failed")
                    attempts[node_id] += 1
                    _record_researcher_retry_count(state, node_id, attempts[node_id])
                    terminal = attempts[node_id] > researcher.max_retries
                    _mark_node_failed(
                        state,
                        node_id=node_id,
                        error=error_text,
                        terminal=terminal,
                        result=node_result,
                        source_catalog=source_catalog,
                    )
                    _append_checkpoint(state, node_id, "failed")
                    _persist_state(state, persist_callback)
                    if terminal:
                        if first_exception is None:
                            first_exception = RuntimeError(error_text)
                            first_failed_node_id = node_id
                    else:
                        pending_node_ids.append(node_id)
                        _emit(progress_callback, f"{node_id} -> retry scheduled after error: {error_text}")
                    continue

                _merge_researcher_result(
                    state,
                    node_result=node_result,
                    source_catalog=source_catalog,
                )
                _persist_state(state, persist_callback)

        if first_exception is not None:
            break

    if first_exception is not None and first_failed_node_id is not None:
        raise first_exception


class ReporterNode:
    node_id = REPORTER_NODE_ID
    node_type = "reporter"

    def __init__(self, *, engine: str) -> None:
        self._engine = engine

    def run(self, state: RunState, progress_callback: ProgressCallback | None = None) -> None:
        started_at = _now_ms()
        _emit(progress_callback, "reporter -> composing final report")

        observations = _collect_observations_for_report(state)
        registry = CitationRegistry()
        rebuilt_observations: list[Observation] = []
        for observation in observations:
            cite_ids = registry.add_many(observation.sources)
            rebuilt_observations.append(
                Observation(
                    content=observation.content,
                    tool=observation.tool,
                    args=dict(observation.args),
                    sources=list(observation.sources),
                    cite_ids=cite_ids,
                )
            )

        final_report = compose_report(
            state.question,
            rebuilt_observations,
            registry,
            engine=self._engine,
            question_type=_question_type_from_state(state),
        )
        artifact = ArtifactRecord(
            artifact_id=FINAL_REPORT_ARTIFACT_ID,
            kind="report",
            title="Final report",
            content=final_report,
            created_by=self.node_id,
            created_at=_now_ms(),
        )
        state.artifacts[artifact.artifact_id] = artifact

        result = NodeResult(
            node_id=self.node_id,
            node_type=self.node_type,
            status="done",
            summary=final_report[:500],
            artifacts=[artifact.artifact_id],
            started_at=started_at,
            finished_at=_now_ms(),
        )
        _set_node_result(state, result)
        _append_checkpoint(state, self.node_id, result.status)
        state.status = "done"


def create_run_state(
    *,
    question: str,
    thread_id: str,
    route_kind: str = "",
    run_id: str | None = None,
) -> RunState:
    now = _now_ms()
    return RunState(
        run_id=run_id or uuid.uuid4().hex,
        thread_id=thread_id,
        question=question,
        route_kind=route_kind,
        status="running",
        created_at=now,
        updated_at=now,
    )


def _execute_static_graph(
    state: RunState,
    *,
    engine: str = "",
    use_planner: bool = False,
    max_steps: int = 8,
    preferred_thread_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
    persist_callback: PersistCallback | None = None,
) -> RunState:
    state.status = "running"
    state.updated_at = _now_ms()
    _persist_state(state, persist_callback)

    if not _node_is_completed(state, COORDINATOR_NODE_ID) or not state.node_order:
        coordinator = CoordinatorNode(use_planner=use_planner, engine=engine)
        _run_node(
            state,
            node_id=COORDINATOR_NODE_ID,
            node_type=coordinator.node_type,
            runner=coordinator,
            progress_callback=progress_callback,
            persist_callback=persist_callback,
        )

    if state.route_kind == "planned_research":
        researcher_retry_budget = _researcher_retry_budget(_question_type_from_state(state))
        if not _node_is_completed(state, PLANNER_NODE_ID):
            planner = PlannerNode(engine=engine, preferred_thread_id=preferred_thread_id)
            _run_node(
                state,
                node_id=PLANNER_NODE_ID,
                node_type=planner.node_type,
                runner=planner,
                progress_callback=progress_callback,
                persist_callback=persist_callback,
            )

        sub_question_map = state.context.get("sub_questions_by_node", {})
        for wave in _researcher_node_batches(state):
            pending_node_ids = [
                node_id
                for node_id in wave
                if node_id in sub_question_map and not _node_is_completed(state, node_id)
            ]
            if not pending_node_ids:
                continue
            researchers = [
                ResearcherNode(
                    node_id=node_id,
                    engine=engine,
                    max_steps=min(max_steps, 4),
                    max_retries=researcher_retry_budget,
                    preferred_thread_id=preferred_thread_id,
                    skill_profile="planner",
                )
                for node_id in pending_node_ids
            ]
            _run_researcher_wave(
                state,
                researchers=researchers,
                progress_callback=progress_callback,
                persist_callback=persist_callback,
            )
    else:
        if not _node_is_completed(state, "researcher"):
            researcher = ResearcherNode(
                node_id="researcher",
                engine=engine,
                max_steps=max_steps,
                max_retries=_researcher_retry_budget(_question_type_from_state(state)),
                preferred_thread_id=preferred_thread_id,
                skill_profile="react_default",
            )
            _run_researcher_wave(
                state,
                researchers=[researcher],
                progress_callback=progress_callback,
                persist_callback=persist_callback,
            )

    if not _node_is_completed(state, REPORTER_NODE_ID):
        reporter = ReporterNode(engine=engine)
        _run_node(
            state,
            node_id=REPORTER_NODE_ID,
            node_type=reporter.node_type,
            runner=reporter,
            progress_callback=progress_callback,
            persist_callback=persist_callback,
        )
    elif state.status != "done":
        state.status = "done"
        state.current_node = REPORTER_NODE_ID
        state.updated_at = _now_ms()
        _persist_state(state, persist_callback)

    return state


def run_static_graph(
    *,
    question: str = "",
    thread_id: str = "",
    engine: str = "",
    use_planner: bool = False,
    max_steps: int = 8,
    preferred_thread_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
    run_id: str | None = None,
    state: RunState | None = None,
    persist_callback: PersistCallback | None = None,
) -> RunState:
    if state is None:
        if not question or not thread_id:
            raise ValueError("question and thread_id are required when state is not provided")
        state = create_run_state(
            question=question,
            thread_id=thread_id,
            run_id=run_id,
        )
    return _execute_static_graph(
        state,
        engine=engine,
        use_planner=use_planner,
        max_steps=max_steps,
        preferred_thread_id=preferred_thread_id,
        progress_callback=progress_callback,
        persist_callback=persist_callback,
    )


def resume_static_graph(
    state: RunState,
    *,
    engine: str = "",
    max_steps: int = 8,
    preferred_thread_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
    use_planner: bool | None = None,
    persist_callback: PersistCallback | None = None,
) -> RunState:
    if use_planner is None:
        use_planner = bool(state.context.get("use_planner", state.route_kind == "planned_research"))
    return _execute_static_graph(
        state,
        engine=engine,
        use_planner=use_planner,
        max_steps=max_steps,
        preferred_thread_id=preferred_thread_id,
        progress_callback=progress_callback,
        persist_callback=persist_callback,
    )


__all__ = [
    "CoordinatorNode",
    "PlannerNode",
    "ResearcherNode",
    "ReporterNode",
    "create_run_state",
    "resume_static_graph",
    "run_static_graph",
]
