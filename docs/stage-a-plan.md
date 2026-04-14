# 计划：阶段 A —— 报告质量与来源追踪升级

## Context

用户反馈指出当前项目「生成报告内容参考不定 / 更科学的内容汇总 / 生成时智能调整」三个痛点。根因是：

1. **无来源追踪**：`agent_loop.py` 的 `_run_tool()` 返回 `str`，观察内容与它来自哪个 URL 脱钩。最终 report 里的每一条事实都无法溯源，用户难判断可信度。
2. **报告模板同质化**：无论用户问的是财报、对比题、趋势题还是列表题，都走同一个 `prompt_react_system` + `finish` 接管。没有按问题类型定制结构。
3. **汇总方式粗糙**：`finish` 的 `answer` 参数直接由 LLM 生成完整 Markdown，超 `max_steps` 的 fallback 也只是把所有 observation 拼接喂给 analyst，缺少主题聚类 / 关键事实提取 / 结构化编排。

阶段 A 的目标：让每条事实可溯源、让报告结构按问题类型自适应、让汇总从"拼接"变成"编排"。完成后阶段 C（skills 外置）将基于 Observation 的结构化接口落地，因此 A 先行不可倒序。

---

## 实现方案

### 总体思路

新建 `report.py` 作为独立的报告生成层（类似 `rag.py` / `tools.py` 的定位）。`agent_loop.py` 与 `agent_planner.py` 只负责跑调研循环，把累积的结构化观察交给 `report.py` 编排成最终报告。`prompts.py` 新增 9 个按问题类型分化的模板。

### 关键文件

| 文件 | 变动 | 说明 |
|------|------|------|
| `d:\agent-one\report.py` | **新建** | 本阶段核心：`Observation` / `CitationRegistry` / `classify_question` / `compose_report` |
| `d:\agent-one\agent_loop.py` | 改造 | `_run_tool` 返回 `Observation`；`run_agent` 持有 `CitationRegistry`；`finish` 走 `compose_report` |
| `d:\agent-one\agent_planner.py` | 改造 | Reporter 阶段改调 `compose_report`；Memory 也存结构化 Observation |
| `d:\agent-one\prompts.py` | 新增 10 个函数 | 1 个分类 prompt + 9 个报告模板 |
| `d:\agent-one\app.py` | 小改 | 运行阶段展示参考来源表；章节化显示 |
| `d:\agent-one\tools.py` | 只读复用 | `web_search` / `fetch_via_jina` 等已返回 URL |

---

### 1. report.py 详细结构

#### 1.1 数据模型

```python
class Source(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""          # 原文摘要（用于 LLM 引用核对）

class Observation(BaseModel):
    content: str               # 工具返回的文本（与现有 str 接口兼容）
    sources: list[Source] = [] # 这条观察依赖的 URL 列表
    tool: str                  # 产出此观察的工具名
    args: dict                 # 调用参数

class CitationRegistry:
    """自动编号引用 → 末尾参考来源 Markdown 表。"""
    def add(self, source: Source) -> int: ...  # 返回 [1] [2] …
    def for_prompt(self) -> str: ...           # "[1] 标题 URL\n[2] …"（给 LLM）
    def as_refs_md(self) -> str: ...           # "## 参考来源\n1. …"（给最终报告）
```

#### 1.2 问题类型分类器

```python
class QuestionType(str, Enum):
    # 基础
    FACTUAL    = "factual"    # 单一事实："X 的 CEO 是谁"
    # 信息组织
    LIST       = "list"       # 列表："有哪些"、"top 10"
    COMPARE    = "compare"    # 对比："A 和 B 的区别"
    # 时间与变化
    TREND      = "trend"      # 趋势："近 3 年的变化"
    TIMELINE   = "timeline"   # 时间线："事件的发展过程"
    # 分析与推理
    ANALYSIS   = "analysis"   # 原因/深度分析："为什么 X 会 Y"
    # 决策与建议
    RECOMMEND  = "recommend"  # 推荐/建议："哪款最值得买"
    # 专业领域
    FINANCIAL  = "financial"  # 财务：营收、利润、估值
    # 兜底
    RESEARCH   = "research"   # 默认：深度综合调研

def classify_question(question: str, engine: str = "") -> QuestionType:
    """轻量级 LLM 分类，一次调用 worker 模型，只输出 enum 名。
    解析失败默认 RESEARCH。"""
```

#### 1.3 报告编排器（核心）

```python
def compose_report(
    question: str,
    history: list[Observation],
    registry: CitationRegistry,
    engine: str = "",
    question_type: QuestionType | None = None,
) -> str:
    """
    工作流程：
      1. 若 question_type 为 None，先调 classify_question
      2. 按类型选对应 prompt 模板（prompt_report_*）
      3. 组装上下文：所有 observation 的 content + 引用编号
      4. 调 analyst 角色 LLM（对 financial/compare 优先选更强模型）
      5. 末尾拼接 registry.as_refs_md()
    """
```

---

### 2. prompts.py 新增

- `prompt_classify_question(question)` — 输出单 JSON `{"type": "compare"}`。
- 9 个报告模板：`prompt_report_factual / list / compare / trend / timeline / analysis / recommend / financial / research`

**共享约束**（所有模板）：
- 正文每条事实后必须带 `[1][2]` 编号
- 结尾一段 `## 关键洞察` 列 2-3 条

**分型约束**：

