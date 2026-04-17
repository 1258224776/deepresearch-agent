"""
Runtime adapters for entrypoint modules.

These wrappers keep the runtime entrypoints off tools.py directly without
pulling in the skills package, which would create circular imports during
report/agent initialization.
"""

from __future__ import annotations

from urllib.parse import urlparse

from tools import (
    deep_scrape,
    fetch_page_content,
    fetch_page_full,
    fetch_via_jina,
    parse_uploaded_file,
    save_report,
    save_scraped,
    web_search,
)


def search_results(query: str, *, max_results: int = 5, timelimit: str = "") -> list[dict]:
    results: list[dict] = []
    for item in web_search(query, max_results=max_results, timelimit=timelimit):
        url = item.get("href") or item.get("url") or ""
        if not url:
            continue
        results.append(
            {
                "title": item.get("title") or item.get("heading") or url or "无标题",
                "url": url,
                "snippet": item.get("body") or item.get("snippet") or item.get("content") or "",
                "domain": urlparse(url).netloc if url else "",
                "provider": item.get("provider") or "ddgs",
            }
        )
        if len(results) >= max_results:
            break
    return results


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
        "links": links,
    }


def deep_scrape_markdown(url: str, *, max_pages: int = 5) -> str:
    return deep_scrape(url, max_pages=max_pages)


def parse_uploaded_document(file_bytes: bytes, filename: str) -> str:
    return parse_uploaded_file(file_bytes, filename)


def save_markdown_report(question: str, reply: str) -> str:
    return save_report(question, reply)


def save_scraped_page(url: str, content: str, extracted: str = "") -> str:
    return save_scraped(url, content, extracted)
