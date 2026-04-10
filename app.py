"""
DeepResearch Agent — v4
深色科技风 UI，内容完整展示
运行方式：streamlit run app.py
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
# 全局样式
# ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif; }

.stApp {
    background: #050a14;
    background-image:
        radial-gradient(ellipse 80% 50% at 50% -10%, rgba(79,70,229,0.12) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 90% 80%, rgba(59,130,246,0.07) 0%, transparent 50%);
}

/* ── 首页模式卡片 ── */
.mode-card {
    background: linear-gradient(135deg, #0f172a 0%, #111827 100%);
    border: 1px solid rgba(99,102,241,0.25);
    border-radius: 16px;
    padding: 36px 30px;
    min-height: 220px;
    transition: all 0.25s ease;
    position: relative;
    overflow: hidden;
}
.mode-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #6366f1, #3b82f6);
    opacity: 0.7;
}
.mode-icon  { font-size: 2.2rem; margin-bottom: 14px; }
.mode-title { font-size: 1.15rem; font-weight: 700; color: #f1f5f9; margin-bottom: 10px; }
.mode-desc  { font-size: 0.87rem; color: #94a3b8; line-height: 1.65; }
.mode-flow  { margin-top: 16px; font-size: 0.78rem; color: #6366f1; letter-spacing: 0.02em; }

/* ── 面包屑 ── */
.breadcrumb {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 0.8rem; color: #64748b;
    margin-bottom: 20px;
}
.breadcrumb span { color: #818cf8; font-weight: 500; }

/* ── 汇总摘要大卡片 ── */
.digest-card {
    background: linear-gradient(135deg, #0f1f3d 0%, #0c1a35 100%);
    border: 1px solid rgba(99,102,241,0.35);
    border-radius: 14px;
    padding: 28px 32px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
}
.digest-card::after {
    content: '';
    position: absolute;
    bottom: 0; right: 0;
    width: 160px; height: 160px;
    background: radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 70%);
    pointer-events: none;
}
.digest-title {
    font-size: 0.75rem; font-weight: 600;
    color: #818cf8; letter-spacing: 0.1em;
    text-transform: uppercase; margin-bottom: 14px;
    display: flex; align-items: center; gap: 8px;
}
.digest-body { font-size: 0.92rem; color: #cbd5e1; line-height: 1.8; }

/* ── 来源卡片 ── */
.src-card {
    background: #0d1520;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 20px 22px;
    margin-bottom: 16px;
    transition: border-color 0.2s;
}
.src-card:hover { border-color: rgba(99,102,241,0.4); }
.src-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 10px; }
.src-num {
    flex-shrink: 0;
    width: 24px; height: 24px;
    background: linear-gradient(135deg, #4f46e5, #3b82f6);
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.72rem; font-weight: 700; color: #fff;
}
.src-title { font-size: 0.93rem; font-weight: 600; color: #e2e8f0; line-height: 1.4; }
.src-meta  { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.src-badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.7rem; font-weight: 500;
}
.badge-high   { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
.badge-medium { background: rgba(245,158,11,0.12); color: #fbbf24; border: 1px solid rgba(245,158,11,0.25); }
.badge-low    { background: rgba(107,114,128,0.15); color: #9ca3af; border: 1px solid rgba(107,114,128,0.25); }
.src-domain   { background: rgba(99,102,241,0.1); color: #818cf8; border: 1px solid rgba(99,102,241,0.2); padding: 2px 9px; border-radius: 20px; font-size: 0.7rem; }
.src-summary  { font-size: 0.87rem; color: #94a3b8; line-height: 1.65; margin-bottom: 12px; padding: 10px 14px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid rgba(99,102,241,0.4); }
.src-points   { font-size: 0.85rem; color: #cbd5e1; line-height: 1.75; white-space: pre-wrap; }

/* ── 报告区 ── */
.report-card {
    background: #0d1520;
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: 14px;
    padding: 32px 36px;
    margin-top: 8px;
    font-size: 0.93rem;
    color: #e2e8f0;
    line-height: 1.85;
}

/* ── 统计徽章 ── */
.stat-row { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.stat-item {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 0.8rem; color: #94a3b8;
}
.stat-item b { color: #a5b4fc; }

/* ── 进度文字 ── */
.progress-line { font-size: 0.83rem; color: #64748b; padding: 4px 0; }
.progress-line.done { color: #34d399; }

/* ── 按钮重写 ── */
div[data-testid="stButton"] > button {
    border-radius: 8px !important;
    font-size: 0.87rem !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%) !important;
    border: none !important;
    color: white !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    box-shadow: 0 4px 20px rgba(99,102,241,0.4) !important;
    transform: translateY(-1px) !important;
}

/* 文件条目 */
.file-item {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 6px;
    padding: 6px 11px;
    margin: 3px 0;
    font-size: 0.8rem; color: #64748b;
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

def go_home():
    for k, v in _defaults.items():
        st.session_state[k] = v

# ──────────────────────────────────────────────
# 侧边栏
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔬 DeepResearch")
    if st.button("← 回首页", use_container_width=True):
        go_home(); st.rerun()
    st.divider()

    st.subheader("🕷️ 手动爬取")
    s_url  = st.text_input("网址", placeholder="https://example.com")
    s_inst = st.text_input("提取内容（可选）")
    s_deep = st.checkbox("深度爬取")
    if st.button("开始爬取", use_container_width=True):
        if s_url:
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
    for f in sorted([f for f in os.listdir("reports") if f.endswith(".md")], reverse=True)[:4]:
        st.markdown(f'<div class="file-item">📄 {f}</div>', unsafe_allow_html=True)
    for f in sorted([f for f in os.listdir("scraped") if f.endswith(".md")], reverse=True)[:4]:
        st.markdown(f'<div class="file-item">🕷️ {f}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════
# 首页
# ══════════════════════════════════════════════
if st.session_state.mode == "home":
    st.markdown("<br>", unsafe_allow_html=True)

    # Logo 区
    st.markdown("""
