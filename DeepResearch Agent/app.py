"""
DeepResearch Agent — v3
两大功能：① 搜索爬取内容  ② 直接生成研究报告
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
    reason, web_search, fetch_page_content, extract_key_points,
    ai_extract, fetch_page_full, deep_scrape,
    save_scraped, save_report, client, SYSTEM_PROMPT,
)
from google.genai import types

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
# 样式
# ──────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #0d1117; }

/* 首页模式选择卡片 */
.mode-card {
    background: #161b22;
    border: 1.5px solid #30363d;
    border-radius: 14px;
    padding: 32px 28px;
    cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s;
    height: 100%;
}
.mode-card:hover { border-color: #58a6ff; box-shadow: 0 0 0 3px rgba(88,166,255,0.15); }
.mode-icon  { font-size: 2.4rem; margin-bottom: 14px; }
.mode-title { font-size: 1.2rem; font-weight: 700; color: #e6edf3; margin-bottom: 8px; }
.mode-desc  { font-size: 0.88rem; color: #8b949e; line-height: 1.6; }
.mode-steps { margin-top: 14px; font-size: 0.8rem; color: #58a6ff; }

/* 面包屑导航 */
.breadcrumb {
    font-size: 0.82rem; color: #8b949e;
    margin-bottom: 18px;
    padding: 8px 14px;
    background: #161b22;
    border-radius: 6px;
    display: inline-block;
}
.breadcrumb span { color: #58a6ff; }

/* 来源卡片 */
.src-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 16px;
}
.src-num    { display:inline-block; background:#1f3a5c; color:#58a6ff; border-radius:50%; width:22px; height:22px; text-align:center; line-height:22px; font-size:0.75rem; font-weight:700; margin-right:8px; }
.src-title  { font-size:0.95rem; font-weight:600; color:#e6edf3; }
.src-domain { display:inline-block; background:#1a2636; color:#58a6ff; border-radius:20px; padding:2px 10px; font-size:0.72rem; margin: 8px 0 10px 0; }
.src-points { color:#8b949e; font-size:0.85rem; line-height:1.75; white-space:pre-wrap; }

/* 报告区 */
.report-wrap {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 28px 32px;
    margin-top: 6px;
}

/* 进度标签 */
.tag-blue {
    display:inline-block; background:#1f3a5c; color:#58a6ff;
    border-radius:4px; padding:2px 9px; font-size:0.75rem; margin-right:6px;
}

.file-item {
    background:#161b22; border-radius:5px;
    padding:6px 10px; margin:4px 0;
    font-size:0.81rem; color:#8b949e;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Session State
# ──────────────────────────────────────────────
_defaults = {
    "mode":    "home",      # home | scrape | direct
    "phase":   "input",     # input | searching | sources_ready | gen_report | report_ready | generating | done
    "question":     "",
    "sources":      [],
    "reasoning_log":[],
    "report":       "",
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

os.makedirs("reports", exist_ok=True)
os.makedirs("scraped",  exist_ok=True)

def go_home():
    for k, v in _defaults.items():
        st.session_state[k] = v

# ──────────────────────────────────────────────
# 侧边栏（已保存文件 + 手动爬取）
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔬 DeepResearch")
    if st.button("← 回到首页", use_container_width=True):
        go_home(); st.rerun()
    st.divider()

    st.subheader("🕷️ 手动爬取")
    s_url  = st.text_input("网址", placeholder="https://example.com")
    s_inst = st.text_input("提取内容（可选）", placeholder="提取所有职位和薪资")
    s_deep = st.checkbox("深度爬取（跟进子页面）")
    if st.button("开始爬取", use_container_width=True):
        if not s_url:
            st.warning("请输入网址")
        else:
            with st.spinner("爬取中..."):
                content = deep_scrape(s_url, 5) if s_deep else fetch_page_full(s_url)[0]
            if content and not content.startswith("（"):
                extracted = ai_extract(content, s_inst) if s_inst else ""
                fp = save_scraped(s_url, content, extracted)
                st.success(f"已保存: {fp}")
                if extracted:
                    st.markdown(extracted)
            else:
                st.error(f"失败: {content}")

    st.divider()
    st.subheader("📁 已保存文件")
    rfiles = sorted([f for f in os.listdir("reports") if f.endswith(".md")], reverse=True)[:5]
    if rfiles:
        st.caption("报告")
        for f in rfiles:
            st.markdown(f'<div class="file-item">📄 {f}</div>', unsafe_allow_html=True)
    sfiles = sorted([f for f in os.listdir("scraped") if f.endswith(".md")], reverse=True)[:5]
    if sfiles:
        st.caption("爬取记录")
        for f in sfiles:
            st.markdown(f'<div class="file-item">🕷️ {f}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════
# 首页：模式选择
# ══════════════════════════════════════════════
if st.session_state.mode == "home":
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("## 🔬 DeepResearch Agent")
    st.markdown("<p style='color:#8b949e;margin-bottom:32px'>选择你想要做的事情</p>", unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
<div class="mode-card">
  <div class="mode-icon">🔍</div>
  <div class="mode-title">搜索 & 爬取内容</div>
  <div class="mode-desc">输入你想了解的内容，AI 自动规划搜索策略，从多个网页抓取并提炼关键信息展示给你。</div>
  <div class="mode-steps">① 输入主题 → ② AI 搜索爬取 → ③ 查看内容摘要 → ④ 可选生成报告</div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("进入搜索爬取 →", use_container_width=True, key="btn_scrape"):
            st.session_state.mode  = "scrape"
            st.session_state.phase = "input"
            st.rerun()

    with col2:
        st.markdown("""
