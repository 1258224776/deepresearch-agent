"""
config.py — 环境变量、API Key、全局常量

提供商配置优先从同目录的 providers.yaml 加载（#7 配置外置）。
找不到 yaml 或解析失败时，自动回退到下方的内置默认值，不影响运行。
修改模型只需编辑 providers.yaml，无需动此文件。
"""
import os
from dotenv import load_dotenv

# 始终加载 config.py 同目录下的 .env，不依赖运行时 cwd
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def _load_providers_yaml() -> dict | None:
    """尝试从 providers.yaml 加载提供商配置，失败返回 None。"""
    yaml_path = os.path.join(os.path.dirname(__file__), "providers.yaml")
    if not os.path.exists(yaml_path):
        return None
    try:
        import yaml  # PyYAML，requirements.txt 里已有
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("providers") or None
    except Exception:
        return None

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

# ══════════════════════════════════════════════
# 多 AI 提供商配置
#
# type 字段说明：
#   "google"      → google-genai SDK（需 VPN）
#   "anthropic"   → anthropic SDK（需 VPN）
#   "openai_compat" → OpenAI 兼容接口（国内直连）
#
# structured_output 字段：
#   True  → 调用时启用原生 JSON 模式，返回 100% 合法 JSON
#   False → 依赖 Prompt 约束 + 正则清洗
# ══════════════════════════════════════════════
_PROVIDERS_DEFAULT: dict[str, dict] = {

    # ━━━ 海外阵营（需 VPN）━━━━━━━━━━━━━━━━━━━━━

    # 主脑首选：Google Gemini 2.5 Pro（当前可用稳定版；3.0 Preview 未公开放出时以此为准）
    "google_pro": {
        "env":               "GOOGLE_API_KEY",
        "model":             "gemini-2.5-pro",
        "type":              "google",
        "structured_output": True,   # 支持 response_mime_type=application/json
    },
    # 主脑备选：Claude Opus 4.6（LMArena 盲测第一，洞察天花板）
    "claude_opus": {
        "env":               "ANTHROPIC_API_KEY",
        "model":             "claude-opus-4-6",
        "type":              "anthropic",
        "structured_output": False,
    },
    # 打工首选：Gemini 2.5 Flash（极速 + 原生 JSON 模式）
    "google": {
        "env":               "GOOGLE_API_KEY",
        "model":             "gemini-2.5-flash",
        "type":              "google",
        "structured_output": True,
    },
    # 打工备选：Claude Haiku 4.5（HTML 结构提取王者）
    "claude_haiku": {
        "env":               "ANTHROPIC_API_KEY",
        "model":             "claude-haiku-4-5-20251001",
        "type":              "anthropic",
        "structured_output": False,
    },

    # ━━━ 国内直连阵营 ━━━━━━━━━━━━━━━━━━━━━━━━━

    # 智谱 GLM —— 主脑：GLM-5（国内榜第一梯队首位）
    "glm_pro": {
        "env":               "GLM_API_KEY",
        "model":             "glm-5",
        "base_url":          "https://open.bigmodel.cn/api/paas/v4/",
        "type":              "openai_compat",
        "native_tools":      False,
        "tool_choice":       "auto",
        "structured_output": False,
    },
    # 智谱 GLM —— 打工：GLM-4-Flash（毫秒级响应，高并发友好）
    "glm": {
        "env":               "GLM_API_KEY",
        "model":             "glm-4-flash",
        "base_url":          "https://open.bigmodel.cn/api/paas/v4/",
        "type":              "openai_compat",
        "native_tools":      False,
        "tool_choice":       "auto",
        "structured_output": False,
    },

    # MiniMax —— 主脑：MiniMax-M2.7（格式遵从极优，幻觉极少）
    "minimax": {
        "env":               "MINIMAX_API_KEY",
        "model":             "MiniMax-M2.7",
        "base_url":          "https://api.minimax.chat/v1/",
        "type":              "openai_compat",
        "structured_output": False,
    },
    # MiniMax —— 打工：abab6.5g（高并发低延迟优化）
    "minimax_worker": {
        "env":               "MINIMAX_API_KEY",
        "model":             "abab6.5g",
        "base_url":          "https://api.minimax.chat/v1/",
        "type":              "openai_compat",
        "structured_output": False,
    },

    # 硅基流动 —— 主脑：DeepSeek-V3（满血开源旗舰）
    "siliconflow_pro": {
        "env":               "SILICONFLOW_API_KEY",
        "model":             "deepseek-ai/DeepSeek-V3",
        "base_url":          "https://api.siliconflow.cn/v1/",
        "type":              "openai_compat",
        "structured_output": False,
    },
    # 硅基流动 —— 打工：Qwen2.5-7B（速度极快，注意 JSON 标签清洗）
    "siliconflow": {
        "env":               "SILICONFLOW_API_KEY",
        "model":             "Qwen/Qwen2.5-7B-Instruct",
        "base_url":          "https://api.siliconflow.cn/v1/",
        "type":              "openai_compat",
        "structured_output": False,
    },

    # OpenAI（保留兼容）
    "openai": {
        "env":               "OPENAI_API_KEY",
        "model":             "gpt-4o-mini",
        "base_url":          "https://api.openai.com/v1/",
        "type":              "openai_compat",
        "structured_output": False,
    },
}