<div style="text-align:center;padding:20px 0 36px">
  <div style="font-size:2.8rem;margin-bottom:10px">🔬</div>
  <div style="font-size:2rem;font-weight:700;color:#f1f5f9;letter-spacing:-0.02em">DeepResearch Agent</div>
  <div style="color:#64748b;margin-top:8px;font-size:0.95rem">AI 驱动的深度研究工具 · 自动搜索 · 精准提炼 · 专业报告</div>
</div>
""", unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
<div class="mode-card">
  <div class="mode-icon">🔍</div>
  <div class="mode-title">搜索 & 爬取内容</div>
  <div class="mode-desc">输入你想了解的主题，AI 自动从多个来源搜索、抓取并深度提炼内容，将完整信息呈现给你，你再决定是否生成研究报告。</div>
  <div class="mode-flow">① 输入主题 → ② 多角度搜索爬取 → ③ 查看完整内容摘要 → ④ 可选生成报告</div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("进入搜索爬取 →", use_container_width=True, type="primary", key="b_scrape"):
            st.session_state.mode = "scrape"; st.session_state.phase = "input"; st.rerun()

    with col2:
        st.markdown("""
<div class="mode-card">
  <div class="mode-icon">📝</div>
  <div class="mode-title">直接生成研究报告</div>
  <div class="mode-desc">输入研究问题，AI 自动搜索多方资料并综合分析，直接输出一份结构完整、有数据支撑的深度研究报告，可保存为本地文件。</div>
  <div class="mode-flow">① 输入问题 → ② AI 搜索综合分析 → ③ 输出完整报告 → ④ 可保存</div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("进入报告生成 →", use_container_width=True, type="primary", key="b_report"):
            st.session_state.mode = "direct"; st.session_state.phase = "input"; st.rerun()


