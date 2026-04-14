"""
skills/extract_structured.py —— 抓 + 抽一体化

定位：给一个 URL 和一个"我要什么"的自然语言 instruction，
内部先 scrape 正文、再用 worker LLM 按 instruction 抽取关键信息。
适合：价格 / 参数 / 名单 / 结论这类"点状事实"。
对比：scrape 给你完整正文；extract 只给按指令抽出来的那部分。
"""

from __future__ import annotations

from agent import ai_generate_role
from report import Observation, Source

from .adapters import fetch_page_bundle
from .base import Skill, SkillContext, SkillSpec


class ExtractStructuredSkill(Skill):
    """注意 instruction 越具体效果越好（"抽第三季度净利润"胜过"抽财务数据"）。"""

    spec = SkillSpec(
        name="extract",
        desc="抓取网页后按指令抽取特定信息，适合价格、参数、名单、结论整理。",
        args=["url", "instruction"],
        optional_args=["max_chars"],
        args_desc={
            "url": "目标网页地址",
            "instruction": "需要抽取的信息说明",
            "max_chars": "抓取文本长度上限，默认 8000",
        },
        category="extract",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        url = args.get("url", "").strip()
        instruction = args.get("instruction", "提取核心内容").strip()
        max_chars = int(str(args.get("max_chars", "8000")).strip() or "8000")
        if ctx.progress_callback:
            ctx.progress_callback(f"定向抽取：{url}")
        bundle = fetch_page_bundle(url, max_chars=max(1000, min(max_chars, 12000)))
        content = bundle.get("content", "")
        prompt = (
            "请根据以下网页内容，严格按指令提取信息。\n\n"
            f"指令：{instruction}\n\n"
            f"网页内容：\n{content[:6000]}\n\n"
            "只输出提取结果，不要额外解释。"
        )
        result = ai_generate_role(prompt, role="worker", engine=ctx.engine, structured=False)
        sources = [Source(url=url, title=url, snippet=result[:200])] if url else []
        return Observation(
            content=result,
            sources=sources,
            tool=self.spec.name,
            args=args,
        )
