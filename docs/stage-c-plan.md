# 计划：阶段 C - Skills 外置与网页检索能力增强

## Context

阶段 A 已完成结构化 `Observation`、`CitationRegistry`、问题分型和报告编排。当前系统的主要瓶颈不再是“报告怎么写”，而是“工具怎么扩展”：

1. `agent_loop.py` 仍然把工具定义和执行逻辑硬编码在 `TOOLS + _run_tool()` 中。
2. 新增一个工具必须修改主循环文件，扩展成本高，回归面大。
3. 当前网页能力只有单一 `DDGS` 搜索、单页抓取、定点抽取、浅层 RAG，搜索广度与爬取深度都偏弱。
4. 阶段 B 计划引入 Tavily / Brave / SearXNG，多源搜索如果继续塞进 `agent_loop.py`，复杂度会快速失控。

阶段 C 的目标不是做“插件市场”，而是先把运行时工具层改造成项目内可维护的 `skills/` 体系，并顺手把网页搜索/爬取能力做强。

---

## Scope

### In Scope

- 将 `agent_loop.TOOLS` 外置到 `skills/*.py`
- 基于 `report.Observation` 定义统一 `Skill` 接口
- 引入 `SkillRegistry` 负责注册、校验、查找、导出 prompt schema
- 把当前内置工具迁移为 built-in skills
- 新增一批搜索与网页抓取增强型 skills
- 为阶段 B 的多源搜索 provider 留出适配层

### Out of Scope

- 不做 LangGraph / 多 agent state machine
- 不做 Python 沙箱执行
- 不做长期记忆磁盘化
- 不做 Docker 化
- 不做真正的第三方热插拔插件系统

---

## 总体设计

### 目标结构

```text
skills/
├── __init__.py
├── base.py              # Skill / SkillSpec / SkillContext
├── registry.py          # SkillRegistry
├── adapters/
│   ├── search.py        # DDGS / Tavily / Brave / SearXNG 适配层
│   └── fetch.py         # jina / trafilatura / bs4 / future browser adapter
├── search_web.py
├── search_site.py
├── search_recent.py
├── search_news.py
├── search_docs.py
├── search_multi.py
├── scrape_page.py
├── scrape_reader.py
├── scrape_batch.py
├── scrape_deep.py
├── extract_links.py
├── extract_structured.py
├── summarize_text.py
└── rag_retrieve.py
```

### 基本原则

1. `agent_loop.py` 只负责 ReAct 编排，不负责工具实现。
2. 所有执行型 skill 统一返回 `Observation`，而不是裸字符串。
3. `finish` 保留为系统控制动作，不作为普通 skill。
4. 搜索 skill 和爬取 skill 解耦：先“找 URL”，再“抓内容”，再“抽结构”。
5. 多源搜索不直接写死在 skill 中，而是先落到 `skills/adapters/search.py`。

---

## 核心接口

### 1. SkillSpec

用于给 LLM 展示工具 schema，也用于参数校验。

| 字段 | 含义 |
|---|---|
| `name` | skill 名称，唯一键 |
| `desc` | 给 LLM 的描述 |
| `args` | 必填参数名列表 |
| `args_desc` | 参数解释 |
| `category` | `search` / `scrape` / `extract` / `rag` / `utility` |
| `returns_sources` | 是否通常会返回 `sources` |

### 2. SkillContext

运行时上下文，避免每个 skill 自己拼全局状态。

| 字段 | 用途 |
|---|---|
| `question` | 用户原问题 |
| `engine` | 当前引擎模式 |
| `history` | ReAct 已执行步骤 |
| `observations` | 已积累 observations |
| `registry` | `CitationRegistry` |
| `progress_callback` | UI 进度回调 |
| `shared` | 可扩展字典，用于跨 skill 共享中间数据 |

### 3. Skill

```python
class Skill:
    spec: SkillSpec

    def run(self, ctx: SkillContext, args: dict) -> Observation:
        ...
```

---

## 技能清单

### A. 第一批：迁移现有工具

| Skill | 来源 | 作用 | 后端复用 | 优先级 |
|---|---|---|---|---|
| `search_web` | 现 `search` | 全网通用搜索 | `tools.web_search` | P0 |
| `search_site` | 现 `search_site` | 站内搜索 | `tools.web_search` | P0 |
| `scrape_page` | 现 `scrape` | 单页正文抓取 | `tools.fetch_via_jina` | P0 |
| `extract_structured` | 现 `extract` | 单页定向抽取 | `fetch_via_jina + ai_generate_role` | P0 |
| `summarize_text` | 现 `summarize` | 长文本摘要 | `ai_generate_role` | P0 |
| `rag_retrieve` | 现 `rag_retrieve` | 本地文档检索 | `rag.py` | P0 |

