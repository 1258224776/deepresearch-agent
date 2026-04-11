"""
agent.py — LLM 调用、推理规划、内容分析核心逻辑
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from google import genai
try:
    from openai import OpenAI as _OAI
except ImportError:
    _OAI = None

from config import PROVIDERS, FETCH_WORKERS, SEARCH_MAX_RESULTS, SEARCH_MAX_QUERIES, load_secret
from prompts import (
    CHAT_SYSTEM_PROMPT,
    prompt_reason,
    prompt_summarize_source,
    prompt_extract_key_points,
    prompt_compile_digest,
    prompt_ai_extract,
    prompt_cross_validate,
    prompt_generate_sub_queries,
    prompt_scrape_digest,
    prompt_chat_with_report,
    prompt_extract_list,
    prompt_aggregation_report,
)
from tools import fetch_page_content, fetch_via_jina, web_search


# ══════════════════════════════════════════════
# LLM 网关：多提供商自动切换
# ══════════════════════════════════════════════

def ai_generate(prompt: str, system: str = "") -> str:
    """
    按优先级依次尝试各 AI 提供商。
    遇到 503 / 429 / 限速时自动切换到下一个。
    """
    order_str = load_secret("AI_PROVIDER_ORDER") or "google,glm,minimax,openai"
    order = [p.strip() for p in order_str.split(",")]
    last_err = None

    for name in order:
        cfg = PROVIDERS.get(name)
        if not cfg:
            continue
        api_key = load_secret(cfg["env"])
        if not api_key:
            continue
        # openai 兼容接口需要 openai 包
        if name != "google" and _OAI is None:
            print(f"[AI] 跳过 {name}：openai 包未安装")
            continue
        try:
            if name == "google":
                client = genai.Client(api_key=api_key)
                return client.models.generate_content(
                    model=cfg["model"], contents=prompt
                ).text
            else:
                client = _OAI(api_key=api_key, base_url=cfg["base_url"])
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})
                return client.chat.completions.create(
                    model=cfg["model"], messages=messages
                ).choices[0].message.content

        except Exception as e:
            err_str = str(e)
            print(f"[AI] {name} 出错: {err_str[:120]}")
            if any(x in err_str for x in ["503", "UNAVAILABLE", "429",
                                           "rate_limit", "overloaded",
                                           "Too Many", "quota",
                                           "500", "Internal", "model"]):
                print(f"[AI] {name} 暂时不可用，切换下一个提供商...")
                last_err = e
                continue
            raise

    raise RuntimeError(f"所有 AI 提供商均不可用。最后错误：{last_err}")


# ══════════════════════════════════════════════
# 推理规划层
# ══════════════════════════════════════════════

def reason(question: str) -> dict:
    """
    AI 先分析问题，输出结构化搜索计划。
    返回字段：task_mode, question_type, need_search, reasoning,
              search_queries, target_item, max_pages, answer_direct
    """
    try:
        text = ai_generate(prompt_reason(question)).strip()
        if "```" in text:
            text = re.split(r"```(?:json)?", text)[1].strip().rstrip("`").strip()
        return json.loads(text)
    except Exception:
        return {
            "task_mode":     "research",
            "question_type": "深度研究",
            "need_search":   True,
            "reasoning":     "（推理解析失败，默认执行搜索）",
            "search_queries": [question],
            "target_item":   "",
            "max_pages":     5,
            "answer_direct": "",
        }


def generate_sub_queries(question: str) -> list[str]:
    """将研究问题拆解为多个搜索角度。"""
    try:
        text = ai_generate(prompt_generate_sub_queries(question)).strip()
        if "```" in text:
            text = re.split(r"```(?:json)?", text)[1].strip().rstrip("`").strip()
        queries = json.loads(text)
        return queries if isinstance(queries, list) else [question]
    except Exception:
        return [question]


# ══════════════════════════════════════════════
# 内容分析层
# ══════════════════════════════════════════════

def extract_key_points(content: str, question: str) -> str:
    """从网页内容中提取与问题相关的要点。"""
    return ai_generate(prompt_extract_key_points(content, question))


def summarize_source(content: str, question: str, title: str) -> dict:
    """
    对单个网页生成结构化摘要。
    返回 {"summary": str, "key_points": str, "relevance": "high|medium|low"}
    """
    try:
        text = ai_generate(prompt_summarize_source(content, question, title)).strip()
        if "```" in text:
            text = re.split(r"```(?:json)?", text)[1].strip().rstrip("`").strip()
        return json.loads(text)
    except Exception:
        return {
            "summary": "内容提炼失败",
            "key_points": extract_key_points(content, question),
            "relevance": "medium",
        }


def compile_digest(sources: list[dict], question: str) -> str:
    """将所有来源整合为连贯的综合摘要（3-5 段）。"""
    if not sources:
        return ""
    parts = "\n\n".join([
        f"【来源{i+1}：{s['title']}】\n{s.get('summary','')}\n"
        f"{s.get('key_points', s.get('raw_content','')[:500])}"
        for i, s in enumerate(sources)
    ])
    return ai_generate(prompt_compile_digest(parts, question))


def ai_extract(content: str, instruction: str) -> str:
    """按 instruction 从网页内容中提取目标信息。"""
    return ai_generate(prompt_ai_extract(content, instruction))


def cross_validate(sources: list[dict], question: str) -> dict:
    """
    多源交叉验证：提取关键结论，标注支持/反对来源，评估可信度。
    """
    if not sources:
        return {}
    parts = "\n\n".join([
        f"【来源{i+1}】{s['title']} ({s.get('domain','')})\n"
        f"{s.get('summary','')}\n{s.get('key_points','')[:300]}"
        for i, s in enumerate(sources)
    ])
    try:
        text = ai_generate(prompt_cross_validate(parts, question)).strip()
        if "```" in text:
            text = re.split(r"```(?:json)?", text)[1].strip().rstrip("`").strip()
        return json.loads(text)
    except Exception:
        return {
            "key_claims": [],
            "credibility": [],
            "consensus": "（验证解析失败）",
            "disputes": "（验证解析失败）",
            "reliability": "medium",
        }


def extract_list_data(page_content: str, target_item: str) -> list[dict]:
    """
    从列表页提取结构化 JSON 数组（Map 阶段）。
    用快速模型把杂乱网页变成整齐的数组。
    """
    try:
        text = ai_generate(prompt_extract_list(page_content, target_item)).strip()
        if "```" in text:
            text = re.split(r"```(?:json)?", text)[1].strip().rstrip("`").strip()
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _fetch_and_extract(args: tuple) -> list[dict]:
    """线程工作函数：抓取列表页并提取结构化数据（aggregation 模式）。"""
    r, target_item = args
    url = r.get("href", "")
    if not url:
        return []
    content = fetch_via_jina(url)
    if not content or len(content) < 100:
        return []
    items = extract_list_data(content, target_item)
    # 补充来源 URL
    domain = urlparse(url).netloc
    for item in items:
        if not item.get("url"):
            item["url"] = url
        item["_source_domain"] = domain
    return items


def generate_scrape_digest(sources: list[dict], topic: str) -> str:
    """对爬取结果生成内容汇总报告。"""
    combined = "\n\n".join([
        f"【来源{i+1}】{s['title']} ({s.get('domain','')})\n{s.get('raw_content','')[:2000]}"
        for i, s in enumerate(sources)
    ])
    return ai_generate(prompt_scrape_digest(combined, topic))


def chat_with_report(question: str, report: str,
                     history: list[dict], user_msg: str) -> str:
    """基于报告上下文回答追问。"""
    history_ctx = "\n".join([
        f"{'用户' if m['role']=='user' else 'AI'}: {m['content']}"
        for m in history
    ])
    return ai_generate(
        prompt_chat_with_report(question, report, history_ctx, user_msg),
        system=CHAT_SYSTEM_PROMPT,
    )


# ══════════════════════════════════════════════
# 数据汇总流程（aggregation 模式）
# ══════════════════════════════════════════════

def run_aggregation(
    question: str,
    plan: dict,
    progress_callback=None,
) -> tuple[list[dict], str, list[str]]:
    """
    数据挖掘模式（Map-Reduce）：
      Map    — 并发抓取列表页，AI 提取结构化 JSON 数组
      Combine — Python 合并去重
      Reduce  — AI 生成数据分析报告

    返回 (all_items, report, reasoning_log)
    """
    def cb(step, total, msg):
        if progress_callback:
            progress_callback(step, total, msg)

    # 预热 secrets
    for _cfg in PROVIDERS.values():
        load_secret(_cfg["env"])
    load_secret("AI_PROVIDER_ORDER")

    queries     = (plan.get("search_queries") or [question])[:SEARCH_MAX_QUERIES]
    target_item = plan.get("target_item") or "相关条目"
    max_pages   = min(int(plan.get("max_pages") or 5), 20)

    reasoning_log = [
        f"**模式：** 🔍 数据汇总（Aggregation）",
        f"**目标对象：** {target_item}",
        f"**分析：** {plan.get('reasoning', '')}",
        f"**搜索角度（{len(queries)} 个）：** {' · '.join(queries)}",
    ]

    cb(1, 10, f"🔎 定向搜索 {len(queries)} 个平台...")
    all_results: list[tuple] = []
    seen_urls: set[str] = set()
    for query in queries:
        for r in web_search(query, max_results=max_pages):
            url = r.get("href", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append((r, target_item))

    total_urls = len(all_results)
    cb(2, 10, f"📋 共 {total_urls} 个列表页，并发提取结构化数据...")

    # Map：并发抓取 + 提取
    all_items: list[dict] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = {executor.submit(_fetch_and_extract, args): args
                   for args in all_results}
        for future in as_completed(futures):
            completed += 1
            items = future.result() or []
            all_items.extend(items)
            progress = 2 + int(completed / max(total_urls, 1) * 6)
            cb(progress, 10, f"   进度 {completed}/{total_urls}，已提取 {len(all_items)} 条")

    # Combine：Python 去重（按 title+company 去重）
    seen_keys: set[str] = set()
    deduped: list[dict] = []
    for item in all_items:
        key = f"{item.get('title','')}-{item.get('company','')}"
        if key and key not in seen_keys:
            seen_keys.add(key)
            deduped.append(item)

    cb(9, 10, f"✅ 共 {len(deduped)} 条去重数据，AI 正在生成分析报告...")

    # Reduce：AI 生成汇总报告
    if deduped:
        import json as _json
        items_md = _json.dumps(deduped[:80], ensure_ascii=False, indent=None)
        report = ai_generate(prompt_aggregation_report(items_md, question, len(deduped)))
    else:
        report = "未能从搜索结果中提取到结构化数据，请尝试换一个更具体的描述。"

    cb(10, 10, "✅ 完成")
    return deduped, report, reasoning_log


# ══════════════════════════════════════════════
# 并行研究流程（research 模式）
# ══════════════════════════════════════════════

def _fetch_and_summarize(args: tuple) -> dict | None:
    """线程工作函数：爬取单个 URL 并提炼摘要。"""
    r, question = args
    url = r.get("href", "")
    if not url:
        return None
    title = r.get("title", "无标题")
    domain = urlparse(url).netloc
    content = fetch_page_content(url)
    if "抓取失败" in content or len(content) < 100:
        return None
    info = summarize_source(content, question, title)
    return {
        "title":       title,
        "url":         url,
        "domain":      domain,
        "summary":     info.get("summary", ""),
        "key_points":  info.get("key_points", ""),
        "relevance":   info.get("relevance", "medium"),
        "raw_content": content,
    }


def run_research(
    question: str,
    progress_callback=None,
) -> tuple[list[dict], str, list[str], str]:
    """
    统一入口：自动判断 research / aggregation 模式并路由。

    progress_callback(step: int, total: int, msg: str) — 可选进度回调
    返回 (sources_or_items, digest_or_report, reasoning_log, task_mode)
    """
    def cb(step, total, msg):
        if progress_callback:
            progress_callback(step, total, msg)

    # 预热：在主线程中把所有 API Key 缓存好，子线程直接读缓存
    for _cfg in PROVIDERS.values():
        load_secret(_cfg["env"])
    load_secret("AI_PROVIDER_ORDER")

    # Step 1: 推理规划 + 模式路由
    cb(0, 10, "🧠 分析意图，判断任务模式...")
    plan = reason(question)

    if plan.get("task_mode") == "aggregation":
        items, report, log = run_aggregation(question, plan, progress_callback)
        return items, report, log, "aggregation"

    queries = (plan.get("search_queries") or [question])[:SEARCH_MAX_QUERIES]
    reasoning_log = [
        f"**模式：** 📖 深度研究（Research）",
        f"**分析：** {plan.get('reasoning', '')}",
        f"**搜索角度（{len(queries)} 个）：** {' · '.join(queries)}",
    ]

    # Step 2: 搜索所有角度，收集 URL 列表
    cb(1, 10, f"🔎 从 {len(queries)} 个角度搜索...")
    all_results: list[tuple] = []
    seen_urls: set[str] = set()
    for query in queries:
        for r in web_search(query, max_results=SEARCH_MAX_RESULTS):
            url = r.get("href", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append((r, question))

    total_urls = len(all_results)
    cb(2, 10, f"📋 共 {total_urls} 个页面，开始并行爬取...")

    # Step 3: 并行爬取 + 摘要
    sources: list[dict] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = {executor.submit(_fetch_and_summarize, args): args
                   for args in all_results}
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            if result:
                sources.append(result)
            progress = 2 + int(completed / total_urls * 6)
            cb(progress, 10, f"   爬取进度 {completed}/{total_urls}，有效 {len(sources)} 个")

    # Step 4: 生成综合摘要
    cb(9, 10, f"✅ 爬取完毕，共 {len(sources)} 个有效来源，正在汇总...")
    digest = compile_digest(sources, question) if sources else ""
    cb(10, 10, "✅ 完成")

    return sources, digest, reasoning_log, "research"
