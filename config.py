"""
config.py — 环境变量、API Key、全局常量
"""
import os
from dotenv import load_dotenv

# 始终加载 config.py 同目录下的 .env，不依赖运行时 cwd
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# ── User-Agent 轮换池 ──
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
    "Gecko/20100101 Firefox/123.0",
]

# ── 多 AI 提供商配置 ──
PROVIDERS: dict[str, dict] = {
    "google": {
        "env":   "GOOGLE_API_KEY",
        "model": "gemini-2.5-flash",
    },
    "glm": {
        "env":      "GLM_API_KEY",
        "model":    "glm-5",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
    },
    "minimax": {
        "env":      "MINIMAX_API_KEY",
        "model":    "MiniMax-M2.7",
        "base_url": "https://api.minimax.chat/v1/",
    },
    "openai": {
        "env":      "OPENAI_API_KEY",
        "model":    "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1/",
    },
}

# ── 并发爬取线程数 ──
FETCH_WORKERS = 4

# ── 每个搜索角度最多取几条结果 ──
SEARCH_MAX_RESULTS = 5

# ── 搜索角度上限 ──
SEARCH_MAX_QUERIES = 4


_secret_cache: dict[str, str] = {}


def load_secret(key: str) -> str:
    """先读环境变量，再尝试 Streamlit Secrets（云端部署时用）。
    结果会被缓存，以便在 ThreadPoolExecutor 子线程中也能正常读取。
    """
    if key in _secret_cache:
        return _secret_cache[key]
    val = os.environ.get(key, "")
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get(key, "") or ""
        except Exception:
            pass
    _secret_cache[key] = val
    return val
