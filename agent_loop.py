"""
Core ReAct agent loop.

Stage C moves execution tools into project-local skills while keeping
the orchestration loop, finish signal, and report composition here.
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Callable

from pydantic import BaseModel, ValidationError, field_validator

from agent import ai_generate_role, ai_tool_call, extract_json
from memory import format_memory_context, search_memory
from prompts import prompt_react_system
from report import CitationRegistry, Observation, QuestionType, classify_question, compose_report
from skills import BUILTIN_SKILL_REGISTRY
from skills.base import SkillContext
from skills.config import get_enabled_skill_names
from skills.guidance import get_guidance_for_skills
from skills.profiles import DEFAULT_SKILL_PROFILE, get_profile_allowlist
from skills.router import build_route_decision, check_loop, suggest_next_step
from skills.stats import record_skill_calls


MAX_PARSE_RETRIES = 2
COMPRESS_AFTER = 4
OBS_FULL_LEN = 1500
OBS_COMPRESSED = 300


class AgentError(Exception):
    """Base agent error."""


class LLMSchemaError(AgentError):
    """LLM output did not match the expected action schema."""


class SearchEmptyError(AgentError):
    """Search returned no results."""


class ScrapeFailedError(AgentError):
    """Page scraping failed."""


class RagNotReadyError(AgentError):
    """Local RAG index is not ready."""


class RateLimitError(AgentError):
    """Upstream provider returned a rate-limit style error."""


SKILL_REGISTRY = BUILTIN_SKILL_REGISTRY
FINISH_TOOL_NAME = "finish"
TOOLS: dict[str, dict] = {
    **SKILL_REGISTRY.export_tool_dict(),
    FINISH_TOOL_NAME: {
        "desc": "信息已足够，输出最终完整答案（Markdown 格式）",
        "args": ["answer"],
    },
}


class ReActAction(BaseModel):
    thought: str
    tool: str
    args: dict

    @field_validator("tool")
    @classmethod
    def tool_must_be_known(cls, value: str) -> str:
        if value not in TOOLS:
            raise ValueError(f"未知工具 '{value}'，可用工具：{list(TOOLS.keys())}")
        return value

    @field_validator("args")
    @classmethod
    def args_must_have_required(cls, value: dict, info) -> dict:
        tool_name = info.data.get("tool", "")
        required = TOOLS.get(tool_name, {}).get("args", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"工具 '{tool_name}' 缺少必填参数：{missing}")
        return value


class _FinishSignal(Exception):
    def __init__(self, answer: str):
        self.answer = answer


def _append_tool_metric(
    tool_metrics: list[dict[str, Any]],
    name: str,
    *,
    success: bool,
    started_at: float,
    error: str = "",
) -> None:
    if not name or name == FINISH_TOOL_NAME:
        return
    tool_metrics.append(
        {
            "skill_name": name,
            "success": success,
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
            "error": error,
        }
    )


def _flush_tool_metrics(tool_metrics: list[dict[str, Any]]) -> None:
    if not tool_metrics:
        return
    try:
        record_skill_calls(tool_metrics)
    except Exception:
        pass


def _run_tool(
    name: str,
    args: dict,
    *,
    question: str,
    engine: str,
    history: list[dict],
    observations: list[Observation],
    registry: CitationRegistry,
    progress_cb: Callable | None = None,
) -> Observation:
    if name == FINISH_TOOL_NAME:
        raise _FinishSignal(args.get("answer", ""))

    ctx = SkillContext(
        question=question,
        engine=engine,
        history=history,
        observations=observations,
        registry=registry,
        progress_callback=progress_cb,
    )

    try:
        obs = SKILL_REGISTRY.run(name, ctx, args)
    except KeyError as exc:
        raise AgentError(str(exc)) from exc
    except RuntimeError as exc:
        err_str = str(exc)
        lowered = err_str.lower()
        if name == "rag_retrieve" and ("向量库" in err_str or "上传文档" in err_str):
            raise RagNotReadyError(err_str) from exc
        if any(token in lowered for token in ("429", "quota", "rate", "limit")):
            raise RateLimitError(err_str) from exc
        raise AgentError(err_str) from exc
    except Exception as exc:
        err_str = str(exc)
        lowered = err_str.lower()
        if any(token in lowered for token in ("429", "quota", "rate", "limit")):
            raise RateLimitError(err_str) from exc
        raise AgentError(err_str) from exc

    if not obs.tool:
        obs.tool = name
    if not obs.args:
        obs.args = dict(args)

    if name.startswith("search") and not obs.sources:
        raise SearchEmptyError(f"搜索 '{args.get('query', '')}' 无结果，请尝试更换关键词。")

    if name.startswith("scrape") and not obs.sources:
        raise ScrapeFailedError(f"抓取失败：{args.get('url', '') or args.get('urls', '')}")

    return obs


def _compress_history(history: list[dict]) -> list[dict]:
    if len(history) <= COMPRESS_AFTER:
        return history

    compressed: list[dict] = []
    cutoff = len(history) - COMPRESS_AFTER

    for index, step in enumerate(history):
        if index < cutoff:
            obs = step.get("observation", "")
            if len(obs) > OBS_COMPRESSED:
                obs = obs[:OBS_COMPRESSED] + "...(已压缩)"
            compressed.append({**step, "observation": obs})
        else:
            compressed.append(step)

    return compressed


def _build_prompt(
    question: str,
    history: list[dict],
    step_num: int = 0,
    max_steps: int = 8,
    registry: CitationRegistry | None = None,
    memory_context: str = "",
    force_finish: bool = False,
) -> str:
    """
    组装当轮 user prompt。
    除历史记录外，Stage 3 会追加「建议下一步」动态提示；
    Stage 4 触发强制 finish 时会注入硬性指令。
    """
    display = _compress_history(history)

    lines = [f"用户问题：{question}", ""]
    if memory_context:
        lines.append(memory_context)
        lines.append("")
    if display:
        lines.append("## 已执行步骤")
        for i, step in enumerate(display, 1):
            lines.append(f"\n### 步骤 {i}")
            lines.append(f"**思考**：{step['thought']}")
            lines.append(f"**工具**：{step['tool']}({step['args']})")
            obs = step.get("observation", "")
            if len(obs) > OBS_FULL_LEN:
                obs = obs[:OBS_FULL_LEN] + "\n...(已截断)"
            lines.append(f"**观察**：\n{obs}")
        lines.append("")

    # Stage 3：步间状态路由 —— 根据最近一步 obs / 已登记来源数 给出建议
    hint = suggest_next_step(history, step_num=step_num, max_steps=max_steps, registry=registry)
    if hint:
        lines.append(hint)
        lines.append("")

    if force_finish:
        lines.append(
            "⛔ 系统判定无需继续检索，请本步直接调用 `finish`，基于已有观察输出答案。"
        )
    else:
        lines.append(
            "请根据以上步骤结果决定下一步行动。如果信息已经足够，请调用 finish 输出最终答案。"
        )
    return "\n".join(lines)


def _parse_action(raw: str, engine: str, prompt: str, system: str) -> ReActAction:
    last_error = ""

    for attempt in range(MAX_PARSE_RETRIES + 1):
        if attempt > 0:
            retry_prompt = (
                f"{prompt}\n\n"
                "【上一次输出格式有误，请修正】\n"
                f"错误信息：{last_error}\n"
                "请重新输出符合格式的单个 JSON，不要有其他内容。"
            )
            raw = ai_generate_role(
                retry_prompt,
                system=system,
                role="orchestrator",
                engine=engine,
                structured=True,
            )

        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            last_error = f"无法解析为 JSON，原始输出：{raw[:200]}"
            continue

        try:
            return ReActAction(**data)
        except ValidationError as exc:
            last_error = str(exc)
            continue

    raise LLMSchemaError(
        f"LLM 输出经过 {MAX_PARSE_RETRIES + 1} 次尝试仍不符合 schema。\n"
        f"最后错误：{last_error}\n最后原始输出：{raw[:300]}"
    )


def run_agent(
    question: str,
    engine: str = "",
    max_steps: int = 8,
    progress_callback: Callable | None = None,
    registry: CitationRegistry | None = None,
    compose: bool = True,
    use_router: bool = True,
    question_type: QuestionType | None = None,
    skill_profile: str = DEFAULT_SKILL_PROFILE,
    memory_context: str | None = None,
    preferred_thread_id: str | None = None,
) -> dict:
    """
    ReAct Agent 主入口。

    Stage A + 路由强化后的关键点：
      - classify_question 产出 QuestionType（若调用方未传）
      - route_entry 生成 skill 白名单 + 起手建议，只把这些喂给 LLM
      - 每步通过 suggest_next_step 注入下一步建议
      - check_loop 检测重复/无新来源，必要时强制 finish
      - finish 与 fallback 都走 compose_report，复用同一个 QuestionType

    Returns:
        {
            "answer": str, "steps": list[dict], "observations": list[dict],
            "registry": CitationRegistry, "question_type": str,
            "allowed_skills": list[str], "route": dict, "step_count": int, "error": str | None,
        }
    """
    history: list[dict] = []
    observations: list[Observation] = []
    tool_metrics: list[dict[str, Any]] = []
    if registry is None:
        registry = CitationRegistry()
    enabled_skills = get_enabled_skill_names(SKILL_REGISTRY.names())
    resolved_profile, profile_skills = get_profile_allowlist(skill_profile, enabled_skills)
    if memory_context is None:
        memory_hits = search_memory(
            question,
            top_k=3,
            preferred_thread_id=preferred_thread_id,
        )
        resolved_memory_context = format_memory_context(memory_hits)
        if progress_callback and memory_hits:
            progress_callback(f"已召回 {len(memory_hits)} 条历史研究记忆")
    else:
        memory_hits = []
        resolved_memory_context = memory_context.strip()

    # ── 入口预路由（Stage 1） ──
    if use_router:
        qtype = question_type or classify_question(question, engine)
        route = build_route_decision(
            qtype,
            profile_skills,
            question=question,
            profile_name=resolved_profile,
        )
        allowed_skills = route.allowed
        starter_hint = route.starter
        preferred_skills = route.preferred
        discouraged_skills = route.discouraged
        route_reasons = route.reasons
        if progress_callback:
            progress_callback(
                f"🧭 预路由：profile = {resolved_profile}，问题类型 = {qtype.value}，"
                f"候选工具 = {allowed_skills}，优先 = {preferred_skills}，起手 = {starter_hint}"
            )
    else:
        qtype = question_type or QuestionType.RESEARCH
        allowed_skills = profile_skills
        starter_hint = ""
        preferred_skills = []
        discouraged_skills = []
        route_reasons = []
        route = None

    # Stage 2：按白名单过滤工具字典（finish 恒保留）
    allow_set = set(allowed_skills) | {FINISH_TOOL_NAME}
    ordered_tool_names = [name for name in allowed_skills if name in TOOLS]
    ordered_tool_names.append(FINISH_TOOL_NAME)
    effective_tools = {
        name: TOOLS[name]
        for name in ordered_tool_names
        if name in allow_set and name in TOOLS
    }
    system = prompt_react_system(
        effective_tools,
        allowed_skills=allowed_skills,
        starter_hint=starter_hint,
        preferred_skills=preferred_skills,
        discouraged_skills=discouraged_skills,
        route_reasons=route_reasons,
        skill_guidance=get_guidance_for_skills(allowed_skills),
    )

    force_finish_next = False

    try:
        for step_num in range(max_steps):
            if progress_callback:
                progress_callback(f"第 {step_num + 1} 步推理中...")

            prompt = _build_prompt(
                question, history,
                step_num=step_num, max_steps=max_steps,
                registry=registry,
                memory_context=resolved_memory_context,
                force_finish=force_finish_next,
            )
            action: ReActAction | None = None

            try:
                tool_name, tool_args, thought = ai_tool_call(
                    prompt,
                    system=system,
                    tools=effective_tools,
                    role="orchestrator",
                    engine=engine,
                )
                action = ReActAction(
                    thought=thought or f"(原生调用 {tool_name})",
                    tool=tool_name,
                    args=tool_args,
                )
                print(f"[Agent] Step {step_num + 1} native call -> {tool_name}")
            except Exception as native_err:
                print(f"[Agent] Native function calling failed, fallback to JSON: {native_err}")

            if action is None:
                raw = ai_generate_role(
                    prompt,
                    system=system,
                    role="orchestrator",
                    engine=engine,
                    structured=True,
                )
                try:
                    action = _parse_action(raw, engine, prompt, system)
                except LLMSchemaError as exc:
                    history.append({
                        "thought": "(格式错误)",
                        "tool": "none",
                        "args": {},
                        "observation": str(exc),
                        "error_type": "LLMSchemaError",
                    })
                    continue

            # Stage 2 强校验：LLM 调了白名单外的工具 → 记录错误并重试
            if action.tool not in allow_set:
                history.append({
                    "thought": action.thought,
                    "tool": action.tool,
                    "args": action.args,
                    "observation": (
                        f"[越权] 工具 `{action.tool}` 不在本次对话白名单 {sorted(allow_set)} 中，"
                        f"请从可用工具中重选。"
                    ),
                    "sources": [],
                    "cite_ids": [],
                    "error_type": "NotAllowedSkill",
                })
                continue

            # Stage 4：重复 / 误选纠偏
            guard = check_loop(
                action.tool, action.args, history,
                registry_size_before=len(registry),
                registry_size_now=len(registry),
            )
            if not guard.ok:
                history.append({
                    "thought": action.thought,
                    "tool": action.tool,
                    "args": action.args,
                    "observation": f"[纠偏] {guard.reason}",
                    "sources": [],
                    "cite_ids": [],
                    "error_type": "LoopGuard",
                })
                continue
            if guard.force_finish and action.tool != FINISH_TOOL_NAME:
                # 下一轮强制 finish；本步放行以收集最后一条观察
                force_finish_next = True
                if progress_callback:
                    progress_callback(guard.warning or "⛔ 强制进入 finish")

            try:
                tool_started_at = time.perf_counter()
                obs = _run_tool(
                    action.tool,
                    action.args,
                    question=question,
                    engine=engine,
                    history=history,
                    observations=observations,
                    registry=registry,
                    progress_cb=progress_callback,
                )
            except _FinishSignal as fin:
                history.append({
                    "thought": action.thought,
                    "tool": FINISH_TOOL_NAME,
                    "args": action.args,
                    "observation": "(任务完成)",
                    "sources": [],
                    "cite_ids": [],
                })
                if compose:
                    if progress_callback:
                        progress_callback("编排最终报告（分型模板 + 引用来源）")
                    answer = compose_report(
                        question, observations, registry,
                        engine=engine, question_type=qtype,
                    )
                else:
                    answer = fin.answer
                return {
                    "answer": answer,
                    "steps": history,
                    "observations": [o.model_dump() for o in observations],
                    "memory_hits": memory_hits,
                    "memory_hit_count": len(memory_hits),
                    "registry": registry,
                    "question_type": qtype.value,
                    "skill_profile": resolved_profile,
                    "allowed_skills": allowed_skills,
                    "route": route.as_dict() if route is not None else {},
                    "step_count": step_num + 1,
                    "error": None,
                }
            except SearchEmptyError as exc:
                _append_tool_metric(tool_metrics, action.tool, success=False, started_at=tool_started_at, error=str(exc))
                _append_error(history, action, f"[搜索为空] {exc}", "SearchEmptyError")
                continue
            except ScrapeFailedError as exc:
                _append_tool_metric(tool_metrics, action.tool, success=False, started_at=tool_started_at, error=str(exc))
                _append_error(history, action, f"[抓取失败] {exc}", "ScrapeFailedError")
                continue
            except RagNotReadyError as exc:
                _append_tool_metric(tool_metrics, action.tool, success=False, started_at=tool_started_at, error=str(exc))
                _append_error(history, action, f"[RAG 未就绪] {exc}", "RagNotReadyError")
                continue
            except RateLimitError as exc:
                _append_tool_metric(tool_metrics, action.tool, success=False, started_at=tool_started_at, error=str(exc))
                _append_error(history, action, f"[限流] {exc}", "RateLimitError")
                continue
            except AgentError as exc:
                _append_tool_metric(tool_metrics, action.tool, success=False, started_at=tool_started_at, error=str(exc))
                _append_error(history, action, f"[工具错误] {exc}", "AgentError")
                continue

            _append_tool_metric(tool_metrics, action.tool, success=True, started_at=tool_started_at)
            cite_ids = registry.add_many(obs.sources)
            obs.cite_ids = cite_ids
            observations.append(obs)
            history.append({
                "thought": action.thought,
                "tool": action.tool,
                "args": action.args,
                "observation": obs.content,
                "sources": [s.model_dump() for s in obs.sources],
                "cite_ids": cite_ids,
            })

        if progress_callback:
            progress_callback("已达最大步数，编排最终报告...")

        if compose:
            answer = compose_report(
                question, observations, registry,
                engine=engine, question_type=qtype,
            )
        else:
            fallback_prompt = (
                f"用户问题：{question}\n\n"
                "以下是调研过程中收集到的所有信息：\n\n"
                + "\n\n".join(
                    f"【步骤 {i + 1} 观察】\n{o.content}"
                    for i, o in enumerate(observations)
                    if o.content
                )
                + "\n\n请综合以上信息，写出完整、结构清晰的最终答案（Markdown 格式）。"
            )
            answer = ai_generate_role(
                fallback_prompt,
                role="analyst",
                engine=engine,
                structured=False,
            )

        return {
            "answer": answer,
            "steps": history,
            "observations": [o.model_dump() for o in observations],
            "memory_hits": memory_hits,
            "memory_hit_count": len(memory_hits),
            "registry": registry,
            "question_type": qtype.value,
            "skill_profile": resolved_profile,
            "allowed_skills": allowed_skills,
            "route": route.as_dict() if route is not None else {},
            "step_count": max_steps,
            "error": None,
        }

    except Exception as exc:
        return {
            "answer": f"Agent 运行出错：{exc}",
            "steps": history,
            "observations": [o.model_dump() for o in observations],
            "memory_hits": memory_hits,
            "memory_hit_count": len(memory_hits),
            "registry": registry,
            "question_type": qtype.value if use_router else "research",
            "skill_profile": resolved_profile,
            "allowed_skills": allowed_skills,
            "route": route.as_dict() if route is not None else {},
            "step_count": len(history),
            "error": traceback.format_exc(),
        }
    finally:
        _flush_tool_metrics(tool_metrics)


def _append_error(history: list[dict], action: ReActAction, msg: str, err_type: str) -> None:
    history.append({
        "thought": action.thought,
        "tool": action.tool,
        "args": action.args,
        "observation": msg,
        "sources": [],
        "cite_ids": [],
        "error_type": err_type,
    })
