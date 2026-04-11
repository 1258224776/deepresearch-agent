"""
agent.py — LLM 调用、推理规划、内容分析核心逻辑
"""
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from google import genai
from google.genai import types as _genai_types
try:
    from openai import OpenAI as _OAI
except ImportError:
    _OAI = None
try:
    import anthropic as _ANT
except ImportError:
    _ANT = None

from config import (
    PROVIDERS, ROLE_ORDER, ENGINE_PRESETS,
    FETCH_WORKERS, WORKER_THREADS, CHUNK_SIZE, JITTER_RANGE,
    NETWORK_PROBE_TIMEOUT, SEARCH_MAX_RESULTS, SEARCH_MAX_QUERIES,
    load_secret,
)
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
    prompt_orchestrate,
    prompt_worker_extract,
)
from tools import fetch_page_content, fetch_via_jina, web_search


# ══════════════════════════════════════════════
# JSON 强力清洗器（容错 90% 提升）
# ══════════════════════════════════════════════

def extract_json(text: str):
    """
    暴力从任意文本中提取第一个合法 JSON 对象或数组。
    处理：markdown 代码块、前后废话、单引号、控制字符等。
    """
    if not text:
        return None
    text = text.strip()

    # 1. 去除 markdown 代码块
    if "```" in text:
        parts = re.split(r"```(?:json)?", text)
        for part in parts[1:]:
            candidate = part.strip().split("```")[0].strip()
            if candidate:
                text = candidate
                break

    # 2. 直接尝试解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 3. 正则暴力匹配 JSON 数组 或 对象
    for pattern in [
        r'(\[[\s\S]*?\])\s*$',   # 末尾数组（最宽松）
        r'(\{[\s\S]*?\})\s*$',   # 末尾对象
        r'(\[[\s\S]*\])',         # 任意位置数组
        r'(\{[\s\S]*\})',         # 任意位置对象
    ]:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

    # 4. 最后尝试：把单引号替换为双引号
    try:
        return json.loads(text.replace("'", '"'))
    except Exception:
        pass

    return None


# ══════════════════════════════════════════════
# 网络探测：自动识别是否能访问海外 API
# ══════════════════════════════════════════════

def detect_network_mode() -> str:
    """
    探测是否能连通 Google API 端点。
    返回 'overseas'（可以） 或 'domestic'（不行，需用国内通道）。
    """
    import socket
    try:
        sock = socket.create_connection(
            ("generativelanguage.googleapis.com", 443),
            timeout=NETWORK_PROBE_TIMEOUT,
        )
        sock.close()
        return "overseas"
    except Exception:
        return "domestic"


# ══════════════════════════════════════════════
# LLM 网关：多提供商自动切换
# ══════════════════════════════════════════════

