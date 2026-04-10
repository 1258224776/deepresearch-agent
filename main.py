"""
main.py — CLI 入口 & 服务启动
企业级模块化结构：
  config.py   — 环境变量、API Key
  prompts.py  — 所有 Prompt 模板
  tools.py    — 爬取、搜索、文件工具
  agent.py    — LLM 调用、推理、分析逻辑
  main.py     — CLI 入口（本文件）
  app.py      — Streamlit Web UI
"""
import os
import re

from agent import ai_generate, reason, ai_extract, chat_with_report, run_research
from prompts import SYSTEM_PROMPT
from tools import (
    fetch_page_content, fetch_page_full, deep_scrape,
    web_search, save_scraped, save_report,
)

os.makedirs("reports", exist_ok=True)
os.makedirs("scraped", exist_ok=True)

last_question = ""
last_reply = ""


# ══════════════════════════════════════════════
# CLI 命令处理
# ══════════════════════════════════════════════

def handle_scrape(command: str) -> None:
    """
    解析 scrape 命令：
      scrape <url>               → 爬取保存完整正文
      scrape <url> <描述>         → 爬取后 AI 提取指定内容
      scrape deep <url>          → 深度爬取（自动跟进子页面）
      scrape deep <url> <描述>    → 深度爬取后 AI 提取
    """
    parts = command[len("scrape"):].strip()
    deep_mode = False
    if parts.startswith("deep "):
        deep_mode = True
        parts = parts[5:].strip()

    match = re.match(r"(https?://\S+)\s*(.*)", parts)
    if not match:
        print("格式错误。用法：scrape <网址> [你想提取的内容]")
        return

    url = match.group(1)
    instruction = match.group(2).strip()

    if deep_mode:
        print(f"\n  开始深度爬取: {url}\n  （最多5页）\n")
        content = deep_scrape(url, max_pages=5)
    else:
        print(f"\n  正在爬取: {url}")
        content, _ = fetch_page_full(url)

    if not content or content.startswith("（"):
        print(f"爬取失败: {content}")
        return

    print(f"  爬取成功，正文共 {len(content)} 字符")

    extracted = ""
    if instruction:
        print(f"  AI 正在提取：{instruction}...")
        extracted = ai_extract(content, instruction)

    filepath = save_scraped(url, content, extracted)
    print(f"\n  已保存到: {filepath}")

    if extracted:
        print(f"\nAI 提取结果：\n{extracted}")


def ask(user_input: str) -> str:
    """完整 CLI 研究流程：推理 → 搜索 → 综合分析。"""
    print("  🧠 正在分析问题...\n")
    plan = reason(user_input)

    print(f"  ┌─ AI 推理过程 {'─'*35}")
    print(f"  │ 问题类型：{plan.get('question_type', '未知')}")
    print(f"  │ 需要搜索：{'是' if plan.get('need_search') else '否'}")
    print(f"  │ 思路：{plan.get('reasoning', '')}")
    if plan.get("need_search") and plan.get("search_queries"):
        print(f"  │ 搜索策略：{plan.get('search_queries')}")
    print(f"  └{'─'*42}\n")

    if not plan.get("need_search"):
        direct = plan.get("answer_direct", "")
        return direct if direct else ai_generate(user_input, system=SYSTEM_PROMPT)

    print("  🔍 开始多角度并行搜索...\n")
    sub_queries = plan.get("search_queries") or [user_input]
    all_blocks, seen_urls = [], set()

    for i, query in enumerate(sub_queries, 1):
        print(f"  [{i}/{len(sub_queries)}] 搜索「{query}」")
        for r in web_search(query, max_results=3):
            url = r.get("href", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = r.get("title", "无标题")
            print(f"    抓取: {url[:70]}...")
            full_text = fetch_page_content(url)
            all_blocks.append(
                f"【标题】{title}\n【网址】{url}\n【正文】{full_text}"
            )

    if not all_blocks:
        search_text = "（未找到相关搜索结果）"
    else:
        header = f"以下是从 {len(sub_queries)} 个角度搜索并抓取的资料（共 {len(all_blocks)} 条）：\n\n"
        search_text = header + "\n\n" + ("─" * 40 + "\n\n").join(all_blocks)

    print("\n  📝 资料收集完毕，正在深度分析...")
    return ai_generate(f"{search_text}\n\n用户的问题：{user_input}", system=SYSTEM_PROMPT)


# ══════════════════════════════════════════════
# CLI 主循环
# ══════════════════════════════════════════════

def main() -> None:
    global last_question, last_reply

    print("=" * 60)
    print("  DeepResearch Agent — 企业级模块化版")
    print()
    print("  输入问题               → 多角度并行搜索研究")
    print("  scrape <网址>          → 爬取并保存网页内容")
    print("  scrape <网址> <描述>    → 爬取后 AI 提取指定内容")
    print("  scrape deep <网址>     → 深度爬取（自动跟进子页面）")
    print("  save                   → 保存上一条研究报告")
    print("  exit                   → 退出")
    print("=" * 60)

    while True:
        user_input = input("\n输入: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("再见！")
            break
        if user_input.lower() == "save":
            if not last_reply:
                print("还没有可以保存的内容，请先提一个问题。")
                continue
            filepath = save_report(last_question, last_reply)
            print(f"报告已保存到: {filepath}")
            continue
        if user_input.lower().startswith("scrape "):
            handle_scrape(user_input)
            continue

        reply = ask(user_input)
        last_question = user_input
        last_reply = reply
        print(f"\n助手:\n{reply}")
        print("\n（输入 save 可保存本次研究报告）")


if __name__ == "__main__":
    main()
