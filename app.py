"""
DeepResearch Agent — v6
企业级模块化重构 + 并行爬取 + 总进度条 + 爬取汇总
"""

import os
import streamlit as st

from agent import (
    ai_generate, ai_generate_role, reason, summarize_source, compile_digest,
    cross_validate, generate_scrape_digest,
    chat_with_report, run_research, run_url_pipeline,
)
from config import (
    ENGINE_PRESETS,
    PROVIDERS,
    ROLE_ORDER,
    clear_runtime_role_orders,
    get_runtime_role_order,
    load_secret,
    set_runtime_key,
    set_runtime_role_order,
)
from skills import BUILTIN_SKILL_REGISTRY
from skills.config import get_skill_state_map
from skills.profiles import DEFAULT_SKILL_PROFILE, get_profile_metadata_list
from tools import (
    web_search, fetch_page_content, save_report, parse_uploaded_file,
)
from prompts import SYSTEM_PROMPT, TEMPLATES

# ──────────────────────────────────────────────
# 页面配置
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="DeepResearch Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# 全局样式（UI/UX · 数字羊皮纸 · 暖阳赭石）
# ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

*, *::before, *::after {
    font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    box-sizing: border-box;
}

/* ══════════════════════════════
   主题 Tokens（暖色调）
══════════════════════════════ */
:root {
    --bg: #FAF8F5;
    --bg-2: #F5F1EA;
    --surface: #FFFFFF;
    --surface-2: #FCF8F3;
    --surface-muted: #F3EEE6;
    --border: rgba(61, 50, 44, 0.10);
    --border-strong: rgba(61, 50, 44, 0.16);
    --border-hover: rgba(194, 87, 26, 0.40);
    --text-primary: #3D322C;
    --text-secondary: #6B5F56;
    --text-muted: #978B82;
    --text-faint: #B8ADA3;
    --accent: #C2571A;
    --accent-hover: #A5481A;
    --accent-soft: rgba(194, 87, 26, 0.10);
    --accent-softer: rgba(194, 87, 26, 0.05);
    --accent-line: rgba(194, 87, 26, 0.28);
    --shadow-sm: 0 2px 8px rgba(120, 76, 40, 0.06);
    --shadow-md: 0 8px 24px rgba(120, 76, 40, 0.10);
    --shadow-lg: 0 18px 48px rgba(120, 76, 40, 0.12);
    --ok: #0F9268;
    --ok-soft: rgba(15, 146, 104, 0.10);
    --warn: #C77700;
    --warn-soft: rgba(199, 119, 0, 0.10);
    --danger: #C4423A;
    --danger-soft: rgba(196, 66, 58, 0.10);
}

/* ══════════════════════════════
   动效 Keyframes
══════════════════════════════ */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(22px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}
@keyframes float {
    0%, 100% { transform: translateY(0px); }
    50%       { transform: translateY(-6px); }
}
@keyframes warmPulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(194, 87, 26, 0.35); }
    50%       { box-shadow: 0 0 0 6px rgba(194, 87, 26, 0); }
}
@keyframes shimmer {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}

/* ── 背景：数字羊皮纸 + 暖阳 ── */
.stApp {
    background: var(--bg);
    background-image:
        radial-gradient(ellipse 60% 40% at 90% 0%, rgba(245, 158, 11, 0.10) 0%, transparent 60%),
        radial-gradient(ellipse 50% 35% at 0% 100%, rgba(194, 87, 26, 0.06) 0%, transparent 55%);
    min-height: 100vh;
    animation: fadeIn 0.5s ease;
    color: var(--text-primary);
}

/* ── 全局文字兜底：Streamlit 内部组件一律用深棕 ── */
.stApp, .stApp p, .stApp span, .stApp div, .stApp li, .stApp label,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp strong, .stApp em, .stApp small, .stApp code {
    color: var(--text-primary);
}
.stApp a { color: var(--accent); }
.stApp a:hover { color: var(--accent-hover); }

/* Streamlit markdown/caption/label */
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li,
div[data-testid="stMarkdownContainer"] span,
div[data-testid="stMarkdownContainer"] strong,
div[data-testid="stMarkdownContainer"] em { color: var(--text-primary) !important; }

div[data-testid="stCaptionContainer"],
div[data-testid="stCaptionContainer"] * { color: var(--text-muted) !important; }

label[data-testid="stWidgetLabel"],
label[data-testid="stWidgetLabel"] * { color: var(--text-primary) !important; }

/* metric / header 组件 */
div[data-testid="stMetricLabel"] * { color: var(--text-muted) !important; }
div[data-testid="stMetricValue"] * { color: var(--text-primary) !important; }
div[data-testid="stMetricDelta"] * { color: var(--text-secondary) !important; }
div[data-testid="stHeader"] { background: transparent !important; }

/* 代码块与行内代码 */
.stApp code, .stApp pre {
    background: var(--surface-2) !important;
    color: var(--accent-hover) !important;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1px 6px;
}
.stApp pre { padding: 12px 14px; }
.stApp pre code { background: transparent !important; border: none; padding: 0; color: var(--text-primary) !important; }

/* 表格 */
.stApp table { color: var(--text-primary); }
.stApp th { color: var(--text-primary); background: var(--surface-2); border-bottom: 1px solid var(--border); }
.stApp td { border-bottom: 1px solid var(--border); }

/* ── 隐藏 Streamlit 默认元素 ── */
footer { visibility: hidden; }
.block-container { padding-top: 2rem !important; padding-bottom: 4rem !important; max-width: 1200px !important; }

/* ══════════════════════════════
   首页 Hero
══════════════════════════════ */
.hero-wrap {
    text-align: center;
    padding: 60px 20px 50px;
    animation: fadeUp 0.7s ease both;
}
.hero-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--accent-soft);
    border: 1px solid var(--accent-line);
    border-radius: 100px;
    padding: 6px 16px;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 24px;
    animation: warmPulse 3s ease-in-out infinite;
}
.hero-title {
    font-size: clamp(2rem, 5vw, 3.2rem);
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.15;
    color: var(--text-primary);
    margin-bottom: 18px;
    animation: fadeUp 0.8s ease 0.1s both;
}
.hero-title .accent {
    background: linear-gradient(135deg, #C2571A 0%, #E5874A 55%, #D4A257 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-sub {
    font-size: 1.05rem;
    color: var(--text-secondary);
    max-width: 520px;
    margin: 0 auto 48px;
    line-height: 1.75;
    font-weight: 400;
}

/* ── 功能选择卡片 ── */
.mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 860px; margin: 0 auto; }

.mode-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 36px 30px 28px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s, transform 0.3s, box-shadow 0.3s;
    text-align: left;
    cursor: default;
    animation: fadeUp 0.6s ease both;
    box-shadow: var(--shadow-sm);
}
.mode-card:hover {
    border-color: var(--border-hover);
    transform: translateY(-5px);
    box-shadow: var(--shadow-lg);
}
.mode-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #C2571A, #E5874A, transparent);
    opacity: 0.7;
}
.mode-card-glow {
    position: absolute;
    top: -40px; right: -40px;
    width: 140px; height: 140px;
    background: radial-gradient(circle, rgba(229, 135, 74, 0.12) 0%, transparent 70%);
    pointer-events: none;
}
.mode-icon-wrap {
    width: 52px; height: 52px;
    background: var(--accent-soft);
    border: 1px solid var(--accent-line);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
    margin-bottom: 20px;
    color: var(--accent);
    animation: float 4s ease-in-out infinite;
}
.mode-title { font-size: 1.05rem; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; }
.mode-desc  { font-size: 0.87rem; color: var(--text-secondary); line-height: 1.7; margin-bottom: 18px; }
.mode-steps {
    display: flex; gap: 6px; flex-wrap: wrap;
}
.mode-step {
    font-size: 0.72rem;
    color: var(--accent);
    background: var(--accent-soft);
    border: 1px solid var(--accent-line);
    border-radius: 100px;
    padding: 3px 10px;
    font-weight: 500;
}

/* ══════════════════════════════
   顶部导航栏
══════════════════════════════ */
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 0 28px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 32px;
}
.topbar-logo {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-primary);
    display: flex; align-items: center; gap: 8px;
}
.topbar-logo .dot {
    width: 8px; height: 8px;
    background: var(--accent);
    border-radius: 50%;
    box-shadow: 0 0 10px rgba(194, 87, 26, 0.45);
}
.topbar-crumb {
    font-size: 0.82rem;
    color: var(--text-muted);
    display: flex; align-items: center; gap: 6px;
}
.topbar-crumb .current { color: var(--accent); font-weight: 500; }

/* ══════════════════════════════
   内容统计条
══════════════════════════════ */
.stat-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 28px;
    flex-wrap: wrap;
}
.stat-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 0.82rem;
    color: var(--text-secondary);
    font-weight: 500;
    box-shadow: var(--shadow-sm);
}
.stat-chip .val { color: var(--accent); font-weight: 700; font-size: 0.95rem; }

/* ══════════════════════════════
   综合摘要卡
══════════════════════════════ */
.digest-card {
    background: linear-gradient(135deg, #FFFFFF 0%, #FCF6EC 100%);
    border: 1px solid var(--accent-line);
    border-radius: 18px;
    padding: 32px 36px;
    margin-bottom: 32px;
    position: relative;
    overflow: hidden;
    box-shadow: var(--shadow-md);
}
.digest-card::after {
    content: '';
    position: absolute;
    bottom: -30px; right: -30px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(229, 135, 74, 0.10) 0%, transparent 65%);
    pointer-events: none;
}
.digest-label {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 16px;
}
.digest-label::before {
    content: '';
    width: 16px; height: 2px;
    background: linear-gradient(90deg, #C2571A, #E5874A);
    border-radius: 2px;
}
.digest-body {
    font-size: 0.95rem;
    color: var(--text-primary);
    line-height: 1.85;
    font-weight: 400;
}

/* ══════════════════════════════
   来源卡片
══════════════════════════════ */
.src-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 22px;
    margin-bottom: 16px;
    transition: border-color 0.25s, box-shadow 0.25s, transform 0.25s;
    animation: fadeUp 0.5s ease both;
    box-shadow: var(--shadow-sm);
}
.src-card:hover {
    border-color: var(--border-hover);
    box-shadow: var(--shadow-md);
    transform: translateY(-3px);
}
.src-header {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 12px;
}
.src-num {
    flex-shrink: 0;
    width: 26px; height: 26px;
    background: linear-gradient(135deg, #C2571A, #E5874A);
    border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.7rem; font-weight: 800; color: #fff;
    letter-spacing: 0;
    box-shadow: 0 4px 12px rgba(194, 87, 26, 0.30);
}
.src-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.4;
    flex: 1;
}
.src-meta {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-bottom: 13px;
    flex-wrap: wrap;
}
.badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 100px;
    font-size: 0.69rem;
    font-weight: 600;
}
.badge-high   { background: var(--ok-soft);     color: var(--ok);     border: 1px solid rgba(15, 146, 104, 0.22); }
.badge-medium { background: var(--warn-soft);   color: var(--warn);   border: 1px solid rgba(199, 119, 0, 0.22); }
.badge-low    { background: rgba(151, 139, 130, 0.12); color: var(--text-muted); border: 1px solid rgba(151, 139, 130, 0.22); }
.badge-domain { background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-line); }

.src-summary {
    font-size: 0.86rem;
    color: var(--text-secondary);
    line-height: 1.7;
    margin-bottom: 12px;
    padding: 11px 14px;
    background: var(--surface-2);
    border-radius: 10px;
    border-left: 3px solid var(--accent-line);
}
.src-points {
    font-size: 0.84rem;
    color: var(--text-primary);
    line-height: 1.8;
    white-space: pre-wrap;
}

/* ══════════════════════════════
   报告区
══════════════════════════════ */
.report-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 36px 40px;
    margin-top: 8px;
    font-size: 0.94rem;
    color: var(--text-primary);
    line-height: 1.9;
    position: relative;
    overflow: hidden;
    box-shadow: var(--shadow-md);
}
.report-wrap::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #C2571A, #E5874A, #D4A257);
}

/* ══════════════════════════════
   分区标题
══════════════════════════════ */
.section-title {
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--text-muted);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin: 32px 0 16px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, var(--border), transparent);
}

/* ══════════════════════════════
   按钮覆盖
══════════════════════════════ */
div[data-testid="stButton"] > button {
    border-radius: 10px !important;
    font-size: 0.86rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em !important;
    padding: 10px 20px !important;
    transition: all 0.2s !important;
    cursor: pointer !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
    background: var(--accent) !important;
    border: 1px solid var(--accent) !important;
    color: #fff !important;
    box-shadow: 0 4px 14px rgba(194, 87, 26, 0.25) !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: var(--accent-hover) !important;
    border-color: var(--accent-hover) !important;
    box-shadow: 0 6px 22px rgba(194, 87, 26, 0.35) !important;
    transform: translateY(-1px) !important;
}
div[data-testid="stButton"] > button[kind="secondary"] {
    background: var(--surface) !important;
    border: 1px solid var(--border-strong) !important;
    color: var(--text-secondary) !important;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background: var(--accent-softer) !important;
    border-color: var(--border-hover) !important;
    color: var(--accent) !important;
}

