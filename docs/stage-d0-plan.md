# 阶段 D0 设计稿

## 目标

阶段 D 的第一版目标不是引入“更复杂的调度”，而是把当前已经可用的研究能力收敛成一套可持久化、可恢复、可重入的多节点运行模型。

当前代码已经具备这些基础能力：

- `agent_loop.py`：单回路 ReAct 研究执行器
- `agent_planner.py`：问题拆解 + 子问题执行 + 汇总
- `report.py`：Observation / CitationRegistry / 最终报告编排
- `memory.py`：SQLite + FAISS 的磁盘化研究记忆
- `api.py`：线程、消息、SSE 研究接口

因此 D0 的设计重点不是“重新发明 agent”，而是定义一套稳定的：

- 运行状态模型
- 节点输入输出协议
- 持久化模型
- 节点间引用聚合规则
- 第一版固定拓扑

## D v1 决策

### 决策 1：采用分层状态，不把 `CitationRegistry` 直接放进 `RunState`

`report.py` 里的 `Observation` 和 `CitationRegistry` 继续承担“单节点执行轮次内的观察与引用管理”职责。

它们和 D 阶段要引入的 `RunState` 不是替换关系，而是嵌套关系：

- 节点内：使用 `Observation` / `CitationRegistry`
- 节点外：使用可序列化的 `NodeResult` / `SourceRecord` / `ArtifactRecord`

`RunState` 不直接保存 `CitationRegistry` 实例，也不把节点内 `cite_id` 当作跨节点主键。原因如下：

- `CitationRegistry` 是运行时对象，不适合直接持久化
- `cite_id` 只在单个 registry 作用域内有意义，跨节点会冲突
- D 阶段要支持 checkpoint / 恢复 / 重放，状态必须是稳定的、可序列化的

因此跨节点聚合引用时，统一采用稳定的 `source_key`：

- 优先使用标准化后的 URL
- 本地文档使用标准化后的 `file://...`
- deer-rag / 外部知识库可使用标准化后的 `source_uri`

最终报告中的编号引用只在 `ReporterNode` 阶段统一分配。

### 决策 2：`CoordinatorNode` 第一版采用静态路由

阶段 D v1 不做运行时动态 task queue，不做并发派发，不做通用图搜索调度。

第一版 Coordinator 只根据问题类型和入口模式决定固定拓扑：

- `direct_research`
- `planned_research`

原因如下：

- 当前 `agent_planner.py` 已经验证了“拆题 -> 执行子问题 -> 合并答案”的价值
- v1 的关键收益来自“状态可恢复、节点可重入、运行可持久化”
- 动态调度会显著放大状态管理、失败恢复、并发一致性的复杂度

结论：

- D v1：静态路由 + 分层状态
- D v2：如有必要，再扩展为动态调度 / task queue / 并发执行

### 决策 3：先做 LangGraph 式接口，不先绑定 LangGraph 运行时

阶段 D v1 的目标是获得“图式状态机”的能力，而不是立即引入外部运行时依赖。

因此第一版采用项目内自定义 state machine：

- 节点有统一 `run(state) -> state delta` 契约
- 拓扑由 Coordinator 固定决定
- checkpoint / 恢复 / 状态落盘由项目内实现

等 D v2 真正需要动态调度、并发、条件分支时，再评估是否迁移到 LangGraph。

## 非目标

阶段 D v1 不包含以下内容：

- 通用动态任务队列
- 并发多 worker 调度
- 自动重试策略编排器
- Python 代码执行沙箱
- 真正的 `CoderNode`
- 通用插件运行时

其中 `CoderNode + 沙箱` 只在确认产品需要代码执行路径时再进入 D v2 范围。

## 状态分层

### 层 1：节点内执行状态

这一层继续沿用当前研究执行模型：

- `Observation`
- `CitationRegistry`
- `SkillContext`

作用范围：

- 单个节点的一次执行
- 单个节点内部的引用去重和 observation 累积
- 节点内部 prompt 构建与报告材料组织

这一层不直接对外持久化运行时对象。

### 层 2：图运行状态

这一层是 D 阶段新增能力，用于表达整个 run：

- 哪些节点已经执行
- 每个节点产出了什么观察、摘要、artifact
- 哪些来源已经被全局聚合
- 当前运行在哪个节点
- 是否可以恢复

这一层只保存可序列化数据。

## 核心数据模型

以下为 D v1 推荐的数据结构。第一版可先用 `TypedDict` / `pydantic` 实现，后续再视需要演进。

### `RunState`

```python
class RunState(BaseModel):
    run_id: str
    thread_id: str
    question: str
    route_kind: str              # "direct_research" | "planned_research"
    status: str                  # "running" | "paused" | "failed" | "done"
    current_node: str            # 当前节点 id
    node_order: list[str]        # 固定拓扑的执行顺序
    node_results: dict[str, "NodeResult"]
    source_catalog: dict[str, "SourceRecord"]
    artifacts: dict[str, "ArtifactRecord"]
    context: dict[str, object]   # 轻量共享状态，例如 question_type / plan
    checkpoints: list["CheckpointRecord"]
    created_at: int
    updated_at: int
```

