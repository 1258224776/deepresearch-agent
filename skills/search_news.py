"""
skills/search_news.py —— 新闻 / 动态向搜索

定位：对查询追加 "新闻 / 最新 公告 / 发布 进展" 三组变体，
配合默认的月内时间窗，适合获取"最近发生了什么"。
适合：TREND / TIMELINE 类问题的起手。
对比：search_recent 是单次带时间窗；search_news 是多变体 + 时间窗。
"""

from __future__ import annotations

from report import Observation

from .adapters import batch_search_queries, merge_result_sets, render_provider_summary, render_results_as_markdown, results_to_sources
from .base import Skill, SkillContext, SkillSpec


class SearchNewsSkill(Skill):
    """TREND / TIMELINE 的起手工具（见 skills/router.py）。"""

    spec = SkillSpec(
        name="search_news",
        desc="偏新闻导向的搜索，适合最新动态、发布、公告、事件进展。",
        args=["query"],
        optional_args=["timelimit", "max_results"],
        args_desc={
            "query": "新闻搜索查询词",
            "timelimit": "时间范围：d/w/m/y，默认 m",
            "max_results": "返回结果数量，默认 8",
        },
        category="search",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        query = args.get("query", "").strip()
        timelimit = str(args.get("timelimit", "m")).strip() or "m"
        max_results = int(str(args.get("max_results", "8")).strip() or "8")
        grouped = batch_search_queries(
            [
                f"{query} 新闻",
                f"{query} 最新 公告",
                f"{query} 发布 进展",
            ],
            max_results=min(max_results, 6),
            timelimit=timelimit,
        )
        results = merge_result_sets(*(items for _, items in grouped), limit=max(1, min(max_results, 10)))
        if ctx.progress_callback:
            ctx.progress_callback(f"新闻搜索：{query}")
        query_plan = "\n".join(f"- {item_query}" for item_query, _ in grouped)
        content = render_results_as_markdown(results) if results else "（新闻搜索无结果）"
        provider_summary = render_provider_summary(results)
        if query_plan:
            content = f"查询变体：\n{query_plan}\n\n搜索结果：\n{content}"
        if provider_summary:
            content = f"{provider_summary}\n\n{content}"
        return Observation(
            content=content,
            sources=results_to_sources(results),
            tool=self.spec.name,
            args=args,
        )
