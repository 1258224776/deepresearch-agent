"""
skills/search_recent.py —— 带时间窗的单次搜索

定位：对 DDG 搜索带上 timelimit=d/w/m/y，拿"最近 N 天/周/月/年"的结果。
适合：只想拿一批近期结果、不需要多变体展开时。
对比：search_news 是多变体 + 时间窗（更重）；search_recent 更轻。
"""

from __future__ import annotations

from report import Observation

from .adapters import ddgs_search, render_results_as_markdown, results_to_sources
from .base import Skill, SkillContext, SkillSpec


class SearchRecentSkill(Skill):
    """默认 timelimit='m'（最近一个月）。"""

    spec = SkillSpec(
        name="search_recent",
        desc="搜索近期信息，适合最近几天、几周、几个月的变化和更新。",
        args=["query"],
        optional_args=["timelimit", "max_results"],
        args_desc={
            "query": "搜索查询词",
            "timelimit": "时间范围：d/w/m/y，默认 m",
            "max_results": "返回结果数量，默认 6",
        },
        category="search",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        query = args.get("query", "").strip()
        period = str(args.get("timelimit", "m")).strip() or "m"
        max_results = int(str(args.get("max_results", "6")).strip() or "6")
        if ctx.progress_callback:
            ctx.progress_callback(f"近期搜索：{query}")
        results = ddgs_search(query, max_results=max(1, min(max_results, 10)), timelimit=period)
        return Observation(
            content=render_results_as_markdown(results) if results else "（近期搜索无结果）",
            sources=results_to_sources(results),
            tool=self.spec.name,
            args=args,
        )
