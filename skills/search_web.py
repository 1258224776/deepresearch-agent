"""
skills/search_web.py —— 通用互联网搜索（DDG）

定位：最朴素的搜索工具，查一次、拿回标题 / 摘要 / 链接。
适合：单一事实题、首轮探路。
不适合：需要对比 / 多视角 —— 请用 search_multi。
"""

from __future__ import annotations

from report import Observation

from .base import Skill, SkillContext, SkillSpec
from .adapters import render_provider_summary, render_results_as_markdown, results_to_sources, search_results


class SearchWebSkill(Skill):
    """FACTUAL / RESEARCH 类问题的默认起手工具。"""

    spec = SkillSpec(
        name="search",
        desc="搜索互联网，返回相关网页标题、摘要和链接。",
        args=["query"],
        optional_args=["max_results", "timelimit"],
        args_desc={
            "query": "搜索查询词",
            "max_results": "返回结果数量，默认 6",
            "timelimit": "时间范围：d/w/m/y",
        },
        category="search",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        query = args.get("query", "").strip()
        max_results = int(str(args.get("max_results", "6")).strip() or "6")
        timelimit = str(args.get("timelimit", "")).strip()
        if ctx.progress_callback:
            ctx.progress_callback(f"搜索：{query}")
        results = search_results(query, max_results=max(1, min(max_results, 10)), timelimit=timelimit)
        content = render_results_as_markdown(results) if results else "（搜索无结果）"
        provider_summary = render_provider_summary(results)
        if provider_summary:
            content = f"{provider_summary}\n\n{content}"
        return Observation(
            content=content,
            sources=results_to_sources(results),
            tool=self.spec.name,
            args=args,
        )
