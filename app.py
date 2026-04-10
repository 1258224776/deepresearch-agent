"""
DeepResearch Agent — v5
UI/UX Pro Max 重设计：Glassmorphism 暗色科技风
"""

import os
import streamlit as st
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from main import (
    reason, web_search, fetch_page_content,
    summarize_source, compile_digest,
    ai_extract, fetch_page_full, deep_scrape,
    save_scraped, save_report, ai_generate, SYSTEM_PROMPT,
)

# ──────────────────────────────────────────────
# 页面配置
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="DeepResearch Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
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
#MainMenu, footer, header { visibility: hidden; }
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
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-size: 0.92rem !important;
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
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Session State
# ──────────────────────────────────────────────
_defaults = {
    "mode":    "home",
    "phase":   "input",
    "question":     "",
    "sources":      [],
    "reasoning_log":[],
    "digest":       "",
    "report":       "",
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

# ──────────────────────────────────────────────
# 侧边栏
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### 🔬 DeepResearch")
    if st.button("← 回首页", use_container_width=True):
        go_home(); st.rerun()
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
                fp = save_scraped(s_url, content, extracted)
                st.success(f"✅ 已保存")
                if extracted:
                    st.markdown(extracted)
            else:
                st.error(f"❌ 爬取失败")

    st.divider()
    st.markdown("**📁 已保存文件**")
    reports = sorted([f for f in os.listdir("reports") if f.endswith(".md")], reverse=True)[:4]
    scraped = sorted([f for f in os.listdir("scraped") if f.endswith(".md")], reverse=True)[:4]
    for f in reports:
        st.markdown(f'<div class="file-item">📄 {f}</div>', unsafe_allow_html=True)
    for f in scraped:
        st.markdown(f'<div class="file-item">🕷️ {f}</div>', unsafe_allow_html=True)
    if not reports and not scraped:
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
</div>
""", unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

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

    # 顶栏
    nav_l, nav_m, nav_r = st.columns([1, 4, 1])
    with nav_l:
        st.markdown('<div class="back-btn-wrap">', unsafe_allow_html=True)
        if st.button("← 返回首页", key="back_scrape"):
            go_home(); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with nav_m:
        st.markdown("""
<div style="text-align:center;padding:8px 0">
  <span style="font-size:0.82rem;color:#475569">首页 › <span style="color:#818cf8;font-weight:600">🔍 搜索 & 爬取</span></span>
</div>""", unsafe_allow_html=True)
    st.markdown('<div style="border-bottom:1px solid rgba(255,255,255,0.05);margin-bottom:28px"></div>', unsafe_allow_html=True)

    # ── 输入 ──
    if st.session_state.phase == "input":
        st.markdown("""
<div style="max-width:640px;margin:0 auto;padding:40px 0 20px;text-align:center">
  <div style="font-size:1.8rem;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;margin-bottom:12px">你想搜索什么？</div>
  <div style="font-size:0.93rem;color:#475569;margin-bottom:36px">描述你感兴趣的主题，AI 会自动规划搜索策略并抓取多个网页。</div>
</div>
""", unsafe_allow_html=True)

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
<div style="margin-bottom:24px">
  <div style="font-size:1.3rem;font-weight:700;color:#f1f5f9;margin-bottom:6px">🔍 正在研究：{question}</div>
  <div style="font-size:0.83rem;color:#475569">AI 正在规划搜索角度并抓取内容，请稍候...</div>
</div>
""", unsafe_allow_html=True)

        with st.status("深度搜索爬取中...", expanded=True) as status:
            st.write("🧠 分析主题，规划搜索角度...")
            plan    = reason(question)
            queries = (plan.get("search_queries") or [question])[:4]
            log = [
                f"**分析：** {plan.get('reasoning', '')}",
                f"**搜索角度（{len(queries)} 个）：** {' · '.join(queries)}",
            ]
            st.write(f"📋 从 **{len(queries)}** 个角度搜索，每角度取 **5** 条")

            sources, seen = [], set()
            for i, query in enumerate(queries, 1):
                st.write(f"🔎 [{i}/{len(queries)}] 搜索「{query}」...")
                results = web_search(query, max_results=5)
                st.write(f"   找到 {len(results)} 条，开始爬取...")
                for r in results:
                    url = r.get("href", "")
                    if not url or url in seen: continue
                    seen.add(url)
                    title  = r.get("title", "无标题")
                    domain = urlparse(url).netloc
                    st.write(f"   📄 {title[:50]}...")
                    content = fetch_page_content(url)
                    if "抓取失败" in content or len(content) < 100: continue
                    info = summarize_source(content, question, title)
                    sources.append({
                        "title":      title,
                        "url":        url,
                        "domain":     domain,
                        "summary":    info.get("summary", ""),
                        "key_points": info.get("key_points", ""),
                        "relevance":  info.get("relevance", "medium"),
                        "raw_content": content,
                    })

            st.write(f"✅ 爬取完毕，共 {len(sources)} 个有效来源，正在汇总...")
            digest = compile_digest(sources, question) if sources else ""
            status.update(label=f"✅ 完成！{len(sources)} 个来源", state="complete", expanded=False)

        st.session_state.sources       = sources
        st.session_state.reasoning_log = log
        st.session_state.digest        = digest
        st.session_state.phase         = "sources_ready"
        st.rerun()

    # ── 展示结果 ──
    elif st.session_state.phase in ("sources_ready", "gen_report", "report_ready"):
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
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                if st.button("📝 基于以上内容生成研究报告", type="primary", use_container_width=True):
                    st.session_state.phase = "gen_report"; st.rerun()
            with c2:
                if st.button("🔍 重新搜索", use_container_width=True):
                    for k in ["sources", "digest", "reasoning_log", "report"]:
                        st.session_state[k] = [] if k not in ("digest", "report") else ""
                    st.session_state.phase = "input"; st.rerun()
            with c3:
                if st.button("🏠 首页", use_container_width=True):
                    go_home(); st.rerun()

        elif st.session_state.phase == "gen_report":
            with st.spinner("📝 正在综合所有来源，生成完整报告..."):
                ctx = "\n\n".join([
                    f"【来源{i+1}】{s['title']}\n{s['url']}\n\n{s['raw_content']}"
                    for i, s in enumerate(sources)
                ])
                report = ai_generate(
                    f"以下是搜集到的资料：\n\n{ctx}\n\n请针对以下问题生成完整研究报告：{question}",
                    system=SYSTEM_PROMPT,
                )
            st.session_state.report = report
            st.session_state.phase  = "report_ready"
            st.rerun()

        elif st.session_state.phase == "report_ready":
            st.markdown('<div class="section-title">研究报告</div>', unsafe_allow_html=True)
            st.markdown('<div class="report-wrap">', unsafe_allow_html=True)
            st.markdown(st.session_state.report)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("")
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                if st.button("💾 保存报告", type="primary", use_container_width=True):
                    fp = save_report(question, st.session_state.report)
                    st.success(f"✅ 已保存：{fp}")
            with c2:
                if st.button("🔍 搜索新内容", use_container_width=True):
                    st.session_state.phase  = "input"
                    st.session_state.report = ""
                    st.session_state.sources = []
                    st.rerun()
            with c3:
                if st.button("🏠 首页", use_container_width=True):
                    go_home(); st.rerun()


