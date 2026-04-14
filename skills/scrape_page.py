"""
skills/scrape_page.py —— 抓取单个网页的正文

定位：给一个 URL，返回 reader 抽取后的正文 + 保留 URL 作为 Source。
适合：search 结果里定位到重点页面后，用它读正文。
对比：scrape_batch 一次多页；scrape_deep 同域深挖。
"""

from __future__ import annotations

from report import Observation, Source

from .adapters import fetch_page_bundle
from .base import Skill, SkillContext, SkillSpec


class ScrapePageSkill(Skill):
    """所有类型的通用读正文工具。"""

    spec = SkillSpec(
        name="scrape",
        desc="抓取指定 URL 的正文内容，优先走 reader 抽取。",
        args=["url"],
        optional_args=["max_chars"],
        args_desc={"url": "目标网页地址", "max_chars": "抓取文本长度上限，默认 6000"},
        category="scrape",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        url = args.get("url", "").strip()
        max_chars = int(str(args.get("max_chars", "6000")).strip() or "6000")
        if ctx.progress_callback:
            ctx.progress_callback(f"抓取页面：{url}")
        bundle = fetch_page_bundle(url, max_chars=max(500, min(max_chars, 12000)))
        content = bundle.get("content", "")
        sources = [Source(url=url, title=url, snippet=content[:200])] if url else []
        return Observation(
            content=content,
            sources=sources,
            tool=self.spec.name,
            args=args,
        )
