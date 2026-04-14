"""
skills/summarize_text.py —— 文本摘要

定位：对一段长文本做 300 字以内的中文摘要，用 worker 模型。
适合：scrape 出来的长正文压缩成要点，再决定是否进入 finish。
特殊：returns_sources=False，但会继承 last_observation 的 sources，
        让后续引用不会因为"摘要"这一步而丢失溯源链路。
"""

from __future__ import annotations

from agent import ai_generate_role
from report import Observation

from .base import Skill, SkillContext, SkillSpec


class SummarizeTextSkill(Skill):
    """无 URL，纯文本压缩；不会登记新来源。"""

    spec = SkillSpec(
        name="summarize",
        desc="对长文本进行摘要，提炼核心信息。",
        args=["text"],
        args_desc={"text": "要总结的文本"},
        category="utility",
        returns_sources=False,
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        text = args.get("text", "").strip()
        if ctx.progress_callback:
            ctx.progress_callback("生成摘要")
        if not text:
            return Observation(content="（summarize_text 输入为空）", tool=self.spec.name, args=args)
        prompt = (
            "请用中文对以下文本做简洁摘要，提炼核心要点，"
            "不超过 300 字：\n\n"
            f"{text[:4000]}"
        )
        result = ai_generate_role(prompt, role="worker", engine=ctx.engine, structured=False)
        sources = list(ctx.last_observation.sources) if ctx.last_observation else []
        return Observation(content=result, sources=sources, tool=self.spec.name, args=args)
