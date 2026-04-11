"""
tools.py — Agent 使用的所有具体工具函数
包含：网页爬取、搜索、文件存储、文档解析
"""
import datetime
import io
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from ddgs import DDGS

from config import USER_AGENTS


# ══════════════════════════════════════════════
# 网页爬取
# ══════════════════════════════════════════════

def fetch_page_content(url: str, max_chars: int = 6000) -> str:
    """
    抓取指定网页正文。
    策略：轮换 UA → trafilatura（高精度） → BeautifulSoup 兜底。
    """
    for ua in USER_AGENTS:
        try:
            resp = httpx.get(
                url, timeout=12, follow_redirects=True,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            if resp.status_code >= 400:
                continue

            # ① trafilatura 优先
            content = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
                no_fallback=False,
            )
            if content and len(content) > 150:
                return content[:max_chars]

            # ② BeautifulSoup 兜底
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
    完整抓取网页，返回 (正文内容, 页面内所有同域链接列表)。
    用于深度爬取时跟进子链接。
    """
    try:
        resp = httpx.get(
            url, timeout=10, follow_redirects=True,
            headers={"User-Agent": USER_AGENTS[0]},
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        content = trafilatura.extract(resp.text, include_comments=False,
                                      include_tables=True) or ""
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        links = []
        for a in soup.find_all("a", href=True):
            full = urljoin(base, a["href"])
            if full.startswith(base) and full != url:
                links.append(full)
        return content, list(set(links))
    except Exception as e:
        return f"（抓取失败: {type(e).__name__}）", []


def deep_scrape(start_url: str, max_pages: int = 5) -> str:
    """
    从 start_url 出发，自动跟进同域子页面（最多 max_pages 页）。
    返回所有页面正文的合并文本。
    """
    visited: set[str] = set()
    queue = [start_url]
    all_content: list[str] = []

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        content, links = fetch_page_full(url)
        if content and not content.startswith("（"):
            all_content.append(f"【页面】{url}\n{content}")
            for link in links:
                if link not in visited:
                    queue.append(link)

    separator = "\n\n" + "─" * 40 + "\n\n"
    return separator.join(all_content)


# ══════════════════════════════════════════════
# 搜索
# ══════════════════════════════════════════════

def fetch_via_jina(url: str, max_chars: int = 15000) -> str:
    """
    使用 Jina Reader API 抓取网页正文（自动解析、反反爬）。
    失败时降级到 fetch_page_content。
    """
    jina_url = f"https://r.jina.ai/{url}"
    try:
        resp = httpx.get(
            jina_url, timeout=10, follow_redirects=True,
            headers={
                "Accept": "text/plain",
                "User-Agent": USER_AGENTS[0],
                "X-Return-Format": "markdown",
            },
        )
        if resp.status_code == 200 and len(resp.text) > 100:
            return resp.text[:max_chars]
    except Exception:
        pass
    return fetch_page_content(url, max_chars)


def web_search(query: str, max_results: int = 5, timelimit: str = "") -> list[dict]:
    """使用 DuckDuckGo 搜索，返回结果列表。
    timelimit: "d"=24小时 / "w"=一周 / "m"=一月 / "y"=一年 / ""=不限
    """
    results = []
    try:
        with DDGS() as ddgs:
            kwargs: dict = {"max_results": max_results}
            if timelimit:
                kwargs["timelimit"] = timelimit
            for r in ddgs.text(query, **kwargs):
                results.append(r)
    except Exception:
        pass
    return results


# ══════════════════════════════════════════════
# 文件存储
# ══════════════════════════════════════════════

def save_scraped(url: str, content: str, extracted: str = "") -> str:
    """将爬取内容保存到 scraped/ 目录，返回保存路径。"""
    import os
    os.makedirs("scraped", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    domain = urlparse(url).netloc.replace(".", "_")
    filepath = f"scraped/{ts}_{domain}.md"

    sections = [
        "# 爬取内容", "",
        f"**来源网址：** {url}",
        f"**爬取时间：** {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}",
        "", "---",
    ]
    if extracted:
        sections += [
            "", "## AI 提取的目标内容", "", extracted,
            "", "---", "", "## 网页完整正文（原始）", "", content,
        ]
    else:
        sections += ["", "## 网页完整正文", "", content]

    sections.append("\n---\n*由 DeepResearch Agent 爬取保存*")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(sections))
    return filepath


def save_report(question: str, reply: str) -> str:
    """将研究报告保存到 reports/ 目录，返回保存路径。"""
    import os
    os.makedirs("reports", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = f"reports/{ts}.md"
    content = f"""# 深度研究报告

**生成时间：** {datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}

---

## 研究问题

{question}

---

## 研究结果

{reply}

---

*本报告由 DeepResearch Agent 自动生成*
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# ══════════════════════════════════════════════
# 本地文档解析（RAG 输入层）
# ══════════════════════════════════════════════

def parse_uploaded_file(file_bytes: bytes, filename: str) -> str:
    """
    解析上传的本地文档，返回文本内容。
    支持：PDF、DOCX、TXT、CSV、MD
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    try:
        if ext == "pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                text = "\n".join(p.extract_text() or "" for p in reader.pages)
                return text[:20000] if text.strip() else "（PDF 无法提取文本，可能是扫描件）"
            except ImportError:
                return "（需要安装 pypdf：pip install pypdf）"

        elif ext == "docx":
            try:
                import docx
                doc = docx.Document(io.BytesIO(file_bytes))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                return text[:20000]
            except ImportError:
                return "（需要安装 python-docx：pip install python-docx）"

        elif ext == "csv":
            try:
                import pandas as pd
                df = pd.read_csv(io.BytesIO(file_bytes))
                return df.to_string(max_rows=200)
            except ImportError:
                return file_bytes.decode("utf-8", errors="ignore")[:10000]

        elif ext in ("txt", "md"):
            return file_bytes.decode("utf-8", errors="ignore")[:20000]

        else:
            return f"（不支持的文件格式：{ext}）"

    except Exception as e:
        return f"（文件解析失败：{e}）"
