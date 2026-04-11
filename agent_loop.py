"""
agent_loop.py — ReAct Agent 核心

LLM 在循环中自主决定下一步调用哪个工具，直到认为任务完成。
每轮：思考(Thought) → 行动(Action) → 观察(Observation) → 再思考…

复用现有模块：
  - agent.ai_generate_role  — LLM 调用（多模型路由）
  - agent.extract_json      — JSON 强力清洗器
  - tools.web_search        — DuckDuckGo 搜索
  - tools.fetch_via_jina    — 网页爬取
  - rag.retrieve_as_context — 本地文档语义检索
  - prompts.prompt_react_system — Agent 系统提示
"""

from __future__ import annotations

import traceback
from typing import Callable

from agent import ai_generate_role, extract_json
from tools import web_search, fetch_via_jina
from prompts import prompt_react_system

# ══════════════════════════════════════════════
# 工具注册表
# ══════════════════════════════════════════════
TOOLS: dict[str, dict] = {
    "search":       {"desc": "搜索网络，获取相关网页列表", "args": ["query"]},
    "scrape":       {"desc": "爬取指定 URL 的完整正文内容", "args": ["url"]},
    "rag_retrieve": {"desc": "从用户已上传的本地文档中语义检索相关内容", "args": ["query"]},
    "finish":       {"desc": "信息已足够，输出最终完整答案", "args": ["answer"]},
}


# ══════════════════════════════════════════════
# 内部：终止信号
# ══════════════════════════════════════════════
class _FinishSignal(Exception):
    def __init__(self, answer: str):
        self.answer = answer


# ══════════════════════════════════════════════
# 工具执行器
# ══════════════════════════════════════════════
def _run_tool(name: str, args: dict, progress_cb: Callable | None = None) -> str:
    """
    执行工具，返回观察结果字符串。
    若 tool == "finish" 则 raise _FinishSignal。
    """
    if name == "finish":
        raise _FinishSignal(args.get("answer", ""))

    if name == "search":
        query = args.get("query", "")
        if progress_cb:
            progress_cb(f"🔍 搜索：{query}")
        results = web_search(query, max_results=5)
        if not results:
            return "搜索无结果，请尝试换一个关键词。"
        lines = []
        for r in results:
            lines.append(f"- [{r.get('title', '无标题')}]({r.get('href', '')})\n  {r.get('body', '')[:200]}")
        return "\n".join(lines)

    if name == "scrape":
        url = args.get("url", "")
        if progress_cb:
            progress_cb(f"🌐 爬取：{url}")
        content = fetch_via_jina(url, max_chars=6000)
        if not content or content.startswith("（"):
            return f"爬取失败：{url}"
        return content[:6000]

    if name == "rag_retrieve":
        query = args.get("query", "")
        if progress_cb:
            progress_cb(f"📂 RAG 检索：{query}")
        try:
            import rag
            if not rag.is_ready():
                return "本地文档向量库未初始化，请先上传文档。"
            return rag.retrieve_as_context(query, top_k=3)
        except Exception as e:
            return f"RAG 检索失败：{e}"

    return f"未知工具：{name}"


# ══════════════════════════════════════════════
# Prompt 构建
# ══════════════════════════════════════════════
def _build_prompt(question: str, history: list[dict]) -> str:
    """把问题 + 历史 thought/observation 拼成当轮的 user prompt"""
    lines = [f"用户问题：{question}", ""]
    if history:
        lines.append("## 已执行步骤")
        for i, step in enumerate(history, 1):
            lines.append(f"\n### 步骤 {i}")
            lines.append(f"**思考**：{step['thought']}")
            lines.append(f"**工具**：{step['tool']}({step['args']})")
            obs = step.get("observation", "")
            # 截断过长的观察结果，避免撑爆上下文
            if len(obs) > 1500:
                obs = obs[:1500] + "\n…（已截断）"
            lines.append(f"**观察**：\n{obs}")
        lines.append("")
    lines.append("请根据以上步骤的结果，决定下一步行动。如果信息已经足够，调用 finish 输出最终答案。")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# ReAct 主循环
# ══════════════════════════════════════════════
def run_agent(
    question: str,
    engine: str = "",
    max_steps: int = 8,
    progress_callback: Callable | None = None,
) -> dict:
    """
    ReAct Agent 主入口。

    参数：
        question:          用户问题
        engine:            引擎预设（"deep" | "fast" | ""）
        max_steps:         最大循环轮数，防止无限循环
        progress_callback: 进度回调 fn(msg: str)，可用于 UI 更新

    返回：
        {
            "answer":     str,          # 最终答案（Markdown）
            "steps":      list[dict],   # 每步 {thought, tool, args, observation}
            "step_count": int,
            "error":      str | None,   # 如有异常
        }
    """
    history: list[dict] = []
    system = prompt_react_system(TOOLS)

    try:
        for step_num in range(max_steps):
            if progress_callback:
                progress_callback(f"第 {step_num + 1} 步推理中…")

            prompt = _build_prompt(question, history)

            # 调用 LLM（主脑角色，支持多模型路由）
            raw = ai_generate_role(
                prompt,
                system=system,
                role="orchestrator",
                engine=engine,
                structured=True,
            )

            # 解析 LLM 输出的 JSON
            action = extract_json(raw)
            if not action or not isinstance(action, dict):
                # LLM 输出格式不对，记录并跳过
                history.append({
                    "thought": "(解析失败)",
                    "tool": "none",
                    "args": {},
                    "observation": f"LLM 输出无法解析为 JSON：{raw[:300]}",
                })
                continue

            thought = action.get("thought", "")
            tool_name = action.get("tool", "")
            tool_args = action.get("args", {})

            # 执行工具
            try:
                observation = _run_tool(tool_name, tool_args, progress_callback)
            except _FinishSignal as fin:
                # Agent 主动宣告完成
                history.append({
                    "thought": thought,
                    "tool": "finish",
                    "args": tool_args,
                    "observation": "(任务完成)",
                })
                return {
                    "answer": fin.answer,
                    "steps": history,
                    "step_count": step_num + 1,
                    "error": None,
                }
            except Exception as e:
                observation = f"工具执行异常：{e}"

            history.append({
                "thought": thought,
                "tool": tool_name,
                "args": tool_args,
                "observation": observation,
            })

        # 超过 max_steps，强制用 analyst 角色汇总
        if progress_callback:
            progress_callback("已达最大步数，强制生成最终答案…")

        fallback_prompt = (
            f"用户问题：{question}\n\n"
            "以下是调研过程中收集到的所有信息：\n\n"
            + "\n\n".join(
                f"【步骤{i+1}观察】\n{s['observation']}"
                for i, s in enumerate(history)
                if s.get("observation") and s["observation"] != "(任务完成)"
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
            "step_count": max_steps,
            "error": None,
        }

    except Exception as e:
        tb = traceback.format_exc()
        return {
            "answer": f"Agent 运行出错：{e}",
            "steps": history,
            "step_count": len(history),
            "error": tb,
        }
