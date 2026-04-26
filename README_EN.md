# DeepResearch Agent

> A multi-agent deep research framework with concurrent sub-research, real-time run visibility, cross-session memory retrieval, structured report generation, and source citation.

[中文](README.md) | **English**

---

## Architecture

```
User question
      │
      ▼
CoordinatorNode      ← retrieves memory, classifies question type, decides route
      │
      ├─ direct_research ──► ResearcherNode ──────────────────────────────────────┐
      │                                                                            │
      └─ planned_research ─► PlannerNode ──► ResearcherNode × N (concurrent) ─────┤
                                                                                  │
                                                                           ReporterNode
                                                                                │
                                                               Structured report + citation refs
                                                               Write conclusions back to FAISS memory
```

Each run produces a `RunState` that streams real-time snapshots to the frontend Run Drawer via SSE. Every node's status, observations, sources, and artifacts are visible as the run progresses.

---

## Features

### Chat
Standard conversation with tool use (web search, scraping, RAG retrieval) and streaming output.

### Deep Research
Single-question → direct research route. Coordinator retrieves relevant memory → Researcher iteratively calls tools → Reporter composes a citation-numbered structured report. Key conclusions are automatically stored in the FAISS memory store for future reuse.

### Deep Planning
Multi-dimensional questions → planned research route. Planner splits the question into 3–5 sub-questions; multiple ResearcherNodes run concurrently (configurable wave batches); Reporter synthesizes all observations into a comprehensive report.

### Memory System
After every completed report, key conclusions are chunked and written to a FAISS vector index. On the next query, semantically similar prior findings are retrieved and injected into the research context, avoiding redundant work on the same domain.

### Real-time Run View
The Run Drawer subscribes to SSE snapshots and displays:
- Node timeline (coordinator / planner / researcher × N / reporter)
- Per-node observations and source catalog
- Artifacts (final report, memory hits, memory write-back)
- Auto-fallback to polling on SSE disconnect

### Skill Governance
The settings panel shows all registered skills with their enabled state, configuration status, call count, success rate, and average duration. Skills can be toggled at runtime without restarting.

---

## Supported AI Providers

| Provider | Role | VPN Required |
|----------|------|-------------|
| Google Gemini 2.5 Pro | Orchestrator (best reasoning) | Yes |
| Claude Opus 4.7 | Orchestrator fallback | Yes |
| Google Gemini 2.5 Flash | Worker (fast extraction) | Yes |
| Claude Haiku 4.5 | Worker fallback | Yes |
| Zhipu GLM-4-Plus / GLM-4-Flash | Orchestrator + worker | No |
| MiniMax MoE | Orchestrator + worker | No |
| SiliconFlow DeepSeek-V3 / Qwen | Orchestrator + worker | No |

Switch models by editing `providers.yaml` — no code changes needed.

---

## Quick Start

### Requirements
- Python 3.11+
- Node.js 20+

### 1. Clone

```bash
git clone https://github.com/1258224776/deepresearch-agent.git
cd deepresearch-agent
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in at least one AI provider key:

```env
# Domestic China providers (free credits on sign-up, no VPN needed)
GLM_API_KEY=your_key
SILICONFLOW_API_KEY=your_key

# Search provider (DuckDuckGo is free and used by default)
SEARCH_PROVIDERS=ddgs
```

### 4. Start

```powershell
# Windows — single command for API + frontend
.\start.ps1
```

```bash
# Linux / macOS — run in two terminals
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
# second terminal
cd frontend && npm run dev
```

Open `http://localhost:3000`

---

## Project Structure

```
deepresearch-agent/
├── frontend/               # Next.js frontend
│   └── src/
│       ├── app/            # Page routes (home, chat session)
│       ├── components/     # UI components (RunDrawer, ChatStream, etc.)
│       └── lib/api.ts      # Frontend ↔ backend API layer
├── skills/                 # Skill modules
│   ├── profiles.py         # Skill profile presets (react_default, planner, etc.)
│   ├── stats.py            # Per-skill call stats written to SQLite
│   └── search_*.py         # Individual search skill implementations
├── agent.py                # AI call core: multi-provider routing, Function Calling
├── agent_loop.py           # ReAct reasoning loop (skill registration, observation chain)
├── agent_planner.py        # Planning mode (sub-question decomposition, parallel exec)
├── graph_runner.py         # Static graph executor (node scheduling, retry, persistence)
├── run_state.py            # Graph state models (RunState, NodeResult, etc.)
├── run_store.py            # SQLite persistence layer (5 tables)
├── memory.py               # FAISS vector memory (retrieval, write-back, stats)
├── report.py               # Report generation (citation registry, question-type templates)
├── prompts.py              # Prompt templates (6 report templates + classifier)
├── api.py                  # FastAPI (REST + SSE event stream)
├── config.py               # Engine presets and global constants
├── providers.yaml          # AI provider / model config (edit here to switch models)
├── tools.py                # Low-level tools (search, scrape, file handling)
├── rag.py                  # Local RAG (Faiss + Sentence-Transformers)
├── start.ps1               # Windows one-command launcher
└── .env                    # API keys (not committed to git)
```

---

## Free API Keys

| Platform | URL | Notes |
|----------|-----|-------|
| Zhipu GLM | [open.bigmodel.cn](https://open.bigmodel.cn) | China domestic, free credits on sign-up |
| SiliconFlow | [cloud.siliconflow.cn](https://cloud.siliconflow.cn) | China domestic, free credits on sign-up |
| MiniMax | [platform.minimaxi.com](https://platform.minimaxi.com) | China domestic, free credits on sign-up |
| Google AI Studio | [aistudio.google.com](https://aistudio.google.com) | VPN required, free tier |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) | VPN required, paid |

---

## License

MIT
