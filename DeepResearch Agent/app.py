"""
DeepResearch Agent — 网页前端
运行方式：streamlit run app.py
"""

import os
import sys
import streamlit as st

# 把当前目录加入路径，这样才能 import main.py 里的函数
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

# 从 main.py 导入核心逻辑函数
from main import (
    reason,
    web_search,
    fetch_page_content,
    fetch_page_full,
    deep_scrape,
    ai_extract,
    save_scraped,
    save_report,
    client,
    SYSTEM_PROMPT,
)
from google.genai import types

# ──────────────────────────────────────────────
# 页面基础配置
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
/* 整体背景 */
.stApp { background-color: #0f1117; }

/* 推理框 */
.reason-box {
    background: #1a1f2e;
    border-left: 3px solid #4f8ef7;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.88rem;
    color: #a0aec0;
}
.reason-box b { color: #4f8ef7; }

/* 步骤标签 */
.step-tag {
    display: inline-block;
    background: #1e3a5f;
    color: #4f8ef7;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.78rem;
    margin-bottom: 6px;
}

/* 保存文件列表 */
.file-item {
    background: #1a1f2e;
    border-radius: 5px;
    padding: 6px 10px;
    margin: 4px 0;
    font-size: 0.82rem;
    color: #a0aec0;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Session State 初始化
# ──────────────────────────────────────────────
if "chat" not in st.session_state:
    st.session_state.chat = client.chats.create(
        model="gemini-3.1-pro-preview",
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
    )

if "messages" not in st.session_state:
    st.session_state.messages = []   # 聊天记录（用于界面显示）

if "last_reply" not in st.session_state:
    st.session_state.last_reply = ""

if "last_question" not in st.session_state:
    st.session_state.last_question = ""

os.makedirs("reports", exist_ok=True)
os.makedirs("scraped", exist_ok=True)


# ──────────────────────────────────────────────
# 核心：带推理的问答（带进度展示）
# ──────────────────────────────────────────────
def ask_with_ui(user_input: str, status_container):
    """
    在 Streamlit 里执行完整的推理→搜索→分析流程，
    把每个步骤的进度实时显示在 status_container 里。
    """
    chat = st.session_state.chat
    log = []  # 推理过程记录，最后渲染成 reason-box

    with status_container:
        # ── 第一步：推理 ──
        with st.spinner("🧠 正在分析问题..."):
            plan = reason(user_input)

        q_type   = plan.get("question_type", "未知")
        need_search = plan.get("need_search", True)
        reasoning   = plan.get("reasoning", "")
        queries     = plan.get("search_queries") or [user_input]
        direct_ans  = plan.get("answer_direct", "")

        log.append(f"<b>问题类型：</b>{q_type}")
        log.append(f"<b>需要搜索：</b>{'是' if need_search else '否'}")
        log.append(f"<b>思路：</b>{reasoning}")
        if need_search:
            log.append(f"<b>搜索策略：</b>{queries}")

        # 不需要搜索 → 直接回答
        if not need_search:
            if direct_ans:
                chat.send_message(f"用户问题：{user_input}\n\n回答：{direct_ans}")
                return direct_ans, log
            else:
                reply = chat.send_message(user_input).text
                return reply, log

        # ── 第二步：多轮搜索 + 抓取 ──
        all_blocks = []
        seen_urls = set()

        for i, query in enumerate(queries, 1):
            with st.spinner(f"🔍 [{i}/{len(queries)}] 搜索「{query}」..."):
                results = web_search(query, max_results=3)

            log.append(f"<b>[搜索{i}]</b> 「{query}」→ 找到 {len(results)} 条")

            for r in results:
                url = r.get("href", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                title   = r.get("title", "无标题")
                summary = r.get("body", "")

                with st.spinner(f"📄 抓取网页..."):
                    full_text = fetch_page_content(url)

                all_blocks.append(
                    f"【标题】{title}\n【网址】{url}\n【摘要】{summary}\n【正文】{full_text}"
                )

        if not all_blocks:
            search_text = "（未找到相关搜索结果）"
        else:
            header = f"以下是从 {len(queries)} 个角度搜索并抓取的网页资料（共 {len(all_blocks)} 条）：\n\n"
            search_text = header + "\n\n" + ("─" * 40 + "\n\n").join(all_blocks)

        log.append(f"<b>共抓取：</b>{len(all_blocks)} 个页面")

        # ── 第三步：深度分析 ──
        with st.spinner("📝 深度分析中..."):
            full_message = f"{search_text}\n\n用户的问题：{user_input}"
            response = chat.send_message(full_message)

        return response.text, log


# ──────────────────────────────────────────────
# 侧边栏
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("🔬 DeepResearch")
    st.caption("多角度搜索 · 全文抓取 · AI 推理")
    st.divider()

    # ── 爬取工具 ──
    st.subheader("🕷️ 网页爬取")
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

    # ── 保存报告 ──
    st.subheader("💾 保存报告")
    if st.button("保存上一条研究报告", use_container_width=True):
        if st.session_state.last_reply:
            fp = save_report(st.session_state.last_question, st.session_state.last_reply)
            st.success(f"已保存: {fp}")
        else:
            st.warning("还没有可以保存的内容")

    st.divider()

    # ── 已保存的文件 ──
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
        st.caption("爬取内容（最近5条）")
        for f in scraped_files:
            st.markdown(f'<div class="file-item">🕷️ {f}</div>', unsafe_allow_html=True)
    else:
        st.caption("暂无爬取记录")

    st.divider()

    # ── 清空对话 ──
    if st.button("清空对话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.chat = client.chats.create(
            model="gemini-3.1-pro-preview",
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
        )
        st.session_state.last_reply = ""
        st.session_state.last_question = ""
        st.rerun()


# ──────────────────────────────────────────────
# 主区域：聊天界面
# ──────────────────────────────────────────────
st.title("深度研究助手")
st.caption("输入研究问题，AI 会先分析、再搜索、再综合回答")

# 渲染历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🔬"):
        # 如果有推理过程，先展示
        if msg.get("reasoning_log"):
            reason_html = "<br>".join(msg["reasoning_log"])
            st.markdown(
                f'<div class="reason-box">'
                f'<div class="step-tag">🧠 AI 推理过程</div><br>'
                f'{reason_html}</div>',
                unsafe_allow_html=True
            )
        st.markdown(msg["content"])

# 输入框
if prompt := st.chat_input("输入你的研究问题..."):

    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # 执行推理 + 搜索 + 回答
    with st.chat_message("assistant", avatar="🔬"):
        status_area = st.empty()
        reply, reasoning_log = ask_with_ui(prompt, status_area)
        status_area.empty()  # 清除进度提示

        # 展示推理过程
        reason_html = "<br>".join(reasoning_log)
        st.markdown(
            f'<div class="reason-box">'
            f'<div class="step-tag">🧠 AI 推理过程</div><br>'
            f'{reason_html}</div>',
            unsafe_allow_html=True
        )
        st.markdown(reply)

    # 记录到历史
    st.session_state.messages.append({
        "role": "assistant",
        "content": reply,
        "reasoning_log": reasoning_log,
    })
    st.session_state.last_question = prompt
    st.session_state.last_reply = reply