# 优先使用 providers.yaml，找不到则用内置默认值
PROVIDERS: dict[str, dict] = _load_providers_yaml() or _PROVIDERS_DEFAULT

# ══════════════════════════════════════════════
# 引擎预设
#
# 深度分析模式：海外最强主脑 + 全线 Worker，质量最高（需 VPN）
# 极速直连模式：全程国内模型，无需 VPN，数秒出结果
#
# 每项格式：逗号分隔的 provider 名称，运行时按序尝试
# ══════════════════════════════════════════════
ENGINE_PRESETS: dict[str, dict] = {
    "deep": {
        "label":        "🌟 深度分析",
        "desc":         "主脑用全球最强模型，洞察质量最高（需 VPN）",
        "orchestrator": "google_pro,claude_opus,glm_pro,minimax,siliconflow_pro",
        "worker":       "google,claude_haiku,glm,minimax_worker,siliconflow",
        "analyst":      "google_pro,claude_opus,glm_pro,minimax",
    },
    "fast": {
        "label":        "⚡ 极速直连",
        "desc":         "全程国内模型，无需 VPN，秒级响应",
        "orchestrator": "glm_pro,minimax,siliconflow_pro",
        "worker":       "glm,minimax_worker,siliconflow",
        "analyst":      "glm_pro,minimax,siliconflow_pro",
    },
}

# 角色化路由（独立使用时的默认顺序，可被引擎预设覆盖）
ROLE_ORDER: dict[str, str] = {
    "orchestrator": "google_pro,claude_opus,glm_pro,minimax,siliconflow_pro",
    "worker":       "google,claude_haiku,glm,minimax_worker,siliconflow",
    "analyst":      "google_pro,glm_pro,minimax,siliconflow_pro",
}

# ── 并发爬取线程数 ──
FETCH_WORKERS = 8

# ── 每个搜索角度最多取几条结果 ──
SEARCH_MAX_RESULTS = 5

# ── 搜索角度上限 ──
SEARCH_MAX_QUERIES = 4

# ── URL 提取流水线：基础切块字符数（动态调整，见 agent.py） ──
CHUNK_SIZE = 2000

# ── URL 提取流水线：并发打工线程数 ──
WORKER_THREADS = 10

# ── Worker 并发限速：每次请求前随机延迟范围（秒） ──
JITTER_RANGE = (0.05, 0.3)

_secret_cache: dict[str, str] = {}
_runtime_role_order: dict[str, str] = {}


def load_secret(key: str) -> str:
    """
    优先级：session state 临时 Key → 环境变量。
    结果会被缓存，以便在 ThreadPoolExecutor 子线程中也能正常读取。
    """
    if key in _secret_cache:
        return _secret_cache[key]
    val = os.environ.get(key, "")
    _secret_cache[key] = val
    return val


def set_runtime_key(env_key: str, value: str) -> None:
    """允许前端在运行时注入 API Key（覆盖缓存，不写 .env）。"""
    if value and value.strip():
        _secret_cache[env_key] = value.strip()
        os.environ[env_key] = value.strip()


def set_runtime_role_order(role: str, providers: list[str] | str) -> None:
    """在当前进程内覆盖某个角色的 provider 顺序。"""
    if isinstance(providers, str):
        order = ",".join(p.strip() for p in providers.split(",") if p.strip())
    else:
        order = ",".join(str(p).strip() for p in providers if str(p).strip())
    if order:
        _runtime_role_order[role] = order
    else:
        _runtime_role_order.pop(role, None)


def get_runtime_role_order(role: str) -> str:
    return _runtime_role_order.get(role, "")


def clear_runtime_role_orders() -> None:
    _runtime_role_order.clear()


def get_effective_role_order(role: str, engine: str = "") -> str:
    preset = ENGINE_PRESETS.get(engine, {})
    if preset.get(role, ""):
        return preset.get(role, "")
    runtime = get_runtime_role_order(role)
    if runtime:
        return runtime
    return ROLE_ORDER.get(role, "")