# ══════════════════════════════════════════════
# 模式二：直接生成报告
# ══════════════════════════════════════════════
elif st.session_state.mode == "direct":

    # 顶栏
    nav_l2, nav_m2, nav_r2 = st.columns([1, 4, 1])
    with nav_l2:
        st.markdown('<div class="back-btn-wrap">', unsafe_allow_html=True)
        if st.button("← 返回首页", key="back_direct"):
            go_home(); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with nav_m2:
        st.markdown("""
<div style="text-align:center;padding:8px 0">
  <span style="font-size:0.82rem;color:#475569">首页 › <span style="color:#818cf8;font-weight:600">📝 生成研究报告</span></span>
</div>""", unsafe_allow_html=True)
    st.markdown('<div style="border-bottom:1px solid rgba(255,255,255,0.05);margin-bottom:28px"></div>', unsafe_allow_html=True)

    if st.session_state.phase == "input":
        st.markdown("""
<div style="max-width:640px;margin:0 auto;padding:40px 0 20px;text-align:center">
  <div style="font-size:1.8rem;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;margin-bottom:12px">你想研究什么问题？</div>
  <div style="font-size:0.93rem;color:#475569;margin-bottom:36px">AI 会自动搜索多方资料、综合分析，直接生成一份完整的研究报告。</div>
</div>
""", unsafe_allow_html=True)

        with st.form("direct_form"):
            q = st.text_input("研究问题", placeholder="例如：2025 年 AI 大模型行业竞争格局分析", label_visibility="collapsed")
            if st.form_submit_button("📝 生成研究报告", use_container_width=True, type="primary"):
                if q.strip():
                    st.session_state.question = q.strip()
                    st.session_state.phase    = "generating"
                    st.rerun()

    elif st.session_state.phase == "generating":
        question = st.session_state.question
        st.markdown(f"""
<div style="margin-bottom:24px">
  <div style="font-size:1.3rem;font-weight:700;color:#f1f5f9;margin-bottom:6px">📝 正在生成报告：{question}</div>
  <div style="font-size:0.83rem;color:#475569">AI 正在搜索并综合多方资料，请稍候...</div>
</div>
""", unsafe_allow_html=True)

        with st.status("深度研究进行中...", expanded=True) as status:
            st.write("🧠 分析问题...")
            plan    = reason(question)
            queries = (plan.get("search_queries") or [question])[:4]
            st.write(f"🔎 从 {len(queries)} 个角度搜索")

            sources, seen = [], set()
            for i, query in enumerate(queries, 1):
                st.write(f"🔎 [{i}/{len(queries)}] 搜索「{query}」...")
                for r in web_search(query, max_results=5):
                    url = r.get("href", "")
                    if not url or url in seen: continue
                    seen.add(url)
                    title   = r.get("title", "无标题")
                    domain  = urlparse(url).netloc
                    st.write(f"   📄 {title[:50]}...")
                    content = fetch_page_content(url)
                    if "抓取失败" in content or len(content) < 100: continue
                    sources.append({"title": title, "url": url,
                                    "domain": domain, "raw_content": content})

            st.write(f"✅ 共收集 {len(sources)} 个来源，正在综合分析...")
            ctx = "\n\n".join([
                f"【来源{i+1}】{s['title']}\n{s['url']}\n\n{s['raw_content']}"
                for i, s in enumerate(sources)
            ])
            report = ai_generate(
                f"以下资料：\n\n{ctx}\n\n问题：{question}\n\n请生成完整研究报告。",
                system=SYSTEM_PROMPT,
            )
            status.update(label="✅ 报告生成完成", state="complete", expanded=False)

        st.session_state.sources = sources
        st.session_state.report  = report
        st.session_state.phase   = "done"
        st.rerun()

    elif st.session_state.phase == "done":
        question = st.session_state.question
        sources  = st.session_state.sources

        st.markdown(f"""
<div style="margin-bottom:20px">
  <div style="font-size:1.4rem;font-weight:700;color:#f1f5f9;letter-spacing:-0.01em">📋 研究报告：{question}</div>
</div>
""", unsafe_allow_html=True)

        st.markdown(f"""
<div class="stat-bar">
  <div class="stat-chip">📚 参考来源 <span class="val">{len(sources)}</span></div>
</div>
""", unsafe_allow_html=True)

        with st.expander(f"📚 查看参考来源（{len(sources)} 个）", expanded=False):
            for i, s in enumerate(sources):
                st.markdown(
                    f'<span style="background:rgba(99,102,241,0.12);color:#818cf8;border-radius:5px;'
                    f'padding:1px 8px;font-size:0.72rem;font-weight:700">{i+1}</span> '
                    f'[{s["title"]}]({s["url"]}) '
                    f'<span style="color:#334155;font-size:0.78rem">{s["domain"]}</span>',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="report-wrap">', unsafe_allow_html=True)
        st.markdown(st.session_state.report)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("")

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            if st.button("💾 保存报告", type="primary", use_container_width=True):
                fp = save_report(question, st.session_state.report)
                st.success(f"✅ 已保存：{fp}")
        with c2:
            if st.button("📝 重新研究", use_container_width=True):
                st.session_state.phase = "input"
                st.session_state.report = ""
                st.session_state.sources = []
                st.rerun()
        with c3:
            if st.button("🏠 首页", use_container_width=True):
                go_home(); st.rerun()
