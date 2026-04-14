# 🔬 DeepResearch Agent

> AI 驱动的深度研究与数据提取工具，支持多家大模型并发协作，一键生成可视化数据看板。

---

## ✨ 核心功能

### 🤖 Agent 自主模式

提供两种子模式，适配不同复杂度的问题：

#### ⚡ ReAct 自主
输入明确的单一问题，AI 自主循环推理：
1. **思考**：分析当前信息缺口，决定下一步行动
2. **调用工具**：搜索网络 / 爬取网页 / 检索本地文档 / 定向提取 / AI 摘要
3. **观察结果**：消化工具返回，继续推理
4. **循环直到完成**：自主判断信息充足时输出完整报告

工具自动使用各大模型的**原生 Function Calling API**，调用可靠性大幅提升，并在不支持时自动降级。

#### 🗺️ 深度规划
适合多维度复杂问题（如「比较 A 和 B」「分析某行业格局」）：
1. **Planner**：主脑 LLM 把大问题拆解为 3-5 个独立子问题
2. **Executor**：对每个子问题独立运行精简 ReAct 循环
3. **Memory**：前序发现自动注入后续子任务，避免重复研究
4. **Reporter**：汇总所有调研结果，生成结构化综合报告

### ⚡ URL 智能提取（核心亮点）
粘贴任意网址 + 描述你想要什么，系统自动完成：
1. **主脑 AI** 理解意图，动态生成字段规则（Schema）
2. **并发爬取** 所有 URL，清洗页面文本
3. **打工 AI 并发提取**，多线程同时处理，带限速保护
4. **看板 AI 汇总分析**，输出带统计卡片、趋势、建议的可视化面板

支持场景：二手房源、竞品监测、电商比价、招聘速报、新闻事件……**万物皆可提取**。

### 🔍 搜索 & 爬取
输入研究主题，AI 自动从多角度搜索并抓取网页，并行提炼关键信息，支持进一步生成深度报告。

### 📝 直接生成研究报告
输入问题，AI 综合多方资料，直接输出结构完整、有数据支撑的报告。支持行业分析、投资备忘录、学术综述、舆情分析、竞品分析等多种模板。

---

## 🤖 支持的 AI 提供商

| 提供商 | 用途 | 是否需要 VPN |
|--------|------|------------|
| Google Gemini 3.0 Pro Preview | 主脑（最强推理） | ✅ 需要 |
| Claude Opus 4.6 | 主脑备选（洞察天花板） | ✅ 需要 |
| Google Gemini 2.5 Flash | 打工（极速提取） | ✅ 需要 |
| Claude Haiku 4.5 | 打工备选 | ✅ 需要 |
| 智谱 GLM-5 / GLM-4-Flash | 主脑 + 打工（国内直连） | ❌ 不需要 |
| MiniMax M2.7 / abab6.5g | 主脑 + 打工（国内直连） | ❌ 不需要 |
| 硅基流动 DeepSeek-V3 / Qwen | 主脑 + 打工（国内直连） | ❌ 不需要 |

**两种引擎模式：**
- 🌟 **深度分析模式**：调用全球最强模型，质量最高（需 VPN）
- ⚡ **极速直连模式**：全程国内模型，无需 VPN，秒级响应

系统会自动探测网络环境并推荐合适的引擎，也支持一键手动切换。

**切换模型：** 直接编辑 `providers.yaml`，无需改动任何 Python 代码。

---

## 🚀 快速开始

**1. 克隆项目**
```bash
git clone https://github.com/1258224776/deepresearch-agent.git
cd deepresearch-agent
```

**2. 安装依赖**
```bash
python -m pip install -r requirements.txt
```

**3. 配置 API Key**

复制并编辑 `.env` 文件：
```bash
cp .env.example .env
```

填入至少一个 API Key：
```env
GOOGLE_API_KEY=你的Key
GLM_API_KEY=你的Key
MINIMAX_API_KEY=你的Key
SILICONFLOW_API_KEY=你的Key
ANTHROPIC_API_KEY=你的Key
```

> 国内推荐使用智谱 GLM 或硅基流动，注册即送免费额度，无需 VPN。

**4. 启动**
```bash
python -m streamlit run app.py
```

浏览器访问 `http://localhost:8501`

---

## 📁 项目结构

```
deepresearch-agent/
├── app.py              # Streamlit 前端主程序（4 种模式）
├── agent.py            # AI 调用核心：多提供商路由、原生 Function Calling
├── agent_loop.py       # ReAct Agent：工具注册 + 推理循环（7 种工具）
├── agent_planner.py    # 深度规划 Agent：Planner/Executor/Memory/Reporter
├── prompts.py          # 所有 Prompt 模板集中管理
├── config.py           # 引擎预设、全局常量（从 providers.yaml 加载）
├── providers.yaml      # AI 提供商配置（模型切换改这里，不动代码）
├── tools.py            # 爬虫工具：搜索、抓取、文件处理
├── rag.py              # 本地向量检索（Faiss + Sentence-Transformers）
├── api.py              # FastAPI 封装（供 Dify 等平台导入）
└── .env                # API Key 配置（不提交 Git）
```

---

## 🔑 免费获取 API Key

| 平台 | 地址 | 说明 |
|------|------|------|
| 智谱 GLM | [open.bigmodel.cn](https://open.bigmodel.cn) | 国内，注册送额度 |
| 硅基流动 | [cloud.siliconflow.cn](https://cloud.siliconflow.cn) | 国内，注册送额度 |
| MiniMax | [platform.minimaxi.com](https://platform.minimaxi.com) | 国内，注册送额度 |
| Google AI Studio | [aistudio.google.com](https://aistudio.google.com) | 需 VPN，免费 |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) | 需 VPN，付费 |

---

## 📄 License

MIT
