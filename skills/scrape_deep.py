"""
skills/scrape_deep.py —— 同域深度抓取（小爬虫）

定位：从起始 URL 出发，顺着同域链接继续抓，最多抓 N 个页面。
适合：一个官网或文档站的栏目页/目录页，想要全局视图时。
对比：scrape_batch 需要你给出所有 URL；scrape_deep 自己顺着链接走。
注意：只跟进同域链接，避免跑到外站。
"""

from __future__ import annotations

from report import Observation

from .adapters import bundles_to_sources, crawl_same_domain, render_page_bundles_as_markdown
from .base import Skill, SkillContext, SkillSpec


class ScrapeDeepSkill(Skill):
    """keywords 参数用于决定"顺着哪些链接走"的优先级。"""

    spec = SkillSpec(
        name="scrape_deep",
        desc="从起始 URL 出发，抓取同域多个页面，适合官网、文档站、博客目录深挖。",
        args=["url"],
        optional_args=["max_pages", "keywords", "max_chars"],
        args_desc={
            "url": "起始页面 URL",
            "max_pages": "最多抓取页面数，默认 5",
            "keywords": "优先跟进链接时参考的关键词，可用逗号分隔",
            "max_chars": "每页保留多少字符，默认 3000",
        },
        category="scrape",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        start_url = args.get("url", "").strip()
        max_pages = int(str(args.get("max_pages", "5")).strip() or "5")
        keywords = str(args.get("keywords", "")).strip()
        max_chars = int(str(args.get("max_chars", "3000")).strip() or "3000")
        if ctx.progress_callback:
            ctx.progress_callback(f"深度抓取：{start_url}")
        bundles = crawl_same_domain(
            start_url,
            max_pages=max(1, min(max_pages, 10)),
            max_chars=max(500, min(max_chars, 12000)),
            keywords=keywords,
        )

        return Observation(
            content=render_page_bundles_as_markdown(bundles) if bundles else "（深度抓取无结果）",
            sources=bundles_to_sources(bundles),
            tool=self.spec.name,
            args=args,
        )
