"""
skills/extract_links.py —— 从入口页抽候选链接

定位：给一个入口页 URL（官网首页、目录页、栏目页），回来一份候选跳转链接。
适合：想"先知道这个站里有哪些页面"再决定抓什么；作为 scrape_deep 的前置。
注意：只给链接列表，不会直接读那些页面 —— 请后续用 scrape / scrape_batch。
"""

from __future__ import annotations

from report import Observation, Source

from .adapters import extract_candidate_links
from .base import Skill, SkillContext, SkillSpec


class ExtractLinksSkill(Skill):
    """可用 keywords 参数让相关链接排在前面。"""

    spec = SkillSpec(
        name="extract_links",
        desc="从入口页或导航页提取同域候选链接，适合在官网、文档站、博客首页中找下一跳页面。",
        args=["url"],
        optional_args=["keywords", "limit", "max_chars"],
        args_desc={
            "url": "入口页面 URL",
            "keywords": "可选关键词，帮助优先挑选链接",
            "limit": "最多返回多少个候选链接，默认 10",
            "max_chars": "入口页摘要长度，默认 2000",
        },
        category="scrape",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        url = args.get("url", "").strip()
        keywords = args.get("keywords", "").strip()
        limit = int(str(args.get("limit", "10")).strip() or "10")
        max_chars = int(str(args.get("max_chars", "2000")).strip() or "2000")

        if ctx.progress_callback:
            ctx.progress_callback(f"提取候选链接：{url}")

        bundle = extract_candidate_links(
            url,
            keywords=keywords,
            limit=max(1, min(limit, 20)),
            max_chars=max(500, min(max_chars, 6000)),
        )
        links = bundle.get("links", [])
        lines = [f"来源页面：{url}"]
        if keywords:
            lines.append(f"筛选关键词：{keywords}")
        lines.append("")
        lines.append("候选链接：")
        if links:
            lines.extend(f"- {link}" for link in links)
        else:
            lines.append("（未发现可跟进链接）")

        source = Source(
            url=url,
            title=url,
            snippet=bundle.get("content", "")[:200],
        ) if url else None

        return Observation(
            content="\n".join(lines),
            sources=[source] if source else [],
            tool=self.spec.name,
            args=args,
        )
