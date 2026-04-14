"""
skills/router.py —— ReAct 工具路由层

把"给 LLM 看所有 14 个工具"改成"按问题类型和对话状态按需呈现"。
分四层递进：

  1. 入口预路由（route_entry）
     根据 classify_question 的结果，返回本次对话的 skill 白名单 + 起手 skill
     让 LLM 在 ReAct 的每一步只看到相关工具，减少选择噪音。

  2. 候选 shortlist（build_shortlist_prompt）
     把白名单渲染进系统提示，附上"起手建议"和可选参数说明。

  3. 步间状态路由（suggest_next_step）
     根据上一步 observation / step 数 / 已登记来源数，
     追加一段"建议下一步考虑 X / Y"的动态提示，不强制但强引导。

  4. 重复 / 误选纠偏（check_loop）
     检测到重复调用同一 (tool, key_arg)、或连续 N 步无新来源时，
     注入硬警告或强制 finish。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from report import QuestionType

if TYPE_CHECKING:
    from report import CitationRegistry


# ══════════════════════════════════════════════
# 1. 入口预路由：问题类型 → skill 白名单 + 起手
# ══════════════════════════════════════════════

# finish 恒定在白名单里，不需要重复列
_ALWAYS_ALLOWED = {"finish"}

# 每种问题类型配一套 skill 白名单（按相关性排序，起手靠前）
ROUTE_MAP: dict[QuestionType, list[str]] = {
    QuestionType.FACTUAL: [
        "search", "rag_retrieve", "search_site", "scrape",
    ],
    QuestionType.LIST: [
        "search_multi", "search", "search_docs", "scrape_batch", "scrape", "extract",
    ],
    QuestionType.COMPARE: [
        "search_multi", "search_company", "search", "scrape_batch", "scrape", "extract",
    ],
    QuestionType.TREND: [
        "search_news", "search_recent", "search", "scrape", "extract",
    ],
    QuestionType.TIMELINE: [
        "search_news", "search_recent", "search", "scrape",
    ],
    QuestionType.ANALYSIS: [
        "search_multi", "search", "scrape", "extract", "summarize",
    ],
    QuestionType.RECOMMEND: [
        "search_multi", "search", "search_docs", "scrape", "extract",
    ],
    QuestionType.FINANCIAL: [
        "search_company", "search_docs", "search", "scrape", "extract",
    ],
    # RESEARCH 兜底 → 全开
    QuestionType.RESEARCH: [
        "search", "search_multi", "search_news", "search_site",
        "search_company", "search_docs", "search_recent",
        "scrape", "scrape_batch", "extract", "extract_links",
        "summarize", "rag_retrieve",
    ],
}

# 每种类型的起手推荐（LLM 第一步优先选这个）
STARTER_MAP: dict[QuestionType, str] = {
    QuestionType.FACTUAL:   "search",
    QuestionType.LIST:      "search_multi",
    QuestionType.COMPARE:   "search_multi",
    QuestionType.TREND:     "search_news",
    QuestionType.TIMELINE:  "search_news",
    QuestionType.ANALYSIS:  "search_multi",
    QuestionType.RECOMMEND: "search_multi",
    QuestionType.FINANCIAL: "search_company",
    QuestionType.RESEARCH:  "search",
}


@dataclass(slots=True)
class EntryRoute:
    """入口预路由的产物。"""
    qtype: QuestionType
    allowed_skills: list[str]          # 不含 finish，prompt 渲染时由调用方追加
    starter: str                       # 建议的起手 skill

    def allowed_with_finish(self) -> list[str]:
        return [*self.allowed_skills, "finish"]


def route_entry(
    qtype: QuestionType,
    available_skills: list[str],
) -> EntryRoute:
    """
    入口预路由：按问题类型选白名单，再跟已注册的 skill 取交集。

    参数：
        qtype:              classify_question 的结果
        available_skills:   SkillRegistry.names() —— 防止路由到未注册的 skill

    返回：EntryRoute（白名单 + 起手）
    """
    wanted = ROUTE_MAP.get(qtype, ROUTE_MAP[QuestionType.RESEARCH])
    available_set = set(available_skills)
    # 保持白名单顺序，过滤掉未注册的
    filtered = [s for s in wanted if s in available_set]
    if not filtered:
        # 极端情况：该类型所有推荐都没注册 → 退回已注册全集
        filtered = [s for s in available_skills if s not in _ALWAYS_ALLOWED]

    starter = STARTER_MAP.get(qtype, "search")
    if starter not in available_set:
        starter = filtered[0] if filtered else "search"

    return EntryRoute(qtype=qtype, allowed_skills=filtered, starter=starter)


# ══════════════════════════════════════════════
# 3. 步间状态路由：根据历史推荐下一步
# ══════════════════════════════════════════════

def suggest_next_step(
    history: list[dict],
    step_num: int,
    max_steps: int,
    registry: "CitationRegistry | None" = None,
) -> str:
    """
    根据对话历史输出一段"下一步建议"文字（空串表示无特别建议）。

    判定规则（按优先级自上而下，只返回第一个命中的）：
      - 接近 max_steps（≥ 80%）：强烈建议 finish
      - 已登记来源 ≥ 5 且最近一步是 search*：建议开始 scrape / finish
      - 最近一步 search* 且 sources 为空：换关键词或换 search_multi
      - 最近一步 scrape* 且内容 ≥ 3000 字：建议 extract / summarize
      - 最近一步 scrape* 且内容 < 500 字：换 URL 或回到搜索
      - 连续 3 步工具类型相同：提示切换
    """
    if step_num >= int(max_steps * 0.8):
        return "⚠️ 已接近最大步数，若信息已够请立刻调用 finish。"

    if not history:
        return ""

    last = history[-1]
    last_tool: str = last.get("tool", "")
    last_sources = last.get("sources", []) or []
    last_obs: str = last.get("observation", "") or ""
    registry_size = len(registry) if registry is not None else 0

    if registry_size >= 5 and last_tool.startswith("search"):
        return (
            f"💡 已累计 {registry_size} 条来源，建议开始 scrape 重点页面或直接 finish 编排报告。"
        )

    if last_tool.startswith("search") and not last_sources:
        return (
            "💡 上一次搜索无结果，建议换一组关键词、或改用 search_multi / search_recent 扩大视角。"
        )

    if last_tool.startswith("scrape"):
        obs_len = len(last_obs)
        if obs_len >= 3000:
            return (
                "💡 页面内容较长，建议下一步 extract 定向抽取关键信息，或 summarize 压缩要点。"
            )
        if 0 < obs_len < 500:
            return (
                "💡 页面内容偏少，可能不是目标页。建议换一个 URL，或回到 search 补充来源。"
            )

    # 连续同类工具三步
    if len(history) >= 3:
        last_three = [h.get("tool", "") for h in history[-3:]]
        prefixes = {_tool_prefix(t) for t in last_three}
        if len(prefixes) == 1 and "finish" not in prefixes:
            prefix = next(iter(prefixes))
            return (
                f"💡 连续 3 步都在 {prefix}*，建议切换类型（search→scrape→extract→finish）。"
            )

    return ""


def _tool_prefix(tool: str) -> str:
    """把 search_news / search_multi 归类为 'search'；scrape_batch → 'scrape'。"""
    if tool.startswith("search"):
        return "search"
    if tool.startswith("scrape"):
        return "scrape"
    if tool.startswith("extract"):
        return "extract"
    return tool


# ══════════════════════════════════════════════
# 4. 重复 / 误选纠偏
# ══════════════════════════════════════════════

@dataclass(slots=True)
class LoopGuardResult:
    """纠偏检查的结果。"""
    ok: bool                       # True=动作可以执行；False=需要拦截
    reason: str = ""               # 拦截原因（用于提示 LLM）
    force_finish: bool = False     # True=必须直接 finish
    warning: str = ""              # ok=True 但要带的警告文字


def check_loop(
    tool: str,
    args: dict,
    history: list[dict],
    registry_size_before: int,
    registry_size_now: int,
) -> LoopGuardResult:
    """
    纠偏 1：完全相同的 (tool, key_arg) 调用超过 2 次 → 拦截
    纠偏 2：连续 3 步没给 registry 新增来源 → 强制 finish
    纠偏 3：scrape/extract 的 url 未在任何历史来源里出现 → 软警告

    参数：
        tool / args:               当前 LLM 选择的动作
        history:                   已完成的步骤列表
        registry_size_before:      本步执行前的 registry 大小
        registry_size_now:         最近一次成功步骤结束时的 registry 大小
    """
    sig = _action_signature(tool, args)

    # 纠偏 1：重复调用
    if sig:
        prior_same = sum(
            1 for h in history
            if _action_signature(h.get("tool", ""), h.get("args", {})) == sig
        )
        if prior_same >= 2:
            return LoopGuardResult(
                ok=False,
                reason=(
                    f"检测到你已经调用过 `{tool}` 同样的参数 {prior_same} 次。"
                    f"请换工具或换参数，不要再重复。"
                ),
            )

    # 纠偏 2：连续无新来源
    if _stalled_no_new_sources(history, lookback=3):
        return LoopGuardResult(
            ok=True,
            force_finish=True,
            warning=(
                "⛔ 最近 3 步都没有新增任何来源，强制进入 finish。"
                "请基于已有观察直接编排最终答案。"
            ),
        )

    # 纠偏 3：scrape/extract URL 未在历史来源中
    if tool in ("scrape", "extract", "scrape_batch", "scrape_deep"):
        url_arg = args.get("url") or args.get("urls") or ""
        if url_arg and not _url_seen_in_history(url_arg, history):
            return LoopGuardResult(
                ok=True,
                warning=(
                    f"⚠️ 你要抓取的 URL 在前面的搜索结果里没有出现过，"
                    f"确认这是可信来源后再继续。"
                ),
            )

    return LoopGuardResult(ok=True)


def _action_signature(tool: str, args: dict) -> str:
    """把 (tool, 关键参数) 压成一个签名字符串，用于判重。"""
    if not tool or tool == "finish":
        return ""
    # 选择该 tool 的第一个关键字参数作为指纹（query / url / text 等）
    for key in ("query", "url", "urls", "text", "company", "instruction"):
        if key in args:
            value = str(args[key]).strip().lower()
            if value:
                return f"{tool}::{key}={value}"
    return f"{tool}::{str(sorted(args.items()))[:120]}"


def _stalled_no_new_sources(history: list[dict], lookback: int = 3) -> bool:
    """最近 lookback 步里全部 cite_ids 为空 → 没有新来源进入 registry。"""
    if len(history) < lookback:
        return False
    recent = history[-lookback:]
    # 只看非 finish 的步骤
    non_finish = [h for h in recent if h.get("tool") != "finish"]
    if len(non_finish) < lookback:
        return False
    return all(not h.get("cite_ids") for h in non_finish)


def _url_seen_in_history(url: str, history: list[dict]) -> bool:
    """判断某个 URL 是否在历史的 sources 里登记过。"""
    target = url.strip().lower().rstrip("/")
    if not target:
        return False
    for h in history:
        for src in h.get("sources", []) or []:
            raw = src.get("url", "") if isinstance(src, dict) else ""
            if raw.strip().lower().rstrip("/") == target:
                return True
    return False
