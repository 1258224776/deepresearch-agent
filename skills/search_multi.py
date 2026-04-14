"""
skills/search_multi.py —— 多变体搜索，去重合并

定位：围绕同一主题自动生成多个查询变体（官方 / 数据 / 分析 / 站内），
并行执行后去重合并，适合需要覆盖多视角的题型。
适合：LIST / COMPARE / ANALYSIS / RECOMMEND 类问题的起手。
对比：比 search 覆盖更广但耗时更长；比 search_company 更通用。
"""

from __future__ import annotations

from report import Observation

from .adapters import (
    batch_search_queries,
    build_site_query,
    merge_result_sets,
    render_results_as_markdown,
    results_to_sources,
)
from .base import Skill, SkillContext, SkillSpec


class SearchMultiSkill(Skill):
    spec = SkillSpec(
        name="search_multi",
        desc="围绕同一主题生成多个搜索变体并合并结果，适合首轮搜索噪声较大时扩展视角。",
        args=["query"],
        optional_args=["site", "timelimit", "max_results"],
        args_desc={
            "query": "核心搜索问题",
            "site": "可选域名，用于同时兼顾站内结果",
            "timelimit": "时间范围：d/w/m/y",
            "max_results": "最终合并保留的结果数，默认 8",
        },
        category="search",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        query = args.get("query", "").strip()
        site = args.get("site", "").strip()
        timelimit = str(args.get("timelimit", "")).strip()
        max_results = int(str(args.get("max_results", "8")).strip() or "8")

        queries = [
            query,
            f"{query} 官方",
            f"{query} 数据 统计",
            f"{query} 分析 解读",
        ]
        if site:
            queries.insert(0, build_site_query(query, site))

        if ctx.progress_callback:
            ctx.progress_callback(f"多角度搜索：{query}")

        grouped = batch_search_queries(
            queries,
            max_results=min(max_results, 6),
            timelimit=timelimit,
        )
        results = merge_result_sets(*(items for _, items in grouped), limit=max(1, min(max_results, 12)))
        query_plan = "\n".join(f"- {item_query}" for item_query, _ in grouped)
        content = render_results_as_markdown(results) if results else "（多角度搜索无结果）"
        if query_plan:
            content = f"查询变体：\n{query_plan}\n\n搜索结果：\n{content}"

        return Observation(
            content=content,
            sources=results_to_sources(results),
            tool=self.spec.name,
            args=args,
        )
