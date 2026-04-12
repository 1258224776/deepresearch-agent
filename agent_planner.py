"""
agent_planner.py — 深度规划 Agent（Planner / Executor / Memory / Reporter）

适用于需要多维度调研的复杂问题，例如：
  - "比较 A 和 B 的优缺点"
  - "分析某行业 2024 年的市场格局"
  - "某公司的财务状况与竞争态势"

执行流程：
  1. Planner  — orchestrator LLM 把大问题拆解为 3-5 个子问题
  2. Executor — 对每个子问题运行精简 ReAct 循环（最多 SUB_MAX_STEPS 步）
  3. Memory   — 把前序子问题的关键发现作为上下文注入后续执行
  4. Reporter — analyst LLM 综合所有发现，生成结构化最终报告
"""

from __future__ import annotations

import traceback
from typing import Callable

from pydantic import BaseModel, field_validator, ValidationError

from agent import ai_generate_role, extract_json
from agent_loop import run_agent
from prompts import prompt_plan_research, prompt_synthesize_report

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
        return [q.strip() for q in v if q.strip()][:5]  # 最多保留 5 个


class SubResult(BaseModel):
    sub_q: str
    answer: str
    step_count: int
    error: str | None = None


# ══════════════════════════════════════════════
# Planner：拆解问题
# ══════════════════════════════════════════════

def _plan_research(question: str, engine: str) -> ResearchPlan:
    """
    调用 orchestrator LLM，把问题拆解为若干子问题。
    若 LLM 输出解析失败，回退到只含原问题的单子问题列表。
    """
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
    """
    轻量共享记忆：记录已完成的子问题及其核心发现。
    后续子执行器读取 as_context() 注入问题前缀，避免重复研究。
    """
    def __init__(self) -> None:
        self._items: list[SubResult] = []

    def add(self, result: SubResult) -> None:
        self._items.append(result)

    def as_context(self) -> str:
        """返回已有发现的简短摘要（可注入到下一个子问题的 prompt 前缀）。"""
        if not self._items:
            return ""
        lines = ["## 已完成的子问题调研结论（供参考）\n"]
        for r in self._items:
            snippet = r.answer[:MEMORY_SNIPPET_LEN]
            if len(r.answer) > MEMORY_SNIPPET_LEN:
                snippet += "…（已截断）"
            lines.append(f"**{r.sub_q}**\n{snippet}\n")
        return "\n".join(lines)


# ══════════════════════════════════════════════
# Executor：对单个子问题运行精简 ReAct
# ══════════════════════════════════════════════

def _execute_sub(
    sub_q: str,
    memory: PlannerMemory,
    engine: str,
    progress_cb: Callable | None = None,
) -> SubResult:
    """
    对单个子问题运行最多 SUB_MAX_STEPS 步的 ReAct 循环。
    如果 memory 里有前序发现，把它拼接到子问题前面作为背景上下文。
    """
    context = memory.as_context()
    enhanced_q = f"{context}\n\n## 当前子问题\n{sub_q}" if context else sub_q

    result = run_agent(
        question=enhanced_q,
        engine=engine,
        max_steps=SUB_MAX_STEPS,
        progress_callback=progress_cb,
    )
    return SubResult(
        sub_q=sub_q,
        answer=result.get("answer", "（无结果）"),
        step_count=result.get("step_count", 0),
        error=result.get("error"),
    )


# ══════════════════════════════════════════════
# Reporter：综合报告
# ══════════════════════════════════════════════

def _synthesize(
    question: str,
    sub_results: list[SubResult],
    engine: str,
    progress_cb: Callable | None = None,
) -> str:
    """
    调用 analyst LLM，把所有子结果综合成最终报告。
    """
    if progress_cb:
        progress_cb("📝 综合所有发现，生成最终报告…")
    prompt = prompt_synthesize_report(
        question,
        [{"sub_q": r.sub_q, "answer": r.answer} for r in sub_results],
    )
    return ai_generate_role(prompt, role="analyst", engine=engine, structured=False)


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

    参数：
        question:          用户的核心研究问题
        engine:            引擎预设（"deep" | "fast" | ""）
        progress_callback: 进度回调 fn(msg: str)

    返回：
        {
            "answer":       str,             # 最终综合报告
            "plan":         dict,            # 研究计划 {reasoning, sub_questions}
            "sub_results":  list[dict],      # 每个子问题的结果 {sub_q, answer, step_count}
            "total_steps":  int,             # 所有子循环的步数之和
            "error":        str | None,
        }
    """
    sub_results: list[SubResult] = []
    plan: ResearchPlan | None = None

    try:
        # ── 1. Planner ──
        if progress_callback:
            progress_callback("🗺️ 规划研究方向，拆解子问题…")
        plan = _plan_research(question, engine)
        if progress_callback:
            progress_callback(
                f"📋 已拆解为 {len(plan.sub_questions)} 个子问题：{plan.reasoning}"
            )

        # ── 2. Executor + Memory ──
        memory = PlannerMemory()
        for idx, sub_q in enumerate(plan.sub_questions, 1):
            if progress_callback:
                progress_callback(
                    f"🔬 [{idx}/{len(plan.sub_questions)}] 调研子问题：{sub_q}"
                )

            def _sub_cb(msg: str, _sub_q=sub_q, _idx=idx) -> None:
                if progress_callback:
                    progress_callback(f"  [{_idx}] {msg}")

            sub_r = _execute_sub(sub_q, memory, engine, _sub_cb)
            memory.add(sub_r)
            sub_results.append(sub_r)

        # ── 3. Reporter ──
        final_answer = _synthesize(question, sub_results, engine, progress_callback)

        return {
            "answer":      final_answer,
            "plan":        plan.model_dump(),
            "sub_results": [r.model_dump() for r in sub_results],
            "total_steps": sum(r.step_count for r in sub_results),
            "error":       None,
        }

    except Exception as e:
        return {
            "answer":      f"规划 Agent 运行出错：{e}",
            "plan":        plan.model_dump() if plan else {},
            "sub_results": [r.model_dump() for r in sub_results],
            "total_steps": sum(r.step_count for r in sub_results),
            "error":       traceback.format_exc(),
        }