### B. 第二批：增强搜索能力

| Skill | 目标 | 第一版实现 | 后续升级 |
|---|---|---|---|
| `search_recent` | 近时效搜索 | `DDGS timelimit` | Tavily / Brave 时间过滤 |
| `search_news` | 新闻导向搜索 | 关键词模板 + `timelimit` | 专门 news provider |
| `search_docs` | 文档/官网搜索 | `site:` + docs/blog/dev heuristics | 多 docs 域名白名单 |
| `search_company` | 公司官方信息搜索 | company + investor relations / newsroom 模板 | IR/年报站点专门路由 |
| `search_multi` | 多源聚合搜索 | 多 adapter 汇总 + URL 去重 | Tavily / Brave / SearXNG 并发 |

### C. 第三批：增强网页抓取能力

| Skill | 目标 | 第一版实现 | 后续升级 |
|---|---|---|---|
| `scrape_reader` | 优先抓取高质量正文 | 明确走 `jina reader` | 支持 reader 参数扩展 |
| `scrape_batch` | 批量抓取多个 URL | 循环抓取并合并 Observation | 并发抓取 |
| `scrape_deep` | 站内深度抓取 | 迁移 `tools.deep_scrape` | BFS 限深、链接质量过滤 |
| `extract_links` | 提取同域可继续抓取的链接 | 基于 `fetch_page_full` | 链接分类和排序 |
| `scrape_pdf` | 网页上 PDF 抓取 | 识别 `.pdf` 链接并下载解析 | 与 `pypdf`、RAG 联动 |

### D. 第四批：检索后处理能力

| Skill | 目标 | 说明 |
|---|---|---|
| `rank_sources` | 对搜索结果做质量排序 | 可按域名、标题匹配度、时效加权 |
| `dedupe_sources` | URL 与内容去重 | 为 `search_multi` 和 `scrape_batch` 服务 |
| `bundle_extract` | 从多页内容中抽统一字段 | 适合榜单/价格/参数汇总 |

---

## 建议的首发 Skill 集合

为了控制阶段 C 的风险，不建议一口气把所有增强能力都做完。首发建议 10 个：

| 批次 | Skill |
|---|---|
| P0 | `search_web` |
| P0 | `search_site` |
| P0 | `scrape_page` |
| P0 | `extract_structured` |
| P0 | `summarize_text` |
| P0 | `rag_retrieve` |
| P1 | `search_recent` |
| P1 | `search_news` |
| P1 | `scrape_batch` |
| P1 | `scrape_deep` |

这样做的好处：

- 能先把现有主流程完整迁移出去
- 能立刻提升“找得更多、抓得更深”的效果
- 不需要等阶段 B 才看到搜索增强收益

---

## 适配层设计

### search adapter

`skills/adapters/search.py` 负责把搜索 provider 统一成同一种结果格式：

```python
{
    "title": str,
    "url": str,
    "snippet": str,
    "source": str,
    "published_at": str | None,
}
```

第一版支持：

| Adapter | 状态 |
|---|---|
| `ddgs_text_search()` | 立刻实现 |
| `ddgs_news_search()` | 可基于查询模板先实现 |
| `multi_search()` | 第一版串行汇总 |

预留：

| Adapter | 阶段 |
|---|---|
| `tavily_search()` | 阶段 B |
| `brave_search()` | 阶段 B |
| `searxng_search()` | 阶段 B |

### fetch adapter

`skills/adapters/fetch.py` 负责把抓取方式统一成：

```python
{
    "url": str,
    "title": str,
    "content": str,
    "links": list[str],
    "fetcher": str,
}
```

第一版支持：

| Adapter | 用途 |
|---|---|
| `fetch_via_reader()` | Jina Reader 优先正文 |
| `fetch_via_trafilatura()` | HTML 正文抽取 |
| `fetch_page_with_links()` | 页面正文 + 同域链接 |

预留：

| Adapter | 阶段 |
|---|---|
| `fetch_via_browser()` | 后续动态渲染页面 |
| `fetch_pdf_content()` | PDF 专用抓取 |

---

## agent_loop 重构方案

### 当前问题

- `TOOLS` 是静态字典
- 参数校验绑死在 `ReActAction`
- `_run_tool()` 是硬编码分支