<div class="mode-card">
  <div class="mode-icon">📝</div>
  <div class="mode-title">直接生成研究报告</div>
  <div class="mode-desc">输入研究问题，AI 搜索、综合多方资料，直接输出一份完整、有条理的深度研究报告。</div>
  <div class="mode-steps">① 输入问题 → ② AI 搜索分析 → ③ 输出完整报告 → ④ 可保存</div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("进入报告生成 →", use_container_width=True, key="btn_report"):
            st.session_state.mode  = "direct"
            st.session_state.phase = "input"
            st.rerun()


# ══════════════════════════════════════════════
# 模式一：搜索爬取内容
# ══════════════════════════════════════════════
elif st.session_state.mode == "scrape":

    # 面包屑
    st.markdown('<div class="breadcrumb">首页 › <span>🔍 搜索 & 爬取内容</span></div>', unsafe_allow_html=True)

    # ── 输入阶段 ──
    if st.session_state.phase == "input":
        st.markdown("### 你想搜索什么内容？")
        st.caption("描述你想了解的主题或问题，AI 会自动找到相关网页并提炼关键内容。")
        st.markdown("")

        with st.form("scrape_form"):
            q = st.text_input("搜索主题", placeholder="例如：特斯拉 2025 年最新车型发布信息",
                              label_visibility="collapsed")
            if st.form_submit_button("🔍 开始搜索爬取", use_container_width=True, type="primary"):
                if q.strip():
                    st.session_state.question = q.strip()
                    st.session_state.phase = "searching"
                    st.rerun()
                else:
                    st.warning("请输入内容")

    # ── 搜索爬取阶段 ──
    elif st.session_state.phase == "searching":
        question = st.session_state.question
        st.markdown(f"### 🔍 正在搜索：{question}")

        with st.status("搜索爬取进行中...", expanded=True) as status:
            st.write("🧠 分析主题，规划搜索角度...")
            plan    = reason(question)
            queries = plan.get("search_queries") or [question]
            q_type  = plan.get("question_type", "深度研究")
            reasoning = plan.get("reasoning", "")

            st.write(f"📋 将从 **{len(queries)}** 个角度搜索")

            log = [
                f"**分析：** {reasoning}",
                f"**搜索角度：** {' · '.join(queries)}",
            ]

            sources, seen = [], set()
            for i, query in enumerate(queries, 1):
                st.write(f"🔎 [{i}/{len(queries)}] 搜索「{query}」...")
                for r in web_search(query, max_results=3):
                    url = r.get("href", "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    title  = r.get("title", "无标题")
                    domain = urlparse(url).netloc
                    st.write(f"   📄 {title[:50]}...")
                    content = fetch_page_content(url, max_chars=3000)
                    if content.startswith("（"):
                        continue
                    kp = extract_key_points(content, question)
                    sources.append({"title": title, "url": url, "domain": domain,
                                    "key_points": kp, "raw_content": content})

            status.update(label=f"✅ 完成，共收集 {len(sources)} 个来源", state="complete", expanded=False)

        st.session_state.sources       = sources
        st.session_state.reasoning_log = log
        st.session_state.phase         = "sources_ready"
        st.rerun()

    # ── 展示爬取内容 ──
    elif st.session_state.phase in ("sources_ready", "gen_report", "report_ready"):
        question = st.session_state.question
        sources  = st.session_state.sources

        st.markdown(f"### 📄 搜索结果：{question}")

        with st.expander("🧠 AI 分析思路", expanded=False):
            for line in st.session_state.reasoning_log:
                st.markdown(f'<div class="file-item" style="padding:10px 14px">{line}</div>', unsafe_allow_html=True)

        st.markdown(f"**共找到 {len(sources)} 个来源**，以下是提炼后的关键内容：")
        st.markdown("")

        if not sources:
            st.warning("未找到有效内容，请尝试更换描述方式。")
        else:
            cols = st.columns(2, gap="medium")
            for i, src in enumerate(sources):
                with cols[i % 2]:
                    st.markdown(f"""
<div class="src-card">
  <div><span class="src-num">{i+1}</span><span class="src-title">{src['title']}</span></div>
  <div class="src-domain">🌐 {src['domain']}</div>
  <div class="src-points">{src['key_points']}</div>
</div>
""", unsafe_allow_html=True)
                    with st.expander(f"原文片段 & 链接"):
                        st.markdown(f"[🔗 访问原页面]({src['url']})")
                        st.caption(src["raw_content"][:500] + "…")

        st.markdown("---")

        # 操作区
        if st.session_state.phase == "sources_ready":
            st.markdown("#### 下一步")
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                if st.button("📝 基于以上内容生成研究报告", type="primary", use_container_width=True):
                    st.session_state.phase = "gen_report"
                    st.rerun()
            with c2:
                if st.button("🔍 重新搜索其他内容", use_container_width=True):
                    st.session_state.phase = "input"
                    st.session_state.sources = []
                    st.rerun()
            with c3:
                if st.button("🏠 首页", use_container_width=True):
                    go_home(); st.rerun()

        elif st.session_state.phase == "gen_report":
            with st.spinner("📝 正在综合所有来源，生成报告..."):
                chat = client.chats.create(
                    model="gemini-3.1-pro-preview",
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
                )
                ctx = "\n\n".join([
                    f"【来源{i+1}】{s['title']}\n{s['url']}\n\n{s['raw_content']}"
                    for i, s in enumerate(sources)
                ])
                report = chat.send_message(
                    f"以下是搜集到的资料：\n\n{ctx}\n\n请针对以下问题生成完整的研究报告：{question}"
                ).text
            st.session_state.report = report
            st.session_state.phase  = "report_ready"
            st.rerun()

        elif st.session_state.phase == "report_ready":
            st.subheader("📋 研究报告")
            st.markdown('<div class="report-wrap">', unsafe_allow_html=True)
            st.markdown(st.session_state.report)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("")
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                if st.button("💾 保存报告", type="primary", use_container_width=True):
                    fp = save_report(question, st.session_state.report)
                    st.success(f"已保存：{fp}")
            with c2:
                if st.button("🔍 继续搜索新内容", use_container_width=True):
                    st.session_state.phase = "input"
                    st.session_state.sources = []
                    st.session_state.report  = ""
                    st.rerun()
            with c3:
                if st.button("🏠 首页", use_container_width=True):
                    go_home(); st.rerun()


# ══════════════════════════════════════════════
# 模式二：直接生成研究报告
# ══════════════════════════════════════════════
elif st.session_state.mode == "direct":

    st.markdown('<div class="breadcrumb">首页 › <span>📝 直接生成研究报告</span></div>', unsafe_allow_html=True)

    # ── 输入 ──
    if st.session_state.phase == "input":
        st.markdown("### 你想研究什么问题？")
        st.caption("AI 会自动搜索多方资料并综合分析，直接生成一份完整的研究报告。")
        st.markdown("")

        with st.form("direct_form"):
            q = st.text_input("研究问题", placeholder="例如：2025 年 AI 大模型行业竞争格局分析",
                              label_visibility="collapsed")
            if st.form_submit_button("📝 生成研究报告", use_container_width=True, type="primary"):
                if q.strip():
                    st.session_state.question = q.strip()
                    st.session_state.phase = "generating"
                    st.rerun()
                else:
                    st.warning("请输入研究问题")

    # ── 生成中 ──
    elif st.session_state.phase == "generating":
        question = st.session_state.question
        st.markdown(f"### 📝 正在生成报告：{question}")

        with st.status("深度研究进行中...", expanded=True) as status:
            st.write("🧠 分析问题...")
            plan    = reason(question)
            queries = plan.get("search_queries") or [question]
            st.write(f"🔎 将从 {len(queries)} 个角度搜索资料")

            sources, seen = [], set()
            for i, query in enumerate(queries, 1):
                st.write(f"🔎 [{i}/{len(queries)}] 搜索「{query}」...")
                for r in web_search(query, max_results=3):
                    url = r.get("href", "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    title   = r.get("title", "无标题")
                    domain  = urlparse(url).netloc
                    st.write(f"   📄 {title[:50]}...")
                    content = fetch_page_content(url, max_chars=3000)
                    if content.startswith("（"):
                        continue
                    sources.append({"title": title, "url": url, "domain": domain,
                                    "raw_content": content})

            st.write(f"✅ 收集完毕，共 {len(sources)} 个来源，正在综合分析...")

            chat = client.chats.create(
                model="gemini-3.1-pro-preview",
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            ctx = "\n\n".join([
                f"【来源{i+1}】{s['title']}\n{s['url']}\n\n{s['raw_content']}"
                for i, s in enumerate(sources)
            ])
            report = chat.send_message(
                f"以下是搜集到的资料：\n\n{ctx}\n\n请针对以下问题生成完整的研究报告：{question}"
            ).text

            status.update(label="✅ 报告生成完成", state="complete", expanded=False)

        st.session_state.sources = sources
        st.session_state.report  = report
        st.session_state.phase   = "done"
        st.rerun()

    # ── 报告展示 ──
    elif st.session_state.phase == "done":
        question = st.session_state.question
        sources  = st.session_state.sources

        st.markdown(f"### 📋 研究报告：{question}")

        # 来源列表（折叠）
        with st.expander(f"📚 参考来源（{len(sources)} 个）", expanded=False):
            for i, s in enumerate(sources):
                st.markdown(f'<span class="tag-blue">{i+1}</span> [{s["title"]}]({s["url"]}) · `{s["domain"]}`', unsafe_allow_html=True)

        st.markdown('<div class="report-wrap">', unsafe_allow_html=True)
        st.markdown(st.session_state.report)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("")

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            if st.button("💾 保存报告", type="primary", use_container_width=True):
                fp = save_report(question, st.session_state.report)
                st.success(f"已保存：{fp}")
        with c2:
            if st.button("📝 重新研究另一个问题", use_container_width=True):
                st.session_state.phase   = "input"
                st.session_state.sources = []
                st.session_state.report  = ""
                st.rerun()
        with c3:
            if st.button("🏠 首页", use_container_width=True):
                go_home(); st.rerun()
