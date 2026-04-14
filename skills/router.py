"""
Routing helpers for the ReAct skill loop.

This module now has two layers:
1. entry routing / route preview
2. step-level nudges and loop guards
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING

from report import QuestionType, classify_question

if TYPE_CHECKING:
    from report import CitationRegistry


_ALWAYS_ALLOWED = {"finish"}
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


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
    QuestionType.RESEARCH: [
        "search", "search_multi", "search_news", "search_site",
        "search_company", "search_docs", "search_recent",
        "scrape", "scrape_batch", "extract", "extract_links",
        "summarize", "rag_retrieve",
    ],
}

STARTER_MAP: dict[QuestionType, str] = {
    QuestionType.FACTUAL: "search",
    QuestionType.LIST: "search_multi",
    QuestionType.COMPARE: "search_multi",
    QuestionType.TREND: "search_news",
    QuestionType.TIMELINE: "search_news",
    QuestionType.ANALYSIS: "search_multi",
    QuestionType.RECOMMEND: "search_multi",
    QuestionType.FINANCIAL: "search_company",
    QuestionType.RESEARCH: "search",
}

_SIGNAL_PRIORITY_MAP: dict[str, list[str]] = {
    "docs": ["search_docs", "search_site", "extract_links", "scrape_deep", "scrape", "extract"],
    "company": ["search_company", "search_recent", "search_news", "scrape", "extract"],
    "news": ["search_news", "search_recent", "search", "scrape"],
    "site": ["search_site", "scrape", "extract_links"],
    "entry_url": ["extract_links", "scrape", "scrape_batch", "scrape_deep", "extract"],
}

_SIGNAL_PREFERRED_MAP: dict[str, list[str]] = {
    "docs": ["search_docs", "search_site", "extract_links"],
    "company": ["search_company", "search_recent", "search_news"],
    "news": ["search_news", "search_recent"],
    "site": ["search_site", "scrape"],
    "entry_url": ["extract_links", "scrape"],
}

_SIGNAL_DISCOURAGED_MAP: dict[str, list[str]] = {
    "docs": ["search_news", "search_company"],
    "company": ["search_docs"],
    "news": ["search_docs", "search_company"],
    "site": ["search_multi"],
    "entry_url": ["search_multi", "search_news"],
}

_STRONG_SIGNALS: tuple[str, ...] = ("site", "entry_url")

_QUESTION_TYPE_DISCOURAGED: dict[QuestionType, list[str]] = {
    QuestionType.FACTUAL: ["search_news", "scrape_deep", "scrape_batch"],
    QuestionType.LIST: ["search_news"],
    QuestionType.COMPARE: ["search_news"],
    QuestionType.TREND: ["search_docs"],
    QuestionType.TIMELINE: ["search_docs"],
    QuestionType.ANALYSIS: ["search_news"],
    QuestionType.RECOMMEND: ["search_news"],
    QuestionType.FINANCIAL: ["scrape_deep", "scrape_batch"],
    QuestionType.RESEARCH: [],
}

_DOC_KEYWORDS = (
    "api", "sdk", "guide", "manual", "reference", "documentation", "docs",
    "开发者", "文档", "官方文档", "参考", "指南", "手册", "接口",
)
_COMPANY_KEYWORDS = (
    "财报", "投资者关系", "investor relations", "earnings", "press release",
    "年报", "季报", "官网", "公告", "ir", "股东信",
)
_NEWS_KEYWORDS = (
    "最新", "最近", "近期", "动态", "新闻", "发布", "进展", "本周", "本月",
    "today", "latest", "recent", "update", "updates", "announcement", "announcements",
)


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def _move_to_front(items: list[str], preferred: list[str]) -> list[str]:
    return _dedupe_keep_order(preferred + items)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _detect_route_signals(question: str) -> list[str]:
    text = question.strip()
    lowered = text.lower()
    signals: list[str] = []

    if _contains_any(lowered, _DOC_KEYWORDS):
        signals.append("docs")
    if _contains_any(lowered, _COMPANY_KEYWORDS):
        signals.append("company")
    if _contains_any(lowered, _NEWS_KEYWORDS):
        signals.append("news")
    if "site:" in lowered or re.search(r"\b[a-z0-9-]+\.[a-z]{2,}\b", lowered):
        signals.append("site")
    if _URL_RE.search(text):
        signals.append("entry_url")

    return _dedupe_keep_order(signals)


def _signal_reason(signal: str) -> str:
    reasons = {
        "docs": "命中文档/API 关键词，优先官方文档检索与同站抓取。",
        "company": "命中公司/财报/IR 关键词，优先官网与投资者关系信息。",
        "news": "命中最新/动态/发布类表达，优先新闻与近期搜索。",
        "site": "问题限定了站点或域名，优先站内检索与同域抓取。",
        "entry_url": "问题里已提供 URL，优先直接抓入口页或先抽候选链接。",
    }
    return reasons.get(signal, "")


@dataclass(slots=True)
class EntryRoute:
    qtype: QuestionType
    allowed_skills: list[str]
    starter: str

    def allowed_with_finish(self) -> list[str]:
        return [*self.allowed_skills, "finish"]


@dataclass(slots=True)
class RouteDecision:
    qtype: QuestionType
    allowed: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    discouraged: list[str] = field(default_factory=list)
    starter: str = ""
    reasons: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    def allowed_with_finish(self) -> list[str]:
        return [*self.allowed, "finish"]

    def as_dict(self) -> dict:
        return {
            "question_type": self.qtype.value,
            "allowed_skills": list(self.allowed),
            "preferred_skills": list(self.preferred),
            "discouraged_skills": list(self.discouraged),
            "starter": self.starter,
            "reasons": list(self.reasons),
            "signals": list(self.signals),
        }


def build_route_decision(
    qtype: QuestionType,
    available_skills: list[str],
    *,
    question: str = "",
    profile_name: str = "",
) -> RouteDecision:
    visible = _dedupe_keep_order([name for name in available_skills if name not in _ALWAYS_ALLOWED])
    visible_set = set(visible)
    signals = _detect_route_signals(question)

    ordered = list(ROUTE_MAP.get(qtype, ROUTE_MAP[QuestionType.RESEARCH]))
    preferred: list[str] = []
    discouraged: list[str] = list(_QUESTION_TYPE_DISCOURAGED.get(qtype, []))
    reasons = [f"问题分类命中 `{qtype.value}`。"]
    if profile_name:
        reasons.append(f"当前 skill profile 为 `{profile_name}`。")

    for signal in signals:
        ordered = _move_to_front(ordered, _SIGNAL_PRIORITY_MAP.get(signal, []))
        preferred.extend(_SIGNAL_PREFERRED_MAP.get(signal, []))
        discouraged.extend(_SIGNAL_DISCOURAGED_MAP.get(signal, []))
        reason = _signal_reason(signal)
        if reason:
            reasons.append(reason)

    filtered = [name for name in _dedupe_keep_order(ordered) if name in visible_set]
    if not filtered:
        filtered = list(visible)
        if filtered:
            reasons.append("题型推荐技能当前都不可见，已回退到当前 profile 可见技能全集。")
    else:
        missing = [name for name in _dedupe_keep_order(ordered) if name not in visible_set]
        if missing:
            reasons.append(f"以下推荐技能被当前 profile 或 enabled 配置过滤：{missing[:5]}")

    preferred_filtered = [name for name in _dedupe_keep_order(preferred) if name in filtered]
    if not preferred_filtered:
        preferred_filtered = filtered[: min(3, len(filtered))]

    for signal in _STRONG_SIGNALS:
        if signal in signals:
            filtered = _dedupe_keep_order(_SIGNAL_PRIORITY_MAP.get(signal, []) + filtered)
            preferred_filtered = _dedupe_keep_order(
                _SIGNAL_PREFERRED_MAP.get(signal, []) + preferred_filtered
            )
            reasons.append(f"强信号 `{signal}` 覆盖了较弱的词义信号排序。")

    filtered = _dedupe_keep_order(preferred_filtered + filtered)

    discouraged_filtered = [
        name for name in _dedupe_keep_order(discouraged)
        if name in visible_set and name not in preferred_filtered
    ][:4]

    starter = STARTER_MAP.get(qtype, "search")
    if preferred_filtered:
        starter = preferred_filtered[0]
    elif starter not in visible_set or starter not in filtered:
        starter = filtered[0] if filtered else ""

    if starter:
        reasons.append(f"建议起手技能为 `{starter}`。")
    else:
        reasons.append("当前没有可用的起手技能。")

    return RouteDecision(
        qtype=qtype,
        allowed=filtered,
        preferred=preferred_filtered,
        discouraged=discouraged_filtered,
        starter=starter,
        reasons=reasons,
        signals=signals,
    )


def route_entry(
    qtype: QuestionType,
    available_skills: list[str],
    *,
    question: str = "",
) -> EntryRoute:
    decision = build_route_decision(qtype, available_skills, question=question)
    return EntryRoute(qtype=decision.qtype, allowed_skills=decision.allowed, starter=decision.starter)


def preview_route(
    question: str,
    available_skills: list[str],
    *,
    engine: str = "",
    profile_name: str = "",
) -> RouteDecision:
    qtype = classify_question(question, engine)
    return build_route_decision(
        qtype,
        available_skills,
        question=question,
        profile_name=profile_name,
    )


def suggest_next_step(
    history: list[dict],
    step_num: int,
    max_steps: int,
    registry: "CitationRegistry | None" = None,
) -> str:
    """
    Return a short nudge for the next step. Empty string means no hint.
    """
    if step_num >= int(max_steps * 0.8):
        return "⚠️ 已接近最大步数，若信息已足请立即调用 finish。"

    if not history:
        return ""

    last = history[-1]
    last_tool: str = last.get("tool", "")
    last_sources = last.get("sources", []) or []
    last_obs: str = last.get("observation", "") or ""
    registry_size = len(registry) if registry is not None else 0

    if registry_size >= 5 and last_tool.startswith("search"):
        return (
            f"📕 已累计 {registry_size} 条来源，建议开始 scrape 重点页面或直接 finish 编排报告。"
        )

    if last_tool.startswith("search") and not last_sources:
        return (
            "📕 上一次搜索无结果，建议换一组关键词，或改用 search_multi / search_recent 扩大视角。"
        )

    if last_tool.startswith("scrape"):
        obs_len = len(last_obs)
        if obs_len >= 3000:
            return (
                "📕 页面内容较长，建议下一步 extract 定向抽取关键信息，或 summarize 压缩要点。"
            )
        if 0 < obs_len < 500:
            return (
                "📕 页面内容偏少，可能不是目标页。建议换一个 URL，或回到 search 补充来源。"
            )

    if len(history) >= 3:
        last_three = [h.get("tool", "") for h in history[-3:]]
        prefixes = {_tool_prefix(t) for t in last_three}
        if len(prefixes) == 1 and "finish" not in prefixes:
            prefix = next(iter(prefixes))
            return (
                f"📕 连续 3 步都在 {prefix}*，建议切换类型（search -> scrape -> extract -> finish）。"
            )

    return ""


def _tool_prefix(tool: str) -> str:
    if tool.startswith("search"):
        return "search"
    if tool.startswith("scrape"):
        return "scrape"
    if tool.startswith("extract"):
        return "extract"
    return tool


@dataclass(slots=True)
class LoopGuardResult:
    ok: bool
    reason: str = ""
    force_finish: bool = False
    warning: str = ""


def check_loop(
    tool: str,
    args: dict,
    history: list[dict],
    registry_size_before: int,
    registry_size_now: int,
) -> LoopGuardResult:
    """
    1. Block repeated identical (tool, key_arg) calls after two prior attempts.
    2. Force finish if the last 3 non-finish steps added no new sources.
    3. Warn when scraping a URL that never appeared in prior sources.
    """
    sig = _action_signature(tool, args)

    if sig:
        prior_same = sum(
            1
            for h in history
            if _action_signature(h.get("tool", ""), h.get("args", {})) == sig
        )
        if prior_same >= 2:
            return LoopGuardResult(
                ok=False,
                reason=(
                    f"检测到你已经调用过 `{tool}` 同样的参数 {prior_same} 次。"
                    "请换工具或换参数，不要再重复。"
                ),
            )

    if _stalled_no_new_sources(history, lookback=3):
        return LoopGuardResult(
            ok=True,
            force_finish=True,
            warning=(
                "⚠️ 最近 3 步都没有新增任何来源，强制进入 finish。"
                "请基于已有观察直接编排最终答案。"
            ),
        )

    if tool in ("scrape", "extract", "scrape_batch", "scrape_deep"):
        url_arg = args.get("url") or args.get("urls") or ""
        if url_arg and not _url_seen_in_history(url_arg, history):
            return LoopGuardResult(
                ok=True,
                warning=(
                    "⚠️ 你要抓取的 URL 在前面的搜索结果里没有出现过。"
                    "确认这是可信来源后再继续。"
                ),
            )

    return LoopGuardResult(ok=True)


def _action_signature(tool: str, args: dict) -> str:
    if not tool or tool == "finish":
        return ""
    for key in ("query", "url", "urls", "text", "company", "instruction"):
        if key in args:
            value = str(args[key]).strip().lower()
            if value:
                return f"{tool}::{key}={value}"
    return f"{tool}::{str(sorted(args.items()))[:120]}"


def _stalled_no_new_sources(history: list[dict], lookback: int = 3) -> bool:
    if len(history) < lookback:
        return False
    recent = history[-lookback:]
    non_finish = [h for h in recent if h.get("tool") != "finish"]
    if len(non_finish) < lookback:
        return False
    return all(not h.get("cite_ids") for h in non_finish)


def _url_seen_in_history(url: str, history: list[dict]) -> bool:
    target = url.strip().lower().rstrip("/")
    if not target:
        return False
    for h in history:
        for src in h.get("sources", []) or []:
            raw = src.get("url", "") if isinstance(src, dict) else ""
            if raw.strip().lower().rstrip("/") == target:
                return True
    return False
