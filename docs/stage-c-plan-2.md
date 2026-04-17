# 计划：阶段 C（第二版）- Skill 路由治理与 DeerFlow 式能力管理

## 背景

第一版阶段 C 已经完成了 `skills/` 外置、`SkillRegistry`、适配层、网页搜索/抓取增强，以及路由预选的第一轮落地。当前项目已经具备这些能力：

- 执行型 `Skill` 抽象：`SkillSpec / SkillContext / SkillRegistry`
- 内置技能注册与元数据导出
- `route_entry()` 入口预路由：按 `QuestionType` 生成白名单和起手 skill
- `suggest_next_step()` 步间提示
- `check_loop()` 重复调用/无新来源纠偏
- UI / API 已能看到 skill catalog

与 DeerFlow 对照后，可以确认一个关键判断：

- **我们不应该把当前 `skills/*.py` 改造成 DeerFlow 那种纯 `SKILL.md` prompt 包**
- **我们应该保留“执行型 skill”模型，同时补上 DeerFlow 擅长的“技能治理层”**

换句话说，第二版阶段 C 的目标不是“继续堆更多 skill”，而是让当前 skill 系统具备：

1. 更强的启停与过滤能力
2. 更细的按模式/按 agent/profile 暴露能力
3. 更干净的 prompt 注入方式
4. 更稳定、可解释的路由决策


## DeerFlow 对照结论

| 维度 | 当前项目 | DeerFlow | 第二版策略 |
|---|---|---|---|
| skill 本质 | 可执行动作 | 结构化 prompt 包 | 保留当前执行型 skill |
| skill 发现 | 代码注册 | 扫描 `SKILL.md` | 保留代码注册 |
| skill 启停 | 暂无配置化启停 | `extensions_config.json` 控制 enabled | 借鉴：加 skill state config |
| per-agent 过滤 | 暂无 | agent config 指定 skill allowlist | 借鉴：加 profile / mode 过滤 |
| prompt 注入 | 直接把 schema 全喂给模型 | 先注入技能目录，再按需读 skill | 借鉴：补“技能附录/提示块”，但不放弃函数 schema |
| skill 管理 API | 只读 `/skills` | list / get / enable / disable / install | 借鉴：先补 enable/disable 与 route preview |
| routing | 已有入口预路由 + loop guard | 更偏 metadata + 自主加载 | 保留当前显式路由，别退回纯 prompt 选择 |


## 第二版目标

### In Scope

- 给 skill 增加“启用状态”和“profile 可见性”
- 让路由结果由三层交集决定：
  - `enabled skills`
  - `profile allowlist`
  - `question route shortlist`
- 引入轻量“技能附录”注入，减少只靠长 schema 提示
- 增加 skill route preview / skill state 的 API 能力
- 增加路由测试和回归样例

### Out of Scope

- 不把 Python skill 改写成 DeerFlow 风格 `SKILL.md` 主体
- 不做 remote skill marketplace
- 不做运行时安装 `.skill` 压缩包
- 不做多 agent / sub-agent 编排（那是阶段 D）


## 设计原则

1. **执行和治理分层**
   运行时动作继续由 `skills/*.py` 执行；启停、过滤、提示、可见性由治理层处理。

2. **路由不只靠 prompt**
   继续保留 `route_entry / suggest_next_step / check_loop` 这类显式控制，不回退到“模型自己在 14 个 skill 里猜”。

3. **借 DeerFlow 的治理，不照抄 DeerFlow 的 skill 形态**
   DeerFlow 的强项是 enabled state、profile、渐进加载、管理接口；这些值得借。

4. **系统提示做减法**
   schema 仍然保留，但只给当前会话真正可见的 skill；额外 guidance 也只注入 shortlist。


## 当前实现现状（已完成）

| 模块 | 已有能力 | 文件 |
|---|---|---|
| 技能抽象 | `SkillSpec / SkillContext / SkillRegistry` | `skills/base.py`, `skills/registry.py` |
| 执行型技能 | 搜索、抓取、抽取、RAG、总结等 | `skills/*.py` |
| 路由第一版 | 问题分类后白名单 + 起手建议 | `skills/router.py`, `agent_loop.py` |
| 路由防抖 | 重复动作拦截、无新来源强制收敛 | `skills/router.py` |
| Prompt 白名单 | 只把 shortlisted skill 喂给 LLM | `prompts.py`, `agent_loop.py` |
| 元数据暴露 | `/skills` API + 侧边栏 | `api.py`, 旧 Web UI（已移除） |


