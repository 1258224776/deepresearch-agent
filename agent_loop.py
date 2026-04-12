"""
agent_loop.py — ReAct Agent 核心（v2）

改进点（对比 _originals/agent_loop.py）：
  #1  LLM 输出用 Pydantic 校验，格式不合法自动重试（最多 MAX_PARSE_RETRIES 次）
  #3  上下文压缩：历史超过 COMPRESS_AFTER 轮时压缩旧观察，节省 token
  #4  工具集扩充：新增 extract（网页定向提取）/ summarize（文本摘要）/ search_site（定点搜索）
  #6  错误分类：区分 LLMSchemaError / SearchEmptyError / ScrapeFailedError /
               RagNotReadyError / RateLimitError，不再统一吞异常

每轮：思考(Thought) → 行动(Action) → 观察(Observation) → 再思考…
"""

from __future__ import annotations

import traceback
from typing import Callable

from pydantic import BaseModel, field_validator, ValidationError

from agent import ai_generate_role, ai_tool_call, extract_json
from tools import web_search, fetch_via_jina
from prompts import prompt_react_system

# ══════════════════════════════════════════════
# 常量
# ══════════════════════════════════════════════
MAX_PARSE_RETRIES = 2    # #1 LLM 输出格式不合法时最多重试次数
COMPRESS_AFTER    = 4    # #3 历史超过此步数后，压缩更早的观察
OBS_FULL_LEN      = 1500 # 近期步骤观察保留字符数
OBS_COMPRESSED    = 300  # 压缩后旧步骤观察保留字符数


# ══════════════════════════════════════════════
# #6 错误类型分类
# ══════════════════════════════════════════════
class AgentError(Exception):
    """Agent 基础异常"""

class LLMSchemaError(AgentError):
    """LLM 输出不符合预期 JSON schema"""

class SearchEmptyError(AgentError):
    """搜索无结果"""

class ScrapeFailedError(AgentError):
    """网页爬取失败"""

class RagNotReadyError(AgentError):
    """RAG 向量库未初始化"""

class RateLimitError(AgentError):
    """API 限速（429 / quota）"""


# ══════════════════════════════════════════════
# #4 工具注册表（扩充后）
# ══════════════════════════════════════════════
TOOLS: dict[str, dict] = {
    "search": {
        "desc": "搜索网络，获取相关网页标题和摘要列表",
        "args": ["query"],
    },
    "search_site": {
        "desc": "在指定网站内搜索，适合精准查找某域名下的内容",
        "args": ["query", "site"],
        "args_desc": {"query": "搜索词", "site": "限定域名，如 wikipedia.org"},
    },
    "scrape": {
        "desc": "爬取指定 URL 的完整正文内容",
        "args": ["url"],
    },
    "extract": {
        "desc": "爬取指定 URL 并按指令提取特定信息（比 scrape 更精准）",
        "args": ["url", "instruction"],
        "args_desc": {"instruction": "告诉 AI 要提取什么，如：提取所有产品价格"},
    },
    "summarize": {
        "desc": "对一段较长文本进行 AI 摘要，提炼核心要点",
        "args": ["text"],
    },
    "rag_retrieve": {
        "desc": "从用户已上传的本地文档中语义检索相关内容",
        "args": ["query"],
    },
    "finish": {
        "desc": "信息已足够，输出最终完整答案（Markdown 格式）",
        "args": ["answer"],
    },
}


# ══════════════════════════════════════════════
# #1 Pydantic 校验模型
# ══════════════════════════════════════════════
class ReActAction(BaseModel):
    thought: str
    tool: str
    args: dict

    @field_validator("tool")
    @classmethod
    def tool_must_be_known(cls, v: str) -> str:
        if v not in TOOLS:
            raise ValueError(
                f"未知工具 '{v}'，可用工具：{list(TOOLS.keys())}"
            )
        return v

    @field_validator("args")
    @classmethod
    def args_must_have_required(cls, v: dict, info) -> dict:
        tool_name = info.data.get("tool", "")
        required = TOOLS.get(tool_name, {}).get("args", [])
        missing = [k for k in required if k not in v]
        if missing:
            raise ValueError(
                f"工具 '{tool_name}' 缺少必填参数：{missing}"
            )
        return v


# ══════════════════════════════════════════════
# 内部：终止信号
# ══════════════════════════════════════════════
class _FinishSignal(Exception):
    def __init__(self, answer: str):
        self.answer = answer


