"""
skills/search_site.py —— 指定站点内搜索（site: 运算符）

定位：已经知道答案大概率在 example.com 上时，用 site:example.com query
强制把结果收敛到该域内。
适合：FACTUAL 类题目、定位官网公告、沿着 search 结果里的域名深挖。
对比：search_docs 是"推测 docs 站点"，search_site 是"你告诉我站点"。
"""

from __future__ import annotations

from report import Observation

from .adapters import build_site_query, render_provider_summary, render_results_as_markdown, results_to_sources, search_results
from .base import Skill, SkillContext, SkillSpec


class SearchSiteSkill(Skill):
    """需要 query + site 两个必填参数。"""

    spec = SkillSpec(
        name="search_site",
        desc="在指定网站内搜索，适合定位官网、文档站、新闻站内页面。",
        args=["query", "site"],
        optional_args=["max_results", "timelimit"],
        args_desc={
            "query": "搜索查询词",
            "site": "目标域名，如 example.com",
            "max_results": "返回结果数量，默认 6",
            "timelimit": "时间范围：d/w/m/y",
        },
        category="search",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        query = args.get("query", "").strip()
        site = args.get("site", "").strip()
        max_results = int(str(args.get("max_results", "6")).strip() or "6")
        timelimit = str(args.get("timelimit", "")).strip()
        full_query = build_site_query(query, site)
        if ctx.progress_callback:
            ctx.progress_callback(f"站内搜索：{full_query}")
        results = search_results(full_query, max_results=max(1, min(max_results, 10)), timelimit=timelimit)
        content = render_results_as_markdown(results) if results else "（站内搜索无结果）"
        provider_summary = render_provider_summary(results)
        if provider_summary:
            content = f"{provider_summary}\n\n{content}"
        return Observation(
            content=content,
            sources=results_to_sources(results),
            tool=self.spec.name,
            args=args,
        )
