"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { ChatStream } from "@/components/chat-stream";
import { InputBox, type SendMode } from "@/components/input-box";
import { useLocale } from "@/components/locale-provider";
import { RunDrawer } from "@/components/run-drawer";
import { useSettings } from "@/components/settings-provider";
import { WorkspaceShell } from "@/components/workspace-shell";
import {
  chatStream,
  createGraphRun,
  getGraphRun,
  getThread,
  listThreadRuns,
  streamRunEvents,
  type Reference,
  type Message,
  type RunState,
  type RunSummary,
  type Step,
  type Thread,
} from "@/lib/api";

const DRAFT_PREFIX = "deepresearch:draft:";
const RUN_POLL_INTERVAL_MS = 1000;

function toRunSummary(state: RunState): RunSummary {
  return {
    run_id: state.run_id,
    thread_id: state.thread_id,
    question: state.question,
    route_kind: state.route_kind,
    status: state.status,
    current_node: state.current_node,
    created_at: state.created_at,
    updated_at: state.updated_at,
  };
}

function sortRunSummaries(items: RunSummary[]) {
  return [...items].sort((a, b) => b.updated_at - a.updated_at);
}

export default function ThreadPage() {
  const params = useParams<{ id: string }>();
  const threadId = params?.id;
  const { text } = useLocale();
  const { settings } = useSettings();

  const [thread, setThread] = useState<Thread | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingThread, setLoadingThread] = useState(true);
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingSteps, setStreamingSteps] = useState<Step[]>([]);
  const [progressText, setProgressText] = useState("");
  const [streamingMode, setStreamingMode] = useState<Message["mode"]>("chat");
  const [composerMode, setComposerMode] = useState<SendMode>("chat");
  const [runSummaries, setRunSummaries] = useState<RunSummary[]>([]);
  const [runStates, setRunStates] = useState<Record<string, RunState>>({});
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runPanelOpen, setRunPanelOpen] = useState(false);
  const [loadingRunDetail, setLoadingRunDetail] = useState(false);

  const draftConsumed = useRef(false);

  const upsertRunState = useCallback((state: RunState) => {
    setRunStates((current) => ({ ...current, [state.run_id]: state }));
    setRunSummaries((current) => {
      const next = current.filter((item) => item.run_id !== state.run_id);
      next.unshift(toRunSummary(state));
      return sortRunSummaries(next);
    });
  }, []);

  const buildRunProgressText = useCallback(
    (state: RunState) => {
      if (state.status === "failed") {
        const error = String(state.context.error ?? "").trim();
        return error ? `${text.runs.statusFailed}: ${error}` : text.runs.statusFailed;
      }
      if (state.status === "done") {
        return text.runs.statusDone;
      }
      if (state.current_node) {
        return `${text.runs.statusRunning}: ${state.current_node}`;
      }
      return text.runs.statusRunning;
    },
    [text.runs.statusDone, text.runs.statusFailed, text.runs.statusRunning],
  );

  const applyRunSnapshot = useCallback(
    (snapshot: RunState) => {
      upsertRunState(snapshot);
      setProgressText((current) => (current ? buildRunProgressText(snapshot) : current));
    },
    [buildRunProgressText, upsertRunState],
  );

  const loadThreadData = useCallback(async () => {
    if (!threadId) {
      return;
    }

    setLoadingThread(true);
    try {
      const [threadData, summaries] = await Promise.all([
        getThread(threadId),
        listThreadRuns(threadId),
      ]);
      setThread(threadData);
      setMessages(threadData.messages ?? []);
      setRunSummaries(sortRunSummaries(summaries));
      setSelectedRunId((current) => {
        if (current && summaries.some((summary) => summary.run_id === current)) {
          return current;
        }
        return summaries[0]?.run_id ?? null;
      });
    } finally {
      setLoadingThread(false);
    }
  }, [threadId]);

  const finalizeRunTracking = useCallback(async () => {
    setSending(false);
    setStreamingContent("");
    setStreamingSteps([]);
    setProgressText("");
    await new Promise((resolve) => window.setTimeout(resolve, 120));
    await loadThreadData();
    window.dispatchEvent(new Event("threads:changed"));
  }, [loadThreadData]);

  const loadRunDetail = useCallback(
    async (runId: string) => {
      setLoadingRunDetail(true);
      try {
        const state = await getGraphRun(runId);
        upsertRunState(state);
        return state;
      } finally {
        setLoadingRunDetail(false);
      }
    },
    [upsertRunState],
  );

  useEffect(() => {
    void loadThreadData();
  }, [loadThreadData, settings.apiBase]);

  useEffect(() => {
    if (!selectedRunId || runStates[selectedRunId]) {
      return;
    }
    void loadRunDetail(selectedRunId);
  }, [loadRunDetail, runStates, selectedRunId]);

  const selectedRun = selectedRunId ? runStates[selectedRunId] ?? null : null;
  const selectedRunStatus = selectedRun?.status;

  useEffect(() => {
    if (!selectedRunId || selectedRunStatus !== "running") {
      return;
    }

    const runId = selectedRunId;
    const abortController = new AbortController();
    let cancelled = false;

    async function finalizeIfTerminal(snapshot: RunState) {
      if (snapshot.status !== "done" && snapshot.status !== "failed") {
        return false;
      }
      await finalizeRunTracking();
      return true;
    }

    async function pollFallback() {
      while (!cancelled) {
        const snapshot = await getGraphRun(runId);
        if (cancelled) {
          return;
        }

        applyRunSnapshot(snapshot);

        if (await finalizeIfTerminal(snapshot)) {
          return;
        }

        await new Promise((resolve) => window.setTimeout(resolve, RUN_POLL_INTERVAL_MS));
      }
    }

    async function consumeRunEvents() {
      let reachedTerminal = false;

      try {
        const stream = streamRunEvents(runId, abortController.signal);
        for await (const event of stream) {
          if (cancelled) {
            return;
          }
          if (event.type !== "snapshot") {
            continue;
          }

          applyRunSnapshot(event.state);
          if (await finalizeIfTerminal(event.state)) {
            reachedTerminal = true;
            return;
          }
        }
      } catch {
        if (cancelled || abortController.signal.aborted) {
          return;
        }
      }

      if (!cancelled && !reachedTerminal) {
        await pollFallback();
      }
    }

    void consumeRunEvents();
    return () => {
      cancelled = true;
      abortController.abort();
    };
  }, [applyRunSnapshot, finalizeRunTracking, selectedRunId, selectedRunStatus]);

  const handleSelectRun = useCallback(
    async (runId: string) => {
      setSelectedRunId(runId);
      setRunPanelOpen(true);
      if (!runStates[runId]) {
        await loadRunDetail(runId);
      }
    },
    [loadRunDetail, runStates],
  );

  const handleSend = useCallback(
    async (content: string, mode: SendMode) => {
      if (!threadId) {
        return;
      }

      const optimisticUser: Message = {
        role: "user",
        content,
        mode,
        ts: Date.now(),
      };

      setMessages((current) => [...current, optimisticUser]);
      setSending(true);
      setStreamingContent("");
      setStreamingSteps([]);
      setProgressText("");
      setStreamingMode(mode);
      setComposerMode(mode);

      try {
        if (mode === "chat") {
          let finalContent = "";
          let finalReferences: Reference[] | undefined;
          let collectedSteps: Step[] = [];

          const stream = chatStream(threadId, content, settings.chatEngine);
          for await (const event of stream) {
            if (event.type === "text_delta") {
              finalContent += event.delta;
              setStreamingContent(finalContent);
              continue;
            }

            if (event.type === "progress") {
              setProgressText(event.text);
              continue;
            }

            if (event.type === "step") {
              collectedSteps = [...collectedSteps, event];
              setStreamingSteps(collectedSteps);
              continue;
            }

            if (event.type === "message_done") {
              finalContent = event.content;
              setStreamingContent(finalContent);
              continue;
            }

            if (event.type === "done") {
              finalContent = event.answer ?? event.content ?? finalContent;
              finalReferences = event.refs;
              setStreamingContent(finalContent);
              continue;
            }

            if (event.type === "error") {
              throw new Error(event.message);
            }
          }

          if (finalContent) {
            setMessages((current) => [
              ...current,
              {
                role: "assistant",
                content: finalContent,
                mode,
                steps: collectedSteps.length ? collectedSteps : undefined,
                references: finalReferences,
                ts: Date.now(),
              },
            ]);
            setStreamingContent("");
            setStreamingSteps([]);
            setProgressText("");
          }

          await loadThreadData();
          window.dispatchEvent(new Event("threads:changed"));
          setSending(false);
          return;
        }

        const run = await createGraphRun(threadId, content, {
          engine: mode === "planner" ? settings.plannerEngine : settings.researchEngine,
          maxSteps: 8,
          usePlanner: mode === "planner",
        });

        upsertRunState(run);
        setSelectedRunId(run.run_id);
        setRunPanelOpen(true);
        setProgressText(buildRunProgressText(run));
        await loadThreadData();
        window.dispatchEvent(new Event("threads:changed"));
      } catch (error) {
        const message = error instanceof Error ? error.message : text.thread.unknownStreamError;
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            content: `${text.thread.streamFailed}${message}`,
            mode,
            ts: Date.now(),
          },
        ]);
        setSending(false);
        setStreamingContent("");
        setStreamingSteps([]);
        setProgressText("");
      }
    },
    [
      buildRunProgressText,
      loadThreadData,
      settings.chatEngine,
      settings.plannerEngine,
      settings.researchEngine,
      text.thread.streamFailed,
      text.thread.unknownStreamError,
      threadId,
      upsertRunState,
    ],
  );

  useEffect(() => {
    if (!threadId || loadingThread || draftConsumed.current) {
      return;
    }

    const raw = sessionStorage.getItem(`${DRAFT_PREFIX}${threadId}`);
    if (!raw) {
      return;
    }

    draftConsumed.current = true;
    sessionStorage.removeItem(`${DRAFT_PREFIX}${threadId}`);

    try {
      const draft = JSON.parse(raw) as { content?: string; mode?: SendMode };
      if (draft.content?.trim()) {
        setComposerMode(draft.mode ?? "chat");
        void handleSend(draft.content, draft.mode ?? "chat");
      }
    } catch {
      // ignore malformed draft payload
    }
  }, [handleSend, loadingThread, threadId]);

  function handleSuggestionClick(suggestion: string) {
    void handleSend(suggestion, composerMode);
  }

  const subtitle = useMemo(() => {
    if (!thread) {
      return text.thread.loading;
    }
    return thread.preview || text.thread.ready;
  }, [text.thread.loading, text.thread.ready, thread]);

  const hasRunningRun = runSummaries.some((summary) => summary.status === "running");

  return (
    <WorkspaceShell
      title={thread?.title || text.thread.fallbackTitle}
      subtitle={subtitle}
      inspector={
        <RunDrawer
          open={runPanelOpen}
          summaries={runSummaries}
          activeRunId={selectedRunId}
          activeRun={selectedRun}
          loading={loadingRunDetail}
          onClose={() => setRunPanelOpen(false)}
          onSelectRun={(runId) => void handleSelectRun(runId)}
        />
      }
      inspectorOpen={runPanelOpen}
      inspectorBusy={hasRunningRun}
      onInspectorToggle={() => setRunPanelOpen((value) => !value)}
      composer={
        <InputBox
          loading={sending}
          mode={composerMode}
          onModeChange={setComposerMode}
          onSend={handleSend}
        />
      }
    >
      <ChatStream
        title={loadingThread ? text.thread.loading : thread?.title || text.thread.fallbackTitle}
        subtitle={text.thread.subtitle[composerMode]}
        messages={messages}
        currentMode={composerMode}
        onRunClick={(runId) => void handleSelectRun(runId)}
        onSuggestionClick={handleSuggestionClick}
        suggestions={text.home.suggestions[composerMode]}
        progressText={progressText}
        streamingContent={streamingContent}
        streamingMode={streamingMode}
        streamingSteps={streamingSteps}
      />
    </WorkspaceShell>
  );
}
