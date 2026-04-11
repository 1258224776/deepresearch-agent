"""
rag.py — 轻量级本地 RAG 模块
依赖：faiss-cpu, sentence-transformers
全部在内存中运行，无需外部数据库。
"""
from __future__ import annotations

import re
import threading
import numpy as np

# ── 懒加载全局状态（避免启动时拖慢 Streamlit）──
_model = None
_model_lock = threading.Lock()

# 当前向量库状态
_index = None          # faiss.IndexFlatIP
_chunks: list[str] = []
_chunk_meta: list[dict] = []   # [{"doc": filename, "idx": chunk_idx}]
_doc_fingerprint: frozenset = frozenset()


def _get_model():
    """懒加载 sentence-transformers 模型（首次调用时下载，约 120MB）。"""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                # multilingual MiniLM：支持中英文，速度快，质量稳定
                _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _model


# ══════════════════════════════════════════════
# 1. 文本切块
# ══════════════════════════════════════════════

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    """
    按段落边界切块，尽量保持语义完整。
    chunk_size: 每块目标字符数
    overlap:    相邻块的重叠字符数（保留上下文连续性）
    """
    # 先按双换行分段
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    chunks: list[str] = []
    buf = ""

    for para in paragraphs:
        # 单段超过 chunk_size 时按句子进一步切分
        if len(para) > chunk_size:
            sentences = re.split(r"(?<=[。！？.!?])\s*", para)
            for sent in sentences:
                if len(buf) + len(sent) > chunk_size and buf:
                    chunks.append(buf.strip())
                    # 保留 overlap 部分作为下一块的开头
                    buf = buf[-overlap:] + sent if overlap else sent
                else:
                    buf += sent
        else:
            if len(buf) + len(para) > chunk_size and buf:
                chunks.append(buf.strip())
                buf = buf[-overlap:] + "\n" + para if overlap else para
            else:
                buf = (buf + "\n" + para) if buf else para

    if buf.strip():
        chunks.append(buf.strip())

    # 过滤掉过短的块（噪音）
    return [c for c in chunks if len(c) >= 30]


# ══════════════════════════════════════════════
# 2. 构建向量库
# ══════════════════════════════════════════════

def build_vector_store(docs: list[dict]) -> int:
    """
    根据文档列表构建（或重建）内存向量库。
    docs: [{"name": filename, "content": full_text}, ...]
    返回总块数。
    """
    global _index, _chunks, _chunk_meta, _doc_fingerprint

    import faiss

    new_fp = frozenset(d["name"] for d in docs)
    if new_fp == _doc_fingerprint and _index is not None:
        return len(_chunks)   # 文档集未变化，跳过重建

    model = _get_model()
    all_chunks: list[str] = []
    all_meta:   list[dict] = []

    for doc in docs:
        doc_chunks = chunk_text(doc["content"])
        for i, c in enumerate(doc_chunks):
            all_chunks.append(c)
            all_meta.append({"doc": doc["name"], "idx": i})

    if not all_chunks:
        _index = None
        _chunks = []
        _chunk_meta = []
        _doc_fingerprint = new_fp
        return 0

    # 编码所有块（batch，速度快）
    embeddings = model.encode(all_chunks, normalize_embeddings=True,
                              show_progress_bar=False, batch_size=32)
    embeddings = np.array(embeddings, dtype="float32")

    # 内积索引（归一化后等价于余弦相似度）
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    _index        = index
    _chunks       = all_chunks
    _chunk_meta   = all_meta
    _doc_fingerprint = new_fp
    return len(all_chunks)


# ══════════════════════════════════════════════
# 3. 检索
# ══════════════════════════════════════════════

def retrieve(query: str, top_k: int = 3) -> list[dict]:
    """
    根据查询检索最相关的文档块。
    返回 [{"chunk": str, "doc": str, "score": float}, ...]
    空库时返回 []。
    """
    if _index is None or not _chunks:
        return []

    model = _get_model()
    q_emb = model.encode([query], normalize_embeddings=True,
                         show_progress_bar=False)
    q_emb = np.array(q_emb, dtype="float32")

    k = min(top_k, len(_chunks))
    scores, indices = _index.search(q_emb, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        results.append({
            "chunk": _chunks[idx],
            "doc":   _chunk_meta[idx]["doc"],
            "score": float(score),
        })
    return results


def retrieve_as_context(query: str, top_k: int = 3) -> str:
    """
    检索并格式化为可直接注入 Prompt 的上下文字符串。
    """
    hits = retrieve(query, top_k=top_k)
    if not hits:
        return ""
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"【本地文档片段 {i}｜来源：{h['doc']}｜相关度：{h['score']:.2f}】\n{h['chunk']}")
    return "\n\n".join(parts)


def is_ready() -> bool:
    """判断向量库是否已构建。"""
    return _index is not None and len(_chunks) > 0