| 类型 | 结构要求 |
|------|----------|
| `factual` | 1-2 段直接回答 + 少量引用，≤200 字 |
| `list` | 条目化，每条 3-5 个属性，可用表格 |
| `compare` | **强制** Markdown 对比表格（维度 × 对象） |
| `trend` | 年份/阶段表格 + 变化文字描述 |
| `timeline` | 时间线格式（`- 日期：事件` 列表或表格），按时间顺序 |
| `analysis` | 论点 → 论据 → 结论 的三段式，每个论点独立小节 |
| `recommend` | 推荐列表，每项含「理由 + 适用场景 + 优缺点」 |
| `financial` | **强制** 财务表格（科目 × 期间），关键指标用 **加粗** |
| `research` | 章节化综合报告（背景 / 现状 / 关键发现 / 展望） |

---

### 3. agent_loop.py 改造点

改动以**最小侵入**为原则：

1. **`_run_tool` 返回值**：从 `str` 改为 `Observation`。内部把 URL 塞进 `sources`：
   - `search` / `search_site` → 每条 result 的 `href` 进 sources
   - `scrape` / `extract` → 把传入的 `url` 进 sources
   - `rag_retrieve` → 用 chunk 的 `meta.filename` 作 `title`，`url=file://…`
   - `summarize` → 继承上一步的 sources（由调用方传入）
2. **`run_agent` 新增字段**：
   - `registry: CitationRegistry`（贯穿整轮循环）
   - `history: list[Observation]`（原为 `list[dict]`，用 `.model_dump()` 向后兼容返回给 app）
3. **`finish` 不再直接返回 `args["answer"]`**：
   - 改为捕获信号 → 调 `report.compose_report(question, history, registry, engine)` → 返回富报告
   - 保留向后兼容：若 LLM 在 `args` 里给了 `answer` 且用户关闭编排器（`compose=False`），走原路径
4. **超 max_steps 的 fallback**：也改走 `compose_report`。

### 4. agent_planner.py 改造点

- `SubResult` 增加 `observations: list[Observation]` 字段
- `_execute_sub` 把每个子问题跑出来的 observation 列表返回（不只是 `answer` 字符串）
- `_synthesize` 改为 `report.compose_report(question, all_obs, shared_registry, engine)`
- `PlannerMemory.as_context()` 可额外包含已有的 [1][2] 编号，让后续子问题的 LLM 学会引用已登记的来源

### 5. app.py 展示层

运行阶段下方新增一个 `st.expander("📚 参考来源", expanded=False)`，列 `registry.as_refs_md()`。每步 observation 的展开面板里多一行 `**来源**：[1][2]`。

---

## 复用 / 已存在的工具

- `tools.web_search()` 已返回 `{href, title, body}`，直接映射到 `Source`
- `tools.fetch_via_jina()` 的输入参数就是 URL，直接作 `Source.url`
- `agent.ai_generate_role()` + `agent.extract_json()` 用于分类器与编排器 LLM 调用
- `config.ENGINE_PRESETS` 已区分 orchestrator/worker/analyst 角色，新模板按问题类型选不同角色：
  - `financial` / `compare` / `analysis` → **orchestrator**（最强推理）
  - `factual` / `list` → **worker**（快即可）
  - `trend` / `timeline` / `recommend` / `research` → **analyst**

---

## 验证方案

1. **单元级**：
   - `python -c "from report import classify_question; print(classify_question('特斯拉和比亚迪 2024 年谁赚得多？'))"` → 期望 `COMPARE`
   - `python -c "from report import CitationRegistry, Source; r=CitationRegistry(); print(r.add(Source(url='a', title='x'))); print(r.as_refs_md())"`
2. **ReAct 端到端**：`streamlit run app.py` → Agent 自主 → 问「小米 SU7 在 2024 年的销量表现如何？」→ 验收：
   - 最终报告每个数字后有 `[数字]` 标注
   - 「参考来源」面板有编号完整的 URL 列表
   - 无 URL 出现在正文里（都被替换成编号）
3. **深度规划端到端**：同上，选「🗺️ 深度规划」→ 问「比较特斯拉和比亚迪 2024 年的市场策略」→ 验收：
   - 每个子问题的观察都贡献到全局 registry
   - 综合报告中 compare 表格带 `[1][2]` 引用
4. **类型分化抽样**：
   - Factual：「ChatGPT 的开发公司是谁」→ 短答 + 1-2 条引用
   - List：「2024 年国产 SUV 销量 top 10」→ 表格 10 行 + 合并引用
   - Trend：「特斯拉近 5 年营收变化」→ 有趋势图文字描述 + 年份表格
5. **回归**：现有 3 种老模式（探索 / 直接研究 / 数据清洗）不受影响（`report.py` 只被 agent_loop/agent_planner 引用）

---

## 后续阶段概览（仅列题目，不展开）

- **阶段 C（skills 外置）**：把 `agent_loop.TOOLS` 外置为 `skills/*.py`，基于阶段 A 的 `Observation` 接口定义 `Skill` 基类
- **阶段 D（多 agent + memory + 沙箱）**：引入 LangGraph 式 state machine；Coordinator/Researcher/Coder/Reporter；faiss 磁盘化长期记忆；Python 子进程沙箱
- **阶段 E（多 RAG + docker）**：`rag.py` 支持多 collection 持久化；Dockerfile + docker-compose
- **阶段 B（多源搜索）**：穿插做，补 Tavily/Brave/SearXNG；扩充免费模型到 providers.yaml

阶段 C-E 的详细计划在 A 落地后另开新 plan。
