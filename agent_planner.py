"""
agent_planner.py — 深度规划 Agent（Planner / Executor / Memory / Reporter）

适用于需要多维度调研的复杂问题，例如：
  - "比较 A 和 B 的优缺点"
  - "分析某行业 2024 年的市场格局"
  - "某公司的财务状况与竞争态势"

执行流程：
  1. Planner  — orchestrator LLM 把大问题拆解为 3-5 个子问题
  2. Executor — 对每个子问题运行精简 ReAct 循环（最多 SUB_MAX_STEPS 步）
  3. Memory   — 把前序子问题的关键发现 + 已登记的引用编号注入后续执行
  4. Reporter — report.compose_report 综合所有 Observation，生成带引用的最终报告
"""

from __future__ import annotations

import traceback
from typing import Callable

from pydantic import BaseModel, field_validator, ValidationError

from agent import ai_generate_role, extract_json
from agent_loop import run_agent
from prompts import prompt_plan_research
from report import Observation, CitationRegistry, QuestionType, classify_question, compose_report

# ── 每个子问题的 ReAct 循环步数上限 ──
SUB_MAX_STEPS = 4

# ── 每个子结果摘要注入下一轮的最大字符数 ──
MEMORY_SNIPPET_LEN = 400


# ══════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════

class ResearchPlan(BaseModel):
    reasoning: str
    sub_questions: list[str]

    @field_validator("sub_questions")
    @classmethod
    def must_have_questions(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("sub_questions 不能为空")
        return [q.strip() for q in v if q.strip()][:5]


class SubResult(BaseModel):
    sub_q: str
    answer: str
    observations: list[dict] = []
    step_count: int
    error: str | None = None


# ══════════════════════════════════════════════
# Planner：拆解问题
# ══════════════════════════════════════════════

def _plan_research(question: str, engine: str) -> ResearchPlan:
    prompt = prompt_plan_research(question)
    raw = ai_generate_role(
        prompt, role="orchestrator", engine=engine, structured=True,
    )
    data = extract_json(raw)
    if not data or not isinstance(data, dict):
        return ResearchPlan(
            reasoning="规划解析失败，直接对原问题执行研究",
            sub_questions=[question],
        )
    try:
        return ResearchPlan(**data)
    except (ValidationError, Exception):
        return ResearchPlan(
            reasoning="规划解析失败，直接对原问题执行研究",
            sub_questions=[question],
        )


# ══════════════════════════════════════════════
# Memory：累积发现，注入后续子任务
# ══════════════════════════════════════════════

class PlannerMemory:
    """记录已完成的子问题及其摘要，注入后续执行器作为背景上下文。"""

    def __init__(self) -> None:
        self._items: list[tuple[str, str, list[int]]] = []  # (sub_q, answer, cite_ids)

    def add(self, sub_q: str, answer: str, cite_ids: list[int]) -> None:
        self._items.append((sub_q, answer, cite_ids))

    def as_context(self) -> str:
        if not self._items:
            return ""
        lines = ["## 已完成的子问题调研结论（供参考，可复用其引用编号）\n"]
        for sub_q, answer, cite_ids in self._items:
            snippet = answer[:MEMORY_SNIPPET_LEN]
            if len(answer) > MEMORY_SNIPPET_LEN:
                snippet += "…（已截断）"
            cite_str = (
                "，可引用：" + "".join(f"[{i}]" for i in cite_ids)
                if cite_ids else ""
            )
            lines.append(f"**{sub_q}**{cite_str}\n{snippet}\n")
        return "\n".join(lines)


# ══════════════════════════════════════════════
# Executor：对单个子问题运行精简 ReAct
# ══════════════════════════════════════════════

def _execute_sub(
    sub_q: str,
    memory: PlannerMemory,
    registry: CitationRegistry,
    engine: str,
    progress_cb: Callable | None = None,
) -> tuple[SubResult, list[Observation]]:
    """
    对单个子问题运行最多 SUB_MAX_STEPS 步的 ReAct 循环，
    共享全局 CitationRegistry，让所有子问题的引用编号连贯。
    """
    context = memory.as_context()
    enhanced_q = f"{context}\n\n## 当前子问题\n{sub_q}" if context else sub_q

    result = run_agent(
        question=enhanced_q,
        engine=engine,
        max_steps=SUB_MAX_STEPS,
        progress_callback=progress_cb,
        registry=registry,
        compose=False,  # 子问题不单独编排，最后统一由 Reporter 汇总
    )
    # 从返回值重建 Observation 列表
    obs_list = [Observation(**o) for o in result.get("observations", [])]
    sub_r = SubResult(
        sub_q=sub_q,
        answer=result.get("answer", "（无结果）"),
        observations=result.get("observations", []),
        step_count=result.get("step_count", 0),
        error=result.get("error"),
    )
    return sub_r, obs_list


# ══════════════════════════════════════════════
# Reporter：综合报告（走 compose_report）
# ══════════════════════════════════════════════

def _synthesize(
    question: str,
    all_observations: list[Observation],
    registry: CitationRegistry,
    engine: str,
    question_type: QuestionType | None = None,
    progress_cb: Callable | None = None,
) -> str:
    if progress_cb:
        progress_cb("📝 综合所有发现，编排最终报告（分型模板 + 引用溯源）…")
    return compose_report(
        question, all_observations, registry,
        engine=engine, question_type=question_type,
    )


# ══════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════

def run_planner_agent(
    question: str,
    engine: str = "",
    progress_callback: Callable | None = None,
) -> dict:
    """
    深度规划 Agent 主入口。

    返回：
        {
            "answer":       str,           # 最终综合报告
            "plan":         dict,          # {reasoning, sub_questions}
            "sub_results":  list[dict],    # 每个子问题的结果（含 observations）
            "registry":     CitationRegistry,
            "total_steps":  int,
            "error":        str | None,
        }
    """
    sub_results: list[SubResult] = []
    all_obs: list[Observation] = []
    registry = CitationRegistry()
    memory = PlannerMemory()
    plan: ResearchPlan | None = None

    try:
        # ── 0. 主问题分类（一次到底，用于最终报告的分型模板） ──
        if progress_callback:
            progress_callback("🧭 识别主问题类型…")
        main_qtype = classify_question(question, engine)
        if progress_callback:
            progress_callback(f"📌 主问题类型：{main_qtype.value}")

        # ── 1. Planner ──
        if progress_callback:
            progress_callback("🗺️ 规划研究方向，拆解子问题…")
        plan = _plan_research(question, engine)
        if progress_callback:
            progress_callback(
                f"📋 已拆解为 {len(plan.sub_questions)} 个子问题：{plan.reasoning}"
            )

        # ── 2. Executor + Memory ──
        for idx, sub_q in enumerate(plan.sub_questions, 1):
            if progress_callback:
                progress_callback(
                    f"🔬 [{idx}/{len(plan.sub_questions)}] 调研子问题：{sub_q}"
                )

            def _sub_cb(msg: str, _idx=idx) -> None:
                if progress_callback:
                    progress_callback(f"  [{_idx}] {msg}")

            sub_r, obs_list = _execute_sub(
                sub_q, memory, registry, engine, _sub_cb,
            )
            all_obs.extend(obs_list)
            # 收集该子问题下所有 cite_ids 供 memory 复用
            cite_ids: list[int] = []
            for o in obs_list:
                cite_ids.extend(o.cite_ids)
            cite_ids = sorted(set(cite_ids))
            memory.add(sub_q, sub_r.answer, cite_ids)
            sub_results.append(sub_r)

        # ── 3. Reporter ──
        final_answer = _synthesize(
            question, all_obs, registry, engine,
            question_type=main_qtype, progress_cb=progress_callback,
        )

        return {
            "answer":        final_answer,
            "plan":          plan.model_dump(),
            "sub_results":   [r.model_dump() for r in sub_results],
            "registry":      registry,
            "question_type": main_qtype.value,
            "total_steps":   sum(r.step_count for r in sub_results),
            "error":         None,
        }

    except Exception as e:
        return {
            "answer":        f"规划 Agent 运行出错：{e}",
            "plan":          plan.model_dump() if plan else {},
            "sub_results":   [r.model_dump() for r in sub_results],
            "registry":      registry,
            "question_type": "research",
            "total_steps":   sum(r.step_count for r in sub_results),
            "error":         traceback.format_exc(),
        }
