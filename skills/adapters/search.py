"""
Search adapter layer for all search_* skills.

Stage B goal:
- keep existing skill interfaces stable
- lift the adapter from single-provider DDGS to configurable multi-provider search
- support graceful fallback/top-up across providers without changing upper-layer skills
"""

from __future__ import annotations

import os
from urllib.parse import urljoin, urlparse

import httpx

from report import Source
from tools import web_search

_SEARCH_TIMEOUT = 15.0
_DEFAULT_PROVIDER_ORDER = ["ddgs"]
_SUPPORTED_PROVIDERS = ("ddgs", "tavily", "brave", "searxng")
_PROVIDER_ENV_HINTS: dict[str, list[str]] = {
    "ddgs": [],
    "tavily": ["TAVILY_API_KEY"],
    "brave": ["BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"],
    "searxng": ["SEARXNG_BASE_URL"],
}

_PROVIDER_MISSING_REASON: dict[str, str] = {
    "ddgs": "",
    "tavily": "missing_api_key",
    "brave": "missing_api_key",
    "searxng": "missing_base_url",
}


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def _split_csv(value: str) -> list[str]:
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def _timelimit_to_brave_freshness(timelimit: str) -> str | None:
    return {
        "d": "pd",
        "w": "pw",
        "m": "pm",
        "y": "py",
    }.get(timelimit.strip().lower())


def _timelimit_to_searxng_range(timelimit: str) -> str | None:
    return {
        "d": "day",
        "w": "week",
        "m": "month",
        "y": "year",
    }.get(timelimit.strip().lower())


def _provider_is_configured(provider: str) -> bool:
    provider = provider.lower().strip()
    if provider == "ddgs":
        return True
    if provider == "tavily":
        return bool(os.getenv("TAVILY_API_KEY"))
    if provider == "brave":
        return bool(os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("BRAVE_API_KEY"))
    if provider == "searxng":
        return bool(os.getenv("SEARXNG_BASE_URL"))
    return False


def get_search_provider_order(preferred: list[str] | None = None) -> list[str]:
    requested = preferred or _split_csv(os.getenv("SEARCH_PROVIDERS", ",".join(_DEFAULT_PROVIDER_ORDER)))
    cleaned: list[str] = []
    for provider in requested:
        if provider not in _SUPPORTED_PROVIDERS:
            continue
        if provider in cleaned:
            continue
        if _provider_is_configured(provider):
            cleaned.append(provider)
    return cleaned or ["ddgs"]


def get_search_provider_catalog(preferred: list[str] | None = None) -> list[dict]:
    active_order = get_search_provider_order(preferred)
    requested = preferred or _split_csv(os.getenv("SEARCH_PROVIDERS", ",".join(_DEFAULT_PROVIDER_ORDER)))
    requested_set = set(requested) if requested else set(_DEFAULT_PROVIDER_ORDER)
    catalog: list[dict] = []
    for provider in _SUPPORTED_PROVIDERS:
        configured = _provider_is_configured(provider)
        catalog.append(
            {
                "name": provider,
                "enabled": provider in active_order,
                "configured": configured,
                "requested": provider in requested_set,
                "env_hints": list(_PROVIDER_ENV_HINTS.get(provider, [])),
            }
        )
    return catalog


def unique_queries(queries: list[str]) -> list[str]:
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


def tavily_search(query: str, max_results: int = 5, timelimit: str = "") -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
        "topic": "news" if timelimit else "general",
    }
    try:
        with httpx.Client(timeout=_SEARCH_TIMEOUT) as client:
            resp = client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"tavily request failed: {exc}") from exc
    return [
        normalize_search_result(item, provider="tavily")
        for item in data.get("results", [])
        if item.get("url")
    ]


def brave_search(query: str, max_results: int = 5, timelimit: str = "") -> list[dict]:
    api_key = (os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("BRAVE_API_KEY") or "").strip()
    if not api_key:
        return []
    params = {
        "q": query,
        "count": max_results,
    }
    freshness = _timelimit_to_brave_freshness(timelimit)
    if freshness:
        params["freshness"] = freshness
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    try:
        with httpx.Client(timeout=_SEARCH_TIMEOUT) as client:
            resp = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"brave request failed: {exc}") from exc
    return [
        normalize_search_result(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("description") or item.get("snippet") or "",
            },
            provider="brave",
        )
        for item in data.get("web", {}).get("results", [])
        if item.get("url")
    ]


