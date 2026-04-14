"""
skills/scrape_batch.py —— 批量抓取多个 URL

定位：一次塞进一串 URL（换行或逗号分隔），并行读正文，汇总成一条观察。
适合：search_multi 产出多条候选后，不想一个一个 scrape 时。
注意：每页字符数会被裁剪，长文请用 scrape + extract 组合。
"""

from __future__ import annotations

from report import Observation

from .adapters import batch_fetch_pages, bundles_to_sources, render_page_bundles_as_markdown
from .base import Skill, SkillContext, SkillSpec


def _parse_urls(raw: str) -> list[str]:
    """把换行 / 逗号分隔的字符串拆成 URL 列表，顺序保持原样。"""
    text = raw.replace("\r", "\n")
    parts = []
    for chunk in text.replace(",", "\n").split("\n"):
        url = chunk.strip()
        if url:
            parts.append(url)
    return parts


class ScrapeBatchSkill(Skill):
    spec = SkillSpec(
        name="scrape_batch",
        desc="批量抓取多个 URL 的正文内容，并汇总为一个 observation。",
        args=["urls"],
        optional_args=["limit", "max_chars"],
        args_desc={
            "urls": "多个 URL，使用换行或逗号分隔",
            "limit": "最多抓取多少个页面，默认 5",
            "max_chars": "每页保留多少字符，默认 4000",
        },
        category="scrape",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        urls = _parse_urls(args.get("urls", ""))
        limit = int(str(args.get("limit", "5")).strip() or "5")
        max_chars = int(str(args.get("max_chars", "4000")).strip() or "4000")
        if ctx.progress_callback:
            ctx.progress_callback(f"批量抓取：{len(urls)} 个 URL")
        bundles = batch_fetch_pages(urls, max_chars=max(500, min(max_chars, 12000)), limit=max(1, min(limit, 10)))
        return Observation(
            content=render_page_bundles_as_markdown(bundles) if bundles else "（批量抓取无结果）",
            sources=bundles_to_sources(bundles),
            tool=self.spec.name,
            args=args,
        )