/* ── 输入框 ── */
div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea {
    background: var(--surface) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: 10px !important;
    color: var(--text-primary) !important;
    font-size: 0.94rem !important;
    font-weight: 500 !important;
    caret-color: var(--accent) !important;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus {
    border-color: var(--border-hover) !important;
    box-shadow: 0 0 0 3px var(--accent-soft) !important;
    color: var(--text-primary) !important;
}
div[data-testid="stTextInput"] input::placeholder,
div[data-testid="stTextArea"] textarea::placeholder {
    color: var(--text-faint) !important;
    opacity: 1 !important;
}

/* ── 侧边栏 ── */
section[data-testid="stSidebar"] {
    background: var(--surface-2) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * {
    color: var(--text-primary);
}

/* ── 文件条目 ── */
.file-item {
    background: var(--surface-muted);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 7px 12px;
    margin: 4px 0;
    font-size: 0.79rem;
    color: var(--text-secondary);
    font-weight: 500;
}

/* ── 返回按钮 ── */
.back-btn-wrap div[data-testid="stButton"] > button {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-secondary) !important;
    font-size: 0.82rem !important;
    padding: 6px 14px !important;
    border-radius: 8px !important;
    width: auto !important;
}
.back-btn-wrap div[data-testid="stButton"] > button:hover {
    background: var(--accent-softer) !important;
    border-color: var(--border-hover) !important;
    color: var(--accent) !important;
}

/* ── 顶栏进入动效 ── */
.topbar { animation: fadeIn 0.4s ease; }
.digest-card { animation: fadeUp 0.6s ease both; }
.report-wrap { animation: fadeUp 0.5s ease both; }
.stat-bar    { animation: fadeUp 0.4s ease 0.1s both; }

/* ── divider ── */
hr { border-color: var(--border) !important; }

/* ── expander ── */
div[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    background: var(--surface) !important;
    box-shadow: var(--shadow-sm);
}
div[data-testid="stExpander"] summary { color: var(--text-primary) !important; }

/* ── status 组件 ── */
div[data-testid="stStatusWidget"] {
    border-radius: 12px !important;
    border: 1px solid var(--accent-line) !important;
    background: var(--surface) !important;
    color: var(--text-primary) !important;
}

/* ══════════════════════════════
   功能页：表单 / 输入卡片
══════════════════════════════ */
div[data-testid="stForm"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 20px !important;
    padding: 32px 36px !important;
    position: relative;
    overflow: hidden;
    box-shadow: var(--shadow-md);
}
div[data-testid="stForm"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #C2571A, #E5874A, transparent);
    opacity: 0.6;
}

/* ── 功能页 Hero 输入区 ── */
.page-hero {
    max-width: 700px;
    margin: 0 auto;
    padding: 48px 0 32px;
    text-align: center;
    animation: fadeUp 0.6s ease both;
}
.page-hero-title {
    font-size: clamp(1.6rem, 3.5vw, 2.2rem);
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -0.02em;
    margin-bottom: 12px;
}
.page-hero-title .accent {
    background: linear-gradient(135deg, #C2571A 0%, #E5874A 55%, #D4A257 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.page-hero-sub {
    font-size: 0.95rem;
    color: var(--text-secondary);
    line-height: 1.75;
    margin-bottom: 36px;
}

/* ── 顶部导航优化 ── */
.topbar-wrap {
    background: rgba(250, 248, 245, 0.90);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
    margin: -32px -24px 36px;
    padding: 16px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    animation: fadeIn 0.3s ease;
    position: sticky;
    top: 0;
    z-index: 100;
}
.topbar-brand {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--accent);
    display: flex; align-items: center; gap: 8px;
}
.topbar-brand .dot {
    width: 7px; height: 7px;
    background: var(--accent);
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(194, 87, 26, 0.55);
    animation: warmPulse 2.5s ease-in-out infinite;
}
.topbar-crumb-new {
    font-size: 0.8rem;
    color: var(--text-muted);
    display: flex; align-items: center; gap: 8px;
}
.topbar-crumb-new .sep { color: var(--text-faint); }
.topbar-crumb-new .cur { color: var(--accent); font-weight: 600; }

/* ── 进度条美化 ── */
div[data-testid="stProgress"] > div {
    background: var(--surface-muted) !important;
    border-radius: 100px !important;
    overflow: hidden;
}
div[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #C2571A, #E5874A, #D4A257) !important;
    border-radius: 100px !important;
    transition: width 0.3s ease !important;
}

/* ── chat 消息 ── */
div[data-testid="stChatMessage"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 14px !important;
    padding: 14px 18px !important;
    margin-bottom: 10px !important;
    color: var(--text-primary) !important;
    box-shadow: var(--shadow-sm);
}

/* ── info / warning / success 提示 ── */
div[data-testid="stAlert"] {
    border-radius: 12px !important;
    border: none !important;
    background: var(--accent-soft) !important;
    border-left: 3px solid var(--accent) !important;
    color: var(--text-primary) !important;
    font-size: 0.86rem !important;
}

/* ── dataframe ── */
div[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 14px !important;
    overflow: hidden !important;
    background: var(--surface) !important;
    box-shadow: var(--shadow-sm);
}

/* ── select / radio ── */
div[data-testid="stSelectbox"] > div,
div[data-testid="stMultiSelect"] > div {
    background: var(--surface) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: 10px !important;
    color: var(--text-primary) !important;
}

/* ── file uploader ── */
div[data-testid="stFileUploader"] {
    background: var(--surface-2) !important;
    border: 1.5px dashed var(--accent-line) !important;
    border-radius: 14px !important;
    padding: 20px !important;
}
div[data-testid="stFileUploader"]:hover {
    border-color: var(--border-hover) !important;
    background: var(--accent-softer) !important;
}

/* ── spinner ── */
div[data-testid="stSpinner"] {
    color: var(--accent) !important;
}

/* ── download button ── */
div[data-testid="stDownloadButton"] > button {
    background: var(--accent-soft) !important;
    border: 1px solid var(--accent-line) !important;
    color: var(--accent) !important;
    border-radius: 10px !important;
    font-size: 0.84rem !important;
    font-weight: 600 !important;
}
div[data-testid="stDownloadButton"] > button:hover {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    color: #fff !important;
}

/* ══════════════════════════════
   Aggregation Dashboard
══════════════════════════════ */
.agg-dashboard { display:flex; flex-direction:column; gap:20px; animation:fadeUp 0.5s ease both; }
.agg-title { font-size:1.5rem; font-weight:800; color:var(--text-primary); letter-spacing:-0.02em; margin-bottom:4px; }

/* stat cards */
.agg-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }
.agg-stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px; padding: 18px 18px 14px; text-align: center;
    box-shadow: var(--shadow-sm);
}
.agg-stat-value { font-size:1.9rem; font-weight:800; color:var(--accent); letter-spacing:-0.03em; line-height:1; margin-bottom:6px; }
.agg-stat-label { font-size:0.76rem; color:var(--text-muted); font-weight:500; }
.agg-stat-change { font-size:0.82rem; font-weight:600; margin-top:6px; }
.agg-stat-change.pos { color:var(--ok); }
.agg-stat-change.neg { color:var(--danger); }

/* highlights */
.agg-highlights { display:flex; flex-direction:column; gap:9px; }
.agg-hl-row {
    background: var(--surface); border: 1px solid var(--border);
    border-left: 3px solid; border-radius: 10px; padding: 11px 16px;
    display: flex; align-items: center; gap: 10px;
    font-size: 0.91rem; color: var(--text-primary);
    box-shadow: var(--shadow-sm);
}
.agg-hl-icon { font-size:1.05rem; flex-shrink:0; }
.agg-hl-content { flex:1; line-height:1.55; }
.agg-hl-tag {
    font-size:0.70rem; font-weight:700; padding:2px 10px; border-radius:100px;
    background: var(--accent-soft); color: var(--accent); white-space:nowrap;
}

/* section title */
.agg-section-title {
    font-size:1rem; font-weight:700; color: var(--text-secondary);
    margin-top:4px; margin-bottom:10px;
    padding-bottom:8px; border-bottom:1px solid var(--border);
}

/* top items */
.agg-items-list { display:flex; flex-direction:column; gap:9px; }
.agg-item-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 14px 18px;
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    box-shadow: var(--shadow-sm);
}
.agg-item-left { flex:1; min-width:0; }
.agg-item-title { font-size:0.97rem; font-weight:700; color: var(--text-primary); margin-bottom:3px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.agg-item-sub { font-size:0.80rem; color: var(--text-muted); margin-bottom:7px; }
.agg-item-tags { display:flex; flex-wrap:wrap; gap:5px; }
.agg-tag { font-size:0.70rem; font-weight:600; padding:2px 9px; border-radius:100px; background: var(--accent-soft); color: var(--accent); }
.agg-new-badge { font-size:0.67rem; font-weight:700; padding:2px 8px; border-radius:100px; background: var(--danger-soft); color: var(--danger); }
.agg-item-value { font-size:1.35rem; font-weight:800; color: var(--accent); white-space:nowrap; }

/* analysis */
.agg-analysis { display:flex; flex-direction:column; gap:18px; }
.agg-metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; }
.agg-metric-card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 14px 16px; box-shadow: var(--shadow-sm); }
.agg-metric-value { font-size:1.55rem; font-weight:800; color: var(--accent); line-height:1.2; }
.agg-metric-label { font-size:0.76rem; color: var(--text-muted); margin-top:4px; }
.agg-metric-sub { font-size:0.73rem; color: var(--text-faint); margin-top:3px; }

