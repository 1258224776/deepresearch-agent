# ============================================================
#   Lightweight DeepResearch Agent — 第五步：自我推理能力
#   目标：AI 先分析问题、制定策略，再决定怎么行动
# ============================================================
#
#  【命令列表】
#    直接输入问题     → AI 先推理，再决定搜索/直接回答
#    scrape <网址>    → 爬取指定网页的完整内容并保存
#    scrape <网址> <你想要的内容描述>
#                    → 爬取后让 AI 提取你指定的内容并保存
#    save             → 保存上一条研究回答为报告
#    exit             → 退出
#
# ============================================================

import os
import re
import json
import datetime
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv           # pip install python-dotenv
load_dotenv()                            # 自动读取同目录下的 .env 文件
from google import genai
from ddgs import DDGS                   # pip install ddgs
import httpx                            # pip install httpx
import trafilatura                      # pip install trafilatura
from bs4 import BeautifulSoup          # pip install beautifulsoup4

# 多 User-Agent 轮换，提高爬取成功率
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# ──────────────────────────────────────────────
# 1. 多 AI 提供商配置与自动切换
# ──────────────────────────────────────────────
_PROVIDERS = {
    "google":  {"env": "GOOGLE_API_KEY",  "model": "gemini-2.5-flash"},
    "glm":     {"env": "GLM_API_KEY",     "model": "glm-5",           "base_url": "https://open.bigmodel.cn/api/paas/v4/"},
    "minimax": {"env": "MINIMAX_API_KEY", "model": "MiniMax-M2.7",  "base_url": "https://api.minimax.chat/v1/"},
    "openai":  {"env": "OPENAI_API_KEY",  "model": "gpt-4o-mini",     "base_url": "https://api.openai.com/v1/"},
}

def _load_secret(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get(key, "") or ""
        except Exception:
            pass
    return val

def ai_generate(prompt: str, system: str = "") -> str:
    """按优先级依次尝试各 AI 提供商，503/429 时自动切换到下一个。"""
    order_str = _load_secret("AI_PROVIDER_ORDER") or "google,glm,minimax,openai"
    order = [p.strip() for p in order_str.split(",")]
    last_err = None
    for name in order:
        cfg = _PROVIDERS.get(name)
        if not cfg:
            continue
        api_key = _load_secret(cfg["env"])
        if not api_key:
            continue
        try:
            if name == "google":
                c = genai.Client(api_key=api_key)
                return c.models.generate_content(
                    model=cfg["model"], contents=prompt
                ).text
            else:
                from openai import OpenAI as _OAI
                c = _OAI(api_key=api_key, base_url=cfg["base_url"])
                msgs = []
                if system:
                    msgs.append({"role": "system", "content": system})
                msgs.append({"role": "user", "content": prompt})
                return c.chat.completions.create(
                    model=cfg["model"], messages=msgs
                ).choices[0].message.content
        except Exception as e:
            s = str(e)
            if any(x in s for x in ["503", "UNAVAILABLE", "429", "rate_limit", "overloaded", "Too Many", "quota"]):
                print(f"[AI] {name} 暂时不可用，切换下一个提供商...")
                last_err = e
                continue
            raise
    raise RuntimeError(f"所有 AI 提供商均不可用。最后错误：{last_err}")

# ──────────────────────────────────────────────
# 2. 系统提示词
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """你是一个深度研究助手。
我会给你提供从多个角度搜索并抓取的网页资料，你需要：
1. 基于这些资料，对用户的问题给出深入、有条理的分析
2. 标注哪些信息来自哪个来源（注明网址）
3. 指出不同来源之间的异同或矛盾
4. 指出资料的局限性或需要进一步核实的地方
5. 最后给出你自己的综合判断

请用中文回答，保持专业但易于理解的风格。
如果搜索结果与问题无关，请直接说明并凭自身知识回答。"""

last_question = ""
last_reply = ""

# 确保保存目录存在
os.makedirs("reports", exist_ok=True)
os.makedirs("scraped", exist_ok=True)  # 爬取的内容单独存这里


# ══════════════════════════════════════════════
# 工具区
# ══════════════════════════════════════════════

# ──────────────────────────────────────────────
# 工具1：抓取单个网页正文
# ──────────────────────────────────────────────
def fetch_page_content(url: str, max_chars: int = 6000) -> str:
    """
    抓取指定网页正文。
    策略：轮换 UA → trafilatura（高精度） → BeautifulSoup 兜底。
    """
    for ua in USER_AGENTS:
        try:
            resp = httpx.get(
                url, timeout=14, follow_redirects=True,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                }
            )
            if resp.status_code >= 400:
                continue

            # ① trafilatura 优先（召回率优先模式）
            content = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
                no_fallback=False,
            )
            if content and len(content) > 150:
                return content[:max_chars]

            # ② BeautifulSoup 兜底：去除噪音标签后提取纯文本
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer",
                              "aside", "advertisement", "figure"]):
                tag.decompose()
            lines = [ln.strip() for ln in soup.get_text(separator="\n").splitlines()
                     if len(ln.strip()) > 25]
            text = "\n".join(lines)
            if text:
                return text[:max_chars]

        except Exception:
            continue

    return "（页面抓取失败，可能为动态渲染或访问受限）"


