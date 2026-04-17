"""
skills/adapters/fetch.py —— 抓取 / 抽取类 skill 的公共底座

职责：
  - 封装 tools.fetch_via_jina（reader 抽正文）与 fetch_page_full（带链接）
  - 提供单页、批量、同域爬虫（crawl_same_domain）、候选链接提取
  - 把抓取结果渲染成 Markdown；转成 Source 登记

设计：scrape_* 和 extract_links 复用这一层；
      crawl_same_domain 带简单 BFS，只跟进同域链接，避免跑到外站。
"""

from __future__ import annotations

from urllib.parse import urlparse

from report import Source
from tools import fetch_page_content, fetch_page_full, fetch_via_jina


def _normalize_url(url: str) -> str:
    """去尾斜杠，保留大小写 —— fetch 时需要原始大小写，去重时再按需再小写。"""
    return url.strip().rstrip("/")


def _normalize_keywords(raw: str | list[str] | None) -> list[str]:
    """把"换行/逗号/列表"三种形态的 keywords 统一压成小写字符串列表。"""
    if raw is None:
        return []
    if isinstance(raw, str):
        chunks = raw.replace("\r", "\n").replace(",", "\n").split("\n")
    else:
        chunks = raw
    return [chunk.strip().lower() for chunk in chunks if chunk and chunk.strip()]


def fetch_page_bundle(url: str, max_chars: int = 6000) -> dict:
    content = fetch_via_jina(url, max_chars=max_chars)
    return {
        "url": url,
        "title": url,
        "content": content[:max_chars],
        "links": [],
        "fetcher": "reader",
        "domain": urlparse(url).netloc if url else "",
    }


def fetch_page_text(url: str, max_chars: int = 6000) -> str:
    return fetch_page_content(url, max_chars=max_chars)


def fetch_reader_text(url: str, max_chars: int = 15000) -> str:
    return fetch_via_jina(url, max_chars=max_chars)


def fetch_page_with_links(url: str, max_chars: int = 4000) -> dict:
    content, links = fetch_page_full(url)
    return {
        "url": url,
        "title": url,
        "content": content[:max_chars],
        "links": _clean_links(links),
        "fetcher": "page_full",
        "domain": urlparse(url).netloc if url else "",
    }


def batch_fetch_pages(urls: list[str], max_chars: int = 4000, limit: int = 5) -> list[dict]:
    bundles: list[dict] = []
    for url in urls[:limit]:
        if not url:
            continue
        bundles.append(fetch_page_bundle(url, max_chars=max_chars))
    return bundles


def deep_scrape_markdown(
    start_url: str,
    *,
    max_pages: int = 5,
    max_chars: int = 3000,
    keywords: str | list[str] | None = None,
) -> str:
    bundles = crawl_same_domain(
        start_url,
        max_pages=max_pages,
        max_chars=max_chars,
        keywords=keywords,
    )
    return render_page_bundles_as_markdown(bundles, per_page_chars=max_chars)


def _clean_links(links: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in links:
        url = _normalize_url(raw)
        if not url or url.startswith(("javascript:", "mailto:", "#")):
            continue
        if url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned


def filter_links(
    links: list[str],
    *,
    base_host: str = "",
    keywords: str | list[str] | None = None,
    limit: int = 10,
) -> list[str]:
    keyword_list = _normalize_keywords(keywords)
    filtered: list[str] = []
    for url in _clean_links(links):
        host = urlparse(url).netloc
        if base_host and host and host != base_host:
            continue
        filtered.append(url)

    if not keyword_list:
        return filtered[:limit]

    matches: list[str] = []
    others: list[str] = []
    for url in filtered:
        lowered = url.lower()
        if any(keyword in lowered for keyword in keyword_list):
            matches.append(url)
        else:
            others.append(url)
    return (matches + others)[:limit]


def extract_candidate_links(
    url: str,
    *,
    keywords: str | list[str] | None = None,
    limit: int = 10,
    max_chars: int = 2000,
) -> dict:
    bundle = fetch_page_with_links(url, max_chars=max_chars)
    bundle["links"] = filter_links(
        bundle.get("links", []),
        base_host=bundle.get("domain", ""),
        keywords=keywords,
        limit=limit,
    )
    return bundle


def crawl_same_domain(
    start_url: str,
    *,
    max_pages: int = 5,
    max_chars: int = 3000,
    keywords: str | list[str] | None = None,
) -> list[dict]:
    if not start_url:
        return []

    visited: set[str] = set()
    queue = [_normalize_url(start_url)]
    bundles: list[dict] = []
    base_host = urlparse(start_url).netloc

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if not url or url in visited:
            continue
        visited.add(url)

        bundle = fetch_page_with_links(url, max_chars=max_chars)
        bundles.append(bundle)

        next_links = filter_links(
            bundle.get("links", []),
            base_host=base_host,
            keywords=keywords,
            limit=max_pages * 3,
        )
        for link in next_links:
            if link not in visited and link not in queue:
                queue.append(link)

    return bundles


def bundles_to_sources(bundles: list[dict]) -> list[Source]:
    return [
        Source(
            url=bundle.get("url", ""),
            title=bundle.get("title", "") or bundle.get("url", ""),
            snippet=bundle.get("content", "")[:200],
        )
        for bundle in bundles
        if bundle.get("url")
    ]


def render_page_bundles_as_markdown(bundles: list[dict], *, per_page_chars: int = 3000) -> str:
    parts: list[str] = []
    for bundle in bundles:
        url = bundle.get("url", "")
        content = bundle.get("content", "")
        parts.append(f"【页面】{url}\n{content[:per_page_chars]}")
    return "\n\n".join(parts)
