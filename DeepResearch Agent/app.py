"""
DeepResearch Agent — 网页前端 v2
运行方式：streamlit run app.py
"""

import os
import sys
import streamlit as st
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from main import (
    reason,
    web_search,
    fetch_page_content,
    extract_key_points,
    ai_extract,
    fetch_page_full,
    deep_scrape,
    save_scraped,
    save_report,
    client,
    SYSTEM_PROMPT,
)
from google.genai import types

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
# 自定义样式
# ──────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #0f1117; }

.phase-banner {
    background: linear-gradient(135deg, #1a1f2e 0%, #1e2d45 100%);
    border: 1px solid #2d3748;
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 20px;
}
.phase-banner h2 { color: #e2e8f0; margin: 0 0 4px 0; font-size: 1.2rem; }
.phase-banner p  { color: #718096; margin: 0; font-size: 0.85rem; }

.source-card {
    background: #1a1f2e;
    border: 1px solid #2d3748;
    border-radius: 10px;
    padding: 16px 18px;
    margin-bottom: 14px;
    transition: border-color 0.2s;
}
.source-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 6px;
    line-height: 1.4;
}
.source-domain {
    display: inline-block;
    background: #1e3a5f;
    color: #63b3ed;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.72rem;
    margin-bottom: 10px;
}
.source-points {
    color: #a0aec0;
    font-size: 0.85rem;
    line-height: 1.7;
    white-space: pre-wrap;
}
.source-link {
    color: #4f8ef7;
    font-size: 0.78rem;
    text-decoration: none;
}

.reason-box {
    background: #1a1f2e;
    border-left: 3px solid #4f8ef7;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.88rem;
    color: #a0aec0;
}

.report-box {
    background: #141920;
    border: 1px solid #2d3748;
    border-radius: 10px;
    padding: 24px 28px;
    margin-top: 10px;
}

.file-item {
    background: #1a1f2e;
    border-radius: 5px;
    padding: 6px 10px;
    margin: 4px 0;
    font-size: 0.82rem;
    color: #a0aec0;
}

div[data-testid="stButton"] button[kind="primary"] {
    background: linear-gradient(135deg, #3b82f6, #1d4ed8);
    border: none;
    font-weight: 600;
    letter-spacing: 0.02em;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Session State 初始化
# ──────────────────────────────────────────────
_defaults = {
    "phase": "idle",          # idle | searching | sources_ready | generating | report_ready
    "sources": [],            # list of {title, url, domain, key_points, raw_content}
    "question": "",
    "report": "",
    "reasoning_log": [],
    "search_queries": [],
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

os.makedirs("reports", exist_ok=True)
os.makedirs("scraped", exist_ok=True)

# ──────────────────────────────────────────────
# 侧边栏
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("🔬 DeepResearch")
    st.caption("AI 规划 · 多源爬取 · 智能摘要")
    st.divider()

    # ── 手动爬取工具 ──
    st.subheader("🕷️ 手动爬取网页")
    scrape_url = st.text_input("网址", placeholder="https://example.com")
    scrape_instruction = st.text_input("提取内容（可选）", placeholder="提取所有职位和薪资")
    deep_mode = st.checkbox("深度爬取（自动跟进子页面）")

    if st.button("开始爬取", use_container_width=True):
        if not scrape_url:
            st.warning("请输入网址")
        else:
            with st.spinner("爬取中..."):
                if deep_mode:
                    content = deep_scrape(scrape_url, max_pages=5)
                else:
                    content, _ = fetch_page_full(scrape_url)
            if content and not content.startswith("（"):
                extracted = ""
                if scrape_instruction:
                    with st.spinner("AI 提取中..."):
                        extracted = ai_extract(content, scrape_instruction)
                filepath = save_scraped(scrape_url, content, extracted)
                st.success(f"已保存: {filepath}")
                if extracted:
                    st.markdown("**AI 提取结果：**")
                    st.markdown(extracted)
            else:
                st.error(f"爬取失败: {content}")

    st.divider()

    # ── 已保存文件 ──
    st.subheader("📁 已保存文件")
    report_files = sorted(
        [f for f in os.listdir("reports") if f.endswith(".md")], reverse=True
    )[:5]
    if report_files:
        st.caption("研究报告（最近5条）")
        for f in report_files:
            st.markdown(f'<div class="file-item">📄 {f}</div>', unsafe_allow_html=True)
    else:
        st.caption("暂无报告")

    scraped_files = sorted(
        [f for f in os.listdir("scraped") if f.endswith(".md")], reverse=True
    )[:5]
    if scraped_files:
        st.caption("爬取记录（最近5条）")
        for f in scraped_files:
            st.markdown(f'<div class="file-item">🕷️ {f}</div>', unsafe_allow_html=True)

    st.divider()

    if st.button("🔄 重置 / 新研究", use_container_width=True):
        for k, v in _defaults.items():
            st.session_state[k] = v
        st.rerun()


# ══════════════════════════════════════════════
# 主区域
# ══════════════════════════════════════════════
st.title("深度研究助手")

# ──────────────────────────────────────────────
# Phase: idle — 输入研究问题
# ──────────────────────────────────────────────
if st.session_state.phase == "idle":
    st.caption("输入研究问题，AI 会自动规划搜索策略、抓取多个来源、提炼关键信息，再由你决定是否生成完整报告。")
    st.markdown("")

    with st.form("research_form", clear_on_submit=False):
        question = st.text_input(
            "研究问题",
            placeholder="例如：2025年大模型市场格局分析",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("🔍 开始研究", use_container_width=True, type="primary")

    if submitted:
        if not question.strip():
            st.warning("请输入研究问题")
        else:
            st.session_state.question = question.strip()
            st.session_state.phase = "searching"
            st.rerun()


# ──────────────────────────────────────────────
# Phase: searching — 实时爬取进度
# ──────────────────────────────────────────────
elif st.session_state.phase == "searching":
    question = st.session_state.question
    st.markdown(f'<div class="phase-banner"><h2>🔍 正在研究：{question}</h2><p>AI 正在规划策略、搜索并提取关键信息...</p></div>', unsafe_allow_html=True)

    with st.status("深度研究进行中...", expanded=True) as status:

        # Step 1: 推理
        st.write("🧠 分析问题，制定搜索策略...")
        plan = reason(question)
        queries     = plan.get("search_queries") or [question]
        reasoning   = plan.get("reasoning", "")
        q_type      = plan.get("question_type", "深度研究")

        st.write(f"📋 策略：从 **{len(queries)}** 个角度搜索（{q_type}）")

        reasoning_log = [
            f"**问题类型：** {q_type}",
            f"**分析思路：** {reasoning}",
            f"**搜索角度：** {' / '.join(queries)}",
        ]

        # Step 2: 搜索 + 抓取 + 提炼
        sources = []
        seen_urls = set()

        for i, query in enumerate(queries, 1):
            st.write(f"🔎 搜索 [{i}/{len(queries)}]：{query}")
            results = web_search(query, max_results=3)

            for r in results:
                url = r.get("href", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title  = r.get("title", "无标题")
                domain = urlparse(url).netloc

                st.write(f"   📄 处理：{title[:45]}...")
                content = fetch_page_content(url, max_chars=3000)

                if content.startswith("（"):
                    continue

                key_points = extract_key_points(content, question)

                sources.append({
                    "title":       title,
                    "url":         url,
                    "domain":      domain,
                    "key_points":  key_points,
                    "raw_content": content,
                })

        status.update(
            label=f"✅ 完成！共收集 {len(sources)} 个信息源",
            state="complete",
            expanded=False,
        )

    st.session_state.sources       = sources
    st.session_state.reasoning_log = reasoning_log
    st.session_state.search_queries = queries
    st.session_state.phase         = "sources_ready"
    st.rerun()


# ──────────────────────────────────────────────
# Phase: sources_ready / generating / report_ready
# ──────────────────────────────────────────────
elif st.session_state.phase in ("sources_ready", "generating", "report_ready"):
    question = st.session_state.question
    sources  = st.session_state.sources

    # ── 顶部：问题 + 推理折叠 ──
    st.markdown(f'<div class="phase-banner"><h2>🔎 {question}</h2><p>来自 {len(sources)} 个信息源的研究摘要</p></div>', unsafe_allow_html=True)

    with st.expander("🧠 查看 AI 分析思路", expanded=False):
        for line in st.session_state.reasoning_log:
            st.markdown(f'<div class="reason-box">{line}</div>', unsafe_allow_html=True)

    # ── 信息源卡片 ──
    st.subheader(f"📚 信息来源（{len(sources)} 个）")

    if not sources:
        st.warning("未能找到有效信息源，请尝试更换问题描述。")
    else:
        cols = st.columns(2, gap="medium")
        for i, src in enumerate(sources):
            with cols[i % 2]:
                st.markdown(f"""
<div class="source-card">
  <div class="source-domain">🌐 {src['domain']}</div>
  <div class="source-title">{src['title']}</div>
  <div class="source-points">{src['key_points']}</div>
</div>
""", unsafe_allow_html=True)
                with st.expander(f"查看原文片段 · {src['domain']}"):
                    st.markdown(f"[🔗 访问原网页]({src['url']})")
                    st.text(src["raw_content"][:600] + "…")

    st.markdown("---")

    # ── 操作区 ──
    if st.session_state.phase == "sources_ready":
        st.subheader("下一步")
        col_yes, col_no = st.columns([2, 1], gap="small")
        with col_yes:
            if st.button("📝 生成完整研究报告", type="primary", use_container_width=True):
                st.session_state.phase = "generating"
                st.rerun()
        with col_no:
            if st.button("✕ 不需要，重新研究", use_container_width=True):
                for k, v in _defaults.items():
                    st.session_state[k] = v
                st.rerun()

    elif st.session_state.phase == "generating":
        with st.spinner("📝 AI 正在综合所有来源，生成研究报告..."):
            chat = client.chats.create(
                model="gemini-3.1-pro-preview",
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            context_blocks = [
                f"【来源{i+1}】{s['title']}\n{s['url']}\n\n{s['raw_content']}"
                for i, s in enumerate(sources)
            ]
            context = (
                f"以下是从 {len(sources)} 个来源收集的资料：\n\n"
                + "\n\n" + ("─" * 40 + "\n\n").join(context_blocks)
            )
            report = chat.send_message(
                f"{context}\n\n用户的问题：{question}"
            ).text

        st.session_state.report = report
        st.session_state.phase  = "report_ready"
        st.rerun()

    elif st.session_state.phase == "report_ready":
        st.subheader("📋 研究报告")
        st.markdown(f'<div class="report-box">', unsafe_allow_html=True)
        st.markdown(st.session_state.report)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("")
        col_save, col_new = st.columns([1, 1], gap="small")
        with col_save:
            if st.button("💾 保存报告到本地", use_container_width=True, type="primary"):
                fp = save_report(question, st.session_state.report)
                st.success(f"已保存：{fp}")
        with col_new:
            if st.button("🔄 开始新研究", use_container_width=True):
                for k, v in _defaults.items():
                    st.session_state[k] = v
                st.rerun()