/* distributions */
.agg-dist-title { font-size:0.82rem; font-weight:600; color: var(--text-muted); margin-bottom:8px; }
.agg-dist-bars { display:flex; flex-direction:column; gap:9px; }
.agg-dist-row { display:flex; align-items:center; gap:10px; }
.agg-dist-label { font-size:0.80rem; color: var(--text-secondary); min-width:36px; }
.agg-dist-bar-wrap { flex:1; background: var(--surface-muted); border-radius:100px; height:7px; overflow:hidden; }
.agg-dist-bar-fill { height:100%; border-radius:100px; background: linear-gradient(90deg, #E5874A, #C2571A); }
.agg-dist-pct { font-size:0.76rem; color: var(--text-muted); white-space:nowrap; min-width:90px; }

/* directions */
.agg-directions { display:flex; flex-wrap:wrap; gap:10px; }
.agg-dir-chip { background: var(--surface); border: 1px solid var(--border); border-radius: 13px; padding: 10px 14px; min-width: 72px; text-align: center; box-shadow: var(--shadow-sm); }
.agg-dir-name { font-size:0.75rem; color: var(--text-muted); margin-bottom:3px; }
.agg-dir-count { font-size:1.25rem; font-weight:800; color: var(--text-primary); }
.agg-dir-trend { font-size:0.70rem; font-weight:600; margin-top:3px; }
.agg-dir-trend.trend-up { color: var(--ok); }
.agg-dir-trend.trend-down { color: var(--danger); }
.agg-dir-trend.trend-flat { color: var(--text-muted); }

/* recommendations */
.agg-recs { display:flex; flex-direction:column; gap:9px; }
.agg-rec-card {
    background: var(--surface); border: 1px solid var(--border);
    border-left: 3px solid; border-radius: 12px; padding: 13px 16px;
    display: flex; gap: 11px; align-items: flex-start;
    box-shadow: var(--shadow-sm);
}
.agg-rec-icon { font-size:1.15rem; flex-shrink:0; margin-top:1px; }
.agg-rec-title { font-size:0.90rem; font-weight:700; color: var(--text-primary); margin-bottom:3px; }
.agg-rec-content { font-size:0.82rem; color: var(--text-secondary); line-height:1.6; }

/* ── toggle / radio 控件微调 ── */
div[data-testid="stToggle"] label { color: var(--text-primary) !important; }
div[data-testid="stRadio"] label { color: var(--text-primary) !important; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Session State
# ──────────────────────────────────────────────
_defaults = {
    "mode":          "workspace",
    "phase":         "input",
    "question":      "",
    "sources":       [],
    "reasoning_log": [],
    "digest":        "",
    "report":        "",
    "template":      "general",
    "chat_history":  [],
    "validation":    {},
    "local_docs":    [],   # [{name, content}]
    "task_mode":     "research",  # "research" 或 "aggregation"
    "agg_items":     [],          # aggregation 模式下提取的结构化数据
    # ── URL 智能提取模式 ──
    "ue_urls":       "",          # 用户输入的 URL 列表（原始字符串）
    "ue_intent":     "",          # 用户提取意图
    "ue_engine":     "",          # 引擎预设："deep" | "fast" | ""(手动路由)
    "ue_schema":     {},          # 主脑生成的字段 Schema
    "ue_items":      [],          # 打工 AI 提取的结构化条目
    "ue_dashboard":  "",          # 看板 AI 生成的 Dashboard JSON
    "ue_log":        [],          # 流水线推理日志
    "scrape_source_type": "全网综合",
    "scrape_time_range":  "不限",
    "scrape_report":      "",    # 按需生成的综合报告（不再自动触发）
    "route_mode":         "manual",
    "workspace_panel":    "chat",
    "workspace_messages": [],
    "workspace_chat_history": [],
    "workspace_context_report": "",
    "workspace_context_title": "",
    "workspace_research_mode": "材料探索",
    "workspace_extract_urls": "",
    "workspace_extract_intent": "",
    "workspace_agent_steps": 8,
    "workspace_agent_profile": DEFAULT_SKILL_PROFILE,
    "workspace_prompt": "",
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

os.makedirs("reports", exist_ok=True)
os.makedirs("scraped",  exist_ok=True)

RELEVANCE_LABEL = {"high": "高相关", "medium": "中相关", "low": "低相关"}
RELEVANCE_DOT   = {"high": "🟢", "medium": "🟡", "low": "⚪"}

def go_home():
    for k, v in _defaults.items():
        st.session_state[k] = v


WORKSPACE_CHAT_SYSTEM_PROMPT = (
    "你是 DeepResearch 工作台助手。你需要在持续会话里帮助用户完成普通问答、"
    "内容探索、网页提取和后续追问。回答要简洁、直接，并优先利用当前工作台上下文。"
)

WORKSPACE_SOURCE_HINTS = {
    "全网综合": "",
    "新闻资讯（时效优先）": " 请优先关注最近的新闻、公告、动态与媒体报道。",
    "技术文档（深度优先）": " 请优先查找官方文档、API reference、guide、SDK 文档。",
    "学术/论文": " 请优先关注论文、研究综述、学术机构资料。",
}

WORKSPACE_TIME_MAP = {
    "不限": "",
    "最近24小时": "d",
    "最近一周": "w",
    "最近一月": "m",
    "最近一年": "y",
}


def _workspace_append_message(
    role: str,
    kind: str,
    content: str,
    data: dict | None = None,
) -> None:
    st.session_state.workspace_messages.append(
        {
            "role": role,
            "kind": kind,
            "content": content,
            "data": data or {},
        }
    )


def _workspace_set_context(title: str, report: str) -> None:
    st.session_state.workspace_context_title = title or ""
    st.session_state.workspace_context_report = report or ""


def _workspace_reset_session() -> None:
    for key in (
        "workspace_messages",
        "workspace_chat_history",
        "workspace_context_report",
        "workspace_context_title",
        "workspace_prompt",
        "workspace_extract_urls",
        "workspace_extract_intent",
    ):
        st.session_state[key] = _defaults[key]


def _workspace_note_chat(role: str, content: str) -> None:
    text = str(content or "").strip()
    if not text:
        return
    st.session_state.workspace_chat_history.append({"role": role, "content": text})
    st.session_state.workspace_chat_history = st.session_state.workspace_chat_history[-12:]


def _workspace_chat_context(limit: int = 8) -> str:
    history = st.session_state.get("workspace_chat_history", [])[-limit:]
    lines: list[str] = []
    for item in history:
        role = "用户" if item.get("role") == "user" else "助手"
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _workspace_answer_chat(user_msg: str) -> str:
    engine = st.session_state.get("ue_engine", "")
    context_report = st.session_state.get("workspace_context_report", "")
    context_title = st.session_state.get("workspace_context_title", "当前工作台上下文")
    chat_history = st.session_state.get("workspace_chat_history", [])
    if context_report:
        return chat_with_report(context_title, context_report, chat_history, user_msg)

    history_ctx = _workspace_chat_context()
    prompt = f"""你正在 DeepResearch 的工作台中与用户持续对话。

最近对话：
{history_ctx or "（暂无）"}

用户最新消息：
{user_msg}

请基于当前上下文直接回答。如果问题需要进一步研究，也先明确告诉用户下一步建议。"""
    return ai_generate_role(
        prompt,
        system=WORKSPACE_CHAT_SYSTEM_PROMPT or SYSTEM_PROMPT,
        role="analyst",
        engine=engine,
    )


def _render_workspace_sources(sources: list[dict]) -> None:
    if not sources:
        return

    for idx, src in enumerate(sources, 1):
        title = src.get("title") or src.get("url") or f"来源 {idx}"
        url = src.get("url", "")
        snippet = (src.get("snippet") or "").strip()
        relevance = src.get("relevance", "")
        badge = RELEVANCE_LABEL.get(relevance, "")

        if url:
            st.markdown(f"{idx}. [{title}]({url})")
        else:
            st.markdown(f"{idx}. {title}")

        meta = []
        if badge:
            meta.append(badge)
        if snippet:
            meta.append(snippet[:180])
        if meta:
            st.caption(" · ".join(meta))


def _render_workspace_extract_items(items: list[dict]) -> None:
    if not items:
        st.caption("没有提取到结构化条目。")
        return

    import pandas as pd

    display_keys = [k for k in items[0].keys() if not str(k).startswith("_")]

    def _norm(value):
        if isinstance(value, list):
            return "、".join(str(x) for x in value if x)
        return value or ""

    df = pd.DataFrame([{k: _norm(item.get(k)) for k in display_keys} for item in items])
    column_config = {}
    if "url" in display_keys:
        column_config["url"] = st.column_config.LinkColumn("链接", display_text="打开")
    st.dataframe(df, use_container_width=True, height=320, column_config=column_config)


def _render_workspace_message(msg: dict, index: int) -> None:
    role = msg.get("role", "assistant")
    kind = msg.get("kind", "chat")
    content = msg.get("content", "")
    data = msg.get("data", {}) or {}
    avatar = "🧑" if role == "user" else "🤖"

    with st.chat_message(role, avatar=avatar):
        if role == "user":
            label_map = {
                "chat": "普通对话",
                "research": "内容探索",
                "extract": "网页提取",
                "agent": "Agent 探索",
            }
            st.caption(label_map.get(kind, "工作台消息"))
            st.markdown(content)
            return

        if kind == "chat":
            st.markdown(content)
            return

        if kind == "research":
            st.caption(f"内容探索结果 · {data.get('mode', '材料探索')}")
            if content:
                st.markdown(content)
            if data.get("reasoning_log"):
                with st.expander("过程记录", expanded=False):
                    for line in data.get("reasoning_log", []):
                        st.markdown(f"- {line}")
            if data.get("sources"):
                with st.expander(f"材料清单（{len(data.get('sources', []))}）", expanded=False):
                    _render_workspace_sources(data.get("sources", []))
            if data.get("task_mode") == "aggregation" and data.get("digest"):
                with st.expander("结构化看板", expanded=True):
                    render_agg_dashboard(data.get("digest", ""))
            return

        if kind == "extract":
            st.caption(
                f"网页提取结果 · {data.get('url_count', 0)} 个 URL · "
                f"{len(data.get('items', []) or [])} 条记录"
            )
            if content:
                st.markdown(content)
            dashboard = data.get("dashboard", "")
            if dashboard:
                render_agg_dashboard(dashboard)
            with st.expander("结构化数据", expanded=False):
                _render_workspace_extract_items(data.get("items", []))
            if data.get("log"):
                with st.expander("流水线记录", expanded=False):
                    for line in data.get("log", []):
                        st.markdown(f"- {line}")
            return

        if kind == "agent":
            result = data.get("result", {}) or {}
            is_planner = bool(data.get("is_planner"))
            st.caption("深度规划" if is_planner else "ReAct 自主")
            if content:
                st.markdown(content)
            if is_planner:
                plan = result.get("plan", {}) or {}
                if plan:
                    with st.expander("研究规划", expanded=False):
                        reasoning = plan.get("reasoning", "")
                        if reasoning:
                            st.caption(reasoning)
                        for idx, sq in enumerate(plan.get("sub_questions", []), 1):
                            st.markdown(f"{idx}. {sq}")
                sub_results = result.get("sub_results", []) or []
                if sub_results:
                    with st.expander(f"子问题结果（{len(sub_results)}）", expanded=False):
                        for idx, sub in enumerate(sub_results, 1):
                            st.markdown(f"**{idx}. {sub.get('sub_q', '')}**")
                            st.markdown(sub.get("answer", ""))
            else:
                _render_route_debug(result.get("route", {}), data.get("skill_profile", DEFAULT_SKILL_PROFILE))
                steps = result.get("steps", []) or []
                if steps:
                    with st.expander(f"推理步骤（{len(steps)}）", expanded=False):
                        for idx, step in enumerate(steps, 1):
                            label = _format_step_label(
                                step.get("tool", ""),
                                step.get("args", {}) or {},
                                idx,
                                "🪄",
                            )
                            with st.expander(label, expanded=False):
                                st.markdown(f"**Thought**\n\n{step.get('thought', '')}")
                                obs = step.get("observation", "")
                                if obs and obs != "(任务完成)":
                                    st.text(obs[:1500] + ("..." if len(obs) > 1500 else ""))
                                _render_observation_sources(
                                    step.get("sources", []),
                                    step.get("cite_ids", []),
                                )
            _render_reference_registry(result)
            return

        st.markdown(content or "（无内容）")


def _apply_single_model_routing(provider: str) -> None:
    if not provider:
        return
    st.session_state.workspace_single_model = provider
    _apply_manual_model_routing(provider, provider, provider)


def _current_workspace_model() -> str:
    provider_names = list(PROVIDERS.keys())
    current = st.session_state.get("workspace_single_model", "")
    if current in provider_names:
        return current
    fallback = _default_provider_for_role("orchestrator")
    if fallback in provider_names:
        st.session_state.workspace_single_model = fallback
        return fallback
    current = provider_names[0] if provider_names else ""
    if current:
        st.session_state.workspace_single_model = current
    return current


def _render_workspace_model_controls() -> None:
    provider_names = list(PROVIDERS.keys())
    current = _current_workspace_model()
    if current:
        _apply_single_model_routing(current)
    label = f"模型 · {_provider_display_name(current)}" if current else "选择模型"
    popover = getattr(st, "popover", None)
    if callable(popover):
        popover_ctx = popover(label, use_container_width=True)
    else:
        popover_ctx = st.expander(label, expanded=False)
    with popover_ctx:
        chosen = st.selectbox(
            "当前模型",
            options=provider_names,
            index=provider_names.index(current) if current in provider_names else 0,
            key="workspace_single_model_selector",
            format_func=_provider_display_name,
        )
        if chosen != current:
            _apply_single_model_routing(chosen)
            st.rerun()
        st.caption("Skills 会自动调用；这里只切换当前会话使用的模型。")


def _render_workspace_advanced_controls(panel: str) -> None:
    if panel == "research":
        research_mode = st.radio(
            "研究方式",
            ["材料探索", "ReAct 自主", "深度规划"],
            key="workspace_research_mode",
            horizontal=True,
        )

        if research_mode == "材料探索":
            st.selectbox(
                "来源类型",
                ["全网综合", "新闻资讯（时效优先）", "技术文档（深度优先）", "学术/论文"],
                key="scrape_source_type",
            )
            st.selectbox(
                "时间范围",
                ["不限", "最近24小时", "最近一周", "最近一月", "最近一年"],
                key="scrape_time_range",
            )
        elif research_mode == "ReAct 自主":
            st.selectbox(
                "Skill Profile",
                options=[DEFAULT_SKILL_PROFILE, "web_research_heavy"],
                index=0 if st.session_state.get("workspace_agent_profile", DEFAULT_SKILL_PROFILE) == DEFAULT_SKILL_PROFILE else 1,
                key="workspace_agent_profile",
                format_func=lambda p: {
                    "react_default": "react_default · 平衡模式",
                    "web_research_heavy": "web_research_heavy · 网页研究增强",
                }.get(p, p),
            )
            st.number_input(
                "最大步骤",
                min_value=3,
                max_value=15,
                value=int(st.session_state.get("workspace_agent_steps", 8)),
                step=1,
                key="workspace_agent_steps",
            )
        else:
            st.caption("深度规划会先拆分子问题，再分别研究后综合。")
    elif panel == "extract":
        st.caption("网页提取模式会根据你的 URL 和目标自动执行提取。")
    else:
        st.caption("对话模式默认最简。")


def render_agg_dashboard(digest: str) -> None:
    """将 aggregation 模式下 AI 生成的 JSON 报告渲染为可视化卡片面板。"""
    import json as _json
    import re as _re

    try:
        text = digest.strip()
        if "```" in text:
            text = _re.split(r"```(?:json)?", text)[1].strip().rstrip("`").strip()
        data = _json.loads(text)
    except Exception:
        # 解析失败退回纯文本
        st.markdown(
            f'<div class="digest-card"><div class="digest-body">'
            f'{digest.replace(chr(10), "<br>")}</div></div>',
            unsafe_allow_html=True,
        )
        return

    COLOR_MAP = {"green": "#10b981", "blue": "#3b82f6", "orange": "#f59e0b", "red": "#ef4444"}
    REC_COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#a78bfa", "#ef4444"]

    parts: list[str] = ['<div class="agg-dashboard">']

    # ── 标题 ──
    title = data.get("title", "数据汇总")
    parts.append(f'<div class="agg-title">{title}</div>')

    # ── 统计指标卡片 ──
    stats = data.get("stats") or []
    if stats:
        parts.append('<div class="agg-stats">')
        for s in stats:
            change = s.get("change") or ""
            is_pos = s.get("is_positive")
            chg_cls = "pos" if is_pos is True else ("neg" if is_pos is False else "")
            chg_html = f'<div class="agg-stat-change {chg_cls}">{change}</div>' if change else ""
            parts.append(
                f'<div class="agg-stat-card">'
                f'<div class="agg-stat-value">{s.get("value","")}</div>'
                f'<div class="agg-stat-label">{s.get("label","")}</div>'
                f'{chg_html}</div>'
            )
        parts.append('</div>')

    # ── 高亮发现 ──
    highlights = data.get("highlights") or []
    if highlights:
        parts.append('<div class="agg-highlights">')
        for h in highlights:
            color = COLOR_MAP.get(h.get("color", "blue"), "#3b82f6")
            tag = h.get("tag") or ""
            tag_html = f'<span class="agg-hl-tag">{tag}</span>' if tag else ""
            parts.append(
                f'<div class="agg-hl-row" style="border-left-color:{color}">'
                f'<span class="agg-hl-icon">{h.get("icon","")}</span>'
                f'<span class="agg-hl-content">{h.get("content","")}</span>'
                f'{tag_html}</div>'
            )
        parts.append('</div>')

    # ── 亮点条目 ──
    top_items = data.get("top_items") or []
    if top_items:
        parts.append('<div class="agg-section-title">今日亮点条目</div>')
        parts.append('<div class="agg-items-list">')
        for item in top_items:
            tags_html = "".join(
                f'<span class="agg-tag">{t}</span>'
                for t in (item.get("tags") or [])
            )
            new_badge = '<span class="agg-new-badge">今日新增</span>' if item.get("is_new") else ""
            val = item.get("value") or ""
            val_html = f'<div class="agg-item-value">{val}</div>' if val else ""
            item_url = item.get("url") or ""
            title_text = item.get("title", "")
            if item_url:
                title_inner = (
                    f'<a href="{item_url}" target="_blank" rel="noopener noreferrer" '
                    f'style="color:inherit;text-decoration:none;border-bottom:1px solid rgba(255,255,255,0.3);">'
                    f'{title_text}</a>'
                )
            else:
                title_inner = title_text
            parts.append(
                f'<div class="agg-item-card">'
                f'<div class="agg-item-left">'
                f'<div class="agg-item-title">{title_inner}{new_badge}</div>'
                f'<div class="agg-item-sub">{item.get("subtitle","")}</div>'
                f'<div class="agg-item-tags">{tags_html}</div>'
                f'</div>{val_html}</div>'
            )
        parts.append('</div>')

    # ── 数据分析 ──
    analysis  = data.get("analysis") or {}
    metrics   = analysis.get("metrics") or []
    dists     = analysis.get("distributions") or []
    dirs      = analysis.get("directions") or []

    if metrics or dists or dirs:
        parts.append('<div class="agg-section-title">数据分析</div>')
        parts.append('<div class="agg-analysis">')

        if metrics:
            parts.append('<div class="agg-metrics">')
            for m in metrics:
                parts.append(
                    f'<div class="agg-metric-card">'
                    f'<div class="agg-metric-value">{m.get("value","")}</div>'
                    f'<div class="agg-metric-label">{m.get("label","")}</div>'
                    f'<div class="agg-metric-sub">{m.get("sub","")}</div>'
                    f'</div>'
                )
            parts.append('</div>')

        for dist in dists:
            parts.append(f'<div class="agg-dist-title">{dist.get("group","")}</div>')
            parts.append('<div class="agg-dist-bars">')
            for it in (dist.get("items") or []):
                pct = it.get("pct", 0)
                parts.append(
                    f'<div class="agg-dist-row">'
                    f'<span class="agg-dist-label">{it.get("label","")}</span>'
                    f'<div class="agg-dist-bar-wrap">'
                    f'<div class="agg-dist-bar-fill" style="width:{pct}%"></div></div>'
                    f'<span class="agg-dist-pct">{it.get("count","")} · {pct}%</span>'
                    f'</div>'
                )
            parts.append('</div>')

        if dirs:
            parts.append('<div class="agg-directions">')
            for d in dirs:
                trend = str(d.get("trend") or "")
                tcls = "trend-up" if "+" in trend else ("trend-down" if "-" in trend else "trend-flat")
                parts.append(
                    f'<div class="agg-dir-chip">'
                    f'<div class="agg-dir-name">{d.get("name","")}</div>'
                    f'<div class="agg-dir-count">{d.get("count","")}</div>'
                    f'<div class="agg-dir-trend {tcls}">{trend}</div>'
                    f'</div>'
                )
            parts.append('</div>')

        parts.append('</div>')  # agg-analysis

    # ── 行动建议 ──
    recs = data.get("recommendations") or []
    if recs:
        parts.append('<div class="agg-section-title">行动建议</div>')
        parts.append('<div class="agg-recs">')
        for i, rec in enumerate(recs):
            color = REC_COLORS[i % len(REC_COLORS)]
            parts.append(
                f'<div class="agg-rec-card" style="border-left-color:{color}">'
                f'<div class="agg-rec-icon">{rec.get("icon","")}</div>'
                f'<div><div class="agg-rec-title">{rec.get("title","")}</div>'
                f'<div class="agg-rec-content">{rec.get("content","")}</div></div>'
                f'</div>'
            )
        parts.append('</div>')

    parts.append('</div>')  # agg-dashboard
    st.markdown("".join(parts), unsafe_allow_html=True)


def _format_cite_ids(cite_ids: list[int] | None) -> str:
    return "".join(f"[{i}]" for i in (cite_ids or []))


def _render_observation_sources(
    sources: list[dict] | None,
    cite_ids: list[int] | None = None,
) -> None:
    cite_text = _format_cite_ids(cite_ids)
    if cite_text:
        st.markdown(f"**引用编号**：{cite_text}")

    sources = sources or []
    if not sources:
        return

    st.markdown("**来源**")
    for idx, src in enumerate(sources, 1):
        cite_prefix = ""
        if cite_ids and idx <= len(cite_ids):
            cite_prefix = f"[{cite_ids[idx - 1]}] "

        title = src.get("title") or src.get("url") or "未命名来源"
        url = src.get("url", "")
        snippet = (src.get("snippet") or "").strip()

        if url:
            st.markdown(f"- {cite_prefix}[{title}]({url})")
        else:
            st.markdown(f"- {cite_prefix}{title}")

        if snippet:
            st.caption(snippet[:180])


def _render_reference_registry(result: dict) -> None:
    registry = result.get("registry")
    refs_md = ""
    ref_count = 0

    if registry and hasattr(registry, "as_refs_md"):
        refs_md = registry.as_refs_md()
        if hasattr(registry, "__len__"):
            ref_count = len(registry)

    if not refs_md:
        refs: list[str] = []
        seen: set[str] = set()
        for obs in result.get("observations", []) or []:
            sources = obs.get("sources", []) or []
            cite_ids = obs.get("cite_ids", []) or []
            for idx, src in enumerate(sources):
                cite_id = cite_ids[idx] if idx < len(cite_ids) else None
                url = src.get("url", "")
                key = f"{cite_id}:{url}" if cite_id else url
                if not key or key in seen:
                    continue
                seen.add(key)

                title = src.get("title") or url or "未命名来源"
                if cite_id and url:
                    refs.append(f"{cite_id}. [{title}]({url})")
                elif cite_id:
                    refs.append(f"{cite_id}. {title}")
                elif url:
                    refs.append(f"- [{title}]({url})")
                else:
                    refs.append(f"- {title}")

        ref_count = len(refs)
        if refs:
            refs_md = "## 参考来源\n\n" + "\n".join(refs)

    if refs_md:
        with st.expander(f"📚 参考来源（{ref_count} 个）", expanded=False):
            st.markdown(refs_md)


def _truncate_text(value: str, limit: int = 48) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_step_label(tool: str, args: dict, index: int, icon: str) -> str:
    if tool == "finish":
        return f"{icon} 步骤 {index}：finish（生成最终答案）"

    if not isinstance(args, dict) or not args:
        return f"{icon} 步骤 {index}：{tool}"

    if "query" in args:
        return f"{icon} 步骤 {index}：{tool} · {_truncate_text(args['query'])}"
    if "url" in args:
        return f"{icon} 步骤 {index}：{tool} · {_truncate_text(args['url'])}"
    if "urls" in args:
        raw_urls = args["urls"]
        if isinstance(raw_urls, list):
            count = len(raw_urls)
        else:
            count = len([u for u in str(raw_urls).splitlines() if u.strip()])
        return f"{icon} 步骤 {index}：{tool} · {count} 个 URL"
    if "instruction" in args:
        return f"{icon} 步骤 {index}：{tool} · {_truncate_text(args['instruction'])}"
    if "text" in args:
        return f"{icon} 步骤 {index}：{tool} · {_truncate_text(args['text'])}"

    return f"{icon} 步骤 {index}：{tool}"


def _render_route_debug(route: dict, skill_profile: str) -> None:
    if not isinstance(route, dict) or not route:
        return

    with st.expander("🧭 Route Debug", expanded=False):
        st.caption(
            f"Profile：`{skill_profile}` | "
            f"Question Type：`{route.get('question_type', '')}` | "
            f"Starter：`{route.get('starter', '')}`"
        )

        preferred = route.get("preferred_skills", []) or []
        discouraged = route.get("discouraged_skills", []) or []
        allowed = route.get("allowed_skills", []) or []
        reasons = route.get("reasons", []) or []
        signals = route.get("signals", []) or []

        if signals:
            st.markdown(f"**Signals**: `{signals}`")
        if preferred:
            st.markdown(f"**Preferred**: `{preferred}`")
        if discouraged:
            st.markdown(f"**Discouraged**: `{discouraged}`")
        if allowed:
            st.markdown(f"**Allowed**: `{allowed}`")
        if reasons:
            st.markdown("**Reasons**")
            for reason in reasons:
                st.markdown(f"- {reason}")


def _provider_display_name(name: str) -> str:
    cfg = PROVIDERS.get(name, {})
    model = cfg.get("model", "")
    key_ready = bool(load_secret(cfg.get("env", ""))) if cfg.get("env") else False
    status = "已配 Key" if key_ready else "未配 Key"
    model_part = f" · {model}" if model else ""
    return f"{name}{model_part} · {status}"


def _default_provider_for_role(role: str) -> str:
    current = get_runtime_role_order(role)
    if current:
        return current.split(",")[0].strip()
    order = ROLE_ORDER.get(role, "")
    if order:
        return order.split(",")[0].strip()
    return next(iter(PROVIDERS.keys()), "")


def _apply_manual_model_routing(
    orchestrator: str,
    worker: str,
    analyst: str,
) -> None:
    st.session_state.ue_engine = ""
    st.session_state.route_mode = "manual"
    set_runtime_role_order("orchestrator", [orchestrator])
    set_runtime_role_order("worker", [worker])
    set_runtime_role_order("analyst", [analyst])


def _apply_preset_model_routing(engine_name: str) -> None:
    st.session_state.ue_engine = engine_name
    st.session_state.route_mode = engine_name
    clear_runtime_role_orders()


def _current_model_route_summary() -> tuple[str, str]:
    engine = st.session_state.get("ue_engine", "")
    if engine in ENGINE_PRESETS:
        preset = ENGINE_PRESETS.get(engine, {})
        return preset.get("label", engine), preset.get("desc", "")

    roles = {
        "主脑": _default_provider_for_role("orchestrator"),
        "打工": _default_provider_for_role("worker"),
        "总结": _default_provider_for_role("analyst"),
    }
    detail = " / ".join(f"{label}:{name}" for label, name in roles.items())
    return "手动模型路由", detail


def _render_skill_catalog_sidebar() -> None:
    category_labels = {
        "search": "搜索",
        "scrape": "抓取",
        "extract": "抽取",
        "rag": "本地 RAG",
        "utility": "整理",
    }
    enabled_map = get_skill_state_map(BUILTIN_SKILL_REGISTRY.names())
    grouped = BUILTIN_SKILL_REGISTRY.as_grouped_metadata(enabled_map=enabled_map)
    enabled_names = [name for name, enabled in enabled_map.items() if enabled]
    profiles = get_profile_metadata_list(enabled_names)
    total = sum(len(items) for items in grouped.values())
    enabled_total = sum(1 for items in grouped.values() for item in items if item["enabled"])

    with st.expander(f"🧰 Skills（{enabled_total}/{total} 启用）", expanded=False):
        st.caption("这里展示 ReAct 可调用的内置技能，不包含 `finish` 这类系统控制动作。")
        if profiles:
            st.markdown("**Profiles**")
            for profile in profiles:
                st.caption(
                    f"`{profile['name']}` · {profile['allowed_count']} 个 skill · {profile['description']}"
                )
        for category, items in grouped.items():
            enabled_count = sum(1 for item in items if item["enabled"])
            st.markdown(
                f"**{category_labels.get(category, category.title())}（{enabled_count}/{len(items)}）**"
            )
            for item in items:
                status = "✅" if item["enabled"] else "⏸️"
                st.markdown(f"- {status} `{item['name']}`: {item['description']}")
                required = ", ".join(item["required_args"]) if item["required_args"] else "无"
                optional = ", ".join(item["optional_args"]) if item["optional_args"] else "无"
                source_flag = "是" if item["returns_sources"] else "否"
                st.caption(
                    f"状态：{'启用' if item['enabled'] else '禁用'} ｜ 必填：{required} ｜ 可选：{optional} ｜ 返回来源：{source_flag}"
                )


# ──────────────────────────────────────────────
# 侧边栏
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### DeepResearch")
    st.caption("侧边栏放特殊功能；主区保持持续对话。")
    if st.session_state.mode == "workspace":
        side_action_cols = st.columns(2)
        with side_action_cols[0]:
            if st.button("新建会话", use_container_width=True, key="sidebar_workspace_reset"):
                _workspace_reset_session()
                st.rerun()
        with side_action_cols[1]:
            if st.button("返回主页", use_container_width=True, key="sidebar_workspace_home"):
                st.session_state.mode = "home"
                st.rerun()

        panel_labels = {
            "chat": "对话",
            "research": "课题研究",
            "extract": "网页提取",
        }
        panel_options = list(panel_labels.keys())
        if st.session_state.get("workspace_panel") not in panel_options:
            st.session_state.workspace_panel = panel_options[0]

        st.divider()
        st.markdown("**功能模式**")
        st.radio(
            "工作模式",
            panel_options,
            key="workspace_panel",
            format_func=panel_labels.get,
            label_visibility="collapsed",
        )
        with st.expander("特殊功能", expanded=st.session_state.get("workspace_panel") != "chat"):
            _render_workspace_advanced_controls(st.session_state.get("workspace_panel", "chat"))

        if st.session_state.get("workspace_context_report"):
            with st.expander("当前上下文", expanded=False):
                st.caption(st.session_state.get("workspace_context_title", ""))
                if st.button("保存当前报告", use_container_width=True, key="sidebar_workspace_save_context"):
                    fp = save_report(
                        st.session_state.get("workspace_context_title", "工作台记录"),
                        st.session_state.get("workspace_context_report", ""),
                    )
                    st.success(f"已保存：{fp}")

    st.divider()

    with st.expander("API Key 配置", expanded=False):
        st.caption("建议直接填你自己的 Key，填入后立即生效，不写入磁盘，刷新页面后失效。")

        _key_fields = [
            ("GOOGLE_API_KEY", "Google / Gemini"),
            ("ANTHROPIC_API_KEY", "Anthropic / Claude"),
            ("GLM_API_KEY", "GLM"),
            ("MINIMAX_API_KEY", "MiniMax"),
            ("SILICONFLOW_API_KEY", "SiliconFlow"),
        ]
        for env_k, label in _key_fields:
            val = st.text_input(
                label,
                type="password",
                placeholder="sk-...",
                key=f"apikey_{env_k}",
            )
            if val and val.strip():
                set_runtime_key(env_k, val.strip())

    st.divider()
    _render_skill_catalog_sidebar()

    st.divider()
    st.markdown("**上传本地文档**")
    st.caption("研究时 AI 会将本地资料与网络信息交叉使用。")
    uploaded = st.file_uploader(
        "支持 PDF / DOCX / TXT / CSV / MD",
        type=["pdf", "docx", "txt", "csv", "md"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded:
        new_docs = []
        for f in uploaded:
            already = any(d["name"] == f.name for d in st.session_state.local_docs)
            if not already:
                content = parse_uploaded_file(f.read(), f.name)
                new_docs.append({"name": f.name, "content": content})
        if new_docs:
            st.session_state.local_docs.extend(new_docs)
            try:
                import rag as _rag
                n = _rag.build_vector_store(st.session_state.local_docs)
                st.success(f"已加载 {len(new_docs)} 个文档，向量化 {n} 个文本块")
            except Exception as _e:
                st.success(f"已加载 {len(new_docs)} 个文档（RAG 未启用：{_e}）")
    if st.session_state.local_docs:
        for doc in st.session_state.local_docs:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f'<div class="file-item">DOC {doc["name"]}</div>', unsafe_allow_html=True)
            with c2:
                if st.button("x", key=f"rm_{doc['name']}"):
                    st.session_state.local_docs = [d for d in st.session_state.local_docs if d["name"] != doc["name"]]
                    try:
                        import rag as _rag
                        _rag.build_vector_store(st.session_state.local_docs)
                    except Exception:
                        pass
                    st.rerun()

    st.divider()
    st.markdown("**已保存文件**")
    reports = sorted([f for f in os.listdir("reports") if f.endswith(".md")], reverse=True)[:4]
    scraped_files = sorted([f for f in os.listdir("scraped") if f.endswith(".md")], reverse=True)[:4]
    for f in reports:
        st.markdown(f'<div class="file-item">DOC {f}</div>', unsafe_allow_html=True)
    for f in scraped_files:
        st.markdown(f'<div class="file-item">WEB {f}</div>', unsafe_allow_html=True)
    if not reports and not scraped_files:
        st.markdown('<div class="file-item">暂无文件</div>', unsafe_allow_html=True)


if st.session_state.mode == "workspace":
    st.markdown("""
<div class="topbar-wrap">
  <div class="topbar-brand"><div class="dot"></div>DeepResearch</div>
  <div class="topbar-crumb-new">
    Workspace<span class="sep">/</span> <span class="cur">Chat</span>
  </div>
  <div></div>
</div>
""", unsafe_allow_html=True)

    workspace_panel = st.session_state.get("workspace_panel", "chat")
    panel_labels = {
        "chat": "对话",
        "research": "课题研究",
        "extract": "网页提取",
    }
    extract_clicked = False
    composer_value = ""
    panel_hint = {
        "chat": "当前是对话模式。直接提问即可，Skills 会在需要时自动调用。",
        "research": "当前是课题研究模式。研究方式和来源范围放在侧边栏的“特殊功能”里。",
        "extract": "当前是网页提取模式。贴入 URL 和提取目标后即可开始。",
    }.get(workspace_panel, "")

    if panel_hint:
        st.caption(panel_hint)
    if st.session_state.local_docs:
        st.caption(f"已加载 {len(st.session_state.local_docs)} 个本地文档，研究时会与网络资料交叉使用。")

    if not st.session_state.workspace_messages:
        empty_hint = {
            "chat": "像普通大模型对话一样直接输入问题即可。",
            "research": "输入研究主题后开始研究；更深入的设置在侧边栏。",
            "extract": "先填好 URL 和提取目标，再开始提取。",
        }.get(workspace_panel, "从下方输入框开始。")
        st.info(empty_hint)
    else:
        for idx, msg in enumerate(st.session_state.workspace_messages):
            _render_workspace_message(msg, idx)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    with st.container():
        if workspace_panel == "extract":
            url_col, intent_col = st.columns([1.2, 1.0], gap="large")
            with url_col:
                st.text_area(
                    "目标 URL",
                    key="workspace_extract_urls",
                    height=150,
                    placeholder="https://example.com/page1\nhttps://example.com/page2",
                )
            with intent_col:
                st.text_area(
                    "提取目标",
                    key="workspace_extract_intent",
                    height=150,
                    placeholder="例如：提取课程名称、价格、讲师、适合人群",
                )
        else:
            prompt_placeholder = (
                "直接输入你的问题，或继续追问当前上下文..."
                if workspace_panel == "chat"
                else "输入你要研究的主题，例如：比较 OpenAI 和 Anthropic 的 API 策略"
            )
            st.text_area(
                "输入框",
                key="workspace_prompt",
                height=120,
                placeholder=prompt_placeholder,
                label_visibility="collapsed",
            )
            composer_value = st.session_state.get("workspace_prompt", "").strip()

        composer_actions = st.columns([1.1, 0.9], gap="small")
        with composer_actions[0]:
            _render_workspace_model_controls()
        with composer_actions[1]:
            action_label = {
                "chat": "发送",
                "research": "开始研究",
                "extract": "开始提取",
            }.get(workspace_panel, "执行")
            extract_clicked = st.button(
                action_label,
                use_container_width=True,
                type="primary",
            )

    if extract_clicked:
        panel = st.session_state.get("workspace_panel", "chat")
        engine = st.session_state.get("ue_engine", "")
        if panel == "extract":
            urls = [
                u.strip()
                for u in st.session_state.get("workspace_extract_urls", "").splitlines()
                if u.strip().startswith("http")
            ]
            intent = st.session_state.get("workspace_extract_intent", "").strip()
            if not urls or not intent:
                st.warning("网页提取需要同时提供 URL 列表和提取目标。")
            else:
                user_text = f"请从 {len(urls)} 个网页中提取：{intent}"
                _workspace_append_message("user", "extract", user_text, {"urls": urls})
                _workspace_note_chat("user", user_text)
                with st.spinner("正在执行网页提取..."):
                    schema, items, dashboard_json, log = run_url_pipeline(
                        urls,
                        intent,
                        engine=engine,
                    )
                summary = (
                    f"已完成网页提取，共处理 {len(urls)} 个 URL，"
                    f"提取出 {len(items)} 条结构化记录。"
                )
                _workspace_append_message(
                    "assistant",
                    "extract",
                    summary,
                    {
                        "schema": schema,
                        "items": items,
                        "dashboard": dashboard_json,
                        "log": log,
                        "url_count": len(urls),
                        "intent": intent,
                    },
                )
                _workspace_note_chat("assistant", summary)
                _workspace_set_context(f"网页提取：{intent}", dashboard_json or summary)
                st.rerun()
        elif not composer_value:
            st.warning("请先输入内容。")
        elif panel == "chat":
            _workspace_append_message("user", "chat", composer_value)
            _workspace_note_chat("user", composer_value)
            with st.spinner("正在回答..."):
                answer = _workspace_answer_chat(composer_value)
            _workspace_append_message("assistant", "chat", answer)
            _workspace_note_chat("assistant", answer)
            st.session_state.workspace_prompt = ""
            st.rerun()
        elif panel == "research":
            research_mode = st.session_state.get("workspace_research_mode", "????")
            if research_mode == "????":
                source_type = st.session_state.get("scrape_source_type", "????")
                time_range = st.session_state.get("scrape_time_range", "??")
                hint = WORKSPACE_SOURCE_HINTS.get(source_type, "")
                timelimit = WORKSPACE_TIME_MAP.get(time_range, "")
                task_question = composer_value.strip() + hint
                _workspace_append_message("user", "research", composer_value, {"mode": research_mode})
                _workspace_note_chat("user", composer_value)
                with st.spinner("正在搜索和整理材料..."):
                    sources, digest, reasoning_log, task_mode = run_research(
                        task_question,
                        timelimit=timelimit,
                    )
                summary = digest or compile_digest(sources, composer_value.strip())
                summary = summary or f"已完成内容探索，共收集 {len(sources)} 条来源。"
                _workspace_append_message(
                    "assistant",
                    "research",
                    summary,
                    {
                        "mode": research_mode,
                        "question": composer_value.strip(),
                        "sources": sources,
                        "digest": summary,
                        "reasoning_log": reasoning_log,
                        "task_mode": task_mode,
                    },
                )
                _workspace_note_chat("assistant", summary)
                _workspace_set_context(f"内容探索：{composer_value.strip()}", summary)
                st.session_state.workspace_prompt = ""
                st.rerun()

            _workspace_append_message("user", "agent", composer_value, {"mode": research_mode})
            _workspace_note_chat("user", composer_value)
            if research_mode == "????":
                from agent_planner import run_planner_agent

                with st.spinner("正在执行深度规划..."):
                    result = run_planner_agent(
                        question=composer_value.strip(),
                        engine=engine,
                    )
                answer = result.get("answer", "") or "已完成深度规划，但未返回总结。"
                _workspace_append_message(
                    "assistant",
                    "agent",
                    answer,
                    {
                        "result": result,
                        "is_planner": True,
                        "skill_profile": "planner",
                    },
                )
                _workspace_note_chat("assistant", answer)
                _workspace_set_context(f"深度规划：{composer_value.strip()}", answer)
                st.session_state.workspace_prompt = ""
                st.rerun()

            from agent_loop import run_agent

            selected_profile = st.session_state.get("workspace_agent_profile", DEFAULT_SKILL_PROFILE)
            max_steps = int(st.session_state.get("workspace_agent_steps", 8))
            with st.spinner("正在执行 ReAct 自主探索..."):
                result = run_agent(
                    question=composer_value.strip(),
                    engine=engine,
                    max_steps=max_steps,
                    skill_profile=selected_profile,
                )
            answer = result.get("answer", "") or "已完成自主探索，但未返回总结。"
            _workspace_append_message(
                "assistant",
                "agent",
                answer,
                {
                    "result": result,
                    "is_planner": False,
                    "skill_profile": selected_profile,
                },
            )
            _workspace_note_chat("assistant", answer)
            _workspace_set_context(f"自主探索：{composer_value.strip()}", answer)
            st.session_state.workspace_prompt = ""
            st.rerun()

elif st.session_state.mode == "home":

    st.markdown("""
<div class="hero-wrap">
  <div class="hero-badge">✦ AI-Powered Research</div>
  <div class="hero-title">深度研究，<span class="accent">交给 AI</span></div>
  <div class="hero-sub">自动搜索全网资料，智能提炼关键信息，生成专业研究报告——只需输入一个问题。</div>
  
                
                
""", unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
<div class="mode-card">
  <div class="mode-card-glow"></div>
  <div class="mode-icon-wrap">📚</div>
  <div class="mode-title">课题探索</div>
  <div class="mode-desc">给一个研究主题，AI 多角度搜索并抓取原始网页，先呈现带引用的材料清单；再按需生成完整研究报告或看板，可选 Agent 自主决策。</div>
  <div class="mode-steps">
    <span class="mode-step">① 输入主题</span>
    <span class="mode-step">② 查看原料</span>
    <span class="mode-step">③ 按需成稿</span>
    <span class="mode-step">④ 可启 Agent</span>
  </div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("开始探索 →", use_container_width=True, type="primary", key="b_scrape"):
            st.session_state.mode  = "scrape"
            st.session_state.phase = "input"
            st.session_state.scrape_report = ""
            st.rerun()

    with col2:
        st.markdown("""
<div class="mode-card">
  <div class="mode-card-glow"></div>
  <div class="mode-icon-wrap">🧩</div>
  <div class="mode-title">网页提取</div>
  <div class="mode-desc">已经有一批 URL，描述你想抽的字段，主脑 AI 制定规则，打工 AI 并发抽取结构化数据并自动生成看板。</div>
  <div class="mode-steps">
    <span class="mode-step">① 贴入 URL</span>
    <span class="mode-step">② 描述意图</span>
    <span class="mode-step">③ 并发提取</span>
    <span class="mode-step">④ 看板呈现</span>
  </div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("开始提取 →", use_container_width=True, type="primary", key="b_ue"):
            st.session_state.mode  = "url_extract"
            st.session_state.phase = "input"
            st.rerun()

    # 底部特性栏
    st.markdown("<br><br>", unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    feats = [
        ("🌐", "多源搜索", "自动从多个网站抓取最新内容"),
        ("🧠", "AI 提炼", "智能筛选并提取关键信息"),
        ("📊", "相关度评分", "自动标注内容与主题的相关性"),
        ("💾", "本地存档", "研究报告可保存为 Markdown 文件"),
    ]
    for col, (icon, title, desc) in zip([f1, f2, f3, f4], feats):
        with col:
            st.markdown(f"""
<div style="text-align:center;padding:20px 12px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:14px;">
  <div style="font-size:1.6rem;margin-bottom:10px">{icon}</div>
  <div style="font-size:0.88rem;font-weight:700;color:#e2e8f0;margin-bottom:6px">{title}</div>
  <div style="font-size:0.78rem;color:#475569;line-height:1.55">{desc}</div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════
# 模式一：搜索爬取
# ══════════════════════════════════════════════
elif st.session_state.mode == "scrape":

    # ── 顶部导航栏 ──
    st.markdown("""
<div class="topbar-wrap">
  <div class="topbar-brand"><div class="dot"></div>DeepResearch</div>
  <div class="topbar-crumb-new">
    首页 <span class="sep">›</span> <span class="cur">🔍 搜索 &amp; 爬取</span>
  </div>
  <div></div>
</div>
""", unsafe_allow_html=True)
    if st.button("← 返回首页", key="back_scrape"):
        go_home(); st.rerun()

    # ── 输入 ──
    if st.session_state.phase == "input":
        st.markdown("""
<div class="page-hero">
  <div class="page-hero-title">📚 <span class="accent">课题</span>探索</div>
  <div class="page-hero-sub">输入研究主题，AI 多角度爬取后呈现材料清单；如需更主动的调研，可开启 Agent 自主决策。</div>
</div>
""", unsafe_allow_html=True)

        if st.session_state.local_docs:
            st.info(f"📂 已加载 {len(st.session_state.local_docs)} 个本地文档，研究时将与网络资料交叉融合")

        # ── Agent 自主决策 开关（form 外，用以动态展开子模式） ──
        agent_mode_on = st.toggle(
            "🤖 启用 Agent 自主决策",
            value=st.session_state.get("scrape_use_agent", False),
            key="scrape_use_agent",
            help=(
                "关闭：标准流程，AI 并行爬取后先给材料清单，你决定是否继续生成报告。\n"
                "开启：Agent 接管，自主规划工具调用，全程可见思考链。"
            ),
        )

        agent_sub_is_planner = False
        agent_profile = DEFAULT_SKILL_PROFILE
        if agent_mode_on:
            agent_sub = st.radio(
                "Agent 运行模式",
                ["⚡ 快速自主", "🗺️ 深度规划"],
                horizontal=True,
                key="scrape_agent_sub",
                help=(
                    "⚡ 快速自主：单一 ReAct 循环，适合明确的单一问题。\n"
                    "🗺️ 深度规划：先拆成 3-5 个子问题逐一调研后综合，适合复杂多维问题。"
                ),
            )
            agent_sub_is_planner = agent_sub.startswith("🗺️")
            if agent_sub_is_planner:
                agent_profile = "planner"
                st.caption("Skill Profile：`planner`（固定，限制深度/批量爬取，控制子问题收敛）")
            else:
                agent_profile = st.selectbox(
                    "Skill Profile",
                    options=[DEFAULT_SKILL_PROFILE, "web_research_heavy"],
                    index=0,
                    key="scrape_agent_profile",
                    format_func=lambda p: {
                        "react_default":       "react_default · 平衡模式",
                        "web_research_heavy":  "web_research_heavy · 网页研究增强",
                    }.get(p, p),
                    help="平衡模式更克制；网页研究增强会开放 batch / deep crawl。",
                )

        with st.form("scrape_form"):
            topic = st.text_input(
                "研究主题（必填）",
                placeholder="例如：特斯拉 2025 年新车规划",
                label_visibility="visible",
            )
            col_a, col_b = st.columns(2)
            with col_a:
                source_type = st.selectbox(
                    "来源类型",
                    ["全网综合", "新闻资讯（时效优先）", "技术文档（深度优先)", "学术/论文"],
                    disabled=agent_mode_on,
                    help="Agent 模式下该筛选失效，由 Agent 自主决策。" if agent_mode_on else None,
                )
            with col_b:
                time_range = st.selectbox(
                    "时间范围",
                    ["不限", "最近24小时", "最近一周", "最近一月", "最近一年"],
                    disabled=agent_mode_on,
                    help="Agent 模式下该筛选失效。" if agent_mode_on else None,
                )
            if agent_mode_on:
                agent_max_steps = st.number_input(
                    "Agent 最大步数",
                    min_value=3, max_value=15, value=8, step=1,
                    disabled=agent_sub_is_planner,
                    help="深度规划固定子步数，数字无效。" if agent_sub_is_planner else None,
                )
            else:
                agent_max_steps = 8

            submit_label = "🤖 启动 Agent" if agent_mode_on else "🔍 开始探索"
            submitted = st.form_submit_button(submit_label, use_container_width=True, type="primary")
            if submitted:
                if not topic.strip():
                    st.error("❌ 请输入研究主题")
                elif agent_mode_on:
                    st.session_state.agent_question_submitted = topic.strip()
                    st.session_state.agent_max_steps          = int(agent_max_steps)
                    st.session_state.agent_is_planner         = agent_sub_is_planner
                    st.session_state.agent_skill_profile      = agent_profile
                    st.session_state.mode                     = "agent"
                    st.session_state.phase                    = "running"
                    st.rerun()
                else:
                    _HINT = {
                        "新闻资讯（时效优先）": "（请侧重搜索最新新闻资讯）",
                        "技术文档（深度优先）": "（请侧重技术文档和深度分析）",
                        "学术/论文":           "（请侧重学术论文和研究报告）",
                    }
                    st.session_state.question           = topic.strip() + _HINT.get(source_type, "")
                    st.session_state.scrape_source_type = source_type
                    st.session_state.scrape_time_range  = time_range
                    st.session_state.scrape_report      = ""
                    st.session_state.phase              = "searching"
                    st.rerun()

    # ── 搜索中 ──
    elif st.session_state.phase == "searching":
        question = st.session_state.question
        st.markdown(f"""
<div style="margin-bottom:16px">
  <div style="font-size:1.3rem;font-weight:700;color:#f1f5f9;margin-bottom:6px">🔍 正在研究：{question}</div>
  <div style="font-size:0.83rem;color:#475569">AI 并行爬取中，请稍候...</div>
</div>
""", unsafe_allow_html=True)

        prog_bar    = st.progress(0)
        status_box  = st.empty()
        _res_log: list[str] = []

        def on_progress(step, total, msg):
            pct = int(step / total * 100)
            prog_bar.progress(pct)
            _res_log.append(msg)
            lines_html = "".join(
                f'<div style="color:{"#a5b4fc" if i == len(_res_log)-1 else "#475569"};'
                f'font-size:0.80rem;padding:2px 0">'
                f'{"⏳" if i == len(_res_log)-1 else "✅"} {l}</div>'
                for i, l in enumerate(_res_log[-6:])
            )
            status_box.markdown(
                f'<div style="background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.15);'
                f'border-radius:10px;padding:12px 16px;margin:6px 0">'
                f'<div style="font-size:0.72rem;font-weight:700;color:#334155;margin-bottom:6px">'
                f'进度 {pct}%</div>{lines_html}</div>',
                unsafe_allow_html=True,
            )

        _TIME_MAP = {"最近24小时": "d", "最近一周": "w", "最近一月": "m", "最近一年": "y"}
        _timelimit = _TIME_MAP.get(st.session_state.get("scrape_time_range", ""), "")
        sources, digest, log, task_mode = run_research(
            question, progress_callback=on_progress, timelimit=_timelimit
        )
        prog_bar.progress(100)
        status_box.empty()

        st.session_state.task_mode     = task_mode
        st.session_state.sources       = sources
        st.session_state.reasoning_log = log
        st.session_state.digest        = digest
        if task_mode == "aggregation":
            st.session_state.agg_items = sources  # sources 里存的是结构化 items
        st.session_state.phase         = "sources_ready"
        st.rerun()

    # ── 展示结果：aggregation 模式 ──
    elif st.session_state.phase in ("sources_ready", "gen_report", "report_ready", "scrape_digest") \
            and st.session_state.get("task_mode") == "aggregation":
        import pandas as pd
        question  = st.session_state.question
        agg_items = st.session_state.get("agg_items", [])
        digest    = st.session_state.digest

        st.markdown(f"""
<div style="margin-bottom:8px">
  <div style="font-size:1.4rem;font-weight:700;color:#f1f5f9;letter-spacing:-0.01em">🔍 数据汇总：{question}</div>
</div>
""", unsafe_allow_html=True)

        st.markdown(f"""
<div class="stat-bar">
  <div class="stat-chip">📦 条目总数 <span class="val">{len(agg_items)}</span></div>
  <div class="stat-chip">🌐 来源平台 <span class="val">{len(set(i.get('_source_domain','') for i in agg_items))}</span></div>
</div>
""", unsafe_allow_html=True)

        with st.expander("🧠 AI 意图分析", expanded=False):
            for line in st.session_state.reasoning_log:
                st.markdown(f"<p style='color:#64748b;font-size:0.86rem;padding:3px 0'>{line}</p>", unsafe_allow_html=True)

        # AI 数据分析报告（可视化卡片面板）
        if digest:
            st.markdown('<div class="section-title">📊 AI 数据分析报告</div>', unsafe_allow_html=True)
            render_agg_dashboard(digest)

        # 结构化数据表格
        st.markdown('<div class="section-title">📋 结构化数据明细</div>', unsafe_allow_html=True)
        if agg_items:
            display_keys = [k for k in agg_items[0].keys() if not k.startswith("_")]

            def _normalize(v):
                if isinstance(v, list):
                    return "、".join(str(x) for x in v if x)
                return v or ""

            df = pd.DataFrame([{k: _normalize(item.get(k)) for k in display_keys} for item in agg_items])
            col_cfg = {}
            if "url" in display_keys:
                col_cfg["url"] = st.column_config.LinkColumn("链接", display_text="🔗 打开")
            st.dataframe(df, use_container_width=True, height=450, column_config=col_cfg)

            csv = df.to_csv(index=False).encode("utf-8-sig")
            dl_col, _ = st.columns([1, 3])
            with dl_col:
                st.download_button(
                    "⬇️ 下载 CSV",
                    data=csv,
                    file_name=f"data_{question[:20]}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="文件将保存到浏览器默认下载文件夹（通常为【下载】）",
                )
        else:
            st.warning("未能提取到结构化数据，请尝试更具体的描述。")

        st.markdown("---")
        ac1, ac2 = st.columns([2, 1])
        with ac1:
            if st.button("💾 保存报告", type="primary", use_container_width=True):
                fp = save_report(question, digest)
                st.success(f"✅ 已保存：{fp}")
        with ac2:
            if st.button("🏠 首页", use_container_width=True, key="home_agg"):
                go_home(); st.rerun()

    # ── 展示结果：research 模式 ──
    elif st.session_state.phase in ("sources_ready", "gen_report", "report_ready", "scrape_digest"):
        question = st.session_state.question
        sources  = st.session_state.sources

        st.markdown(f"""
<div style="margin-bottom:8px">
  <div style="font-size:1.4rem;font-weight:700;color:#f1f5f9;letter-spacing:-0.01em">🔍 {question}</div>
</div>
""", unsafe_allow_html=True)

        high_cnt = sum(1 for s in sources if s.get("relevance") == "high")
        _src_type = st.session_state.get("scrape_source_type", "全网综合")
        _time_rng = st.session_state.get("scrape_time_range", "不限")
        st.markdown(f"""
<div class="stat-bar">
  <div class="stat-chip">📚 来源 <span class="val">{len(sources)}</span></div>
  <div class="stat-chip">⭐ 高相关 <span class="val">{high_cnt}</span></div>
  <div class="stat-chip">🗂 {_src_type}</div>
  <div class="stat-chip">🕐 {_time_rng}</div>
</div>
""", unsafe_allow_html=True)

        with st.expander("🧠 AI 分析思路", expanded=False):
            for line in st.session_state.reasoning_log:
                st.markdown(f"<p style='color:#64748b;font-size:0.86rem;padding:3px 0'>{line}</p>", unsafe_allow_html=True)

        # ── 操作栏（按需报告 + 导入到提取器）──
        st.markdown(f'<div class="section-title">原始材料清单 · {len(sources)} 个来源</div>', unsafe_allow_html=True)

        if not sources:
            st.warning("未找到有效内容，请尝试换一个描述方式。")
        else:
            order_map = {"high": 0, "medium": 1, "low": 2}
            sorted_sources = sorted(sources, key=lambda s: order_map.get(s.get("relevance", "medium"), 1))

            # 操作栏
            act1, act2, act3, _ = st.columns([2, 2, 1, 2])
            with act1:
                gen_report_btn = st.button("📝 生成综合分析报告", use_container_width=True, type="primary")
            with act2:
                transfer_btn = st.button("📊 导入已选URL到数据提取器", use_container_width=True)
            with act3:
                if st.button("🔍 重搜", use_container_width=True):
                    for k in ["sources", "digest", "reasoning_log", "report", "scrape_report"]:
                        st.session_state[k] = [] if k == "sources" else ""
                    st.session_state.phase = "input"; st.rerun()

            # 处理"导入到提取器"
            if transfer_btn:
                selected_urls = [
                    sorted_sources[i]["url"]
                    for i in range(len(sorted_sources))
                    if st.session_state.get(f"sel_{i}", False)
                ]
                if selected_urls:
                    st.session_state.ue_urls  = "\n".join(selected_urls)
                    st.session_state.mode     = "url_extract"
                    st.session_state.phase    = "input"
                    st.rerun()
                else:
                    st.warning("请先勾选至少一个来源（卡片左侧复选框）")

            # 处理"生成综合报告"
            if gen_report_btn:
                with st.spinner("📝 综合分析报告生成中..."):
                    st.session_state.scrape_report = compile_digest(sources, question)

            # 展示报告（如已生成）
            if st.session_state.get("scrape_report"):
                _rpt = st.session_state.scrape_report
                st.markdown(f"""
<div class="digest-card">
  <div class="digest-label">综合分析报告</div>
  <div class="digest-body">{_rpt.replace(chr(10), '<br>')}</div>
</div>
""", unsafe_allow_html=True)
                rsc1, rsc2 = st.columns([3, 1])
                with rsc1:
                    if st.button("💾 保存报告", use_container_width=True, type="primary"):
                        fp = save_report(question, _rpt)
                        st.success(f"✅ 已保存：{fp}")
                with rsc2:
                    if st.button("🏠 首页", use_container_width=True, key="home_rpt"):
                        go_home(); st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            # 来源卡片（带复选框）
            for i, src in enumerate(sorted_sources):
                rel = src.get("relevance", "medium")
                chk_col, card_col = st.columns([0.05, 0.95])
                with chk_col:
                    st.checkbox("", key=f"sel_{i}", label_visibility="collapsed")
                with card_col:
                    st.markdown(f"""
<div class="src-card">
  <div class="src-header">
    <div class="src-num">{i+1}</div>
    <div class="src-title"><a href="{src['url']}" target="_blank" rel="noopener noreferrer"
      style="color:inherit;text-decoration:none;border-bottom:1px solid rgba(255,255,255,0.2)">{src['title']}</a></div>
  </div>
  <div class="src-meta">
    <span class="badge badge-{rel}">{RELEVANCE_DOT[rel]} {RELEVANCE_LABEL[rel]}</span>
    <span class="badge badge-domain">🌐 {src['domain']}</span>
  </div>
  <div class="src-summary">{src['summary']}</div>
  <div class="src-points">{src['key_points']}</div>
</div>
""", unsafe_allow_html=True)
                    with st.expander("📖 原文片段"):
                        st.code(src["raw_content"][:800], language=None)

        st.markdown("---")
        if st.button("🏠 首页", use_container_width=False, key="home_src"):
            go_home(); st.rerun()

        if st.session_state.phase == "scrape_digest":
            with st.spinner("📋 AI 正在生成内容汇总..."):
                scrape_sum = generate_scrape_digest(sources, question)
            st.markdown('<div class="section-title">内容汇总报告</div>', unsafe_allow_html=True)
            st.markdown('<div class="report-wrap">', unsafe_allow_html=True)
            st.markdown(scrape_sum)
            st.markdown('</div>', unsafe_allow_html=True)

            # 保存 / 首页
            sc1, sc2 = st.columns([3, 1])
            with sc1:
                if st.button("💾 保存汇总", type="primary", use_container_width=True):
                    fp = save_report(f"爬取汇总：{question}", scrape_sum)
                    st.success(f"✅ 已保存：{fp}")
            with sc2:
                if st.button("🏠 首页", use_container_width=True, key="home_sd"):
                    go_home(); st.rerun()

            # 模板选择 → 生成深度报告
            st.markdown("---")
            st.markdown('<div style="font-size:0.85rem;color:#94a3b8;font-weight:600;margin-bottom:12px">需要进一步生成深度报告？选择一个报告模板：</div>', unsafe_allow_html=True)
            tkeys = list(TEMPLATES.keys())
            tcols = st.columns(3)
            for i, tk in enumerate(tkeys):
                with tcols[i % 3]:
                    tpl = TEMPLATES[tk]
                    is_sel = st.session_state.template == tk
                    border = "rgba(99,102,241,0.6)" if is_sel else "rgba(255,255,255,0.07)"
                    bg = "rgba(99,102,241,0.10)" if is_sel else "rgba(255,255,255,0.02)"
                    st.markdown(f"""
<div style="background:{bg};border:1px solid {border};border-radius:10px;padding:12px 14px;margin-bottom:8px">
  <div style="font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:3px">{tpl['label']}</div>
  <div style="font-size:0.72rem;color:#475569">{tpl['desc']}</div>
</div>""", unsafe_allow_html=True)
                    if st.button("选择" if not is_sel else "✓ 已选", key=f"tpl_sd_{tk}", use_container_width=True):
                        st.session_state.template = tk; st.rerun()
            if st.button("📝 生成深度研究报告", use_container_width=True):
                st.session_state.phase = "gen_report"; st.rerun()

        elif st.session_state.phase == "gen_report":
            tpl_sys = TEMPLATES.get(st.session_state.template, TEMPLATES["general"])["system"]
            with st.spinner("📝 正在综合所有来源，生成完整报告..."):
                ctx = "\n\n".join([
                    f"【来源{i+1}】{s['title']}\n{s['url']}\n\n{s['raw_content']}"
                    for i, s in enumerate(sources)
                ])
                # 融合本地文档
                local_ctx = ""
                if st.session_state.local_docs:
                    try:
                        import rag as _rag
                        _rag.build_vector_store(st.session_state.local_docs)
                        local_ctx = "\n\n【本地文档精准摘录（RAG检索）】\n" + _rag.retrieve_as_context(question)
                    except Exception:
                        # 降级：截取前3000字
                        local_ctx = "\n\n【本地文档资料】\n" + "\n\n".join([
                            f"《{d['name']}》\n{d['content'][:3000]}"
                            for d in st.session_state.local_docs
                        ])
                report = ai_generate(
                    f"以下是搜集到的资料：\n\n{ctx}{local_ctx}\n\n请针对以下问题生成完整研究报告：{question}",
                    system=tpl_sys,
                )
            st.session_state.report = report
            st.session_state.chat_history = []
            st.session_state.phase = "report_ready"
            st.rerun()

        elif st.session_state.phase == "report_ready":
            tpl_label = TEMPLATES.get(st.session_state.template, TEMPLATES["general"])["label"]
            st.markdown(f'<div class="section-title">研究报告 · {tpl_label}</div>', unsafe_allow_html=True)

            # ── 交叉验证按钮 ──
            if not st.session_state.validation:
                if st.button("🔬 运行多源交叉验证", use_container_width=False):
                    with st.spinner("AI 正在分析各来源的一致性与争议点..."):
                        st.session_state.validation = cross_validate(sources, question)
                    st.rerun()

            # ── 显示交叉验证结果 ──
            if st.session_state.validation:
                val = st.session_state.validation
                reliability_color = {"high": "#34d399", "medium": "#fbbf24", "low": "#f87171"}.get(val.get("reliability", "medium"), "#fbbf24")
                st.markdown(f"""
<div style="background:rgba(15,23,42,0.7);border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:20px 24px;margin-bottom:20px">
  <div style="font-size:0.72rem;font-weight:700;color:#475569;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:14px">🔬 多源交叉验证结果</div>
  <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:14px">
    <div><span style="font-size:0.78rem;color:#64748b">整体可靠性</span><br><span style="font-size:1.1rem;font-weight:700;color:{reliability_color}">{val.get('reliability','').upper()}</span></div>
    <div style="flex:1"><span style="font-size:0.78rem;color:#64748b">共识</span><br><span style="font-size:0.86rem;color:#cbd5e1">{val.get('consensus','')}</span></div>
  </div>
  <div style="background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.15);border-radius:8px;padding:10px 14px;font-size:0.84rem;color:#fbbf24">
    ⚡ 争议点：{val.get('disputes', '无明显争议')}
  </div>
</div>""", unsafe_allow_html=True)

                # 关键结论验证
                claims = val.get("key_claims", [])
                if claims:
                    with st.expander(f"📋 关键结论验证（{len(claims)} 条）", expanded=False):
                        for c in claims:
                            verdict_map = {"confirmed": ("✅", "#34d399"), "disputed": ("⚠️", "#fbbf24"), "unverified": ("❓", "#94a3b8")}
                            icon, color = verdict_map.get(c.get("verdict", "unverified"), ("❓", "#94a3b8"))
                            st.markdown(f"""
<div style="border-left:3px solid {color};padding:8px 14px;margin-bottom:10px;background:rgba(255,255,255,0.02);border-radius:0 8px 8px 0">
  <span style="font-size:0.75rem;color:{color};font-weight:700">{icon} {c.get('verdict','').upper()}</span>
  <div style="font-size:0.88rem;color:#e2e8f0;margin-top:4px">{c.get('claim','')}</div>
  <div style="font-size:0.75rem;color:#475569;margin-top:4px">支持来源: {c.get('support',[])} · 反对来源: {c.get('oppose',[])}</div>
</div>""", unsafe_allow_html=True)

            # ── 报告正文 ──
            st.markdown('<div class="report-wrap">', unsafe_allow_html=True)
            st.markdown(st.session_state.report)
            st.markdown('</div>', unsafe_allow_html=True)

            # ── 操作按钮 ──
            st.markdown("")
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                if st.button("💾 保存报告", type="primary", use_container_width=True):
                    fp = save_report(question, st.session_state.report)
                    st.success(f"✅ 已保存：{fp}")
            with c2:
                if st.button("🔍 搜索新内容", use_container_width=True):
                    st.session_state.phase = "input"
                    st.session_state.report = ""
                    st.session_state.sources = []
                    st.session_state.validation = {}
                    st.session_state.chat_history = []
                    st.rerun()
            with c3:
                if st.button("🏠 首页", use_container_width=True):
                    go_home(); st.rerun()

            # ── Chat with Report ──
            st.markdown('<div class="section-title" style="margin-top:36px">💬 追问报告</div>', unsafe_allow_html=True)
            st.markdown('<div style="font-size:0.82rem;color:#475569;margin-bottom:16px">基于本次研究内容继续提问，AI 会结合报告和原始资料回答</div>', unsafe_allow_html=True)

            # 显示历史消息
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])

            # 输入框
            chat_input = st.chat_input("继续追问，例如：帮我展开第二部分的竞品数据...")
            if chat_input:
                st.session_state.chat_history.append({"role": "user", "content": chat_input})
                with st.chat_message("user", avatar="🧑"):
                    st.markdown(chat_input)
                with st.chat_message("assistant", avatar="🤖"):
                    with st.spinner("思考中..."):
                        answer = chat_with_report(
                            question, st.session_state.report,
                            st.session_state.chat_history[:-1], chat_input,
                        )
                    st.markdown(answer)
                st.session_state.chat_history.append({"role": "assistant", "content": answer})


# ══════════════════════════════════════════════
# 模式四：URL 智能提取
# ══════════════════════════════════════════════
elif st.session_state.mode == "url_extract":
    import pandas as pd

    # ── 顶部导航栏 ──
    st.markdown("""
<div class="topbar-wrap">
  <div class="topbar-brand"><div class="dot"></div>DeepResearch</div>
  <div class="topbar-crumb-new">
    首页 <span class="sep">›</span> <span class="cur">⚡ URL 智能提取</span>
  </div>
  <div></div>
</div>
""", unsafe_allow_html=True)
    if st.button("← 返回首页", key="back_ue"):
        go_home(); st.rerun()

    # ══════════════════════════════════════════════
    # 阶段一：输入
    # ══════════════════════════════════════════════
    if st.session_state.phase == "input":
        st.markdown("""
<div class="page-hero">
  <div class="page-hero-title">告诉 AI 你想<span class="accent">提取什么</span></div>
  <div class="page-hero-sub">粘贴目标网址，用一句话描述意图——主脑 AI 自动制定规则，打工 AI 并发提取，秒出数据看板。</div>
</div>
""", unsafe_allow_html=True)

        # ── 行业模板快捷标签 ──
        UE_TEMPLATES = {
            "🏢 房源分析":  "帮我提取这些链接里的二手房/租房信息，重点关注小区名、总价、单价、面积、楼层、建成年代和区域。",
            "💻 竞品监测":  "提取这些竞品页面里的产品名称、核心功能亮点、定价、目标用户和最新发布动态。",
            "🛒 电商比价":  "从这些商品页面提取商品名、品牌、当前售价、原价、评分、销量和主要规格参数。",
            "👔 职位速报":  "提取这些招聘页面里的职位名称、公司名、薪资范围、工作地点、经验要求和学历要求。",
            "📰 新闻事件":  "从这些新闻页面提取事件标题、发生时间、核心内容摘要、涉及主体和关键数据。",
        }

        # ── 当前模型路由徽章 ──
        route_title, route_desc = _current_model_route_summary()
        engine_html = (
            f'<span style="background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.35);'
            f'border-radius:100px;padding:3px 12px;font-size:0.75rem;font-weight:700;color:#a5b4fc">'
            f'{route_title}</span>'
        )
        st.markdown(
            f'<div style="margin-bottom:12px">{engine_html} '
            f'<span style="font-size:0.75rem;color:#334155;margin-left:6px">'
            f'{route_desc}</span></div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div style="font-size:0.78rem;font-weight:600;color:#475569;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:10px">快捷模板</div>', unsafe_allow_html=True)
        tag_cols = st.columns(len(UE_TEMPLATES))
        for col, (label, prompt_text) in zip(tag_cols, UE_TEMPLATES.items()):
            with col:
                if st.button(label, use_container_width=True, key=f"tpl_{label}"):
                    st.session_state.ue_intent = prompt_text
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        with st.form("ue_form"):
            url_input = st.text_area(
                "目标 URL 列表（每行一个）",
                value=st.session_state.ue_urls,
                height=140,
                placeholder="https://example.com/page1\nhttps://example.com/page2\n...",
                label_visibility="visible",
            )
            intent_input = st.text_area(
                "提取意图（描述你想要什么）",
                value=st.session_state.ue_intent,
                height=100,
                placeholder="例如：帮我提取这些链接里的招聘岗位，重点关注职位名、公司、薪资、工作地点和经验要求。",
                label_visibility="visible",
            )
            submitted = st.form_submit_button("⚡ 启动智能提取", use_container_width=True, type="primary")

        if submitted:
            urls_raw = [u.strip() for u in url_input.splitlines() if u.strip().startswith("http")]
            if not urls_raw:
                st.error("❌ 请至少输入一个有效 URL（以 http 开头）")
            elif not intent_input.strip():
                st.error("❌ 请描述你想提取的内容")
            else:
                st.session_state.ue_urls      = url_input
                st.session_state.ue_intent    = intent_input.strip()
                st.session_state.ue_schema    = {}
                st.session_state.ue_items     = []
                st.session_state.ue_dashboard = ""
                st.session_state.ue_log       = []
                st.session_state.phase        = "running"
                st.rerun()

    # ══════════════════════════════════════════════
    # 阶段二：运行流水线
    # ══════════════════════════════════════════════
    elif st.session_state.phase == "running":
        urls   = [u.strip() for u in st.session_state.ue_urls.splitlines() if u.strip().startswith("http")]
        intent = st.session_state.ue_intent
        engine = st.session_state.ue_engine
        route_title, _ = _current_model_route_summary()

        st.markdown(f"""
<div style="margin-bottom:16px">
  <div style="font-size:1.2rem;font-weight:700;color:#f1f5f9;margin-bottom:4px">
    ⚡ 流水线运行中 · {route_title}
  </div>
  <div style="font-size:0.82rem;color:#475569">
    {len(urls)} 个 URL · {intent[:60]}{'...' if len(intent) > 60 else ''}
  </div>
</div>
""", unsafe_allow_html=True)

        prog_bar    = st.progress(0)
        status_box  = st.empty()
        _ue_log: list[str] = []

        def on_ue_progress(step, total, msg):
            pct = int(step / total * 100)
            prog_bar.progress(pct)
            _ue_log.append(msg)
            lines_html = "".join(
                f'<div style="color:{"#a5b4fc" if i == len(_ue_log)-1 else "#475569"};'
                f'font-size:0.80rem;padding:2px 0">'
                f'{"⏳" if i == len(_ue_log)-1 else "✅"} {l}</div>'
                for i, l in enumerate(_ue_log[-6:])
            )
            status_box.markdown(
                f'<div style="background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.15);'
                f'border-radius:10px;padding:12px 16px;margin:6px 0">'
                f'<div style="font-size:0.72rem;font-weight:700;color:#334155;margin-bottom:6px">'
                f'进度 {pct}%</div>{lines_html}</div>',
                unsafe_allow_html=True,
            )

        schema, items, dashboard_json, log = run_url_pipeline(
            urls, intent,
            engine=engine,
            progress_callback=on_ue_progress,
        )

        st.session_state.ue_schema    = schema
        st.session_state.ue_items     = items
        st.session_state.ue_dashboard = dashboard_json
        st.session_state.ue_log       = log
        st.session_state.phase        = "ready"
        st.rerun()

    # ══════════════════════════════════════════════
    # 阶段三：展示结果
    # ══════════════════════════════════════════════
    elif st.session_state.phase == "ready":
        schema    = st.session_state.ue_schema
        items     = st.session_state.ue_items
        dashboard = st.session_state.ue_dashboard
        intent    = st.session_state.ue_intent
        log       = st.session_state.ue_log
        engine    = st.session_state.ue_engine
        route_title, _ = _current_model_route_summary()

        # 顶部概览
        fields     = schema.get("fields", [])
        urls_count = len([u for u in st.session_state.ue_urls.splitlines() if u.strip().startswith("http")])
        st.markdown(f"""
<div class="stat-bar">
  <div class="stat-chip">📦 提取条目 <span class="val">{len(items)}</span></div>
  <div class="stat-chip">🌐 URL 数 <span class="val">{urls_count}</span></div>
  <div class="stat-chip">📋 字段数 <span class="val">{len(fields)}</span></div>
  <div class="stat-chip">🎯 对象 <span class="val">{schema.get('target_object','—')}</span></div>
  <div class="stat-chip">🤖 模型路由 <span class="val">{route_title}</span></div>
</div>
""", unsafe_allow_html=True)

        # 推理日志
        with st.expander("🧠 流水线执行日志", expanded=False):
            for line in log:
                st.markdown(f"<p style='color:#64748b;font-size:0.85rem;padding:2px 0'>{line}</p>",
                            unsafe_allow_html=True)

        # 主脑 Schema 展示
        if fields:
            with st.expander(f"🔧 主脑生成的字段规则（{len(fields)} 个字段）", expanded=False):
                fcols = st.columns(3)
                for i, f in enumerate(fields):
                    with fcols[i % 3]:
                        req = "✦ 必填" if f.get("required") else "选填"
                        st.markdown(f"""
<div style="background:rgba(15,23,42,0.7);border:1px solid rgba(99,102,241,0.18);border-radius:10px;padding:12px 14px;margin-bottom:8px">
  <div style="font-size:0.85rem;font-weight:700;color:#a5b4fc;margin-bottom:2px">{f.get('label','')} <span style="font-size:0.68rem;color:#334155">({f.get('key','')})</span></div>
  <div style="font-size:0.75rem;color:#475569;margin-bottom:4px">{f.get('desc','')}</div>
  <div style="font-size:0.68rem;color:#334155">{req}</div>
</div>""", unsafe_allow_html=True)

        # Dashboard 可视化
        if dashboard:
            st.markdown('<div class="section-title">📊 数据看板</div>', unsafe_allow_html=True)
            render_agg_dashboard(dashboard)

        # 结构化数据表格
        st.markdown('<div class="section-title">📋 结构化数据明细</div>', unsafe_allow_html=True)
        if items:
            display_keys = [k for k in items[0].keys() if not k.startswith("_")]

            def _norm(v):
                if isinstance(v, list):
                    return "、".join(str(x) for x in v if x)
                return v or ""

            df = pd.DataFrame([{k: _norm(item.get(k)) for k in display_keys} for item in items])
            col_cfg_ue = {}
            if "url" in display_keys:
                col_cfg_ue["url"] = st.column_config.LinkColumn("链接", display_text="🔗 打开")
            st.dataframe(df, use_container_width=True, height=420, column_config=col_cfg_ue)

            csv = df.to_csv(index=False).encode("utf-8-sig")
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                st.download_button(
                    "⬇️ 下载 CSV",
                    data=csv,
                    file_name=f"extract_{intent[:20]}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="文件保存到浏览器默认下载文件夹（通常为【下载】），手机用户在文件管理器中查找",
                )
            with c2:
                if st.button("💾 保存看板报告", use_container_width=True, type="primary"):
                    fp = save_report(f"URL提取：{intent}", dashboard)
                    st.success(f"✅ 已保存：{fp}")
            with c3:
                if st.button("🏠 首页", use_container_width=True, key="home_ue"):
                    go_home(); st.rerun()
        else:
            st.warning("未能提取到结构化数据，请检查 URL 是否可访问，或调整意图描述后重试。")
            c_retry, c_home = st.columns([2, 1])
            with c_retry:
                if st.button("← 重新输入", use_container_width=True):
                    st.session_state.phase = "input"
                    st.rerun()
            with c_home:
                if st.button("🏠 首页", use_container_width=True, key="home_ue_empty"):
                    go_home(); st.rerun()


# ══════════════════════════════════════════════
# 模式四：Agent 自主模式
# ══════════════════════════════════════════════
elif st.session_state.mode == "agent":
    from agent_loop import run_agent, TOOLS as AGENT_TOOLS

    # ── 顶部导航栏 ──
    st.markdown("""
<div class="topbar-wrap">
  <div class="topbar-brand"><div class="dot"></div>DeepResearch</div>
  <div class="topbar-crumb-new">
    首页 <span class="sep">›</span> <span class="cur">🤖 Agent 自主模式</span>
  </div>
  <div></div>
</div>
""", unsafe_allow_html=True)
    if st.button("← 返回首页", key="back_agent"):
        go_home(); st.rerun()

    # ── 输入阶段 ──
    if st.session_state.phase == "input":
        st.markdown("### 🤖 Agent 自主模式")

        # ── sub-mode 选择 ──
        agent_sub = st.radio(
            "运行模式",
            ["⚡ ReAct 自主", "🗺️ 深度规划"],
            horizontal=True,
            key="agent_sub_mode",
            help=(
                "⚡ ReAct 自主：单一 ReAct 循环，适合明确的单一问题。\n"
                "🗺️ 深度规划：先拆解为 3-5 个子问题，分别调研后综合成报告，适合复杂多维问题。"
            ),
        )
        is_planner = agent_sub.startswith("🗺️")

        if is_planner:
            st.caption("输入复杂问题，Agent 先自动拆解为多个子问题，逐一深度调研，最后综合出结构化报告。")
        else:
            st.caption("输入你的问题，Agent 会自主规划：搜索、爬取网页、检索本地文档……逐步推理，直到给出完整答案。")

        if is_planner:
            selected_profile = "planner"
            st.caption("Skill Profile：`planner`（固定，限制深度与批量爬取以控制子问题收敛）")
        else:
            profile_options = [DEFAULT_SKILL_PROFILE, "web_research_heavy"]
            selected_profile = st.selectbox(
                "Skill Profile",
                options=profile_options,
                index=0,
                key="agent_skill_profile_select",
                format_func=lambda profile: {
                    "react_default": "react_default · 平衡模式",
                    "web_research_heavy": "web_research_heavy · 网页研究增强",
                }.get(profile, profile),
                help="平衡模式更克制；网页研究增强会开放 batch/deep crawl 这类网页能力。",
            )

        question = st.text_area(
            "你的问题",
            placeholder=(
                "例如：比较特斯拉和比亚迪 2024 年的市场策略和财务表现"
                if is_planner else
                "例如：特斯拉 2024 年的核心财务指标和市场表现如何？"
            ),
            height=100,
            key="agent_question_input",
        )

        if is_planner:
            run_btn = st.button("🗺️ 启动深度规划", use_container_width=True,
                                type="primary", disabled=not question.strip())
            max_steps = SUB_MAX_STEPS_DEFAULT = 4   # 固定子步数，不暴露给用户
        else:
            c_run, c_adv = st.columns([3, 1])
            with c_adv:
                max_steps = st.number_input("最大步数", min_value=3, max_value=15,
                                            value=8, step=1)
            with c_run:
                run_btn = st.button("🚀 启动 Agent", use_container_width=True,
                                    type="primary", disabled=not question.strip())

        if run_btn and question.strip():
            st.session_state.agent_question_submitted = question.strip()
            st.session_state.agent_max_steps          = int(max_steps)
            st.session_state.agent_is_planner         = is_planner
            st.session_state.agent_skill_profile      = selected_profile
            st.session_state.phase                    = "running"
            st.rerun()

    # ── 运行阶段 ──
    elif st.session_state.phase == "running":
        question   = st.session_state.get("agent_question_submitted", "")
        max_steps  = st.session_state.get("agent_max_steps", 8)
        engine     = st.session_state.get("ue_engine", "")
        is_planner = st.session_state.get("agent_is_planner", False)
        skill_profile = st.session_state.get(
            "agent_skill_profile",
            "planner" if is_planner else DEFAULT_SKILL_PROFILE,
        )

        mode_label = "🗺️ 深度规划" if is_planner else "🤖 ReAct 自主"
        st.markdown(f"### {mode_label} 正在处理：{question}")
        st.caption(f"Skill Profile：`{skill_profile}`")

        status_box = st.empty()

        def _progress(msg: str):
            status_box.info(f"⏳ {msg}")

        # ══ 分支：深度规划模式 ══
        if is_planner:
            from agent_planner import run_planner_agent

            with st.spinner("规划 Agent 运行中，请稍候…"):
                result = run_planner_agent(
                    question=question,
                    engine=engine,
                    progress_callback=_progress,
                )
            status_box.empty()

            # 展示规划方案
            plan = result.get("plan", {})
            if plan:
                with st.expander("📋 研究规划", expanded=True):
                    st.caption(plan.get("reasoning", ""))
                    for idx, sq in enumerate(plan.get("sub_questions", []), 1):
                        st.markdown(f"**{idx}.** {sq}")

            # 展示每个子问题结果
            sub_results = result.get("sub_results", [])
            if sub_results:
                st.markdown("#### 子问题调研结果")
                for i, sr in enumerate(sub_results, 1):
                    label = f"🔬 子问题 {i}：{sr['sub_q']}"
                    with st.expander(label, expanded=False):
                        st.markdown(sr.get("answer", "（无结果）"))
                        observations = sr.get("observations", [])
                        if observations:
                            st.caption(f"Collected {len(observations)} observations")
                            for j, obs in enumerate(observations, 1):
                                obs_label = f"Observation {j} | {obs.get('tool', '')}"
                                with st.expander(obs_label, expanded=False):
                                    content = obs.get("content", "")
                                    if content:
                                        st.text(content[:1500] + ("..." if len(content) > 1500 else ""))
                                    _render_observation_sources(
                                        obs.get("sources", []),
                                        obs.get("cite_ids", []),
                                    )
                        if sr.get("error"):
                            st.warning(f"执行出错：{sr['error'][:200]}")

            # 最终综合报告
            st.divider()
            st.markdown("#### 📋 最终综合报告")
            answer = result.get("answer", "")
            st.markdown(answer)

            # 操作按钮
            st.divider()
            _render_reference_registry(result)
            cb1, cb2, cb3 = st.columns(3)
            with cb1:
                if st.button("💾 保存报告", use_container_width=True, type="primary",
                             key="planner_save"):
                    from tools import save_report
                    fp = save_report(question, answer)
                    st.success(f"✅ 已保存：{fp}")
            with cb2:
                if st.button("🔄 重新提问", use_container_width=True, key="planner_retry"):
                    st.session_state.phase = "input"
                    st.rerun()
            with cb3:
                if st.button("🏠 返回首页", use_container_width=True, key="planner_home"):
                    go_home(); st.rerun()

        # ══ 分支：ReAct 自主模式 ══
        else:
            with st.spinner("Agent 推理中，请稍候…"):
                result = run_agent(
                    question=question,
                    engine=engine,
                    max_steps=max_steps,
                    progress_callback=_progress,
                    skill_profile=skill_profile,
                )
            status_box.empty()

            # 展示每步过程
            _render_route_debug(result.get("route", {}), skill_profile)
            steps = result.get("steps", [])
            if steps:
                st.markdown("#### 推理步骤")
                for i, step in enumerate(steps, 1):
                    tool_icon = {
                        "search":       "🔍",
                        "search_multi": "🔎",
                        "search_docs":  "📚",
                        "search_company": "🏢",
                        "search_site":  "🔍",
                        "search_recent": "🕒",
                        "search_news":  "📰",
                        "scrape":       "🌐",
                        "extract_links": "🧭",
                        "scrape_batch": "🗂️",
                        "scrape_deep":  "🕸️",
                        "extract":      "🔎",
                        "summarize":    "📝",
                        "rag_retrieve": "📂",
                        "finish":       "🏁",
                    }.get(step.get("tool", ""), "🔧")
                    label = _format_step_label(
                        step.get("tool", ""),
                        step.get("args", {}) or {},
                        i,
                        tool_icon,
                    )
                    with st.expander(label, expanded=False):
                        st.markdown(f"**💭 思考**\n\n{step.get('thought', '')}")
                        obs = step.get("observation", "")
                        _render_observation_sources(
                            step.get("sources", []),
                            step.get("cite_ids", []),
                        )
                        if step.get("error_type"):
                            st.caption(f"Error Type: {step['error_type']}")
                        if obs and obs != "(任务完成)":
                            st.markdown("**👁️ 观察结果**")
                            st.text(obs[:1500] + ("..." if len(obs) > 1500 else ""))

            # 最终答案
            st.divider()
            answer = result.get("answer", "")
            with st.expander("📋 最终答案", expanded=True):
                st.markdown(answer)

            # 操作按钮
            st.divider()
            _render_reference_registry(result)
            cb1, cb2, cb3 = st.columns(3)
            with cb1:
                if st.button("💾 保存报告", use_container_width=True, type="primary",
                             key="react_save"):
                    from tools import save_report
                    fp = save_report(question, answer)
                    st.success(f"✅ 已保存：{fp}")
            with cb2:
                if st.button("🔄 重新提问", use_container_width=True, key="react_retry"):
                    st.session_state.phase = "input"
                    st.rerun()
            with cb3:
                if st.button("🏠 返回首页", use_container_width=True, key="react_home"):
                    go_home(); st.rerun()
