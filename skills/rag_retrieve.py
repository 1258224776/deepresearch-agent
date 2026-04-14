"""
skills/rag_retrieve.py —— 本地文档语义检索

定位：从用户已经上传并建过索引的本地文档中做 top-k 向量检索。
适合：文档 QA 场景，或企业内部资料问答（离线可靠来源）。
特殊：命中片段的 url 填成 file://<doc>，在最终报告引用里能和外部 URL 并列。
注意：rag.is_ready() 为 False 时直接抛错，由 agent_loop 转成友好提示。
"""

from __future__ import annotations

from report import Observation, Source

from .base import Skill, SkillContext, SkillSpec


class RagRetrieveSkill(Skill):
    """FACTUAL 白名单里排第二位 —— 本地资料命中时比搜网快得多。"""

    spec = SkillSpec(
        name="rag_retrieve",
        desc="从用户已上传的本地文档中做语义检索。",
        args=["query"],
        optional_args=["top_k"],
        args_desc={"query": "检索问题", "top_k": "返回片段数，默认 3"},
        category="rag",
    )

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        query = args.get("query", "").strip()
        if ctx.progress_callback:
            ctx.progress_callback(f"RAG 检索：{query}")

        import rag

        if not rag.is_ready():
            raise RuntimeError("本地文档向量库未初始化，请先上传文档。")

        top_k = int(str(args.get("top_k", "3")).strip() or "3")
        hits = rag.retrieve(query, top_k=max(1, min(top_k, 8)))
        parts, sources = [], []
        for idx, hit in enumerate(hits, 1):
            doc = hit.get("doc", "unknown")
            chunk = hit.get("chunk", "")
            score = hit.get("score", 0.0)
            parts.append(f"【本地文档片段 {idx}｜来源：{doc}｜相关度：{score:.2f}】\n{chunk}")
            sources.append(Source(url=f"file://{doc}", title=doc, snippet=chunk[:200]))

        return Observation(
            content="\n\n".join(parts),
            sources=sources,
            tool=self.spec.name,
            args=args,
        )