def searxng_search(query: str, max_results: int = 5, timelimit: str = "") -> list[dict]:
    base_url = os.getenv("SEARXNG_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return []
    params = {
        "q": query,
        "format": "json",
        "language": "zh-CN",
    }
    time_range = _timelimit_to_searxng_range(timelimit)
    if time_range:
        params["time_range"] = time_range
    try:
        with httpx.Client(timeout=_SEARCH_TIMEOUT) as client:
            resp = client.get(urljoin(base_url + "/", "search"), params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"searxng request failed: {exc}") from exc
    results = [
        normalize_search_result(item, provider="searxng")
        for item in data.get("results", [])
        if item.get("url")
    ]
    return results[:max_results]


def provider_search(
    provider: str,
    query: str,
    *,
    max_results: int = 5,
    timelimit: str = "",
) -> list[dict]:
    provider = provider.lower().strip()
    try:
        if provider == "ddgs":
            return ddgs_search(query, max_results=max_results, timelimit=timelimit)
        if provider == "tavily":
            return tavily_search(query, max_results=max_results, timelimit=timelimit)
        if provider == "brave":
            return brave_search(query, max_results=max_results, timelimit=timelimit)
        if provider == "searxng":
            return searxng_search(query, max_results=max_results, timelimit=timelimit)
    except Exception:
        return []
    return []


def provider_search_detailed(
    provider: str,
    query: str,
    *,
    max_results: int = 5,
    timelimit: str = "",
) -> tuple[list[dict], dict]:
    provider = provider.lower().strip()
    configured = _provider_is_configured(provider)
    if not configured:
        return [], {
            "provider": provider,
            "configured": False,
            "status": "skipped_unconfigured",
            "result_count": 0,
            "error": _PROVIDER_MISSING_REASON.get(provider, "unconfigured"),
        }

    try:
        if provider == "ddgs":
            results = ddgs_search(query, max_results=max_results, timelimit=timelimit)
        elif provider == "tavily":
            results = tavily_search(query, max_results=max_results, timelimit=timelimit)
        elif provider == "brave":
            results = brave_search(query, max_results=max_results, timelimit=timelimit)
        elif provider == "searxng":
            results = searxng_search(query, max_results=max_results, timelimit=timelimit)
        else:
            results = []
        return results, {
            "provider": provider,
            "configured": True,
            "status": "ok" if results else "empty",
            "result_count": len(results),
            "error": "",
        }
    except Exception as exc:
        return [], {
            "provider": provider,
            "configured": True,
            "status": "error",
            "result_count": 0,
            "error": str(exc),
        }


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


def summarize_result_providers(results: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for item in results:
        provider = str(item.get("provider", "")).strip().lower() or "unknown"
        counts[provider] = counts.get(provider, 0) + 1
    return [
        {"provider": provider, "count": count}
        for provider, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    ]


def render_provider_summary(results: list[dict]) -> str:
    summary = summarize_result_providers(results)
    if not summary:
        return ""
    items = " / ".join(f"{row['provider']} x{row['count']}" for row in summary)
    return f"搜索源：{items}"


def search_results(
    query: str,
    *,
    max_results: int = 5,
    timelimit: str = "",
    providers: list[str] | None = None,
) -> list[dict]:
    merged: list[dict] = []
    for provider in get_search_provider_order(providers):
        provider_results = provider_search(
            provider,
            query,
            max_results=max_results,
            timelimit=timelimit,
        )
        if not provider_results:
            continue
        merged = merge_result_sets(merged, provider_results, limit=max_results)
        if len(merged) >= max_results:
            break
    return merged[:max_results]


def search_results_with_trace(
    query: str,
    *,
    max_results: int = 5,
    timelimit: str = "",
    providers: list[str] | None = None,
) -> dict:
    merged: list[dict] = []
    attempts: list[dict] = []
    active_order = get_search_provider_order(providers)
    for provider in active_order:
        provider_results, attempt = provider_search_detailed(
            provider,
            query,
            max_results=max_results,
            timelimit=timelimit,
        )
        merged_before = len(merged)
        if provider_results:
            merged = merge_result_sets(merged, provider_results, limit=max_results)
        attempt["added_count"] = max(0, len(merged) - merged_before)
        attempts.append(attempt)
        if len(merged) >= max_results:
            break
    return {
        "query": query,
        "active_order": active_order,
        "results": merged[:max_results],
        "provider_summary": summarize_result_providers(merged[:max_results]),
        "attempts": attempts,
    }


def batch_search_queries(
    queries: list[str],
    *,
    max_results: int = 5,
    timelimit: str = "",
    providers: list[str] | None = None,
) -> list[tuple[str, list[dict]]]:
    return [
        (
            query,
            search_results(
                query,
                max_results=max_results,
                timelimit=timelimit,
                providers=providers,
            ),
        )
        for query in unique_queries(queries)
    ]


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