# ══════════════════════════════════════════════
# #6 工具执行器（区分错误类型）
# ══════════════════════════════════════════════
def _run_tool(name: str, args: dict, progress_cb: Callable | None = None) -> str:
    """
    执行工具，返回观察结果字符串。
    出错时抛出具体的 AgentError 子类，而非统一吞异常。
    若 tool == "finish" 则 raise _FinishSignal。
    """
    if name == "finish":
        raise _FinishSignal(args.get("answer", ""))

    # ── search ──────────────────────────────
    if name == "search":
        query = args.get("query", "").strip()
        if progress_cb:
            progress_cb(f"🔍 搜索：{query}")
        results = web_search(query, max_results=5)
        if not results:
            raise SearchEmptyError(f"搜索 '{query}' 无结果，请换关键词")
        lines = [
            f"- [{r.get('title','无标题')}]({r.get('href','')})\n  {r.get('body','')[:200]}"
            for r in results
        ]
        return "\n".join(lines)

    # ── search_site ──────────────────────────
    if name == "search_site":
        query = args.get("query", "").strip()
        site  = args.get("site", "").strip()
        full_query = f"site:{site} {query}" if site else query
        if progress_cb:
            progress_cb(f"🔍 定点搜索：{full_query}")
        results = web_search(full_query, max_results=5)
        if not results:
            raise SearchEmptyError(f"在 {site} 内搜索 '{query}' 无结果")
        lines = [
            f"- [{r.get('title','无标题')}]({r.get('href','')})\n  {r.get('body','')[:200]}"
            for r in results
        ]
        return "\n".join(lines)

    # ── scrape ───────────────────────────────
    if name == "scrape":
        url = args.get("url", "").strip()
        if progress_cb:
            progress_cb(f"🌐 爬取：{url}")
        content = fetch_via_jina(url, max_chars=6000)
        if not content or content.startswith("（"):
            raise ScrapeFailedError(f"爬取失败：{url}（返回内容为空或错误）")
        return content[:6000]

    # ── extract ──────────────────────────────
    if name == "extract":
        url         = args.get("url", "").strip()
        instruction = args.get("instruction", "提取核心内容").strip()
        if progress_cb:
            progress_cb(f"🔎 提取：{url} → {instruction}")
        content = fetch_via_jina(url, max_chars=8000)
        if not content or content.startswith("（"):
            raise ScrapeFailedError(f"爬取失败，无法提取：{url}")
        # 调用 AI 按指令提取
        extract_prompt = (
            f"请从以下网页内容中，按照指令提取信息。\n\n"
            f"指令：{instruction}\n\n"
            f"网页内容：\n{content[:6000]}\n\n"
            f"只输出提取结果，不要废话。"
        )
        result = ai_generate_role(extract_prompt, role="worker", structured=False)
        return result

    # ── summarize ────────────────────────────
    if name == "summarize":
        text = args.get("text", "").strip()
        if not text:
            return "（summarize：输入文本为空）"
        if progress_cb:
            progress_cb("📝 AI 摘要生成中…")
        summary_prompt = (
            f"请对以下文本进行简洁摘要，提炼核心要点，用中文输出，不超过 300 字：\n\n{text[:4000]}"
        )
        return ai_generate_role(summary_prompt, role="worker", structured=False)

    # ── rag_retrieve ─────────────────────────
    if name == "rag_retrieve":
        query = args.get("query", "").strip()
        if progress_cb:
            progress_cb(f"📂 RAG 检索：{query}")
        try:
            import rag
            if not rag.is_ready():
                raise RagNotReadyError("本地文档向量库未初始化，请先上传文档")
            return rag.retrieve_as_context(query, top_k=3)
        except RagNotReadyError:
            raise
        except Exception as e:
            # 区分是否为限速错误
            err_str = str(e).lower()
            if any(k in err_str for k in ("429", "quota", "rate", "limit")):
                raise RateLimitError(f"RAG 检索触发限速：{e}")
            raise AgentError(f"RAG 检索异常：{e}") from e

    return f"未知工具：{name}"


# ══════════════════════════════════════════════
# #3 上下文压缩：压缩旧步骤的观察内容
# ══════════════════════════════════════════════
def _compress_history(history: list[dict]) -> list[dict]:
    """
    当历史超过 COMPRESS_AFTER 步时，
    将前面的旧步骤观察截断为 OBS_COMPRESSED 字符，
    保留最近 COMPRESS_AFTER 步完整。
    """
    if len(history) <= COMPRESS_AFTER:
        return history

    compressed = []
    cutoff = len(history) - COMPRESS_AFTER

    for i, step in enumerate(history):
        if i < cutoff:
            obs = step.get("observation", "")
            if len(obs) > OBS_COMPRESSED:
                obs = obs[:OBS_COMPRESSED] + "…（已压缩）"
            compressed.append({**step, "observation": obs})
        else:
            compressed.append(step)

    return compressed


# ══════════════════════════════════════════════
# Prompt 构建
# ══════════════════════════════════════════════
def _build_prompt(question: str, history: list[dict]) -> str:
    """把问题 + 压缩后的历史拼成当轮 user prompt"""
    display = _compress_history(history)  # #3 先压缩再展示

    lines = [f"用户问题：{question}", ""]
    if display:
        lines.append("## 已执行步骤")
        for i, step in enumerate(display, 1):
            lines.append(f"\n### 步骤 {i}")
            lines.append(f"**思考**：{step['thought']}")
            lines.append(f"**工具**：{step['tool']}({step['args']})")
            obs = step.get("observation", "")
            if len(obs) > OBS_FULL_LEN:
                obs = obs[:OBS_FULL_LEN] + "\n…（已截断）"
            lines.append(f"**观察**：\n{obs}")
        lines.append("")
    lines.append("请根据以上步骤的结果，决定下一步行动。如果信息已经足够，调用 finish 输出最终答案。")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# #1 LLM 输出解析 + Pydantic 校验 + 重试