约束：

- `RunState` 中不保存 `CitationRegistry` 实例
- `RunState` 中不保存不可序列化对象
- `RunState` 中不保存节点本地 `cite_id`

### `NodeResult`

```python
class NodeResult(BaseModel):
    node_id: str
    node_type: str               # coordinator | planner | researcher | reporter
    status: str                  # pending | running | done | failed | skipped
    summary: str = ""
    observations: list["ObservationRecord"] = []
    source_keys: list[str] = []
    artifacts: list[str] = []    # artifact ids
    error: str | None = None
    started_at: int | None = None
    finished_at: int | None = None
```

说明：

- `NodeResult` 是节点完成后的序列化结果
- `summary` 是节点的可复用摘要，不等于最终答案
- `source_keys` 指向全局 `source_catalog`

### `ObservationRecord`

```python
class ObservationRecord(BaseModel):
    content: str
    tool: str = ""
    args: dict[str, object] = {}
    source_keys: list[str] = []
```

说明：

- 这是 `report.Observation` 的持久化投影
- 不保存节点内的 `cite_ids`
- 由 `source_keys` 建立到全局来源目录的关联

### `SourceRecord`

```python
class SourceRecord(BaseModel):
    source_key: str
    url: str
    title: str = ""
    snippet: str = ""
    source_type: str = ""        # web | file | rag | api
    metadata: dict[str, object] = {}
```

说明：

- `source_key` 为跨节点稳定主键
- 生成规则必须可重复、可重建
- `ReporterNode` 负责将 `source_catalog` 重新编号为最终引用

### `ArtifactRecord`

```python
class ArtifactRecord(BaseModel):
    artifact_id: str
    kind: str                    # plan | answer | report | notes
    title: str = ""
    content: str
    created_by: str              # node_id
    created_at: int
```

### `CheckpointRecord`

```python
class CheckpointRecord(BaseModel):
    checkpoint_id: str
    run_id: str
    node_id: str
    status: str
    snapshot_ref: str            # 快照存储位置或序列化主键
    created_at: int
```

## 节点职责边界

### `CoordinatorNode`

职责：

- 识别入口模式
- 决定固定拓扑
- 初始化 `RunState`
- 写入第一条 checkpoint

输入：

- 用户问题
- thread 信息
- 入口参数，例如 `use_planner`

输出：

- `route_kind`
- `node_order`
- 初始化后的 `RunState`

第一版路由规则：

- `use_planner=False` -> `direct_research`
- `use_planner=True` -> `planned_research`

可选增强：

- 当未显式指定时，再根据 `QuestionType` 做轻量默认路由

### `PlannerNode`

职责：

- 只负责生成研究计划
- 只产出计划，不负责执行子问题

输入：

- 原始问题
- memory context

输出 artifact：

- `plan`

输出 context：

- `sub_questions`
- `question_type`

说明：

- 当前 `agent_planner.py` 里的 `_plan_research()` 可以直接迁移为 `PlannerNode` 核心逻辑
- 规划与执行必须拆开，避免一个节点同时承担多重职责

### `ResearcherNode`

职责：

- 执行一次完整研究回路
- 产出 observation records
- 产出节点本地来源集合
- 可用于“直接研究”或“子问题研究”

输入：

- 问题
- memory context
- 可选的局部计划上下文

输出：

- `NodeResult.summary`
- `ObservationRecord[]`
- `source_catalog` 增量

说明：

- 当前 `agent_loop.run_agent(..., compose=False)` 可直接包装成 ResearcherNode

### `ReporterNode`

职责：

- 汇总所有 `NodeResult`
- 统一建立最终引用编号
- 生成最终报告 artifact

输入：

- 全量 `node_results`
- 全局 `source_catalog`

输出 artifact：

- `final_report`
- `final_answer`

关键规则：

- `ReporterNode` 内部可临时重建一个新的 `CitationRegistry`
- 按 `source_catalog` 顺序或稳定规则统一编号
- 最终 `[1][2]...` 引用只在这里生成

说明：

- 当前 `report.compose_report()` 是 ReporterNode 的核心能力
- 但输入应从“当前回路 observations”扩展为“全局节点聚合 observations”

## D v1 固定拓扑

### 路径 A：直接研究

```text
Coordinator -> Researcher -> Reporter
```

适用场景：

- 问题简单
- 不需要显式拆题
- 已由入口明确指定 `use_planner=False`

### 路径 B：规划研究

```text
Coordinator -> Planner -> Researcher(sub-question loop) -> Reporter
```

说明：

- `Researcher(sub-question loop)` 在 v1 中是顺序循环，不并发
- 每个子问题都生成独立 `NodeResult`
- 这些 `NodeResult` 最终交由 Reporter 汇总

