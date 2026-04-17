"""
skills/rag_retrieve.py — local-document semantic retrieval

Backend priority:
  1. deer-rag (remote, hybrid BM25+dense+rerank) when DEER_RAG_URL is set
     and the service responds, AND the collection already has indexed content.
  2. local rag.py (in-memory FAISS) as fallback when deer-rag is unavailable
     or returns empty results.

Raises RuntimeError if both backends have no indexed content.
"""

from __future__ import annotations

import os

from report import Observation, Source

from .base import Skill, SkillContext, SkillSpec


class RagRetrieveSkill(Skill):
    """FACTUAL whitelist priority 2 — local docs beat a web search when present."""

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
        if not query:
            raise ValueError("query 参数不能为空")

        if ctx.progress_callback:
            ctx.progress_callback(f"RAG 检索：{query}")

        top_k = max(1, min(int(str(args.get("top_k", "3")).strip() or "3"), 8))

        # ── 1. Try deer-rag ──────────────────────────────────────────────────
        import rag_client

        if rag_client.is_available():
            collection = os.getenv("DEER_RAG_DEFAULT_COLLECTION", "default")
            context_str, sources = rag_client.query(
                collection=collection,
                text=query,
                top_k=top_k,
            )
            # Non-empty result → deer-rag is ready and returned content
            if context_str:
                return Observation(
                    content=context_str,
                    sources=sources,
                    tool=self.spec.name,
                    args=args,
                )
            # Empty result: collection exists but has no indexed content yet.
            # Fall through to local rag.py instead of returning an empty answer.

        # ── 2. Local rag.py fallback ─────────────────────────────────────────
        import rag

        if not rag.is_ready():
            raise RuntimeError(
                "本地文档向量库未初始化，且 deer-rag 服务不可用或集合为空。"
                "请先上传文档，或配置 DEER_RAG_URL 并向集合中入库内容。"
            )

        hits = rag.retrieve(query, top_k=top_k)
        parts: list[str] = []
        sources: list[Source] = []
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