def fetch_page_full(url: str) -> tuple[str, list[str]]:
    """
    完整抓取网页：
    - 返回 (正文内容, 页面内所有链接列表)
    用于深度爬取时跟进子链接。
    """
    try:
        resp = httpx.get(
            url, timeout=10, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        # 提取正文
        content = trafilatura.extract(resp.text, include_comments=False, include_tables=True) or ""

        # 提取页面内所有绝对链接（同域名）
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(base, href)
            # 只保留同域名的 http/https 链接
            if full.startswith(base) and full != url:
                links.append(full)

        return content, list(set(links))
    except Exception as e:
        return f"（抓取失败: {type(e).__name__}）", []


# ──────────────────────────────────────────────
# 工具2：保存爬取内容到文件
# ──────────────────────────────────────────────
def save_scraped(url: str, content: str, extracted: str = "") -> str:
    """
    把爬取的内容保存到 scraped/ 目录。
    - content: 网页原始正文
    - extracted: AI 提取后的目标内容（如果有）
    返回保存路径。
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # 用域名做文件名，方便识别
    domain = urlparse(url).netloc.replace(".", "_")
    filepath = f"scraped/{timestamp}_{domain}.md"

    sections = [
        f"# 爬取内容",
        f"",
        f"**来源网址：** {url}",
        f"**爬取时间：** {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}",
        f"",
        f"---",
    ]

    if extracted:
        sections += [
            f"",
            f"## AI 提取的目标内容",
            f"",
            extracted,
            f"",
            f"---",
            f"",
            f"## 网页完整正文（原始）",
            f"",
            content,
        ]
    else:
        sections += [
            f"",
            f"## 网页完整正文",
            f"",
            content,
        ]

    sections.append(f"\n---\n*由 DeepResearch Agent 爬取保存*")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(sections))

    return filepath


# ──────────────────────────────────────────────
# 工具3：深度爬取（一个起始页 → 自动跟进子链接）
# ──────────────────────────────────────────────
def deep_scrape(start_url: str, max_pages: int = 5) -> str:
    """
    从 start_url 开始，自动发现并爬取同域名的子页面（最多 max_pages 页）。
    返回所有页面正文的合并文本。
    """
    visited = set()
    queue = [start_url]
    all_content = []

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        print(f"    爬取第 {len(visited)}/{max_pages} 页: {url[:70]}...")
        content, links = fetch_page_full(url)

        if content and not content.startswith("（"):
            all_content.append(f"【页面】{url}\n{content}")
            # 把新发现的链接加入队列
            for link in links:
                if link not in visited:
                    queue.append(link)

    return "\n\n" + ("─" * 40 + "\n\n").join(all_content)


# ──────────────────────────────────────────────
# 工具4：AI 从爬取内容中提取目标信息
# ──────────────────────────────────────────────
def extract_key_points(content: str, question: str) -> str:
    """返回与问题相关的要点列表（Markdown）。"""
    prompt = f"""从以下网页内容中，提取与"{question}"最相关的 4-6 个关键信息点。
要求：每条以 "• " 开头，一句话，包含具体数据或观点；去掉广告/导航噪音；只返回要点列表。
网页内容：\n{content[:4000]}"""
    return ai_generate(prompt)


def summarize_source(content: str, question: str, title: str) -> dict:
    """
    对单个网页生成结构化摘要。
    返回 {"summary": str, "key_points": str, "relevance": "high|medium|low"}
    """
    prompt = f"""你是信息提炼专家。针对研究主题"{question}"，分析以下网页。

标题：{title}
内容：
{content[:5000]}

请严格返回 JSON，格式：
{{
  "summary": "2-3句核心摘要，说明本页主要内容及与主题的关系",
  "key_points": "4-6个要点，每点以 • 开头，包含具体数据/事实/观点",
  "relevance": "high 或 medium 或 low"
}}
只返回 JSON，不要其他内容。"""

    try:
        text = ai_generate(prompt).strip()
        if "```" in text:
            text = re.split(r"```(?:json)?", text)[1].strip().rstrip("`").strip()
        return json.loads(text)
    except Exception:
        return {
            "summary": "内容提炼失败",
            "key_points": extract_key_points(content, question),
            "relevance": "medium",
        }


def compile_digest(sources: list, question: str) -> str:
    """
    将所有来源内容整合成一份连贯的内容概述（3-5 段）。
    """
    if not sources:
        return ""
    parts = "\n\n".join([
        f"【来源{i+1}：{s['title']}】\n{s.get('summary', '')}\n{s.get('key_points', s.get('raw_content', '')[:500])}"
        for i, s in enumerate(sources)
    ])
    prompt = f"""基于以下多个来源，针对"{question}"写一份综合性内容概述。

{parts}

要求：
- 3-5 段，每段聚焦一个维度（如：现状、趋势、数据、争议、结论等）
- 整合各来源信息，标注差异或共识
- 客观陈述，有具体数据支撑
- 用中文，专业流畅"""

    return ai_generate(prompt)


def ai_extract(content: str, instruction: str) -> str:
    """
    让 Gemini 从爬取的网页内容中，按 instruction 提取你想要的信息。
    例如：instruction = "提取所有招聘职位名称、薪资和要求"
    """
    prompt = f"""请从以下网页内容中，提取出：{instruction}

要求：
- 只返回提取到的内容，不要加多余解释
- 用清晰的格式输出（列表、表格均可）
- 如果找不到相关内容，说明"未找到相关内容"

网页内容：
{content[:8000]}"""  # 限制输入长度

    return ai_generate(prompt)


# ══════════════════════════════════════════════
# 推理层：AI 先想清楚再行动
# ══════════════════════════════════════════════

def reason(question: str) -> dict:
    """
    让 Gemini 先分析问题，输出结构化的思考计划。
    返回一个字典，包含：
      - question_type: 问题类型
      - need_search:   是否需要联网搜索
      - reasoning:     推理过程（给用户看）
      - search_queries: 建议的搜索关键词列表
      - answer_direct: 如果不需要搜索，直接在这里给出答案
    """
    prompt = f"""你是一个严谨的研究助手。请先分析以下问题，制定最佳处理策略。

问题：{question}

请以 JSON 格式返回你的分析，包含以下字段：
{{
  "question_type": "问题类型，从以下选一个：实时信息/深度研究/简单事实/闲聊对话",
  "need_search": true 或 false,
  "reasoning": "你的分析思路，解释为什么这样处理（2-4句话）",
  "search_queries": ["搜索词1", "搜索词2", "搜索词3", "搜索词4", "搜索词5"],
  "answer_direct": "如果 need_search 为 false，在这里直接给出完整回答；否则留空字符串"
}}

判断规则：
- 实时信息（天气/新闻/股价/招聘/活动）→ need_search: true
- 深度研究（分析/对比/趋势）→ need_search: true
- 简单事实（AI 本身知识库能准确回答）→ need_search: false
- 闲聊对话（你好/谢谢/怎么了）→ need_search: false

只返回 JSON，不要返回任何其他内容。"""

    try:
        text = ai_generate(prompt).strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)
    except Exception:
        # 解析失败就默认搜索
        return {
            "question_type": "深度研究",
            "need_search": True,
            "reasoning": "（推理解析失败，默认执行搜索）",
            "search_queries": [question],
            "answer_direct": ""
        }


# ══════════════════════════════════════════════
# 研究功能（原有逻辑）
# ══════════════════════════════════════════════

def web_search(query: str, max_results: int = 5) -> list[dict]:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(r)
    return results


def generate_sub_queries(question: str) -> list[str]:
    prompt = f"""请将以下研究问题拆解为3个不同角度的搜索关键词，用于网络搜索。
每个关键词应该覆盖问题的不同侧面。
只返回一个 JSON 数组，格式如：["关键词1", "关键词2", "关键词3"]
不要返回任何其他内容。

研究问题：{question}"""

    try:
        text = ai_generate(prompt).strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:].strip()
        queries = json.loads(text)
        return queries if isinstance(queries, list) else [question]
    except Exception:
        return [question]


def multi_search(question: str) -> str:
    print("  正在分析问题，生成搜索策略...")
    sub_queries = generate_sub_queries(question)
    print(f"  搜索角度: {sub_queries}")

    all_blocks = []
    seen_urls = set()

    for i, query in enumerate(sub_queries, 1):
        print(f"\n  [{i}/{len(sub_queries)}] 搜索「{query}」")
        results = web_search(query, max_results=3)
        print(f"  找到 {len(results)} 条结果")

        for r in results:
            url = r.get("href", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = r.get("title", "无标题")
            summary = r.get("body", "")
            print(f"    抓取: {url[:70]}...")
            full_text = fetch_page_content(url)

            block = (
                f"【标题】{title}\n"
                f"【网址】{url}\n"
                f"【摘要】{summary}\n"
                f"【正文】{full_text}"
            )
            all_blocks.append(block)

    if not all_blocks:
        return "（未找到相关搜索结果）"

    header = f"以下是从 {len(sub_queries)} 个角度搜索并抓取的网页资料（共 {len(all_blocks)} 条）：\n\n"
    return header + "\n\n" + ("─" * 40 + "\n\n").join(all_blocks)


def ask(user_input: str) -> str:
    """
    完整处理流程：
      第一步 → AI 推理：分析问题，制定策略
      第二步 → 根据策略决定：搜索 or 直接回答
      第三步 → 综合分析，输出结果
    """
    # ── 第一步：推理 ──
    print("  🧠 正在分析问题...\n")
    plan = reason(user_input)

    # 打印推理过程（让用户看到 AI 在想什么）
    print(f"  ┌─ AI 推理过程 {'─'*35}")
    print(f"  │ 问题类型：{plan.get('question_type', '未知')}")
    print(f"  │ 需要搜索：{'是' if plan.get('need_search') else '否'}")
    print(f"  │ 思路：{plan.get('reasoning', '')}")
    if plan.get('need_search') and plan.get('search_queries'):
        print(f"  │ 搜索策略：{plan.get('search_queries')}")
    print(f"  └{'─'*42}\n")

    # ── 第二步：根据推理结果决定行动 ──
    if not plan.get("need_search"):
        direct_answer = plan.get("answer_direct", "")
        if direct_answer:
            return direct_answer
        else:
            return ai_generate(user_input, system=SYSTEM_PROMPT)

    # 需要搜索：用推理出的关键词替换自动生成的关键词
    print("  🔍 开始多角度搜索...\n")
    sub_queries = plan.get("search_queries") or [user_input]

    all_blocks = []
    seen_urls = set()

    for i, query in enumerate(sub_queries, 1):
        print(f"  [{i}/{len(sub_queries)}] 搜索「{query}」")
        results = web_search(query, max_results=3)
        print(f"  找到 {len(results)} 条结果")

        for r in results:
            url = r.get("href", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = r.get("title", "无标题")
            summary = r.get("body", "")
            print(f"    抓取: {url[:70]}...")
            full_text = fetch_page_content(url)
            all_blocks.append(
                f"【标题】{title}\n【网址】{url}\n【摘要】{summary}\n【正文】{full_text}"
            )

    if not all_blocks:
        search_text = "（未找到相关搜索结果）"
    else:
        header = f"以下是从 {len(sub_queries)} 个角度搜索并抓取的网页资料（共 {len(all_blocks)} 条）：\n\n"
        search_text = header + "\n\n" + ("─" * 40 + "\n\n").join(all_blocks)

    # ── 第三步：综合分析 ──
    print("\n  📝 资料收集完毕，正在深度分析...")
    full_message = f"{search_text}\n\n用户的问题：{user_input}"
    return ai_generate(full_message, system=SYSTEM_PROMPT)


# ──────────────────────────────────────────────
# 保存研究报告
# ──────────────────────────────────────────────
def save_report(question: str, reply: str) -> str:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = f"reports/{timestamp}.md"
    content = f"""# 深度研究报告

**生成时间：** {datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}

---

## 研究问题

{question}

---

## 研究结果

{reply}

---

*本报告由 Lightweight DeepResearch Agent 自动生成*
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# ══════════════════════════════════════════════
# 处理 scrape 命令
# ══════════════════════════════════════════════
def handle_scrape(command: str):
    """
    解析 scrape 命令：
      scrape <网址>                     → 爬取并保存完整正文
      scrape <网址> <内容描述>          → 爬取后 AI 提取指定内容再保存
      scrape deep <网址>                → 深度爬取（自动跟进子页面）
      scrape deep <网址> <内容描述>     → 深度爬取后 AI 提取指定内容
    """
    # 去掉开头的 "scrape"
    parts = command[len("scrape"):].strip()

    deep_mode = False
    if parts.startswith("deep "):
        deep_mode = True
        parts = parts[5:].strip()

    # 分离 URL 和指令（URL 是第一个以 http 开头的词）
    match = re.match(r'(https?://\S+)\s*(.*)', parts)
    if not match:
        print("格式错误。用法：scrape <网址> [你想提取的内容]")
        print("示例：scrape https://example.com 提取所有招聘岗位和薪资")
        return

    url = match.group(1)
    instruction = match.group(2).strip()

    if deep_mode:
        print(f"\n  开始深度爬取: {url}")
        print("  （会自动跟进同域名子页面，最多5页）\n")
        content = deep_scrape(url, max_pages=5)
    else:
        print(f"\n  正在爬取: {url}")
        content, _ = fetch_page_full(url)

    if not content or content.startswith("（"):
        print(f"爬取失败: {content}")
        return

    print(f"  爬取成功，正文共 {len(content)} 字符")

    # 如果有提取指令，让 AI 处理
    extracted = ""
    if instruction:
        print(f"  AI 正在提取：{instruction}...")
        extracted = ai_extract(content, instruction)

    # 保存
    filepath = save_scraped(url, content, extracted)
    print(f"\n  已保存到: {filepath}")

    # 打印 AI 提取结果（如果有）
    if extracted:
        print(f"\nAI 提取结果：\n{extracted}")


# ══════════════════════════════════════════════
# 主循环
# ══════════════════════════════════════════════
def main():
    global last_question, last_reply

    print("=" * 60)
    print("  深度研究助手 — 多轮搜索 + 爬取保存版")
    print()
    print("  输入问题           → 多角度搜索并研究")
    print("  scrape <网址>      → 爬取并保存网页内容")
    print("  scrape <网址> <描述> → 爬取后 AI 提取指定内容")
    print("  scrape deep <网址> → 深度爬取（自动跟进子页面）")
    print("  save               → 保存上一条研究报告")
    print("  exit               → 退出")
    print("=" * 60)

    while True:
        user_input = input("\n输入: ").strip()

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("再见！")
            break

        if user_input.lower() == "save":
            if not last_reply:
                print("还没有可以保存的内容，请先提一个问题。")
                continue
            filepath = save_report(last_question, last_reply)
            print(f"报告已保存到: {filepath}")
            continue

        if user_input.lower().startswith("scrape "):
            handle_scrape(user_input)
            continue

        # 普通研究问题
        print("\n" + "=" * 42)
        reply = ask(user_input)
        last_question = user_input
        last_reply = reply
        print(f"\n助手:\n{reply}")
        print("\n（输入 save 可保存本次研究报告）")


if __name__ == "__main__":
    main()
