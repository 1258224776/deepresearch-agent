"""
Deep planning agent with planner / executor / memory / reporter stages.
"""

from __future__ import annotations

import traceback
from typing import Callable

from pydantic import BaseModel, ValidationError, field_validator

from agent import ai_generate_role, extract_json
from agent_loop import run_agent
from memory import format_memory_context, search_memory
from prompts import prompt_plan_research
from report import CitationRegistry, Observation, QuestionType, classify_question, compose_report

SUB_MAX_STEPS = 4
MEMORY_SNIPPET_LEN = 400


class ResearchPlan(BaseModel):
    reasoning: str
    sub_questions: list[str]

    @field_validator("sub_questions")
    @classmethod
    def must_have_questions(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("sub_questions cannot be empty")
        return [item.strip() for item in value if item.strip()][:5]


class SubResult(BaseModel):
    sub_q: str
    answer: str
    observations: list[dict] = []
    step_count: int
    error: str | None = None


class PlannerMemory:
    """Store completed sub-question findings for later planner steps."""

    def __init__(self) -> None:
        self._items: list[tuple[str, str, list[int]]] = []

    def add(self, sub_q: str, answer: str, cite_ids: list[int]) -> None:
        self._items.append((sub_q, answer, cite_ids))

    def as_context(self) -> str:
        if not self._items:
            return ""
        lines = ["## Completed sub-question findings", ""]
        for sub_q, answer, cite_ids in self._items:
            snippet = answer[:MEMORY_SNIPPET_LEN]
            if len(answer) > MEMORY_SNIPPET_LEN:
                snippet += " ..."
            cite_text = f" Reusable citations: {cite_ids}" if cite_ids else ""
            lines.append(f"### {sub_q}{cite_text}")
            lines.append(snippet)
            lines.append("")
        return "\n".join(lines).strip()


def _plan_research(question: str, engine: str) -> ResearchPlan:
    prompt = prompt_plan_research(question)
    raw = ai_generate_role(
        prompt,
        role="orchestrator",
        engine=engine,
        structured=True,
    )
    data = extract_json(raw)
    if not data or not isinstance(data, dict):
        return ResearchPlan(
            reasoning="Planning parse failed, falling back to the original research question.",
            sub_questions=[question],
        )
    try:
        return ResearchPlan(**data)
    except (ValidationError, Exception):
        return ResearchPlan(
            reasoning="Planning parse failed, falling back to the original research question.",
            sub_questions=[question],
        )


def _execute_sub(
    sub_q: str,
    memory: PlannerMemory,
    registry: CitationRegistry,
    engine: str,
    progress_cb: Callable | None = None,
    global_memory_context: str = "",
    preferred_thread_id: str | None = None,
) -> tuple[SubResult, list[Observation]]:
    """Run a bounded ReAct loop for one sub-question."""
    context = memory.as_context()
    enhanced_q = f"{context}\n\n## Current sub-question\n{sub_q}" if context else sub_q

    result = run_agent(
        question=enhanced_q,
        engine=engine,
        max_steps=SUB_MAX_STEPS,
        progress_callback=progress_cb,
        registry=registry,
        memory_context=global_memory_context,
        preferred_thread_id=preferred_thread_id,
        compose=False,
        skill_profile="planner",
    )

    obs_list = [Observation(**item) for item in result.get("observations", [])]
    sub_result = SubResult(
        sub_q=sub_q,
        answer=result.get("answer", "(no result)"),
        observations=result.get("observations", []),
        step_count=result.get("step_count", 0),
        error=result.get("error"),
    )
    return sub_result, obs_list


def _synthesize(
    question: str,
    all_observations: list[Observation],
    registry: CitationRegistry,
    engine: str,
    question_type: QuestionType | None = None,
    progress_cb: Callable | None = None,
) -> str:
    if progress_cb:
        progress_cb("综合所有发现，编排最终报告…")
    return compose_report(
        question,
        all_observations,
        registry,
        engine=engine,
        question_type=question_type,
    )


def run_planner_agent(
    question: str,
    engine: str = "",
    progress_callback: Callable | None = None,
    memory_context: str | None = None,
    preferred_thread_id: str | None = None,
) -> dict:
    """Run the planner agent and return the synthesized research result."""
    sub_results: list[SubResult] = []
    all_observations: list[Observation] = []
    registry = CitationRegistry()
    memory = PlannerMemory()
    plan: ResearchPlan | None = None

    if memory_context is None:
        memory_hits = search_memory(question, top_k=3, preferred_thread_id=preferred_thread_id)
        resolved_memory_context = format_memory_context(memory_hits)
        if progress_callback and memory_hits:
            progress_callback(f"已召回 {len(memory_hits)} 条历史研究记忆")
    else:
        memory_hits = []
        resolved_memory_context = memory_context.strip()

    try:
        if progress_callback:
            progress_callback("识别主问题类型…")
        main_qtype = classify_question(question, engine)
        if progress_callback:
            progress_callback(f"主问题类型：{main_qtype.value}")

        if progress_callback:
            progress_callback("规划研究方向，拆解子问题…")
        planning_question = question
        if resolved_memory_context:
            planning_question = f"{resolved_memory_context}\n\n## 当前研究任务\n{question}"
        plan = _plan_research(planning_question, engine)
        if progress_callback:
            progress_callback(f"已拆解为 {len(plan.sub_questions)} 个子问题：{plan.reasoning}")

        for index, sub_q in enumerate(plan.sub_questions, 1):
            if progress_callback:
                progress_callback(f"[{index}/{len(plan.sub_questions)}] 调研子问题：{sub_q}")

            def _sub_cb(message: str, _index=index) -> None:
                if progress_callback:
                    progress_callback(f"  [{_index}] {message}")

            sub_result, obs_list = _execute_sub(
                sub_q,
                memory,
                registry,
                engine,
                _sub_cb,
                resolved_memory_context,
                preferred_thread_id,
            )
            all_observations.extend(obs_list)

            cite_ids: list[int] = []
            for observation in obs_list:
                cite_ids.extend(observation.cite_ids)
            cite_ids = sorted(set(cite_ids))
            memory.add(sub_q, sub_result.answer, cite_ids)
            sub_results.append(sub_result)

        final_answer = _synthesize(
            question,
            all_observations,
            registry,
            engine,
            question_type=main_qtype,
            progress_cb=progress_callback,
        )

        return {
            "answer": final_answer,
            "plan": plan.model_dump() if plan else {},
            "sub_results": [item.model_dump() for item in sub_results],
            "memory_hits": memory_hits,
            "memory_hit_count": len(memory_hits),
            "registry": registry,
            "question_type": main_qtype.value,
            "total_steps": sum(item.step_count for item in sub_results),
            "error": None,
        }
    except Exception as exc:
        return {
            "answer": f"Planner agent failed: {exc}",
            "plan": plan.model_dump() if plan else {},
            "sub_results": [item.model_dump() for item in sub_results],
            "memory_hits": memory_hits,
            "memory_hit_count": len(memory_hits),
            "registry": registry,
            "question_type": "research",
            "total_steps": sum(item.step_count for item in sub_results),
            "error": traceback.format_exc(),
        }
