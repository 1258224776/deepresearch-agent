"""
Short guidance appendix for shortlisted skills.

This is intentionally lightweight. The executable behavior stays in skills/*.py;
these hints only help the orchestrator choose among visible skills.
"""

from __future__ import annotations


SKILL_GUIDANCE: dict[str, dict[str, str]] = {
    "search": {
        "when": "通用网页检索，适合先摸清主题和来源面。",
        "avoid": "已有明确站点、明确 URL、或明显是官方文档题时不要先手泛搜。",
        "next": "通常下一步接 scrape / extract。",
    },
    "search_multi": {
        "when": "需要并行换角度、对比多个对象、或做列表收集时使用。",
        "avoid": "单一事实问答或已有足够精准 query 时不要滥用。",
        "next": "通常下一步接 scrape_batch / extract。",
    },
    "search_docs": {
        "when": "官方文档、API、SDK、guide、reference、开发者问题。",
        "avoid": "新闻、财报、公司动态类问题不要优先用它。",
        "next": "通常下一步接 extract_links / scrape_deep / scrape。",
    },
    "search_company": {
        "when": "公司官网、IR、财报、公告、press release、品牌官方信息。",
        "avoid": "纯技术文档题或泛知识题不要先手用它。",
        "next": "通常下一步接 scrape / extract。",
    },
    "search_site": {
        "when": "问题已经限定站点、域名或明确要在某官网/文档站内找内容。",
        "avoid": "还没确定可信站点前，不要过早锁死在单域名内。",
        "next": "通常下一步接 scrape / extract_links。",
    },
    "search_recent": {
        "when": "最近、近一周、近一月、近期进展、最新变化。",
        "avoid": "稳定知识、历史概念、官方文档题不要先手用它。",
        "next": "通常下一步接 scrape / extract。",
    },
    "search_news": {
        "when": "新闻、发布、公告、更新、动态、事件进展。",
        "avoid": "官方文档 how-to 或纯官网结构题不要优先用它。",
        "next": "通常下一步接 scrape / extract。",
    },
    "scrape": {
        "when": "已经拿到明确 URL，想读正文或详情页内容。",
        "avoid": "还没有可信 URL 时不要盲抓。",
        "next": "通常下一步接 extract / summarize。",
    },
    "extract_links": {
        "when": "给定入口页、目录页、首页，先找可继续跟进的同域链接。",
        "avoid": "已经知道要抓哪几个详情页时，不必多此一步。",
        "next": "通常下一步接 scrape_batch / scrape_deep / scrape。",
    },
    "scrape_batch": {
        "when": "手头已经有多个 URL，要统一抓取多个页面。",
        "avoid": "只有单页或还没整理出链接集合时不要先用。",
        "next": "通常下一步接 extract / summarize。",
    },
    "scrape_deep": {
        "when": "需要沿同域继续深挖官网、文档站、博客目录。",
        "avoid": "简单事实题、低步数场景、或 profile 明显偏保守时不要先手使用。",
        "next": "通常下一步接 extract / summarize。",
    },
    "extract": {
        "when": "已有较长正文，想按问题定向抽取事实、数据、结论。",
        "avoid": "还没有足够正文材料时不要空抽。",
        "next": "通常下一步接 summarize / finish。",
    },
    "summarize": {
        "when": "已经抓到较多文本，想先压缩要点再继续判断。",
        "avoid": "还在找来源阶段时不要过早总结。",
        "next": "通常下一步接 finish 或继续定向补证据。",
    },
    "rag_retrieve": {
        "when": "用户已上传本地文档，且问题明显依赖这些文档内容。",
        "avoid": "没有上传资料时不要优先选择。",
        "next": "通常下一步接 extract / summarize / finish。",
    },
}


def get_skill_guidance(skill_name: str) -> dict[str, str]:
    return dict(SKILL_GUIDANCE.get(skill_name, {}))


def get_guidance_for_skills(skill_names: list[str]) -> dict[str, dict[str, str]]:
    return {
        name: dict(SKILL_GUIDANCE[name])
        for name in skill_names
        if name in SKILL_GUIDANCE
    }
