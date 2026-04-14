"""
skills/adapters/search.py —— 搜索类 skill 的公共底座

职责：
  - 封装 tools.web_search（DDG），统一归一化每条结果（title/url/snippet/domain）
  - 提供查询去重、site: 运算符拼装、批量查询、多组去重合并
  - 把结果渲染成 Markdown 供 LLM 观察；转成 Source 供 registry 登记

设计：所有 search_* skill 共用这一层，避免每个 skill 各自写"归一化 / 去重 / 渲染"。
"""

from __future__ import annotations

from urllib.parse import urlparse

from report import Source
from tools import web_search


def _normalize_url(url: str) -> str:
    """把 URL 转成去尾斜杠 + 小写的"比较用"形式，用于去重判等。"""
    return url.strip().rstrip("/").lower()


def unique_queries(queries: list[str]) -> list[str]:
    """按小写去重保留首次出现顺序；空串被丢弃。"""
    seen: set[str] = set()
    result: list[str] = []
    for raw in queries:
        query = raw.strip()
        key = query.lower()
        if not query or key in seen:
            continue
        seen.add(key)
        result.append(query)
    return result


def build_site_query(query: str, site: str = "") -> str:
    query = query.strip()
    site = site.strip()
    return f"site:{site} {query}".strip() if site else query


def normalize_search_result(item: dict, provider: str = "ddgs") -> dict:
    url = item.get("href") or item.get("url") or ""
    title = item.get("title") or item.get("heading") or url or "无标题"
    snippet = item.get("body") or item.get("snippet") or item.get("content") or ""
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "domain": urlparse(url).netloc if url else "",
        "provider": provider,
    }


def ddgs_search(query: str, max_results: int = 5, timelimit: str = "") -> list[dict]:
    raw = web_search(query, max_results=max_results, timelimit=timelimit)
    return [
        normalize_search_result(item, provider="ddgs")
        for item in raw
        if (item.get("href") or item.get("url"))
    ]


def batch_search_queries(
    queries: list[str],
    *,
    max_results: int = 5,
    timelimit: str = "",
) -> list[tuple[str, list[dict]]]:
    return [
        (query, ddgs_search(query, max_results=max_results, timelimit=timelimit))
        for query in unique_queries(queries)
    ]


def dedupe_results(results: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in results:
        url = item.get("url", "")
        key = _normalize_url(url)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def merge_result_sets(*result_sets: list[dict], limit: int | None = None) -> list[dict]:
    flat: list[dict] = []
    for result_set in result_sets:
        flat.extend(result_set)
    merged = dedupe_results(flat)
    if limit is not None:
        return merged[:limit]
    return merged


def render_results_as_markdown(results: list[dict]) -> str:
    lines = []
    for item in results:
        title = item.get("title", "无标题")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        provider = item.get("provider", "")
        provider_suffix = f" [{provider}]" if provider else ""
        lines.append(f"- [{title}]({url}){provider_suffix}\n  {snippet[:200]}")
    return "\n".join(lines)


def results_to_sources(results: list[dict]) -> list[Source]:
    return [
        Source(
            url=item.get("url", ""),
            title=item.get("title", ""),
            snippet=item.get("snippet", "")[:200],
        )
        for item in results
        if item.get("url")
    ]