# ══════════════════════════════════════════════
# 模式一：搜索爬取
# ══════════════════════════════════════════════
elif st.session_state.mode == "scrape":

    st.markdown('<div class="breadcrumb">🏠 首页 › <span>🔍 搜索 & 爬取内容</span></div>', unsafe_allow_html=True)

    # ── 输入 ──
    if st.session_state.phase == "input":
        st.markdown("## 你想搜索什么内容？")
        st.markdown("<p style='color:#64748b;margin-bottom:24px'>描述你感兴趣的主题，AI 会自动规划搜索策略，抓取多个网页并提炼完整内容。</p>", unsafe_allow_html=True)

        with st.form("scrape_form"):
            q = st.text_input("", placeholder="例如：特斯拉 2025 年最新车型发布信息")
            if st.form_submit_button("🔍 开始搜索爬取", use_container_width=True, type="primary"):
                if q.strip():
                    st.session_state.question = q.strip()
                    st.session_state.phase = "searching"
                    st.rerun()

    # ── 搜索爬取中 ──
    elif st.session_state.phase == "searching":
        question = st.session_state.question
        st.markdown(f"## 🔍 正在研究：{question}")

        prog = st.empty()

        with prog.container():
            with st.status("深度搜索爬取中...", expanded=True) as status:

                st.write("🧠 分析主题，规划搜索角度...")
                plan    = reason(question)
                queries = plan.get("search_queries") or [question]
                # 最多取前 4 个角度，避免时间太长
                queries = queries[:4]

                log = [
                    f"**分析：** {plan.get('reasoning', '')}",
                    f"**搜索角度（{len(queries)} 个）：** {' · '.join(queries)}",
                ]
                st.write(f"📋 将从 **{len(queries)}** 个角度搜索，每角度取 **5** 条结果")

                sources, seen = [], set()
                for i, query in enumerate(queries, 1):
                    st.write(f"🔎 [{i}/{len(queries)}] 搜索「{query}」...")
                    results = web_search(query, max_results=5)
                    st.write(f"   找到 {len(results)} 条，开始爬取...")
                    for r in results:
                        url = r.get("href", "")
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        title  = r.get("title", "无标题")
                        domain = urlparse(url).netloc
                        st.write(f"   📄 {title[:48]}...")
                        content = fetch_page_content(url)
                        if "抓取失败" in content or len(content) < 100:
                            continue
                        info = summarize_source(content, question, title)
                        sources.append({
                            "title":       title,
                            "url":         url,
                            "domain":      domain,
                            "summary":     info.get("summary", ""),
                            "key_points":  info.get("key_points", ""),
                            "relevance":   info.get("relevance", "medium"),
                            "raw_content": content,
                        })

                st.write(f"✅ 爬取完毕，共 {len(sources)} 个有效来源，正在汇总...")
                digest = compile_digest(sources, question) if sources else ""

                status.update(label=f"✅ 完成！{len(sources)} 个来源 · 内容已提炼", state="complete", expanded=False)

        st.session_state.sources       = sources
        st.session_state.reasoning_log = log
        st.session_state.digest        = digest
        st.session_state.phase         = "sources_ready"
        st.rerun()

    # ── 展示内容 ──
    elif st.session_state.phase in ("sources_ready", "gen_report", "report_ready"):
        question = st.session_state.question
        sources  = st.session_state.sources
        digest   = st.session_state.digest

        # 标题 + 统计
        st.markdown(f"## 📄 {question}")

        high_cnt = sum(1 for s in sources if s.get("relevance") == "high")
        st.markdown(f"""
<div class="stat-row">
  <div class="stat-item">📚 来源数 <b>{len(sources)}</b></div>
  <div class="stat-item">⭐ 高相关 <b>{high_cnt}</b></div>
  <div class="stat-item">🔍 搜索角度 <b>{len(st.session_state.reasoning_log and st.session_state.reasoning_log[-1].split('（')[1].split('）')[0] if '（' in (st.session_state.reasoning_log or [''])[0] else '—')}</b></div>
</div>
""", unsafe_allow_html=True)

        # 推理折叠
        with st.expander("🧠 AI 分析思路", expanded=False):
            for line in st.session_state.reasoning_log:
                st.markdown(f"<p style='color:#94a3b8;font-size:0.87rem;padding:4px 0'>{line}</p>", unsafe_allow_html=True)

        # 汇总摘要大卡片
        if digest:
            st.markdown(f"""
<div class="digest-card">
  <div class="digest-title">✦ 综合内容摘要</div>
  <div class="digest-body">{digest.replace(chr(10), '<br>')}</div>
</div>
""", unsafe_allow_html=True)

        # 来源卡片
        st.markdown(f"### 📚 各来源详细内容（{len(sources)} 个）")

        if not sources:
            st.warning("未找到有效内容，请尝试换一个描述方式。")
        else:
            # 按相关度排序
            order = {"high": 0, "medium": 1, "low": 2}
            sorted_sources = sorted(sources, key=lambda s: order.get(s.get("relevance", "medium"), 1))

            cols = st.columns(2, gap="medium")
            for i, src in enumerate(sorted_sources):
                rel    = src.get("relevance", "medium")
                badge  = f'<span class="src-badge badge-{rel}">{RELEVANCE_LABEL[rel]}</span>'
                domain_badge = f'<span class="src-domain">🌐 {src["domain"]}</span>'

                with cols[i % 2]:
                    st.markdown(f"""
<div class="src-card">
  <div class="src-header">
    <div class="src-num">{i+1}</div>
    <div class="src-title">{src['title']}</div>
  </div>
  <div class="src-meta">{badge}{domain_badge}</div>
  <div class="src-summary">{src['summary']}</div>
  <div class="src-points">{src['key_points']}</div>
</div>
""", unsafe_allow_html=True)
                    with st.expander("📖 原文片段 & 链接"):
                        st.markdown(f"[🔗 访问原页面]({src['url']})")
                        st.code(src["raw_content"][:800], language=None)

        st.markdown("---")

        # 操作区
        if st.session_state.phase == "sources_ready":
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                if st.button("📝 基于以上内容生成研究报告", type="primary", use_container_width=True):
                    st.session_state.phase = "gen_report"; st.rerun()
            with c2:
                if st.button("🔍 重新搜索", use_container_width=True):
                    for k in ["sources", "digest", "reasoning_log", "report"]:
                        st.session_state[k] = [] if k != "digest" and k != "report" else ""
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
            st.markdown("### 📋 研究报告")
            st.markdown('<div class="report-card">', unsafe_allow_html=True)
            st.markdown(st.session_state.report)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("")
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                if st.button("💾 保存报告", type="primary", use_container_width=True):
                    fp = save_report(question, st.session_state.report)
                    st.success(f"已保存：{fp}")
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

    st.markdown('<div class="breadcrumb">🏠 首页 › <span>📝 直接生成研究报告</span></div>', unsafe_allow_html=True)

    if st.session_state.phase == "input":
        st.markdown("## 你想研究什么问题？")
        st.markdown("<p style='color:#64748b;margin-bottom:24px'>AI 会自动搜索多方资料、综合分析，直接生成一份完整的研究报告。</p>", unsafe_allow_html=True)

        with st.form("direct_form"):
            q = st.text_input("", placeholder="例如：2025 年 AI 大模型行业竞争格局分析")
            if st.form_submit_button("📝 生成研究报告", use_container_width=True, type="primary"):
                if q.strip():
                    st.session_state.question = q.strip()
                    st.session_state.phase    = "generating"
                    st.rerun()

    elif st.session_state.phase == "generating":
        question = st.session_state.question
        st.markdown(f"## 📝 正在生成报告：{question}")

        with st.status("深度研究进行中...", expanded=True) as status:
            st.write("🧠 分析问题...")
            plan    = reason(question)
            queries = (plan.get("search_queries") or [question])[:4]
            st.write(f"🔎 将从 {len(queries)} 个角度搜索")

            sources, seen = [], set()
            for i, query in enumerate(queries, 1):
                st.write(f"🔎 [{i}/{len(queries)}] 搜索「{query}」...")
                for r in web_search(query, max_results=5):
                    url = r.get("href", "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    title   = r.get("title", "无标题")
                    domain  = urlparse(url).netloc
                    st.write(f"   📄 {title[:48]}...")
                    content = fetch_page_content(url)
                    if "抓取失败" in content or len(content) < 100:
                        continue
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

        st.markdown(f"## 📋 研究报告：{question}")

        with st.expander(f"📚 参考来源（{len(sources)} 个）", expanded=False):
            for i, s in enumerate(sources):
                st.markdown(
                    f'<span style="background:rgba(99,102,241,0.15);color:#818cf8;border-radius:4px;padding:1px 7px;font-size:0.72rem">{i+1}</span> '
                    f'[{s["title"]}]({s["url"]}) `{s["domain"]}`',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="report-card">', unsafe_allow_html=True)
        st.markdown(st.session_state.report)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("")

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            if st.button("💾 保存报告", type="primary", use_container_width=True):
                fp = save_report(question, st.session_state.report)
                st.success(f"已保存：{fp}")
        with c2:
            if st.button("📝 重新研究", use_container_width=True):
                st.session_state.phase = "input"
                st.session_state.report = ""
                st.session_state.sources = []
                st.rerun()
        with c3:
            if st.button("🏠 首页", use_container_width=True):
                go_home(); st.rerun()
