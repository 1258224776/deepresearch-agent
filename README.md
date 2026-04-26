# DeepResearch Agent

> 多 Agent 深度研究框架，支持并发调研、实时进度追踪、跨轮记忆检索，内置结构化报告生成与来源溯源。

**[English](README_EN.md)** | 中文

---

## 架构概览

```
用户提问
    │
    ▼
CoordinatorNode          ← 检索历史记忆，分类问题类型，决定路由
    │
    ├─ direct_research ──► ResearcherNode ─────────────────────────────────────┐
    │                                                                           │
    └─ planned_research ─► PlannerNode ──► ResearcherNode × N（并发波次）───────┤
                                                                               │
                                                                        ReporterNode
                                                                           │
                                                                    结构化报告 + 引用编号
                                                                    写回记忆库（FAISS）
```

每次调研生成一个 `RunState`，通过 SSE 实时推送到前端 Run Drawer，全程可见每个节点的运行状态、观察结果、来源、Artifact。

---

## 功能

### 聊天模式
普通对话，支持工具调用（搜索、抓取、RAG 检索）和流式输出。

### 深度研究
单轮问题→直接研究路由。Coordinator 检索历史记忆 → Researcher 循环调用工具 → Reporter 生成带引用编号的结构化报告，结论自动写入 FAISS 记忆库供后续复用。

### 深度规划
多维问题→规划研究路由。Planner 把大问题拆成 3-5 个子问题，多个 ResearcherNode 并发执行（可配置 wave 批次），Reporter 汇总全部观察后生成综合报告。

### 记忆系统
每次完成的报告自动提炼关键结论写入 FAISS 向量库，下次提问时语义检索最相关的历史发现并注入上下文，避免重复调研相同领域。

### 实时运行视图
Run Drawer 通过 SSE 订阅实时快照，展示：
- 节点时间线（coordinator / planner / researcher × N / reporter）
- 每个节点的观察列表与来源
- Artifact（报告、记忆命中、记忆写回）
- 断线自动降级为轮询

### Skill 治理
设置面板可查看所有已注册技能的启用状态、配置情况、调用次数 / 成功率 / 均时，支持运行时一键停用。

---

## 支持的 AI 提供商

| 提供商 | 用途 | 是否需要代理 |
|--------|------|------------|
| Google Gemini 2.5 Pro | 主脑（推理最强） | 需要 |
| Claude Opus 4.7 | 主脑备选 | 需要 |
| Google Gemini 2.5 Flash | 工作节点（极速） | 需要 |
| Claude Haiku 4.5 | 工作节点备选 | 需要 |
| 智谱 GLM-4-Plus / GLM-4-Flash | 主脑 + 工作节点 | 不需要 |
| MiniMax MoE | 主脑 + 工作节点 | 不需要 |
| 硅基流动 DeepSeek-V3 / Qwen | 主脑 + 工作节点 | 不需要 |

在 `providers.yaml` 里切换模型，不需要改代码。

---

## 快速开始

### 环境要求
- Python 3.11+
- Node.js 20+

### 1. 克隆

```bash
git clone https://github.com/1258224776/deepresearch-agent.git
cd deepresearch-agent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 3. 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入至少一个 AI 提供商的 Key：

```env
# 国内直连（推荐，注册送额度）
GLM_API_KEY=your_key
SILICONFLOW_API_KEY=your_key

# 搜索（默认使用免费的 DuckDuckGo，无需配置）
SEARCH_PROVIDERS=ddgs
```

### 4. 启动

```powershell
# Windows — 一条命令启动 API + 前端
.\start.ps1
```

```bash
# Linux / macOS — 分两个终端运行
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
# 另一个终端
cd frontend && npm run dev
```

访问 `http://localhost:3000`

---

## 项目结构

```
deepresearch-agent/
├── frontend/               # Next.js 前端
│   └── src/
│       ├── app/            # 页面路由（首页、会话页）
│       ├── components/     # UI 组件（RunDrawer、ChatStream 等）
│       └── lib/api.ts      # 前后端接口层
├── skills/                 # 技能模块
│   ├── profiles.py         # 技能组合预设（react_default / planner 等）
│   ├── stats.py            # 调用统计写入 SQLite
│   └── search_*.py         # 各搜索技能实现
├── agent.py                # AI 调用核心：多提供商路由、Function Calling
├── agent_loop.py           # ReAct 推理循环（技能注册、观察链）
├── agent_planner.py        # 规划模式（子问题拆解、并发执行、结果合并）
├── graph_runner.py         # 静态图执行器（节点调度、重试、持久化）
├── run_state.py            # 图状态数据模型（RunState、NodeResult 等）
├── run_store.py            # SQLite 持久化层（5 张表）
├── memory.py               # FAISS 向量记忆（检索、写回、统计）
├── report.py               # 报告生成层（引用注册、按问题类型选模板）
├── prompts.py              # Prompt 模板（6 种报告模板 + 分类器）
├── api.py                  # FastAPI（REST + SSE 事件流）
├── config.py               # 引擎预设、全局常量
├── providers.yaml          # AI 提供商 / 模型配置（改这里切换模型）
├── tools.py                # 底层工具（搜索、爬取、文件处理）
├── rag.py                  # 本地 RAG（Faiss + Sentence-Transformers）
├── start.ps1               # Windows 一键启动脚本
└── .env                    # API Key 配置（不提交 Git）
```

---

## 免费 API Key

| 平台 | 地址 | 说明 |
|------|------|------|
| 智谱 GLM | [open.bigmodel.cn](https://open.bigmodel.cn) | 国内，注册送额度 |
| 硅基流动 | [cloud.siliconflow.cn](https://cloud.siliconflow.cn) | 国内，注册送额度 |
| MiniMax | [platform.minimaxi.com](https://platform.minimaxi.com) | 国内，注册送额度 |
| Google AI Studio | [aistudio.google.com](https://aistudio.google.com) | 需代理，免费 |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) | 需代理，付费 |

---

## License

MIT
