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
)
from tools import fetch_page_content, web_search


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
        try:
            if name == "google":
                client = genai.Client(api_key=api_key)
                return client.models.generate_content(
                    model=cfg["model"], contents=prompt
                ).text
            else:
                if _OAI is None:
                    raise RuntimeError("openai 未安装，无法使用该提供商")
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
            if any(x in err_str for x in ["503", "UNAVAILABLE", "429",
                                           "rate_limit", "overloaded",
                                           "Too Many", "quota"]):
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
    返回字段：question_type, need_search, reasoning, search_queries, answer_direct
    """
    try:
        text = ai_generate(prompt_reason(question)).strip()
        if "```" in text:
            text = re.split(r"```(?:json)?", text)[1].strip().rstrip("`").strip()
        return json.loads(text)
    except Exception:
        return {
            "question_type": "深度研究",
            "need_search": True,
            "reasoning": "（推理解析失败，默认执行搜索）",
            "search_queries": [question],
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
# 并行研究流程
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
) -> tuple[list[dict], str, list[str]]:
    """
    完整研究流程（支持并行爬取）：
      1. AI 推理规划搜索角度
      2. 并行搜索 + 爬取 + 摘要
      3. 生成综合摘要

    progress_callback(step: int, total: int, msg: str) — 可选进度回调
    返回 (sources, digest, reasoning_log)
    """
    def cb(step, total, msg):
        if progress_callback:
            progress_callback(step, total, msg)

    # Step 1: 推理规划
    cb(0, 10, "🧠 分析主题，规划搜索角度...")
    plan = reason(question)
    queries = (plan.get("search_queries") or [question])[:SEARCH_MAX_QUERIES]
    reasoning_log = [
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

    return sources, digest, reasoning_log