## 第二版总体方案

### 1. 增加 Skill State Config

借鉴 DeerFlow 的 `extensions_config.json` 思路，为当前项目增加一个轻量 skill 配置文件，例如：

- `skills_config.yaml`

建议结构：

```yaml
skills:
  search:
    enabled: true
  search_news:
    enabled: true
  scrape_deep:
    enabled: true
  rag_retrieve:
    enabled: true
```

作用：

- 全局关闭某个 skill，而不需要改代码
- 用于 API/UI 展示 skill 当前状态
- 为后续 profile 与 route preview 提供统一数据源

建议新增：

- `skills/config.py`


### 2. 增加 Skill Profile / Mode Filtering

借鉴 DeerFlow 的 per-agent `skills` allowlist，但更贴合当前项目，先做 **profile** 而不是 custom agent。

建议定义：

- `react_default`
- `planner`
- `api_safe`
- `web_research_heavy`

示例：

```yaml
profiles:
  react_default:
    allow:
      - search
      - search_multi
      - search_docs
      - search_company
      - search_recent
      - search_news
      - search_site
      - scrape
      - scrape_batch
      - scrape_deep
      - extract_links
      - extract
      - summarize
      - rag_retrieve

  planner:
    allow:
      - search
      - search_multi
      - search_docs
      - search_company
      - search_recent
      - search_news
      - scrape
      - extract
      - summarize
      - rag_retrieve
```

运行时可见 skill 由三层求交集：

```text
visible_skills
= enabled_skills
∩ profile_allowed_skills
∩ route_entry_shortlist
```

建议新增：

- `skills/profiles.py`


### 3. 路由升级为 RouteDecision

当前 `EntryRoute` 已经能返回：

- `allowed_skills`
- `starter`

第二版建议升级成更完整的 `RouteDecision`：

```python
class RouteDecision:
    qtype: QuestionType
    allowed: list[str]
    preferred: list[str]
    discouraged: list[str]
    starter: str
    reasons: list[str]
```

这样做的好处：

- prompt 可以明确写“优先考虑 X / 尽量避免 Y”
- API 可以直接返回 route preview
- UI 可以展示“这次为什么只开放这些 skill”

建议在 `skills/router.py` 中新增：

- `build_route_decision(...)`
- `preview_route(...)`

并保留现有：

- `route_entry()`
- `suggest_next_step()`
- `check_loop()`


### 4. 加一层 Skill Guidance Appendix

这是 DeerFlow 最值得借的点之一：**不是只有函数 schema，还要有“什么时候用/别什么时候用”的说明。**

但我们不采用 DeerFlow 的完整 `SKILL.md` 机制，而是做一个轻量版：

- 每个执行型 skill 可以提供一个很短的 guidance 文本
- 只在当前 shortlist 中注入
- guidance 不超过 3-5 行

建议形式有两种，二选一：

#### 方案 A：直接写在 `SkillSpec`

新增字段：

- `when_to_use`
- `when_not_to_use`
- `next_step_hint`

#### 方案 B：单独放到 `skills/guidance.py`

例如：

```python
SKILL_GUIDANCE = {
    "search_docs": {
        "when": "官方文档、API、guide、manual",
        "avoid": "新闻或财报类问题",
        "next": "通常下一步接 extract_links 或 scrape_deep",
    }
}
```

推荐先用 **方案 B**，不污染 `SkillSpec` 主体。


### 5. 增加 Skill Route Preview API

当前 `/skills` 只能列目录。第二版建议再补一个只读调试接口：

- `POST /skills/route-preview`

请求：

```json
{
  "question": "OpenAI Responses API background mode 怎么用？",
  "profile": "react_default"
}
```

返回：

```json
{
  "question_type": "research",
  "profile": "react_default",
  "allowed_skills": ["search_docs", "extract_links", "scrape_deep", "extract", "summarize"],
  "preferred_skills": ["search_docs", "extract_links"],
  "starter": "search_docs",
  "reasons": [
    "命中 docs/API 类问题",
    "profile 允许 docs 系技能",
    "未开放公司/新闻类首选技能"
  ]
}
```

这个接口会极大降低调试成本。


### 6. UI 增加 Route Debug 面板

在旧 Web UI（已移除）中增加一个只读调试面板，展示：

- 当前 profile
- 当前问题分类
- 当前 allowed skills
- starter
- route reasons

这一步的意义和 DeerFlow 的 `/api/skills` 类似：

- 让 skill 不是“黑盒”
- 让路由不是“猜”


## 建议目录增量

