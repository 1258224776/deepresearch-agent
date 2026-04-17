"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type Locale = "zh" | "en";

const STORAGE_KEY = "deepresearch:locale";

const dictionary = {
  zh: {
    shell: {
      appTitle: "DeepResearch",
      appSubtitle: "本地研究工作台",
      runStatus: "运行状态",
      share: "分享",
    },
    sidebar: {
      newChat: "新建对话",
      searchChats: "搜索对话",
      recentChats: "最近对话",
      noChats: "还没有对话",
      noMessages: "暂无消息",
      deleteThread: "删除对话",
      settingsLabel: "设置与连接",
      stageLabel: "当前阶段：Step D 实时轨迹 + Step E 本地设置",
    },
    home: {
      title: {
        chat: "开始新对话",
        research: "开始研究任务",
        planner: "开始规划调查",
      },
      subtitle: {
        chat: "直接提问，获得连续对话式回答。",
        research: "输入研究主题，系统会联网搜索、抓取并展示执行轨迹。",
        planner: "适合复杂问题，系统会先拆解课题，再逐步调查汇总。",
      },
      suggestions: {
        chat: [
          "南京今天会下雨吗？",
          "帮我总结这篇文章的核心观点",
          "解释一下 RAG 和 Agent 的区别",
        ],
        research: [
          "分析一家上市公司的最新财报电话会",
          "追踪最近一周 AI Agent 的行业动态",
          "从官方文档中提取某个 API 的关键能力",
        ],
        planner: [
          "对比 OpenAI、Anthropic、Google 的开发者产品策略",
          "规划一份私有化部署研究代理的技术路线",
          "拆解一个行业报告并输出可执行调研框架",
        ],
      },
    },
    thread: {
      loading: "正在加载对话...",
      ready: "对话已就绪",
      fallbackTitle: "对话",
      subtitle: {
        chat: "这里会显示连续对话消息。",
        research: "这里会显示研究过程、引用来源和最终答案。",
        planner: "这里会显示规划步骤、执行轨迹和最终结论。",
      },
      streamFailed: "流式请求失败：",
      unknownStreamError: "未知流式错误",
    },
    chat: {
      assistant: "DeepResearch",
      planner: "规划",
      research: "研究",
    },
    input: {
      send: "发送",
      attachmentsSoon: "附件会在后续步骤接入",
      modeChat: "对话",
      modeResearch: "研究",
      modePlanner: "规划",
      placeholderChat: "输入问题，像普通大模型对话一样直接提问...",
      placeholderResearch: "输入研究主题，系统会自动搜索、抓取并整理来源...",
      placeholderPlanner: "输入复杂课题，系统会先拆解问题再逐步调查...",
      helperChat: "适合直接问答、追问和轻量讨论。",
      helperResearch: "适合需要联网搜索、抓取网页和引用来源的课题。",
      helperPlanner: "适合复杂任务，会先规划子问题，再逐步执行。",
      quickChat: "普通对话",
      quickResearch: "ReAct 研究",
      quickPlanner: "Planner 调查",
    },
    trace: {
      title: "执行轨迹",
      steps: "步",
      step: "步骤",
    },
    runs: {
      title: "运行详情",
      recent: "最近运行",
      empty: "这个对话还没有运行记录。",
      question: "问题",
      route: "路线",
      status: "状态",
      currentNode: "当前节点",
      createdAt: "创建时间",
      updatedAt: "更新时间",
      nodes: "节点时间线",
      artifacts: "产物",
      checkpoints: "检查点",
      noNodes: "还没有节点结果。",
      noArtifacts: "还没有产物。",
      noCheckpoints: "还没有检查点。",
      routeDirect: "直接研究",
      routeCode: "代码分析",
      routePlanned: "规划研究",
      statusPending: "等待中",
      statusRunning: "运行中",
      statusDone: "已完成",
      statusFailed: "失败",
      statusPaused: "暂停",
      open: "打开运行面板",
      close: "关闭运行面板",
      select: "查看运行",
      nodePending: "等待执行",
      active: "当前运行",
      latest: "最近一次",
    },
    language: {
      zh: "中文",
      en: "English",
    },
    settings: {
      open: "打开设置",
      title: "本地设置",
      subtitle: "这些设置只保存在当前浏览器，用于本地部署的前端调试与运行。",
      apiBase: "后端 API 地址",
      apiBaseHint: "指向 FastAPI 服务，例如 http://127.0.0.1:8000",
      chatEngine: "普通对话模型",
      chatEngineHint: "留空则由后端使用默认模型。",
      researchEngine: "研究模型",
      researchEngineHint: "用于 ReAct 研究模式。",
      plannerEngine: "规划模型",
      plannerEngineHint: "用于 Planner 多步调查模式。",
      researchProfile: "研究 Skill Profile",
      researchProfileHint: "默认 react_default，可切到 web_research_heavy。",
      plannerProfile: "规划 Skill Profile",
      plannerProfileHint: "Planner 模式默认使用 planner。",
      reset: "恢复默认",
      cancel: "取消",
      save: "保存设置",
      status: "当前连接",
      statusReady: "已保存到本地浏览器存储",
    },
  },
  en: {
    shell: {
      appTitle: "DeepResearch",
      appSubtitle: "Local research workspace",
      runStatus: "Run status",
      share: "Share",
    },
    sidebar: {
      newChat: "New chat",
      searchChats: "Search chats",
      recentChats: "Recent chats",
      noChats: "No chats yet",
      noMessages: "No messages yet",
      deleteThread: "Delete thread",
      settingsLabel: "Settings & connections",
      stageLabel: "Current stage: Step D live trace + Step E local settings",
    },
    home: {
      title: {
        chat: "Start a new thread",
        research: "Start a research run",
        planner: "Start a planned investigation",
      },
      subtitle: {
        chat: "Ask directly and continue the conversation naturally.",
        research: "Enter a research topic and the app will search, fetch, and trace the workflow.",
        planner: "Best for complex topics that need decomposition before investigation.",
      },
      suggestions: {
        chat: [
          "What are the key differences between RAG and agents?",
          "Summarize this article into three clear bullets",
          "Will it rain in Nanjing today?",
        ],
        research: [
          "Analyze the latest earnings call of a public company",
          "Track the biggest AI agent updates from the past week",
          "Extract the most important facts from an official API doc page",
        ],
        planner: [
          "Compare OpenAI, Anthropic, and Google developer strategies",
          "Plan a private deployment architecture for a research agent",
          "Break down an industry report into an execution-ready research plan",
        ],
      },
    },
    thread: {
      loading: "Loading thread...",
      ready: "Thread ready",
      fallbackTitle: "Thread",
      subtitle: {
        chat: "This thread will show the ongoing conversation.",
        research: "This thread will show live research steps, sources, and the final answer.",
        planner: "This thread will show planning steps, execution traces, and the final conclusion.",
      },
      streamFailed: "Stream failed: ",
      unknownStreamError: "Unknown stream error",
    },
    chat: {
      assistant: "DeepResearch",
      planner: "Planner",
      research: "Research",
    },
    input: {
      send: "Send",
      attachmentsSoon: "Attachments will be added in a later step",
      modeChat: "Ask",
      modeResearch: "Research",
      modePlanner: "Planner",
      placeholderChat: "Ask anything, just like a regular LLM chat...",
      placeholderResearch: "Describe a research topic and the app will search, fetch, and cite sources...",
      placeholderPlanner: "Describe a complex task and the app will decompose it before execution...",
      helperChat: "Best for direct Q&A, follow-ups, and lightweight discussion.",
      helperResearch: "Best for topics that need web search, page fetching, and cited sources.",
      helperPlanner: "Best for complex work that benefits from planning before execution.",
      quickChat: "Chat",
      quickResearch: "ReAct research",
      quickPlanner: "Planner investigation",
    },
    trace: {
      title: "Execution trace",
      steps: "steps",
      step: "Step",
    },
    runs: {
      title: "Run inspector",
      recent: "Recent runs",
      empty: "No runs have been created in this thread yet.",
      question: "Question",
      route: "Route",
      status: "Status",
      currentNode: "Current node",
      createdAt: "Created",
      updatedAt: "Updated",
      nodes: "Node timeline",
      artifacts: "Artifacts",
      checkpoints: "Checkpoints",
      noNodes: "No node results yet.",
      noArtifacts: "No artifacts yet.",
      noCheckpoints: "No checkpoints yet.",
      routeDirect: "Direct research",
      routeCode: "Code analysis",
      routePlanned: "Planned research",
      statusPending: "Pending",
      statusRunning: "Running",
      statusDone: "Done",
      statusFailed: "Failed",
      statusPaused: "Paused",
      open: "Open run panel",
      close: "Close run panel",
      select: "Open run",
      nodePending: "Waiting to run",
      active: "Active run",
      latest: "Latest run",
    },
    language: {
      zh: "中文",
      en: "English",
    },
    settings: {
      open: "Open settings",
      title: "Local settings",
      subtitle: "These values stay in this browser and drive the locally deployed frontend.",
      apiBase: "Backend API URL",
      apiBaseHint: "Point to the FastAPI service, for example http://127.0.0.1:8000",
      chatEngine: "Chat engine",
      chatEngineHint: "Leave empty to let the backend use its default engine.",
      researchEngine: "Research engine",
      researchEngineHint: "Used for ReAct research mode.",
      plannerEngine: "Planner engine",
      plannerEngineHint: "Used for planner mode.",
      researchProfile: "Research skill profile",
      researchProfileHint: "Default is react_default; switch to web_research_heavy if needed.",
      plannerProfile: "Planner skill profile",
      plannerProfileHint: "Planner mode usually uses planner.",
      reset: "Reset",
      cancel: "Cancel",
      save: "Save settings",
      status: "Current connection",
      statusReady: "Saved to local browser storage",
    },
  },
} as const;

type Dictionary = (typeof dictionary)[Locale];

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  text: Dictionary;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(() => {
    if (typeof window === "undefined") {
      return "zh";
    }
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === "zh" || saved === "en" ? saved : "zh";
  });

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      setLocale,
      text: dictionary[locale],
    }),
    [locale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error("useLocale must be used inside LocaleProvider");
  }
  return context;
}
