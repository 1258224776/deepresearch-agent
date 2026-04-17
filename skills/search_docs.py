"""
skills/search_docs.py —— 面向官方文档 / API reference 的搜索

定位：对查询自动追加 "documentation" / "guide" / "api reference" 等术语，
优先命中 docs.*、help.*、developer.* 这类站点。
适合：开发类问题、产品 how-to、SDK / API 用法。
对比：比 search_web 更聚焦技术文档；若知道站点，用 search_site 更直接。
"""

from __future__ import annotations

from report import Observation

from .adapters import (
    batch_search_queries,
    build_site_query,
    merge_result_sets,
    render_provider_summary,
    render_results_as_markdown,
    results_to_sources,
)
from .base import Skill, SkillContext, SkillSpec


class SearchDocsSkill(Skill):
    spec = SkillSpec(
        name="search_docs",
        desc="面向官方文档、API reference、guide、manual 的搜索，适合开发文档和产品帮助中心。",
        args=["query"],
        optional_args=["site", "timelimit", "max_results"],
        args_desc={
            "query": "文档主题或技术问题",
            "site": "目标文档站域名，如 docs.example.com",
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

        if site:
            queries = [
                build_site_query(query, site),
                build_site_query(f"{query} documentation", site),
                build_site_query(f"{query} guide", site),
                build_site_query(f"{query} api reference", site),
            ]
        else:
            queries = [
                f"{query} 官方文档",
                f"{query} documentation",
                f"{query} guide",
                f"{query} api reference",
            ]

        if ctx.progress_callback:
            ctx.progress_callback(f"文档搜索：{query}")

        grouped = batch_search_queries(
            queries,
            max_results=min(max_results, 6),
            timelimit=timelimit,
        )
        results = merge_result_sets(*(items for _, items in grouped), limit=max(1, min(max_results, 12)))
        query_plan = "\n".join(f"- {item_query}" for item_query, _ in grouped)
        content = render_results_as_markdown(results) if results else "（文档搜索无结果）"
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
