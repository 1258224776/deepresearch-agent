"""
DeepResearch Agent — v6
企业级模块化重构 + 并行爬取 + 总进度条 + 爬取汇总
"""

import os
import streamlit as st

from agent import (
    ai_generate, reason, summarize_source, compile_digest,
    ai_extract, cross_validate, generate_scrape_digest,
    chat_with_report, run_research, run_url_pipeline,
    detect_network_mode,
)
from config import ENGINE_PRESETS, set_runtime_key
from tools import (
    web_search, fetch_page_content, fetch_page_full,
    deep_scrape, save_scraped, save_report, parse_uploaded_file,
)
from prompts import TEMPLATES

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
# 全局样式（UI/UX Pro Max · Glassmorphism Dark）
# ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

*, *::before, *::after {
    font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    box-sizing: border-box;
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
@keyframes pulseGlow {
    0%, 100% { box-shadow: 0 0 8px rgba(99,102,241,0.4); }
    50%       { box-shadow: 0 0 20px rgba(99,102,241,0.8), 0 0 40px rgba(99,102,241,0.3); }
}
@keyframes shimmer {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}
@keyframes scanline {
    0%   { transform: translateY(-100%); }
    100% { transform: translateY(100vh); }
}
@keyframes borderFlow {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* ── 背景 ── */
.stApp {
    background: #03060f;
    background-image:
        radial-gradient(ellipse 70% 45% at 20% 10%, rgba(99,102,241,0.10) 0%, transparent 60%),
        radial-gradient(ellipse 55% 40% at 80% 85%, rgba(59,130,246,0.08) 0%, transparent 55%),
        radial-gradient(ellipse 40% 30% at 60% 45%, rgba(139,92,246,0.05) 0%, transparent 50%);
    min-height: 100vh;
    animation: fadeIn 0.5s ease;
}

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
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.30);
    border-radius: 100px;
    padding: 6px 16px;
    font-size: 0.75rem;
    font-weight: 600;
    color: #a5b4fc;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 24px;
    animation: pulseGlow 3s ease-in-out infinite;
}
.hero-title {
    font-size: clamp(2rem, 5vw, 3.2rem);
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.15;
    color: #f8fafc;
    margin-bottom: 18px;
    animation: fadeUp 0.8s ease 0.1s both;
}
.hero-title .accent {
    background: linear-gradient(135deg, #818cf8 0%, #60a5fa 50%, #a78bfa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-sub {
    font-size: 1.05rem;
    color: #64748b;
    max-width: 520px;
    margin: 0 auto 48px;
    line-height: 1.75;
    font-weight: 400;
}

/* ── 功能选择卡片 ── */
.mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 860px; margin: 0 auto; }