def _call_provider(name: str, cfg: dict, prompt: str, system: str,
                   structured: bool = False) -> str:
    """
    调用单个提供商，返回文本结果。失败时抛出异常。
    structured=True 时，支持的厂商会启用原生 JSON 模式。
    """
    api_key = load_secret(cfg["env"])
    if not api_key:
        raise ValueError(f"API Key 未配置：{cfg['env']}")
    model = cfg.get("model", "")
    if not model:
        raise ValueError(f"模型名称未配置：{name}")

    ptype = cfg.get("type", "openai_compat")
    use_json_mode = structured and cfg.get("structured_output", False)

    # ── Google ──
    if ptype == "google":
        client = genai.Client(api_key=api_key)
        cfg_kwargs = {}
        if use_json_mode:
            cfg_kwargs["response_mime_type"] = "application/json"
        if system:
            cfg_kwargs["system_instruction"] = system
        gen_cfg = _genai_types.GenerateContentConfig(**cfg_kwargs) if cfg_kwargs else None
        kwargs = {"model": model, "contents": prompt}
        if gen_cfg:
            kwargs["config"] = gen_cfg
        return client.models.generate_content(**kwargs).text

    # ── Anthropic ──
    elif ptype == "anthropic":
        if _ANT is None:
            raise ImportError("anthropic 包未安装，请 pip install anthropic")
        client = _ANT.Anthropic(api_key=api_key)
        kwargs = {
            "model":      model,
            "max_tokens": 8192,
            "messages":   [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        resp = client.messages.create(**kwargs)
        return resp.content[0].text

    # ── OpenAI 兼容 ──
    else:
        if _OAI is None:
            raise ImportError("openai 包未安装")
        client = _OAI(api_key=api_key, base_url=cfg["base_url"])
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        extra = {"response_format": {"type": "json_object"}} if use_json_mode else {}
        return client.chat.completions.create(
            model=model, messages=messages, **extra
        ).choices[0].message.content


# 触发自动跳过的错误关键词
_SKIP_ERRORS = (
    "503", "UNAVAILABLE", "429", "rate_limit", "overloaded",
    "Too Many", "quota", "500", "Internal", "model",
    "未配置", "TODO", "ImportError", "anthropic 包", "openai 包",
    "timed out", "ConnectionError", "ConnectTimeout",
)


def ai_generate(prompt: str, system: str = "",
                _order: list[str] | None = None,
                structured: bool = False) -> str:
    """
    按优先级依次尝试各 AI 提供商，遇到限速/不可用自动跳下一个。
    structured=True：对支持的厂商启用原生 JSON 模式。
    """
    if _order is None:
        order_str = load_secret("AI_PROVIDER_ORDER") or "google,glm,minimax,openai"
        _order = [p.strip() for p in order_str.split(",")]

    last_err = None
    for name in _order:
        cfg = PROVIDERS.get(name)
        if not cfg:
            continue
        try:
            return _call_provider(name, cfg, prompt, system, structured=structured)
        except Exception as e:
            err_str = str(e)
            print(f"[AI] {name} 出错: {err_str[:120]}")
            if any(x in err_str for x in _SKIP_ERRORS):
                print(f"[AI] {name} 跳过，切换下一个...")
                last_err = e
                continue
            raise

    raise RuntimeError(f"所有 AI 提供商均不可用。最后错误：{last_err}")


def ai_generate_role(prompt: str, system: str = "",
                     role: str = "default",
                     engine: str = "",
                     structured: bool = False) -> str:
    """
    按角色 + 引擎预设路由选择提供商列表，再调用 ai_generate。
    engine: "deep" | "fast" | "" (空=用默认 ROLE_ORDER)
    """
    preset = ENGINE_PRESETS.get(engine, {})
    order_str = preset.get(role, "") or ROLE_ORDER.get(role, "")
    if not order_str:
        return ai_generate(prompt, system, structured=structured)
    order = [p.strip() for p in order_str.split(",")]
    return ai_generate(prompt, system, _order=order, structured=structured)


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
# URL 智能提取流水线（Orchestrator → Workers → Analyst）
# ══════════════════════════════════════════════

def orchestrate(user_intent: str, engine: str = "") -> dict:
    """
    主脑 AI：解析用户意图，生成字段 Schema + 打工指令。
    启用结构化输出（支持的厂商 100% 返回合法 JSON）。
    """
    try:
        text = ai_generate_role(
            prompt_orchestrate(user_intent),
            role="orchestrator",
            engine=engine,
            structured=True,       # 对 Google/支持厂商启用原生 JSON 模式
        ).strip()
        data = extract_json(text)
        if data and isinstance(data, dict):
            return data
        raise ValueError("主脑返回内容无法解析为 dict")
    except Exception as e:
        print(f"[Orchestrator] 解析失败，降级到默认 Schema: {e}")
        return {
            "task_summary":       user_intent,
            "target_object":      "相关条目",
            "fields": [
                {"key": "title", "label": "标题", "desc": "条目标题或名称", "required": True},
                {"key": "desc",  "label": "描述", "desc": "简短描述",       "required": False},
                {"key": "price", "label": "价格", "desc": "价格或薪资",     "required": False},
                {"key": "url",   "label": "链接", "desc": "原始链接",       "required": False},
            ],
            "worker_instructions": f"从文本中提取与以下需求相关的条目：{user_intent}",
            "dedup_keys":          ["title"],
            "dashboard_hint":      "",
        }


def _preclean_text(text: str) -> str:
    """
    文本预清洗：切块前去除导航栏、页脚、版权声明、广告等噪音行。
    保留实质性内容，提升打工 AI 提取精度，同时减少 Token 消耗。
    """
    # 噪音行特征（正则，匹配则丢弃整行）
    NOISE_PATTERNS = [
        r"^(首页|home|导航|nav|menu|菜单)\s*[>｜|]",   # 面包屑导航
        r"(copyright|版权所有|©|\(c\)|all rights reserved)",
        r"(cookie|隐私政策|privacy policy|使用条款|terms of use)",
        r"(关注我们|follow us|扫码关注|微信公众号|二维码)",
        r"(加载中|loading\.\.|skeleton|占位符)",
        r"^(分享|share|转发|点赞|收藏|举报)\s*$",
        r"(广告|advertisement|sponsored|赞助商)",
        r"^\s*(上一篇|下一篇|相关推荐|猜你喜欢|热门推荐)\s*$",
        r"^\s*[\|｜─\-─]{3,}\s*$",                    # 纯分隔符行
        r"^\s*(登录|注册|login|sign up|sign in)\s*$",
        r"(icp备|京icp|粤icp|工业和信息化部)",          # 备案号
    ]
    compiled = [re.compile(p, re.IGNORECASE) for p in NOISE_PATTERNS]

    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 跳过过短行（纯数字、单字符、空行）
        if len(stripped) < 5:
            continue
        if any(pat.search(stripped) for pat in compiled):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


def _smart_chunk(text: str, base_size: int = CHUNK_SIZE) -> list[str]:
    """
    智能切块：按段落边界切分，根据内容总长度动态调整块数上限。
    短页面（<5000字）最多切 3 块；长页面才切更多，避免无效 API 调用。
    """
    total = len(text)
    # 动态调整：内容越少，块越大，避免切出过多空块
    size = max(base_size, total // 5) if total < base_size * 3 else base_size

    paragraphs = re.split(r"\n{2,}", text)
    chunks, buf = [], ""
    for para in paragraphs:
        if len(buf) + len(para) > size and buf:
            chunks.append(buf.strip())
            buf = para
        else:
            buf = (buf + "\n\n" + para) if buf else para
    if buf.strip():
        chunks.append(buf.strip())

    # 上限兜底：不超过 8 块（防止滥用并发线程）
    return (chunks or [text[:size]])[:8]


def _worker_extract_chunk(args: tuple) -> list[dict]:
    """
    线程工作函数：对单个文本块调用打工 AI 提取结构化数据。
    包含 Jitter 延迟（防限速）+ 强力 JSON 清洗。
    """
    chunk, fields_desc, worker_instructions, source_url, engine, neg_kws, disc_criteria = args

    # Jitter：随机微小延迟，防高并发触发 Rate Limit
    time.sleep(random.uniform(*JITTER_RANGE))

    try:
        raw = ai_generate_role(
            prompt_worker_extract(chunk, fields_desc, worker_instructions,
                                  negative_keywords=neg_kws,
                                  discrimination_criteria=disc_criteria),
            role="worker",
            engine=engine,
        )
        data = extract_json(raw)          # 强力清洗器，容错率大幅提升
        items = data if isinstance(data, list) else []
        domain = urlparse(source_url).netloc
        for item in items:
            if not item.get("url"):
                item["url"] = source_url
            item["_source_domain"] = domain
        return items
    except Exception as e:
        print(f"[Worker] 块提取失败: {str(e)[:80]}")
        return []


def run_url_pipeline(
    urls: list[str],
    user_intent: str,
    engine: str = "",
    progress_callback=None,
) -> tuple[dict, list[dict], str, list[str]]:
    """
    URL 智能提取完整流水线（五步）：
      1. 主脑 AI    → 生成 Schema + 打工指令（结构化输出）
      2. 并发爬取   → 多线程抓取所有 URL
      3. 智能切块   → 动态分块 + 并发打工 AI 提取（Map，含 Jitter）
      4. 合并去重   → Python 合并所有结果（Combine）
      5. 看板 AI    → 汇总分析，输出 Dashboard JSON（Reduce）

    engine: "deep" | "fast" | "" (空=用 ROLE_ORDER 默认)
    返回 (schema_dict, deduped_items, dashboard_json_str, reasoning_log)
    """
    def cb(step: int, total: int, msg: str):
        if progress_callback:
            progress_callback(step, total, msg)

    # ── Step 1+2 并行：主脑解析 & 并发爬取同时启动（核心提速）──
    engine_label = ENGINE_PRESETS.get(engine, {}).get("label", "默认") if engine else "默认"
    cb(1, 10, f"🧠 主脑解析意图 + 🌐 并发爬取同步启动（{engine_label}）...")

    raw_contents: list[tuple[str, str]] = []
    schema: dict = {}
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS + 1) as ex:
        orch_fut  = ex.submit(orchestrate, user_intent, engine)
        fetch_map = {ex.submit(fetch_via_jina, url): url for url in urls}

        done = 0
        for fut in as_completed(fetch_map):
            url     = fetch_map[fut]
            done   += 1
            content = fut.result() or ""
            if len(content) > 200:
                raw_contents.append((url, content))
            cb(1 + int(done / len(urls) * 3), 10,
               f"   🌐 页面 {done}/{len(urls)} 爬取完毕，有效 {len(raw_contents)} 个（主脑思考中...）")

        cb(4, 10, "⏳ 等待主脑 Schema 就绪...")
        schema = orch_fut.result()

    target    = schema.get("target_object", "条目")
    fields    = schema.get("fields", [])
    w_instr   = schema.get("worker_instructions", "")
    dedup_k   = schema.get("dedup_keys") or ["title"]
    neg_kws   = schema.get("negative_keywords") or []
    disc_crit = schema.get("discrimination_criteria", "")

    fields_desc = "\n".join(
        f'- {f["key"]}（{f["label"]}）：{f.get("desc", "")}{"（必填）" if f.get("required") else ""}'
        for f in fields
    )
    reasoning_log = [
        f"**引擎：** {engine_label}",
        f"**任务：** {schema.get('task_summary', user_intent)}",
        f"**提取对象：** {target}",
        f"**字段数：** {len(fields)} 个 — {', '.join(f['label'] for f in fields)}",
        f"**URL 数：** {len(urls)} 个 · 有效爬取 {len(raw_contents)} 个",
    ]

    if not raw_contents:
        return schema, [], "", reasoning_log + ["❌ 所有 URL 均无法获取内容"]

    # ── Step 3: 智能切块 + 并发打工提取（Map + Jitter）──
    all_chunks: list[tuple] = []
    for url, content in raw_contents:
        clean = _preclean_text(content)          # 预清洗：去导航/页脚/广告噪音
        for chunk in _smart_chunk(clean, CHUNK_SIZE):
            all_chunks.append((chunk, fields_desc, w_instr, url, engine, neg_kws, disc_crit))

    reasoning_log.append(f"**文本块：** {len(all_chunks)} 块（{WORKER_THREADS} 线程并发）")
    cb(4, 10, f"🤖 打工 AI 提取中：{len(all_chunks)} 块 × {WORKER_THREADS} 线程并发...")

    all_items: list[dict] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=WORKER_THREADS) as ex:
        futs = {ex.submit(_worker_extract_chunk, args): args for args in all_chunks}
        for fut in as_completed(futs):
            completed += 1
            items = fut.result() or []
            all_items.extend(items)
            prog = 4 + int(completed / max(len(all_chunks), 1) * 4)
            cb(prog, 10,
               f"   🤖 {completed}/{len(all_chunks)} 块完成，累计提取 {len(all_items)} 条数据")

    # ── Step 4: 合并去重（Combine）──
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in all_items:
        key = "-".join(str(item.get(k, "")) for k in dedup_k)
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)

    reasoning_log.append(f"**去重后：** {len(deduped)} 条（原始 {len(all_items)} 条）")
    cb(9, 10, f"📊 去重后 {len(deduped)} 条，看板 AI 正在生成分析报告...")

    # ── Step 5: 看板 AI 汇总分析（Reduce）──
    dashboard_json = ""
    if deduped:
        items_md   = json.dumps(deduped[:100], ensure_ascii=False)
        hint       = schema.get("dashboard_hint", "")
        full_intent = f"{user_intent}\n\n分析维度提示：{hint}" if hint else user_intent
        dashboard_json = ai_generate_role(
            prompt_aggregation_report(items_md, full_intent, len(deduped)),
            role="analyst",
            engine=engine,
            structured=True,
        )

    cb(10, 10, "✅ 流水线完成")
    return schema, deduped, dashboard_json, reasoning_log


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