### 目标改造

| 旧结构 | 新结构 |
|---|---|
| `TOOLS` 字典 | `registry.export_specs()` |
| `_run_tool(name, args)` | `registry.run(name, ctx, args)` |
| `if name == "search": ...` | 每个 skill 自己实现 `run()` |
| `ReActAction.tool in TOOLS` | `ReActAction.tool in registry.names()` |

### `finish` 的处理

`finish` 不进入 `SkillRegistry`，仍保留在 `agent_loop.py` 里作为系统保留动作。

原因：

- 它不是执行型工具，而是流程控制信号
- 避免 skill 层和主循环之间出现责任混乱
- 后面做多 agent 时，`finish` 更适合作为 state transition

---

## 分阶段实施表

| 子阶段 | 目标 | 主要改动 | 产出 | 验收标准 |
|---|---|---|---|---|
| C1 | 定义技能抽象 | `SkillSpec / SkillContext / Skill / SkillRegistry` | `skills/base.py`, `skills/registry.py` | 能注册 skill 并导出给 prompt |
| C2 | 迁移现有工具 | 迁移 6 个现有工具 | `skills/*.py` 首批模块 | ReAct 结果与当前一致 |
| C3 | 搜索增强 | 加入 `search_recent / search_news / search_multi` | 搜索增强 skills | 问“最近/新闻/多角度”时结果更稳定 |
| C4 | 抓取增强 | 加入 `scrape_batch / scrape_deep / extract_links` | 抓取增强 skills | 能批量抓页、站内继续追踪 |
| C5 | 主循环瘦身 | `agent_loop` 全面改为 registry 驱动 | 更薄的 `agent_loop.py` | 新增 skill 不再改主循环 |
| C6 | UI/API 元数据 | 暴露当前 skills 和参数结构 | skill 列表与调试信息 | 可以查看当前加载了哪些 skills |
| C7 | 回归与抽样验收 | 覆盖 ReAct / Planner / 引用 / 报告 | 回归清单 | 阶段 A 能力完全保留 |

---

## 验收样例

### 1. ReAct 搜索增强

问题：

- “过去 30 天里关于 OpenAI 最新模型更新有哪些官方消息？”

期望：

- 优先选择 `search_recent` / `search_news`
- 最终报告引用更多近期来源

### 2. 官网深挖

问题：

- “总结某公司官网产品页里关于定价和套餐的关键信息”

期望：

- 先 `search_company` 或 `search_site`
- 再 `scrape_page` / `scrape_batch`
- 必要时 `extract_structured`

### 3. 站内多页抓取

问题：

- “整理某文档站关于 authentication 的主要文档页面与差异”

期望：

- `search_docs`
- `extract_links`
- `scrape_deep`
- 结果按多页面 observation 归并

---

## 风险与约束

| 风险 | 说明 | 应对 |
|---|---|---|
| skill 粒度过细 | LLM 选择困难，prompt 变长 | 首发只保留 10 个高频 skill |
| 搜索 provider 差异大 | 结果字段不一致 | 先统一 adapter 输出格式 |
| 深度爬取噪音大 | 链接多、正文质量参差不齐 | `extract_links` + 域内过滤 + 限深 |
| skill 间重复能力 | 如 `scrape_page` 和 `scrape_reader` 重叠 | 用 category 和描述拉开边界 |
| 迁移回归面大 | 阶段 A 的引用链路可能被破坏 | 每迁移 1 个 skill 就做端到端回归 |

---

## 推荐执行顺序

1. 先完成 `C1`：`Skill` 基类和 `SkillRegistry`
2. 再完成 `C2`：迁移现有 6 个 tool
3. 接着做 `C3`：`search_recent / search_news / search_multi`
4. 再做 `C4`：`scrape_batch / scrape_deep / extract_links`
5. 最后做 `C5-C7`：主循环瘦身、元数据暴露、回归

---

## 与阶段 B 的关系

阶段 C 不是阶段 B 的替代，而是阶段 B 的前置基础。

| 阶段 | 负责什么 |
|---|---|
| 阶段 C | 把搜索/抓取能力 skill 化、模块化 |
| 阶段 B | 给搜索 skill 补更多 provider 和更强结果源 |

也就是说：

- 现在先把接口和 skill 结构搭起来
- 后面加 Tavily / Brave / SearXNG 时，只需要补 adapter 和少量 skill 配置
- 不需要再次重构 `agent_loop.py`