# ══════════════════════════════════════════════
def _parse_action(raw: str, engine: str, prompt: str, system: str) -> ReActAction:
    """
    解析 LLM 输出为 ReActAction。
    若格式不合法，把错误反馈给 LLM 重试（最多 MAX_PARSE_RETRIES 次）。
    """
    last_error: str = ""

    for attempt in range(MAX_PARSE_RETRIES + 1):
        if attempt > 0:
            # 把上次的校验错误反馈给 LLM，让它修正
            retry_prompt = (
                f"{prompt}\n\n"
                f"【上一次输出格式有误，请修正】\n"
                f"错误信息：{last_error}\n"
                f"请重新输出符合格式的单个 JSON，不要有其他内容。"
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
        except ValidationError as e:
            last_error = str(e)
            continue

    raise LLMSchemaError(
        f"LLM 输出经 {MAX_PARSE_RETRIES + 1} 次尝试仍不符合 schema。\n"
        f"最后错误：{last_error}\n最后原始输出：{raw[:300]}"
    )


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
        max_steps:         最大循环轮数
        progress_callback: 进度回调 fn(msg: str)

    返回：
        {
            "answer":     str,
            "steps":      list[dict],   # {thought, tool, args, observation, error_type?}
            "step_count": int,
            "error":      str | None,
        }
    """
    history: list[dict] = []
    system = prompt_react_system(TOOLS)

    try:
        for step_num in range(max_steps):
            if progress_callback:
                progress_callback(f"第 {step_num + 1} 步推理中…")

            prompt = _build_prompt(question, history)

            # ── #2 优先尝试原生 Function Calling，失败降级 JSON 模式 ──
            action: ReActAction | None = None
            try:
                tool_name, tool_args, thought = ai_tool_call(
                    prompt, system=system, tools=TOOLS,
                    role="orchestrator", engine=engine,
                )
                action = ReActAction(
                    thought=thought or f"(原生调用 {tool_name})",
                    tool=tool_name,
                    args=tool_args,
                )
                print(f"[Agent] 步骤 {step_num + 1} 使用原生调用 → {tool_name}")
            except Exception as native_err:
                print(f"[Agent] 原生调用失败，降级 JSON 模式: {native_err}")

            if action is None:
                # 降级：JSON 模式
                raw = ai_generate_role(
                    prompt,
                    system=system,
                    role="orchestrator",
                    engine=engine,
                    structured=True,
                )
                try:
                    action = _parse_action(raw, engine, prompt, system)
                except LLMSchemaError as e:
                    history.append({
                        "thought": "(格式错误)",
                        "tool": "none",
                        "args": {},
                        "observation": str(e),
                        "error_type": "LLMSchemaError",
                    })
                    continue

            # 执行工具
            try:
                observation = _run_tool(action.tool, action.args, progress_callback)

            except _FinishSignal as fin:
                history.append({
                    "thought": action.thought,
                    "tool": "finish",
                    "args": action.args,
                    "observation": "(任务完成)",
                })
                return {
                    "answer": fin.answer,
                    "steps": history,
                    "step_count": step_num + 1,
                    "error": None,
                }

            # #6 分类错误，记录 error_type，继续循环（不崩溃）
            except SearchEmptyError as e:
                observation = f"[搜索为空] {e}"
                history.append({
                    "thought": action.thought, "tool": action.tool,
                    "args": action.args, "observation": observation,
                    "error_type": "SearchEmptyError",
                })
                continue

            except ScrapeFailedError as e:
                observation = f"[爬取失败] {e}"
                history.append({
                    "thought": action.thought, "tool": action.tool,
                    "args": action.args, "observation": observation,
                    "error_type": "ScrapeFailedError",
                })
                continue

            except RagNotReadyError as e:
                observation = f"[RAG未就绪] {e}"
                history.append({
                    "thought": action.thought, "tool": action.tool,
                    "args": action.args, "observation": observation,
                    "error_type": "RagNotReadyError",
                })
                continue

            except RateLimitError as e:
                observation = f"[限速] {e}，等待后重试或换关键词"
                history.append({
                    "thought": action.thought, "tool": action.tool,
                    "args": action.args, "observation": observation,
                    "error_type": "RateLimitError",
                })
                continue

            except AgentError as e:
                observation = f"[工具错误] {e}"
                history.append({
                    "thought": action.thought, "tool": action.tool,
                    "args": action.args, "observation": observation,
                    "error_type": "AgentError",
                })
                continue

            history.append({
                "thought": action.thought,
                "tool": action.tool,
                "args": action.args,
                "observation": observation,
            })

        # 超过 max_steps，强制汇总
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
            fallback_prompt, role="analyst", engine=engine, structured=False,
        )
        return {
            "answer": answer,
            "steps": history,
            "step_count": max_steps,
            "error": None,
        }

    except Exception as e:
        return {
            "answer": f"Agent 运行出错：{e}",
            "steps": history,
            "step_count": len(history),
            "error": traceback.format_exc(),
        }