### 为什么不做动态拓扑

因为第一版要解决的问题是：

- checkpoint
- run persistence
- 节点可重入
- 节点结果聚合

而不是：

- 任意拓扑生成
- 并发任务编排
- 通用重试/回退/再调度

## 持久化设计

当前系统已经有线程和消息表。D v1 建议新增 run 级别数据表，而不是把节点执行信息塞回 message JSON。

推荐新增以下表：

### `agent_runs`

- `run_id`
- `thread_id`
- `question`
- `route_kind`
- `status`
- `current_node`
- `context_json`
- `created_at`
- `updated_at`

### `agent_run_nodes`

- `run_id`
- `node_id`
- `node_type`
- `status`
- `summary`
- `result_json`
- `error`
- `started_at`
- `finished_at`

### `agent_run_sources`

- `run_id`
- `source_key`
- `url`
- `title`
- `snippet`
- `source_type`
- `metadata_json`

### `agent_run_artifacts`

- `run_id`
- `artifact_id`
- `kind`
- `title`
- `content`
- `created_by`
- `created_at`

### `agent_run_checkpoints`

- `checkpoint_id`
- `run_id`
- `node_id`
- `status`
- `snapshot_json`
- `created_at`

## 恢复与重入

### 恢复粒度

第一版只要求节点级恢复，不要求节点内部 step 级恢复。

即：

- `ResearcherNode` 如果失败，恢复时从该节点重新执行
- `PlannerNode` 如果已完成，不再重复规划
- `ReporterNode` 如果失败，可直接重跑

这已经足够支撑稳定的 run 恢复。

### checkpoint 策略

建议在这些边界写 checkpoint：

- Coordinator 决定路由后
- Planner 完成后
- 每个 ResearcherNode 完成后
- Reporter 开始前
- Run 完成后

## 与现有代码的映射

### 可直接复用

- `agent_loop.run_agent(..., compose=False)` -> `ResearcherNode`
- `agent_planner._plan_research()` -> `PlannerNode`
- `report.compose_report()` -> `ReporterNode`
- `memory.search_memory()` / `format_memory_context()` -> node 输入增强

### 需要拆分

- `agent_planner.run_planner_agent()` 当前同时做了：
  - memory 召回
  - 主问题分类
  - 规划
  - 子问题执行
  - 汇总报告

阶段 D 要拆成：

- `CoordinatorNode`
- `PlannerNode`
- `ResearcherNode`
- `ReporterNode`

### 需要新增

- `run_state.py` 或等价模块
- `graph_runner.py`
- `run_store.py`
- API 层 `run_id` 读写与恢复接口

## 迁移顺序

### D1：状态模型

新增：

- `RunState`
- `NodeResult`
- `ObservationRecord`
- `SourceRecord`
- `ArtifactRecord`
- `CheckpointRecord`

同时明确：

- `source_key` 生成规则
- `ReporterNode` 的统一编号规则

### D2：静态图执行器

新增项目内 graph runner：

- 支持固定节点顺序
- 支持节点结果写回 `RunState`
- 支持节点级失败与恢复

第一版只实现两条固定拓扑：

- `direct_research`
- `planned_research`

### D3：run 持久化

在 `api.py` 中新增 run 级别接口：

- 创建 run
- 查询 run
- 恢复 run
- 查询节点结果

### D4：前端接入

前端按 `run_id` 展示：

- 当前节点
- 节点状态
- 子问题结果
- 最终报告

## 风险与约束

### 风险 1：混淆“节点内引用”与“全局引用”

规避策略：

- 节点内仍然允许本地 `CitationRegistry`
- 跨节点只传 `source_key`
- 最终引用编号只在 ReporterNode 生成

### 风险 2：把 D v1 做成半动态调度器

规避策略：

- Coordinator 只输出固定拓扑
- 不引入通用 task queue
- 不在 v1 做节点并发

### 风险 3：持久化粒度过细

规避策略：

- v1 只做节点级 checkpoint
- 不做 step 级 replay

## D v2 展望

在 D v1 稳定后，可扩展到：

- 动态任务队列
- 并发子任务执行
- retry / fallback / merge 策略
- 真正的 `CoderNode`
- Python 子进程沙箱
- 必要时再评估迁移到 LangGraph 运行时

## 最终结论

阶段 D v1 的定义如下：

- 采用分层状态
- `RunState` 只保存可序列化图运行状态
- `CitationRegistry` 只留在节点内与 ReporterNode 内部使用
- `ReporterNode` 统一生成最终编号引用
- `CoordinatorNode` 第一版采用静态路由
- 固定拓扑只支持 `direct_research` 与 `planned_research`
- 不在 v1 引入动态调度与代码沙箱

这套方案能最大化复用当前 `agent_loop.py`、`agent_planner.py`、`report.py`、`memory.py` 的现有能力，并把阶段 D 的风险收敛到“状态治理”而不是“调度系统设计”。