.mode-card {
    background: rgba(15, 23, 42, 0.7);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(99,102,241,0.18);
    border-radius: 20px;
    padding: 36px 30px 28px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s, transform 0.3s, box-shadow 0.3s;
    text-align: left;
    cursor: default;
    animation: fadeUp 0.6s ease both;
}
.mode-card:hover {
    border-color: rgba(99,102,241,0.55);
    transform: translateY(-5px);
    box-shadow: 0 24px 64px rgba(99,102,241,0.16);
}
.mode-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #6366f1, #3b82f6, transparent);
    opacity: 0.6;
}
.mode-card-glow {
    position: absolute;
    top: -40px; right: -40px;
    width: 140px; height: 140px;
    background: radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 70%);
    pointer-events: none;
}
.mode-icon-wrap {
    width: 52px; height: 52px;
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.22);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
    margin-bottom: 20px;
    animation: float 4s ease-in-out infinite;
}
.mode-title { font-size: 1.05rem; font-weight: 700; color: #f1f5f9; margin-bottom: 10px; }
.mode-desc  { font-size: 0.87rem; color: #64748b; line-height: 1.7; margin-bottom: 18px; }
.mode-steps {
    display: flex; gap: 6px; flex-wrap: wrap;
}
.mode-step {
    font-size: 0.72rem;
    color: #818cf8;
    background: rgba(99,102,241,0.08);
    border: 1px solid rgba(99,102,241,0.15);
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
    border-bottom: 1px solid rgba(255,255,255,0.05);
    margin-bottom: 32px;
}
.topbar-logo {
    font-size: 1rem;
    font-weight: 700;
    color: #f1f5f9;
    display: flex; align-items: center; gap: 8px;
}
.topbar-logo .dot {
    width: 8px; height: 8px;
    background: #6366f1;
    border-radius: 50%;
    box-shadow: 0 0 10px rgba(99,102,241,0.8);
}
.topbar-crumb {
    font-size: 0.82rem;
    color: #475569;
    display: flex; align-items: center; gap: 6px;
}
.topbar-crumb .current { color: #818cf8; font-weight: 500; }

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
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 0.82rem;
    color: #64748b;
    font-weight: 500;
}
.stat-chip .val { color: #a5b4fc; font-weight: 700; font-size: 0.95rem; }

/* ══════════════════════════════
   综合摘要卡
══════════════════════════════ */
.digest-card {
    background: linear-gradient(135deg,
        rgba(15,31,61,0.9) 0%,
        rgba(12,26,53,0.9) 100%);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(99,102,241,0.28);
    border-radius: 18px;
    padding: 32px 36px;
    margin-bottom: 32px;
    position: relative;
    overflow: hidden;
}
.digest-card::after {
    content: '';
    position: absolute;
    bottom: -30px; right: -30px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(99,102,241,0.10) 0%, transparent 65%);
    pointer-events: none;
}
.digest-label {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #818cf8;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 16px;
}
.digest-label::before {
    content: '';
    width: 16px; height: 2px;
    background: linear-gradient(90deg, #6366f1, #3b82f6);
    border-radius: 2px;
}
.digest-body {
    font-size: 0.95rem;
    color: #cbd5e1;
    line-height: 1.85;
    font-weight: 400;
}

/* ══════════════════════════════
   来源卡片
══════════════════════════════ */
.src-card {
    background: rgba(13, 21, 32, 0.85);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 22px;
    margin-bottom: 16px;
    transition: border-color 0.25s, box-shadow 0.25s, transform 0.25s;
    animation: fadeUp 0.5s ease both;
}
.src-card:hover {
    border-color: rgba(99,102,241,0.35);
    box-shadow: 0 12px 40px rgba(0,0,0,0.35);
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
    background: linear-gradient(135deg, #4f46e5, #3b82f6);
    border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.7rem; font-weight: 800; color: #fff;
    letter-spacing: 0;
    box-shadow: 0 4px 12px rgba(79,70,229,0.35);
}
.src-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: #e2e8f0;
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
.badge-high   { background: rgba(16,185,129,0.12); color: #34d399; border: 1px solid rgba(16,185,129,0.25); }
.badge-medium { background: rgba(245,158,11,0.10); color: #fbbf24; border: 1px solid rgba(245,158,11,0.22); }
.badge-low    { background: rgba(100,116,139,0.12); color: #94a3b8; border: 1px solid rgba(100,116,139,0.22); }
.badge-domain { background: rgba(99,102,241,0.08); color: #818cf8; border: 1px solid rgba(99,102,241,0.18); }

.src-summary {
    font-size: 0.86rem;
    color: #94a3b8;
    line-height: 1.7;
    margin-bottom: 12px;
    padding: 11px 14px;
    background: rgba(255,255,255,0.025);
    border-radius: 10px;
    border-left: 3px solid rgba(99,102,241,0.4);
}
.src-points {
    font-size: 0.84rem;
    color: #cbd5e1;
    line-height: 1.8;
    white-space: pre-wrap;
}

/* ══════════════════════════════
   报告区
══════════════════════════════ */
.report-wrap {
    background: rgba(13, 21, 32, 0.85);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(99,102,241,0.22);
    border-radius: 18px;
    padding: 36px 40px;
    margin-top: 8px;
    font-size: 0.94rem;
    color: #e2e8f0;
    line-height: 1.9;
    position: relative;
    overflow: hidden;
}
.report-wrap::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #6366f1, #3b82f6, #a78bfa);
}

/* ══════════════════════════════
   分区标题
══════════════════════════════ */
.section-title {
    font-size: 0.75rem;
    font-weight: 700;
    color: #475569;
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
    background: linear-gradient(90deg, rgba(255,255,255,0.06), transparent);
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
    background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%) !important;
    border: none !important;
    color: #fff !important;
    box-shadow: 0 4px 16px rgba(79,70,229,0.30) !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    box-shadow: 0 6px 24px rgba(99,102,241,0.45) !important;
    transform: translateY(-1px) !important;
}
div[data-testid="stButton"] > button[kind="secondary"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    color: #94a3b8 !important;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.07) !important;
    color: #e2e8f0 !important;
}

/* ── 输入框 ── */
div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea {
    background: #0f1729 !important;
    border: 1px solid rgba(99,102,241,0.25) !important;
    border-radius: 10px !important;
    color: #cbd5e1 !important;
    font-size: 0.94rem !important;
    font-weight: 500 !important;
    caret-color: #818cf8 !important;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus {
    border-color: rgba(99,102,241,0.55) !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.12) !important;
    color: #e2e8f0 !important;
}
div[data-testid="stTextInput"] input::placeholder,
div[data-testid="stTextArea"] textarea::placeholder {
    color: #334155 !important;
    opacity: 1 !important;
}
div[data-testid="stTextInput"] input:focus, div[data-testid="stTextArea"] textarea:focus {
    border-color: rgba(99,102,241,0.50) !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.12) !important;
}

/* ── 侧边栏 ── */
section[data-testid="stSidebar"] {
    background: rgba(5,10,20,0.95) !important;
    backdrop-filter: blur(20px) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}

/* ── 文件条目 ── */
.file-item {
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 7px 12px;
    margin: 4px 0;
    font-size: 0.79rem;
    color: #475569;
    font-weight: 500;
}

/* ── 返回按钮 ── */
.back-btn-wrap div[data-testid="stButton"] > button {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    color: #64748b !important;
    font-size: 0.82rem !important;
    padding: 6px 14px !important;
    border-radius: 8px !important;
    width: auto !important;
}
.back-btn-wrap div[data-testid="stButton"] > button:hover {
    background: rgba(99,102,241,0.10) !important;
    border-color: rgba(99,102,241,0.30) !important;
    color: #a5b4fc !important;
}

/* ── 顶栏进入动效 ── */
.topbar { animation: fadeIn 0.4s ease; }
.digest-card { animation: fadeUp 0.6s ease both; }
.report-wrap { animation: fadeUp 0.5s ease both; }
.stat-bar    { animation: fadeUp 0.4s ease 0.1s both; }

/* ── divider ── */
hr { border-color: rgba(255,255,255,0.06) !important; }

/* ── expander ── */
div[data-testid="stExpander"] {
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 12px !important;
    background: rgba(255,255,255,0.02) !important;
}

/* ── status 组件 ── */
div[data-testid="stStatusWidget"] {
    border-radius: 12px !important;
    border: 1px solid rgba(99,102,241,0.20) !important;
    background: rgba(15,23,42,0.8) !important;
}

/* ══════════════════════════════
   功能页：表单 / 输入卡片
══════════════════════════════ */
div[data-testid="stForm"] {
    background: rgba(15, 23, 42, 0.75) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border: 1px solid rgba(99,102,241,0.20) !important;
    border-radius: 20px !important;
    padding: 32px 36px !important;
    position: relative;
    overflow: hidden;
}
div[data-testid="stForm"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #6366f1, #3b82f6, transparent);
    opacity: 0.5;
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
    color: #f1f5f9;
    letter-spacing: -0.02em;
    margin-bottom: 12px;
}
.page-hero-title .accent {
    background: linear-gradient(135deg, #818cf8 0%, #60a5fa 50%, #a78bfa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.page-hero-sub {
    font-size: 0.95rem;
    color: #475569;
    line-height: 1.75;
    margin-bottom: 36px;
}

/* ── 顶部导航优化 ── */
.topbar-wrap {
    background: rgba(3, 6, 15, 0.85);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255,255,255,0.05);
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
    color: #818cf8;
    display: flex; align-items: center; gap: 8px;
}
.topbar-brand .dot {
    width: 7px; height: 7px;
    background: #6366f1;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(99,102,241,0.9);
    animation: pulseGlow 2.5s ease-in-out infinite;
}
.topbar-crumb-new {
    font-size: 0.8rem;
    color: #334155;
    display: flex; align-items: center; gap: 8px;
}
.topbar-crumb-new .sep { color: #1e293b; }
.topbar-crumb-new .cur { color: #818cf8; font-weight: 600; }

/* ── 进度条美化 ── */
div[data-testid="stProgress"] > div {
    background: rgba(255,255,255,0.05) !important;
    border-radius: 100px !important;
    overflow: hidden;
}
div[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #4f46e5, #3b82f6, #818cf8) !important;
    border-radius: 100px !important;
    transition: width 0.3s ease !important;
}

/* ── chat 消息 ── */
div[data-testid="stChatMessage"] {
    background: rgba(255,255,255,0.025) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 14px !important;
    padding: 14px 18px !important;
    margin-bottom: 10px !important;
}

/* ── info / warning / success 提示 ── */
div[data-testid="stAlert"] {
    border-radius: 12px !important;
    border: none !important;
    background: rgba(99,102,241,0.08) !important;
    border-left: 3px solid rgba(99,102,241,0.5) !important;
    color: #a5b4fc !important;
    font-size: 0.86rem !important;
}

/* ── dataframe ── */
div[data-testid="stDataFrame"] {
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 14px !important;
    overflow: hidden !important;
    background: rgba(13,21,32,0.9) !important;
}

/* ── select / radio ── */
div[data-testid="stSelectbox"] > div,
div[data-testid="stMultiSelect"] > div {
    background: #0f1729 !important;
    border: 1px solid rgba(99,102,241,0.25) !important;
    border-radius: 10px !important;
    color: #cbd5e1 !important;
}

/* ── file uploader ── */
div[data-testid="stFileUploader"] {
    background: rgba(255,255,255,0.02) !important;
    border: 1.5px dashed rgba(99,102,241,0.30) !important;
    border-radius: 14px !important;
    padding: 20px !important;
}
div[data-testid="stFileUploader"]:hover {
    border-color: rgba(99,102,241,0.55) !important;
    background: rgba(99,102,241,0.04) !important;
}

/* ── spinner ── */
div[data-testid="stSpinner"] {
    color: #818cf8 !important;
}

/* ── download button ── */
div[data-testid="stDownloadButton"] > button {
    background: rgba(99,102,241,0.10) !important;
    border: 1px solid rgba(99,102,241,0.30) !important;
    color: #a5b4fc !important;
    border-radius: 10px !important;
    font-size: 0.84rem !important;
    font-weight: 600 !important;
}
div[data-testid="stDownloadButton"] > button:hover {
    background: rgba(99,102,241,0.20) !important;
    border-color: rgba(99,102,241,0.55) !important;
    color: #c7d2fe !important;
}

/* ══════════════════════════════
   Aggregation Dashboard
══════════════════════════════ */
.agg-dashboard { display:flex; flex-direction:column; gap:20px; animation:fadeUp 0.5s ease both; }
.agg-title { font-size:1.5rem; font-weight:800; color:#f1f5f9; letter-spacing:-0.02em; margin-bottom:4px; }

/* stat cards */
.agg-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }
.agg-stat-card {
    background:rgba(15,23,42,0.88);
    border:1px solid rgba(99,102,241,0.18);
    border-radius:16px; padding:18px 18px 14px; text-align:center;
}
.agg-stat-value { font-size:1.9rem; font-weight:800; color:#22d3ee; letter-spacing:-0.03em; line-height:1; margin-bottom:6px; }
.agg-stat-label { font-size:0.76rem; color:#64748b; font-weight:500; }
.agg-stat-change { font-size:0.82rem; font-weight:600; margin-top:6px; }
.agg-stat-change.pos { color:#10b981; }
.agg-stat-change.neg { color:#ef4444; }

/* highlights */
.agg-highlights { display:flex; flex-direction:column; gap:9px; }
.agg-hl-row {
    background:rgba(15,23,42,0.72); border:1px solid rgba(255,255,255,0.06);
    border-left:3px solid; border-radius:10px; padding:11px 16px;
    display:flex; align-items:center; gap:10px;
    font-size:0.91rem; color:#e2e8f0;
}
.agg-hl-icon { font-size:1.05rem; flex-shrink:0; }
.agg-hl-content { flex:1; line-height:1.55; }
.agg-hl-tag {
    font-size:0.70rem; font-weight:700; padding:2px 10px; border-radius:100px;
    background:rgba(34,211,238,0.15); color:#22d3ee; white-space:nowrap;
}

/* section title */
.agg-section-title {
    font-size:1rem; font-weight:700; color:#94a3b8;
    margin-top:4px; margin-bottom:10px;
    padding-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.06);
}

/* top items */
.agg-items-list { display:flex; flex-direction:column; gap:9px; }
.agg-item-card {
    background:rgba(15,23,42,0.75); border:1px solid rgba(255,255,255,0.07);
    border-radius:14px; padding:14px 18px;
    display:flex; align-items:center; justify-content:space-between; gap:14px;
}
.agg-item-left { flex:1; min-width:0; }
.agg-item-title { font-size:0.97rem; font-weight:700; color:#f1f5f9; margin-bottom:3px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.agg-item-sub { font-size:0.80rem; color:#64748b; margin-bottom:7px; }
.agg-item-tags { display:flex; flex-wrap:wrap; gap:5px; }
.agg-tag { font-size:0.70rem; font-weight:600; padding:2px 9px; border-radius:100px; background:rgba(99,102,241,0.15); color:#818cf8; }
.agg-new-badge { font-size:0.67rem; font-weight:700; padding:2px 8px; border-radius:100px; background:rgba(239,68,68,0.18); color:#f87171; }
.agg-item-value { font-size:1.35rem; font-weight:800; color:#f59e0b; white-space:nowrap; }

/* analysis */
.agg-analysis { display:flex; flex-direction:column; gap:18px; }
.agg-metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; }
.agg-metric-card { background:rgba(15,23,42,0.72); border:1px solid rgba(99,102,241,0.14); border-radius:14px; padding:14px 16px; }
.agg-metric-value { font-size:1.55rem; font-weight:800; color:#22d3ee; line-height:1.2; }
.agg-metric-label { font-size:0.76rem; color:#64748b; margin-top:4px; }
.agg-metric-sub { font-size:0.73rem; color:#475569; margin-top:3px; }

/* distributions */
.agg-dist-title { font-size:0.82rem; font-weight:600; color:#64748b; margin-bottom:8px; }
.agg-dist-bars { display:flex; flex-direction:column; gap:9px; }
.agg-dist-row { display:flex; align-items:center; gap:10px; }
.agg-dist-label { font-size:0.80rem; color:#94a3b8; min-width:36px; }
.agg-dist-bar-wrap { flex:1; background:rgba(255,255,255,0.05); border-radius:100px; height:7px; overflow:hidden; }
.agg-dist-bar-fill { height:100%; border-radius:100px; background:linear-gradient(90deg,#10b981,#22d3ee); }
.agg-dist-pct { font-size:0.76rem; color:#64748b; white-space:nowrap; min-width:90px; }

/* directions */
.agg-directions { display:flex; flex-wrap:wrap; gap:10px; }
.agg-dir-chip { background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.07); border-radius:13px; padding:10px 14px; min-width:72px; text-align:center; }
.agg-dir-name { font-size:0.75rem; color:#64748b; margin-bottom:3px; }
.agg-dir-count { font-size:1.25rem; font-weight:800; color:#e2e8f0; }
.agg-dir-trend { font-size:0.70rem; font-weight:600; margin-top:3px; }
.agg-dir-trend.trend-up { color:#10b981; }
.agg-dir-trend.trend-down { color:#ef4444; }
.agg-dir-trend.trend-flat { color:#64748b; }

/* recommendations */
.agg-recs { display:flex; flex-direction:column; gap:9px; }
.agg-rec-card {
    background:rgba(15,23,42,0.75); border:1px solid rgba(255,255,255,0.06);
    border-left:3px solid; border-radius:12px; padding:13px 16px;
    display:flex; gap:11px; align-items:flex-start;
}
.agg-rec-icon { font-size:1.15rem; flex-shrink:0; margin-top:1px; }
.agg-rec-title { font-size:0.90rem; font-weight:700; color:#e2e8f0; margin-bottom:3px; }
.agg-rec-content { font-size:0.82rem; color:#64748b; line-height:1.6; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Session State
# ──────────────────────────────────────────────
_defaults = {
    "mode":          "home",
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
    "ue_engine":     "fast",      # 引擎预设："deep" | "fast"
    "ue_schema":     {},          # 主脑生成的字段 Schema
    "ue_items":      [],          # 打工 AI 提取的结构化条目
    "ue_dashboard":  "",          # 看板 AI 生成的 Dashboard JSON
    "ue_log":        [],          # 流水线推理日志
    "net_mode":      "",          # 网络探测结果："overseas"|"domestic"|""
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


# ──────────────────────────────────────────────
# 侧边栏
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### 🔬 DeepResearch")
    if st.button("← 回首页", use_container_width=True):
        go_home(); st.rerun()

    st.divider()

    # ══════════════════════════════════════════
    # 引擎选择 + 网络自动探测
    # ══════════════════════════════════════════
    st.markdown("**⚡ 运行引擎**")

    # 网络探测按钮
    net_mode = st.session_state.get("net_mode", "")
    net_label = {
        "overseas": "🟢 海外节点可用",
        "domestic": "🔴 仅国内直连",
        "":         "⚪ 未探测",
    }.get(net_mode, "⚪ 未探测")
    col_net1, col_net2 = st.columns([2, 1])
    with col_net1:
        st.caption(net_label)
    with col_net2:
        if st.button("测速", key="probe_net", use_container_width=True):
            with st.spinner("探测中..."):
                detected = detect_network_mode()
            st.session_state.net_mode = detected
            # 自动切换推荐引擎
            if detected == "domestic" and st.session_state.ue_engine == "deep":
                st.session_state.ue_engine = "fast"
                st.toast("🔴 检测到海外不可达，已自动切换为极速直连模式", icon="⚡")
            elif detected == "overseas":
                st.toast("🟢 海外节点可用，可使用深度分析模式", icon="🌟")
            st.rerun()

    for eid, epreset in ENGINE_PRESETS.items():
        is_sel = st.session_state.ue_engine == eid
        border = "rgba(99,102,241,0.6)" if is_sel else "rgba(255,255,255,0.07)"
        bg     = "rgba(99,102,241,0.10)" if is_sel else "rgba(255,255,255,0.02)"
        st.markdown(f"""
<div style="background:{bg};border:1px solid {border};border-radius:10px;padding:10px 12px;margin-bottom:6px">
  <div style="font-size:0.85rem;font-weight:700;color:#e2e8f0">{epreset['label']}</div>
  <div style="font-size:0.73rem;color:#475569;margin-top:2px">{epreset['desc']}</div>
</div>""", unsafe_allow_html=True)
        if not is_sel:
            if st.button(f"切换到此模式", key=f"eng_{eid}", use_container_width=True):
                st.session_state.ue_engine = eid
                st.rerun()

    st.divider()

    # ══════════════════════════════════════════
    # API Key 管理（防刷爆额度，朋友自填）
    # ══════════════════════════════════════════
    with st.expander("🔑 API Key 配置", expanded=False):
        st.caption("在此填入 Key 后立即生效，不写入磁盘，刷新页面后失效。")

        _key_fields = [
            ("GOOGLE_API_KEY",       "Google / Gemini"),
            ("ANTHROPIC_API_KEY",    "Anthropic / Claude"),
            ("GLM_API_KEY",          "智谱 GLM"),
            ("MINIMAX_API_KEY",      "MiniMax"),
            ("SILICONFLOW_API_KEY",  "硅基流动"),
        ]
        for env_k, label in _key_fields:
            val = st.text_input(
                label,
                type="password",
                placeholder="sk-…（留空表示使用服务器默认）",
                key=f"apikey_{env_k}",
            )
            if val and val.strip():
                set_runtime_key(env_k, val.strip())

    st.divider()

    # ══════════════════════════════════════════
    # 本地文档上传
    # ══════════════════════════════════════════
    st.markdown("**📂 上传本地文档**")
    st.caption("研究时 AI 会将本地数据与网络资料交叉融合")
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
            st.success(f"✅ 已加载 {len(new_docs)} 个文档")
    if st.session_state.local_docs:
        for doc in st.session_state.local_docs:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f'<div class="file-item">📄 {doc["name"]}</div>', unsafe_allow_html=True)
            with c2:
                if st.button("✕", key=f"rm_{doc['name']}"):
                    st.session_state.local_docs = [d for d in st.session_state.local_docs if d["name"] != doc["name"]]
                    st.rerun()

    st.divider()
    st.markdown("**🕷️ 手动爬取**")
    s_url  = st.text_input("网址", placeholder="https://example.com")
    s_inst = st.text_input("提取内容（可选）")
    s_deep = st.checkbox("深度爬取（多层级）")
    if st.button("开始爬取", use_container_width=True, type="primary"):
        if s_url:
            with st.spinner("爬取中..."):
                content = deep_scrape(s_url, 5) if s_deep else fetch_page_full(s_url)[0]
            if content and not content.startswith("（"):
                extracted = ai_extract(content, s_inst) if s_inst else ""
                save_scraped(s_url, content, extracted)
                st.success("✅ 已保存")
                if extracted:
                    st.markdown(extracted)
            else:
                st.error("❌ 爬取失败")

    st.divider()
    st.markdown("**📁 已保存文件**")
    reports       = sorted([f for f in os.listdir("reports") if f.endswith(".md")], reverse=True)[:4]
    scraped_files = sorted([f for f in os.listdir("scraped")  if f.endswith(".md")], reverse=True)[:4]
    for f in reports:
        st.markdown(f'<div class="file-item">📄 {f}</div>', unsafe_allow_html=True)
    for f in scraped_files:
        st.markdown(f'<div class="file-item">🕷️ {f}</div>', unsafe_allow_html=True)
    if not reports and not scraped_files:
        st.markdown('<div class="file-item">暂无文件</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════
# 首页
# ══════════════════════════════════════════════
if st.session_state.mode == "home":

    st.markdown("""
<div class="hero-wrap">
  <div class="hero-badge">✦ AI-Powered Research</div>
  <div class="hero-title">深度研究，<span class="accent">交给 AI</span></div>
  <div class="hero-sub">自动搜索全网资料，智能提炼关键信息，生成专业研究报告——只需输入一个问题。</div>
  
                
                
""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3, gap="large")

    with col1:
        st.markdown("""
<div class="mode-card">
  <div class="mode-card-glow"></div>
  <div class="mode-icon-wrap">🔍</div>
  <div class="mode-title">搜索 & 爬取内容</div>
  <div class="mode-desc">输入主题，AI 从多角度搜索并抓取网页，完整呈现所有信息，你再决定是否生成报告。</div>
  <div class="mode-steps">
    <span class="mode-step">① 输入主题</span>
    <span class="mode-step">② 多角度搜索</span>
    <span class="mode-step">③ 查看摘要</span>
    <span class="mode-step">④ 可选报告</span>
  </div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("开始搜索爬取 →", use_container_width=True, type="primary", key="b_scrape"):
            st.session_state.mode = "scrape"
            st.session_state.phase = "input"
            st.rerun()

    with col2:
        st.markdown("""
<div class="mode-card">
  <div class="mode-card-glow"></div>
  <div class="mode-icon-wrap">📝</div>
  <div class="mode-title">直接生成研究报告</div>
  <div class="mode-desc">输入研究问题，AI 自动搜索综合多方资料，直接输出结构完整、有数据支撑的深度报告。</div>
  <div class="mode-steps">
    <span class="mode-step">① 输入问题</span>
    <span class="mode-step">② AI 综合分析</span>
    <span class="mode-step">③ 输出报告</span>
    <span class="mode-step">④ 可保存</span>
  </div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("生成研究报告 →", use_container_width=True, type="primary", key="b_report"):
            st.session_state.mode = "direct"
            st.session_state.phase = "input"
            st.rerun()

    with col3:
        st.markdown("""
<div class="mode-card">
  <div class="mode-card-glow"></div>
  <div class="mode-icon-wrap">⚡</div>
  <div class="mode-title">URL 智能提取</div>
  <div class="mode-desc">粘贴任意网址 + 描述你想要什么，主脑 AI 制定规则，打工 AI 并发提取，自动生成数据看板。</div>
  <div class="mode-steps">
    <span class="mode-step">① 贴入 URL</span>
    <span class="mode-step">② 描述意图</span>
    <span class="mode-step">③ 并发提取</span>
    <span class="mode-step">④ 看板呈现</span>
  </div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("开始 URL 提取 →", use_container_width=True, type="primary", key="b_ue"):
            st.session_state.mode = "url_extract"
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
  <div class="page-hero-title">你想<span class="accent">搜索</span>什么？</div>
  <div class="page-hero-sub">描述你感兴趣的主题，AI 会自动判断意图、规划搜索策略并并行抓取多个网页。</div>
</div>
""", unsafe_allow_html=True)

        # 显示本地文档提示
        if st.session_state.local_docs:
            st.info(f"📂 已加载 {len(st.session_state.local_docs)} 个本地文档，研究时将与网络资料交叉融合")

        with st.form("scrape_form"):
            q = st.text_input("搜索内容", placeholder="例如：特斯拉 2025 年最新车型发布信息", label_visibility="collapsed")
            if st.form_submit_button("🔍 开始搜索爬取", use_container_width=True, type="primary"):
                if q.strip():
                    st.session_state.question = q.strip()
                    st.session_state.phase = "searching"
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

        sources, digest, log, task_mode = run_research(question, progress_callback=on_progress)
        prog_bar.progress(100, text="✅ 完成")
        prog_text.empty()

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
        digest   = st.session_state.digest

        st.markdown(f"""
<div style="margin-bottom:8px">
  <div style="font-size:1.4rem;font-weight:700;color:#f1f5f9;letter-spacing:-0.01em">📄 {question}</div>
</div>
""", unsafe_allow_html=True)

        high_cnt = sum(1 for s in sources if s.get("relevance") == "high")
        st.markdown(f"""
<div class="stat-bar">
  <div class="stat-chip">📚 来源 <span class="val">{len(sources)}</span></div>
  <div class="stat-chip">⭐ 高相关 <span class="val">{high_cnt}</span></div>
  <div class="stat-chip">🔍 搜索角度 <span class="val">4</span></div>
</div>
""", unsafe_allow_html=True)

        with st.expander("🧠 AI 分析思路", expanded=False):
            for line in st.session_state.reasoning_log:
                st.markdown(f"<p style='color:#64748b;font-size:0.86rem;padding:3px 0'>{line}</p>", unsafe_allow_html=True)

        if digest:
            st.markdown(f"""
<div class="digest-card">
  <div class="digest-label">综合内容摘要</div>
  <div class="digest-body">{digest.replace(chr(10), '<br>')}</div>
</div>
""", unsafe_allow_html=True)

        st.markdown(f'<div class="section-title">各来源详细内容 · {len(sources)} 个</div>', unsafe_allow_html=True)

        if not sources:
            st.warning("未找到有效内容，请尝试换一个描述方式。")
        else:
            order_map = {"high": 0, "medium": 1, "low": 2}
            sorted_sources = sorted(sources, key=lambda s: order_map.get(s.get("relevance", "medium"), 1))
            cols = st.columns(2, gap="medium")
            for i, src in enumerate(sorted_sources):
                rel = src.get("relevance", "medium")
                with cols[i % 2]:
                    st.markdown(f"""
<div class="src-card">
  <div class="src-header">
    <div class="src-num">{i+1}</div>
    <div class="src-title">{src['title']}</div>
  </div>
  <div class="src-meta">
    <span class="badge badge-{rel}">{RELEVANCE_DOT[rel]} {RELEVANCE_LABEL[rel]}</span>
    <span class="badge badge-domain">🌐 {src['domain']}</span>
  </div>
  <div class="src-summary">{src['summary']}</div>
  <div class="src-points">{src['key_points']}</div>
</div>
""", unsafe_allow_html=True)
                    with st.expander("📖 原文片段 & 链接"):
                        st.markdown(f"[🔗 访问原页面]({src['url']})")
                        st.code(src["raw_content"][:800], language=None)

        st.markdown("---")

        if st.session_state.phase == "sources_ready":
            # 先生成内容汇总 / 重搜 / 首页
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                if st.button("📋 生成内容汇总", type="primary", use_container_width=True):
                    st.session_state.phase = "scrape_digest"; st.rerun()
            with c2:
                if st.button("🔍 重新搜索", use_container_width=True):
                    for k in ["sources", "digest", "reasoning_log", "report"]:
                        st.session_state[k] = [] if k not in ("digest", "report") else ""
                    st.session_state.phase = "input"; st.rerun()
            with c3:
                if st.button("🏠 首页", use_container_width=True):
                    go_home(); st.rerun()

        elif st.session_state.phase == "scrape_digest":
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
# 模式二：直接生成报告
# ══════════════════════════════════════════════
elif st.session_state.mode == "direct":

    # ── 顶部导航栏 ──
    st.markdown("""
<div class="topbar-wrap">
  <div class="topbar-brand"><div class="dot"></div>DeepResearch</div>
  <div class="topbar-crumb-new">
    首页 <span class="sep">›</span> <span class="cur">📝 生成研究报告</span>
  </div>
  <div></div>
</div>
""", unsafe_allow_html=True)
    if st.button("← 返回首页", key="back_direct"):
        go_home(); st.rerun()

    if st.session_state.phase == "input":
        st.markdown("""
<div class="page-hero">
  <div class="page-hero-title">你想<span class="accent">研究</span>什么？</div>
  <div class="page-hero-sub">AI 自动搜索多方资料、综合分析，直接生成结构完整、有数据支撑的深度报告。</div>
</div>
""", unsafe_allow_html=True)

        # 模板选择
        st.markdown('<div style="font-size:0.8rem;color:#475569;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:10px">选择报告模板</div>', unsafe_allow_html=True)
        tcols2 = st.columns(3)
        tkeys2 = list(TEMPLATES.keys())
        for i, tk in enumerate(tkeys2):
            with tcols2[i % 3]:
                tpl = TEMPLATES[tk]
                is_sel = st.session_state.template == tk
                border = "rgba(99,102,241,0.6)" if is_sel else "rgba(255,255,255,0.07)"
                bg = "rgba(99,102,241,0.10)" if is_sel else "rgba(255,255,255,0.02)"
                st.markdown(f"""
<div style="background:{bg};border:1px solid {border};border-radius:12px;padding:14px 16px;margin-bottom:10px">
  <div style="font-size:0.88rem;font-weight:700;color:#e2e8f0;margin-bottom:4px">{tpl['label']}</div>
  <div style="font-size:0.75rem;color:#475569">{tpl['desc']}</div>
</div>""", unsafe_allow_html=True)
                if st.button("选择" if not is_sel else "✓ 已选", key=f"tpl_d_{tk}", use_container_width=True):
                    st.session_state.template = tk
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.session_state.local_docs:
            st.info(f"📂 已加载 {len(st.session_state.local_docs)} 个本地文档，将与网络资料交叉融合")

        with st.form("direct_form"):
            q = st.text_input("研究问题", placeholder="例如：2025 年 AI 大模型行业竞争格局分析", label_visibility="collapsed")
            if st.form_submit_button("📝 生成研究报告", use_container_width=True, type="primary"):
                if q.strip():
                    st.session_state.question = q.strip()
                    st.session_state.phase    = "generating"
                    st.rerun()

    elif st.session_state.phase == "generating":
        question = st.session_state.question
        tpl_sys  = TEMPLATES.get(st.session_state.template, TEMPLATES["general"])["system"]

        st.markdown(f"""
<div style="margin-bottom:16px">
  <div style="font-size:1.3rem;font-weight:700;color:#f1f5f9;margin-bottom:6px">📝 正在生成报告：{question}</div>
  <div style="font-size:0.83rem;color:#475569">AI 并行搜索中，请稍候...</div>
</div>
""", unsafe_allow_html=True)

        prog_bar2  = st.progress(0, text="初始化...")
        prog_text2 = st.empty()

        def on_progress2(step, total, msg):
            pct = int(step / total * 100)
            prog_bar2.progress(pct, text=msg)
            prog_text2.markdown(
                f'<div style="font-size:0.81rem;color:#64748b;padding:2px 0">{msg}</div>',
                unsafe_allow_html=True,
            )

        sources, _, _ = run_research(question, progress_callback=on_progress2)
        prog_bar2.progress(100, text="✅ 数据收集完成，生成报告中...")
        prog_text2.empty()

        with st.spinner("📝 AI 综合分析，生成报告..."):
            ctx = "\n\n".join([
                f"【来源{i+1}】{s['title']}\n{s['url']}\n\n{s['raw_content']}"
                for i, s in enumerate(sources)
            ])
            local_ctx = ""
            if st.session_state.local_docs:
                local_ctx = "\n\n【本地文档资料】\n" + "\n\n".join([
                    f"《{d['name']}》\n{d['content'][:3000]}"
                    for d in st.session_state.local_docs
                ])
            report = ai_generate(
                f"以下资料：\n\n{ctx}{local_ctx}\n\n问题：{question}\n\n请生成完整研究报告。",
                system=tpl_sys,
            )

        st.session_state.sources      = sources
        st.session_state.report       = report
        st.session_state.chat_history = []
        st.session_state.validation   = {}
        st.session_state.phase        = "done"
        st.rerun()

    elif st.session_state.phase == "done":
        question = st.session_state.question
        sources  = st.session_state.sources
        tpl_label = TEMPLATES.get(st.session_state.template, TEMPLATES["general"])["label"]

        st.markdown(f"""
<div style="margin-bottom:16px">
  <div style="font-size:1.4rem;font-weight:700;color:#f1f5f9;letter-spacing:-0.01em">📋 {question}</div>
</div>
""", unsafe_allow_html=True)

        st.markdown(f"""
<div class="stat-bar">
  <div class="stat-chip">📚 参考来源 <span class="val">{len(sources)}</span></div>
  <div class="stat-chip">📋 模板 <span class="val">{tpl_label}</span></div>
  {'<div class="stat-chip">📂 本地文档 <span class="val">' + str(len(st.session_state.local_docs)) + '</span></div>' if st.session_state.local_docs else ''}
</div>
""", unsafe_allow_html=True)

        with st.expander(f"📚 参考来源（{len(sources)} 个）", expanded=False):
            for i, s in enumerate(sources):
                st.markdown(
                    f'<span style="background:rgba(99,102,241,0.12);color:#818cf8;border-radius:5px;'
                    f'padding:1px 8px;font-size:0.72rem;font-weight:700">{i+1}</span> '
                    f'[{s["title"]}]({s["url"]}) '
                    f'<span style="color:#334155;font-size:0.78rem">{s["domain"]}</span>',
                    unsafe_allow_html=True,
                )

        # 交叉验证
        if not st.session_state.validation:
            if st.button("🔬 运行多源交叉验证", key="val_direct"):
                with st.spinner("AI 正在分析各来源的一致性与争议点..."):
                    st.session_state.validation = cross_validate(sources, question)
                st.rerun()

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

        st.markdown(f'<div class="section-title">研究报告 · {tpl_label}</div>', unsafe_allow_html=True)
        st.markdown('<div class="report-wrap">', unsafe_allow_html=True)
        st.markdown(st.session_state.report)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("")

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            if st.button("💾 保存报告", type="primary", use_container_width=True, key="save_direct"):
                fp = save_report(question, st.session_state.report)
                st.success(f"✅ 已保存：{fp}")
        with c2:
            if st.button("📝 重新研究", use_container_width=True):
                st.session_state.phase = "input"
                st.session_state.report = ""
                st.session_state.sources = []
                st.session_state.validation = {}
                st.session_state.chat_history = []
                st.rerun()
        with c3:
            if st.button("🏠 首页", use_container_width=True, key="home_direct"):
                go_home(); st.rerun()

        # ── Chat with Report ──
        st.markdown('<div class="section-title" style="margin-top:36px">💬 追问报告</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.82rem;color:#475569;margin-bottom:16px">基于本次研究内容继续提问</div>', unsafe_allow_html=True)

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
                st.markdown(msg["content"])

        chat_input2 = st.chat_input("继续追问，例如：帮我把竞品数据做成表格...", key="chat_direct")
        if chat_input2:
            st.session_state.chat_history.append({"role": "user", "content": chat_input2})
            with st.chat_message("user", avatar="🧑"):
                st.markdown(chat_input2)
            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("思考中..."):
                    answer = chat_with_report(
                        question, st.session_state.report,
                        st.session_state.chat_history[:-1], chat_input2,
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

        # ── 当前引擎徽章 ──
        cur_engine  = st.session_state.ue_engine
        cur_preset  = ENGINE_PRESETS.get(cur_engine, {})
        engine_html = (
            f'<span style="background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.35);'
            f'border-radius:100px;padding:3px 12px;font-size:0.75rem;font-weight:700;color:#a5b4fc">'
            f'{cur_preset.get("label","默认引擎")}</span>'
        )
        st.markdown(
            f'<div style="margin-bottom:12px">{engine_html} '
            f'<span style="font-size:0.75rem;color:#334155;margin-left:6px">'
            f'可在左侧侧边栏切换引擎或测速</span></div>',
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
        preset = ENGINE_PRESETS.get(engine, {})

        st.markdown(f"""
<div style="margin-bottom:16px">
  <div style="font-size:1.2rem;font-weight:700;color:#f1f5f9;margin-bottom:4px">
    ⚡ 流水线运行中 · {preset.get('label','默认引擎')}
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
        preset    = ENGINE_PRESETS.get(engine, {})

        # 顶部概览
        fields     = schema.get("fields", [])
        urls_count = len([u for u in st.session_state.ue_urls.splitlines() if u.strip().startswith("http")])
        st.markdown(f"""
<div class="stat-bar">
  <div class="stat-chip">📦 提取条目 <span class="val">{len(items)}</span></div>
  <div class="stat-chip">🌐 URL 数 <span class="val">{urls_count}</span></div>
  <div class="stat-chip">📋 字段数 <span class="val">{len(fields)}</span></div>
  <div class="stat-chip">🎯 对象 <span class="val">{schema.get('target_object','—')}</span></div>
  <div class="stat-chip">⚡ 引擎 <span class="val">{preset.get('label','默认')}</span></div>
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
