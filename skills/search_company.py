"""
skills/search_company.py —— 公司调研专用搜索

定位：围绕企业名 + 可选 topic 生成一组偏官方资料的查询（官网 / IR /
公告 / press release / annual report），覆盖财务与公告口径。
适合：FINANCIAL 问题、企业背景调研。
对比：search_multi 更通用；search_company 专门调用带"投资者关系"等维度。
"""

from __future__ import annotations

from report import Observation

from .adapters import batch_search_queries, merge_result_sets, render_provider_summary, render_results_as_markdown, results_to_sources
from .base import Skill, SkillContext, SkillSpec


class SearchCompanySkill(Skill):
    """FINANCIAL 类问题的起手首选（见 skills/router.py STARTER_MAP）。"""

    spec = SkillSpec(
        name="search_company",
        desc="面向公司官网、投资者关系、公告、财报和新闻稿的搜索，适合企业研究。",
        args=["company"],
        optional_args=["topic", "timelimit", "max_results"],
        args_desc={
            "company": "公司或品牌名称",
            "topic": "可选专题，如 财报、产品、战略、ESG",
            "timelimit": "时间范围：d/w/m/y",
            "max_results": "最终合并保留的结果数，默认 8",
        },
        category="search",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        company = args.get("company", "").strip()
        topic = args.get("topic", "").strip()
        timelimit = str(args.get("timelimit", "")).strip()
        max_results = int(str(args.get("max_results", "8")).strip() or "8")
        focus = f"{company} {topic}".strip()

        queries = [
            f"{focus} 官网",
            f"{focus} 投资者关系",
            f"{focus} 公告",
            f"{focus} press release",
            f"{focus} annual report",
        ]

        if ctx.progress_callback:
            ctx.progress_callback(f"公司信息搜索：{focus}")

        grouped = batch_search_queries(
            queries,
            max_results=min(max_results, 6),
            timelimit=timelimit,
        )
        results = merge_result_sets(*(items for _, items in grouped), limit=max(1, min(max_results, 12)))
        query_plan = "\n".join(f"- {item_query}" for item_query, _ in grouped)
        content = render_results_as_markdown(results) if results else "（公司信息搜索无结果）"
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