```text
skills/
├── base.py
├── registry.py
├── router.py
├── config.py          # 新增：skill enabled state
├── profiles.py        # 新增：mode/profile allowlist
├── guidance.py        # 新增：短 guidance 附录
└── ...

docs/
├── stage-c-plan.md
└── stage-c-plan-2.md
```


## 实施步骤

| 子阶段 | 目标 | 主要改动 | 涉及文件 | 验收标准 |
|---|---|---|---|---|
| C8 | Skill 状态配置化 | 新增 `skills_config.yaml` + `skills/config.py` | `skills/config.py`, `skills/registry.py` | 能全局启用/停用某个 skill |
| C9 | Profile 过滤 | 定义 `react_default/planner/api_safe` | `skills/profiles.py`, `agent_loop.py` | 可见 skill = enabled ∩ profile ∩ route |
| C10 | Router v2 | 从 `EntryRoute` 扩成 `RouteDecision` | `skills/router.py`, `agent_loop.py` | 返回 allowed / preferred / starter / reasons |
| C11 | Guidance 附录 | 为 shortlisted skill 注入短说明 | `skills/guidance.py`, `prompts.py` | prompt 里不只剩 schema，还有精简使用建议 |
| C12 | 调试接口 | 新增 `/skills/route-preview` | `api.py`, `openapi.yaml` | 可用 HTTP 预览路由结果 |
| C13 | UI 可解释性 | 展示 route debug 面板 | 旧 Web UI（已移除） | 页面里能看见分类、starter、候选 skill |
| C14 | 测试与回归 | 增加路由快照测试与回归问题集 | `tests/` 或本地验证脚本 | 常见问题命中预期 skill |


## 优先级建议

### P0：先做

1. `C8` Skill 状态配置化
2. `C9` Profile 过滤
3. `C10` Router v2

原因：

- 这三步完成后，路由体系就不再依赖硬编码全集暴露
- 也是 DeerFlow 最值得借的部分

### P1：紧接着做

4. `C11` Guidance 附录
5. `C12` Route Preview API
6. `C13` UI Route Debug

原因：

- 这些会显著提高系统“可解释性”和调试效率

### P2：最后做

7. `C14` 路由测试集

原因：

- 测试应在路由结构稳定后补，不然维护成本高


## 第二版重点样例

### 样例 1：文档题

问题：

`OpenAI Responses API background mode 怎么用？`

理想 route：

- `question_type = research`
- `preferred = ["search_docs", "extract_links"]`
- `starter = "search_docs"`
- 允许：
  - `search_docs`
  - `extract_links`
  - `scrape_deep`
  - `extract`
  - `summarize`
  - `finish`

### 样例 2：公司研究

问题：

`英伟达 2025 财报和投资者关系更新`

理想 route：

- `question_type = financial`
- `preferred = ["search_company", "search_recent"]`
- `starter = "search_company"`

### 样例 3：站点入口页

问题：

`帮我研究 https://docs.langchain.com 的核心能力`

理想 route：

- 起手不一定是 `search`
- 优先：
  - `extract_links`
  - `scrape_deep`
  - `extract`


## 风险与控制

| 风险 | 说明 | 对策 |
|---|---|---|
| 配置层过重 | 还没到 DeerFlow 那种平台规模，过早做复杂安装系统会过度设计 | 第二版只做 enabled/profile，不做 marketplace |
| profile 与 route 冲突 | 某题型推荐 skill 被 profile 禁掉 | `RouteDecision.reasons` 必须解释冲突来源 |
| prompt 还是过长 | guidance 加太多反而污染上下文 | guidance 仅注入 shortlisted skill，且每个 skill 3-5 行上限 |
| 路由过硬 | 显式路由把模型卡死 | 保留 `preferred` 和 `discouraged`，不是全都强制封死 |


## 不借鉴 DeerFlow 的部分

以下几点明确不纳入第二版：

1. 不把 skill 主体改成 `SKILL.md`
2. 不做 `.skill` 安装包机制
3. 不做 custom skill 编辑/回滚平台
4. 不为了“渐进加载”而放弃当前函数调用 schema


## 结论

第二版阶段 C 的方向应当是：

- **保留当前执行型 skill 架构**
- **保留你已经做出来的显式路由器**
- **借 DeerFlow 的治理层：enabled state、profile 过滤、prompt 附录、管理接口**

一句话概括：

> 第一版阶段 C 解决了“skill 能跑”；第二版阶段 C 要解决“skill 怎么被稳定、可控、可解释地用起来”。  
