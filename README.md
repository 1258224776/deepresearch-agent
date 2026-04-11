# 🔬 DeepResearch Agent

> AI 驱动的深度研究与数据提取工具，支持多家大模型并发协作，一键生成可视化数据看板。

**在线体验：** [deepresearch-agent-3zq2q8sgtcqocvicjyk8m6.streamlit.app](https://deepresearch-agent-3zq2q8sgtcqocvicjyk8m6.streamlit.app/)

---

## ✨ 核心功能

### 🤖 Agent 自主模式（新功能）
输入任意问题，AI 自主决策每一步行动：
1. **思考**：分析当前信息缺口，决定下一步
2. **调用工具**：搜索网络 / 爬取网页 / 检索本地文档
3. **观察结果**：消化工具返回的内容，继续推理
4. **循环直到完成**：自主判断何时信息充足，输出完整报告

全程可见每步的**思考过程 + 工具调用 + 观察结果**，真正的 ReAct Agent 架构。

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

---

## 🚀 快速开始

### 在线使用
直接访问：[在线体验地址](https://deepresearch-agent-3zq2q8sgtcqocvicjyk8m6.streamlit.app/)

在左侧侧边栏的 **🔑 API Key 配置** 中填入自己的 Key 即可使用，无需部署。

### 本地部署

**1. 克隆项目**
```bash
git clone https://github.com/1258224776/deepresearch-agent.git
cd deepresearch-agent
```

**2. 安装依赖**
```bash
pip install -r requirements.txt
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
streamlit run app.py
```

浏览器访问 `http://localhost:8501`

---

## 📁 项目结构

```
deepresearch-agent/
├── app.py           # Streamlit 前端主程序（4 种模式）
├── agent.py         # AI 调用核心：多提供商路由、流水线逻辑
├── agent_loop.py    # ReAct Agent 核心：工具注册 + 推理循环
├── prompts.py       # 所有 Prompt 模板集中管理
├── config.py        # 提供商配置、引擎预设、全局常量
├── tools.py         # 爬虫工具：搜索、抓取、文件处理
├── rag.py           # 本地向量检索（Faiss + Sentence-Transformers）
└── .env             # API Key 配置（不提交 Git）
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
