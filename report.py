"""
report.py — 报告生成层（阶段 A）

职责：
  - Source / Observation：结构化观察 + 来源
  - CitationRegistry：统一编号引用，产出参考来源 Markdown
  - QuestionType + classify_question：按问题类型分化
  - compose_report：按类型选模板，编排最终报告

agent_loop.py 与 agent_planner.py 调本模块产出报告，
不再让主循环 LLM 自己写 finish 里的完整 Markdown。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from agent import ai_generate_role, extract_json
from prompts import (
    prompt_classify_question,
    prompt_report_factual,
    prompt_report_list,
    prompt_report_compare,
    prompt_report_trend,
    prompt_report_timeline,
    prompt_report_analysis,
    prompt_report_recommend,
    prompt_report_financial,
    prompt_report_research,
)


# ══════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════
class Source(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""

    def dedupe_key(self) -> str:
        return self.url.strip().rstrip("/").lower()


class Observation(BaseModel):
    content: str
    sources: list[Source] = Field(default_factory=list)
    tool: str = ""
    args: dict = Field(default_factory=dict)
    cite_ids: list[int] = Field(default_factory=list)


# ══════════════════════════════════════════════
# CitationRegistry：自动编号引用
# ══════════════════════════════════════════════
class CitationRegistry:
    """按 URL 去重登记来源，产出给 LLM 的引用表与最终报告的「参考来源」。"""

    def __init__(self) -> None:
        self._sources: list[Source] = []
        self._index: dict[str, int] = {}

    def add(self, source: Source) -> int:
        if not source.url:
            return 0
        key = source.dedupe_key()
        if key in self._index:
            existing = self._sources[self._index[key] - 1]
            if not existing.title and source.title:
                existing.title = source.title
            if not existing.snippet and source.snippet:
                existing.snippet = source.snippet
            return self._index[key]
        self._sources.append(source.model_copy())
        idx = len(self._sources)
        self._index[key] = idx
        return idx

    def add_many(self, sources: list[Source]) -> list[int]:
        return [i for i in (self.add(s) for s in sources if s.url) if i > 0]

    def for_prompt(self) -> str:
        if not self._sources:
            return ""
        return "\n".join(
            f"[{i}] {s.title or '（无标题）'} — {s.url}"
            for i, s in enumerate(self._sources, 1)
        )

    def as_refs_md(self) -> str:
        if not self._sources:
            return ""
        lines = ["## 参考来源", ""]
        for i, s in enumerate(self._sources, 1):
            title = s.title or s.url
            lines.append(f"{i}. [{title}]({s.url})")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._sources)


# ══════════════════════════════════════════════
# QuestionType + 分类器
# ══════════════════════════════════════════════
class QuestionType(str, Enum):
    FACTUAL   = "factual"
    LIST      = "list"
    COMPARE   = "compare"
    TREND     = "trend"
    TIMELINE  = "timeline"
    ANALYSIS  = "analysis"
    RECOMMEND = "recommend"
    FINANCIAL = "financial"
    RESEARCH  = "research"


_ROLE_MAP: dict[QuestionType, str] = {
    QuestionType.FINANCIAL: "orchestrator",
    QuestionType.COMPARE:   "orchestrator",
    QuestionType.ANALYSIS:  "orchestrator",
    QuestionType.FACTUAL:   "worker",
    QuestionType.LIST:      "worker",
    QuestionType.TREND:     "analyst",
    QuestionType.TIMELINE:  "analyst",
    QuestionType.RECOMMEND: "analyst",
    QuestionType.RESEARCH:  "analyst",
}

_PROMPT_MAP = {
    QuestionType.FACTUAL:   prompt_report_factual,
    QuestionType.LIST:      prompt_report_list,
    QuestionType.COMPARE:   prompt_report_compare,
    QuestionType.TREND:     prompt_report_trend,
    QuestionType.TIMELINE:  prompt_report_timeline,
    QuestionType.ANALYSIS:  prompt_report_analysis,
    QuestionType.RECOMMEND: prompt_report_recommend,
    QuestionType.FINANCIAL: prompt_report_financial,
    QuestionType.RESEARCH:  prompt_report_research,
}


def classify_question(question: str, engine: str = "") -> QuestionType:
    """轻量 LLM 分类，一次调用 worker 模型；解析失败默认 RESEARCH。"""
    try:
        raw = ai_generate_role(
            prompt_classify_question(question),
            role="worker",
            engine=engine,
            structured=True,
        )
    except Exception:
        return QuestionType.RESEARCH

    data = extract_json(raw)
    if not data or not isinstance(data, dict):
        return QuestionType.RESEARCH
    t = str(data.get("type", "")).strip().lower()
    try:
        return QuestionType(t)
    except ValueError:
        return QuestionType.RESEARCH


# ══════════════════════════════════════════════
# compose_report
# ══════════════════════════════════════════════
MAX_OBS_CHARS = 2500


def _format_history(history: list[Observation]) -> str:
    if not history:
        return "（无调研观察）"
    parts = []
    for i, obs in enumerate(history, 1):
        content = obs.content or ""
        if len(content) > MAX_OBS_CHARS:
            content = content[:MAX_OBS_CHARS] + "…（截断）"
        cite = (
            "，对应引用：" + "".join(f"[{n}]" for n in obs.cite_ids)
            if obs.cite_ids else ""
        )
        parts.append(
            f"### 观察 {i}（工具：{obs.tool}{cite}）\n{content}"
        )
    return "\n\n".join(parts)


def compose_report(
    question: str,
    history: list[Observation],
    registry: CitationRegistry,
    engine: str = "",
    question_type: QuestionType | None = None,
) -> str:
    """
    流程：
      1. 若 question_type 为 None，先调 classify_question
      2. 按类型选 prompt 模板 + LLM 角色
      3. 组装历史观察 + 可用引用 → 调 LLM
      4. 末尾拼接 registry.as_refs_md()
    """
    qtype = question_type or classify_question(question, engine)
    prompt_fn = _PROMPT_MAP.get(qtype, prompt_report_research)
    role = _ROLE_MAP.get(qtype, "analyst")

    history_text = _format_history(history)
    refs_text = registry.for_prompt() or "（无）"

    prompt = prompt_fn(question=question, history=history_text, refs=refs_text)

    body = ai_generate_role(
        prompt, role=role, engine=engine, structured=False,
    )
    refs_md = registry.as_refs_md()
    if refs_md:
        return f"{body.rstrip()}\n\n{refs_md}"
    return body
