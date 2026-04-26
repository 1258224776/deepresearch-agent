import { DEFAULT_API_BASE, readStoredSettings } from "@/lib/settings";

function resolveBase() {
  return readStoredSettings().apiBase;
}

function resolveHeaders(init?: RequestInit) {
  const settings = readStoredSettings();
  const headers = new Headers(init?.headers ?? {});
  if (settings.apiKey.trim() && !headers.has("X-API-Key")) {
    headers.set("X-API-Key", settings.apiKey.trim());
  }
  return headers;
}

function getBaseCandidates() {
  const current = resolveBase().replace(/\/+$/, "");
  const fallback = DEFAULT_API_BASE.replace(/\/+$/, "");
  return current === fallback ? [current] : [current, fallback];
}

async function request(path: string, init?: RequestInit) {
  const headers = resolveHeaders(init);
  for (const base of getBaseCandidates()) {
    try {
      return await fetch(`${base}${path}`, { ...init, headers });
    } catch {
      // try the next candidate base
    }
  }

  const target = getBaseCandidates()[0];
  throw new Error(`API unreachable at ${target}`);
}

async function responseDetail(response: Response): Promise<string> {
  const raw = await response.text();
  if (!raw) {
    return "";
  }
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    // fall through to raw body
  }
  return raw;
}

async function requestWithPathFallback(paths: string[], init?: RequestInit) {
  let lastResponse: Response | null = null;

  for (const path of paths) {
    const response = await request(path, init);
    if (response.ok || response.status !== 404) {
      return response;
    }
    lastResponse = response;
  }

  return lastResponse ?? request(paths[0], init);
}

export type ThreadMode = "chat" | "research" | "planner";

export interface Source {
  url: string;
  title: string;
  snippet: string;
}

export interface Reference {
  cite_id: number;
  url: string;
  title: string;
  snippet: string;
}

export interface UploadedAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: number;
  text_preview?: string;
}

export interface Step {
  thought: string;
  tool: string;
  args: Record<string, unknown>;
  observation: string;
  sources: Source[];
  cite_ids: number[];
  error_type?: string | null;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  mode?: ThreadMode;
  steps?: Step[];
  references?: Reference[];
  attachments?: UploadedAttachment[];
  ts?: number;
  runId?: string;
}

export interface Thread {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  preview?: string;
  message_count?: number;
  metadata?: Record<string, unknown>;
  messages?: Message[];
}

export interface ObservationRecord {
  content: string;
  tool: string;
  args: Record<string, unknown>;
  source_keys: string[];
}

export interface SourceRecord {
  source_key: string;
  url: string;
  title: string;
  snippet: string;
  source_type: string;
  metadata: Record<string, unknown>;
}

export interface ArtifactRecord {
  artifact_id: string;
  kind: string;
  title: string;
  content: string;
  created_by: string;
  created_at: number;
}

export interface CheckpointRecord {
  checkpoint_id: string;
  run_id: string;
  node_id: string;
  status: string;
  snapshot_ref: string;
  created_at: number;
}

export interface NodeResultRecord {
  node_id: string;
  node_type: string;
  status: string;
  summary: string;
  observations: ObservationRecord[];
  source_keys: string[];
  artifacts: string[];
  error?: string | null;
  started_at?: number | null;
  finished_at?: number | null;
}

export interface RunSummary {
  run_id: string;
  thread_id: string;
  question: string;
  route_kind: string;
  status: string;
  current_node: string;
  created_at: number;
  updated_at: number;
}

export interface RunState {
  run_id: string;
  thread_id: string;
  question: string;
  route_kind: string;
  status: string;
  current_node: string;
  node_order: string[];
  node_results: Record<string, NodeResultRecord>;
  source_catalog: Record<string, SourceRecord>;
  artifacts: Record<string, ArtifactRecord>;
  context: Record<string, unknown>;
  checkpoints: CheckpointRecord[];
  created_at: number;
  updated_at: number;
}

export interface RunSnapshotEvent {
  type: "snapshot";
  run_id: string;
  status: string;
  ts: number;
  state: RunState;
}

export interface RunPingEvent {
  type: "ping";
}

export type RunStreamEvent = RunSnapshotEvent | RunPingEvent;

export interface SearchProviderInfo {
  name: string;
  enabled: boolean;
  configured: boolean;
  requested: boolean;
  env_hints: string[];
}

export interface SearchProviderCatalog {
  active_order: string[];
  providers: SearchProviderInfo[];
}

export interface EnginePresetInfo {
  name: string;
  roles: string[];
}

export interface EngineProviderInfo {
  name: string;
  model: string;
  configured: boolean;
}

export interface EngineCatalog {
  presets: EnginePresetInfo[];
  providers: EngineProviderInfo[];
}

export interface SearchProviderAttempt {
  provider: string;
  configured: boolean;
  status: string;
  result_count: number;
  added_count: number;
  error: string;
}

export interface SearchProviderSummary {
  provider: string;
  count: number;
}

export interface SearchDiagnosticsResult {
  title: string;
  url: string;
  snippet: string;
  domain: string;
  provider: string;
}

export interface SearchDiagnostics {
  query: string;
  active_order: string[];
  attempts: SearchProviderAttempt[];
  provider_summary: SearchProviderSummary[];
  results: SearchDiagnosticsResult[];
}

export interface SkillStats {
  call_count: number;
  success_count: number;
  failure_count: number;
  total_duration_ms: number;
  average_duration_ms: number;
  last_used_at: number;
  last_status: string;
  last_error: string;
}

export interface SkillInfo {
  name: string;
  description: string;
  category: string;
  required_args: string[];
  optional_args: string[];
  args_desc: Record<string, string>;
  returns_sources: boolean;
  enabled: boolean;
  configured: boolean;
  env_hints: string[];
  stats: SkillStats;
}

export interface SkillProfileInfo {
  name: string;
  description: string;
  allowed_skills: string[];
  allowed_count: number;
}

export interface SkillCatalog {
  total_skills: number;
  enabled_skills: number;
  categories: string[];
  profiles: SkillProfileInfo[];
  skills: SkillInfo[];
}

type RawMessage = Omit<Message, "runId"> & {
  run_id?: string;
  runId?: string;
};

function normalizeMessage(message: RawMessage): Message {
  return {
    ...message,
    runId: message.runId ?? message.run_id,
  };
}

function normalizeThread(thread: Thread & { messages?: RawMessage[] }): Thread {
  return {
    ...thread,
    messages: thread.messages?.map(normalizeMessage),
  };
}

export type SSEEvent =
  | { type: "message_start"; role: string; content: string }
  | { type: "text_delta"; delta: string }
  | { type: "progress"; text: string }
  | { type: "step"; thought: string; tool: string; args: Record<string, unknown>; observation: string; sources: Source[]; cite_ids: number[]; error_type?: string | null }
  | { type: "message_done"; content: string; step_count?: number; error?: string | null }
  | { type: "done"; thread_id: string; content?: string; answer?: string; step_count?: number; refs?: Reference[]; references_md?: string; error?: string | null }
  | { type: "error"; message: string }
  | { type: "ping" };

export async function createThread(title = "New chat"): Promise<Thread> {
  const res = await request(`/api/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) {
    throw new Error(`createThread: ${res.status}`);
  }
  return normalizeThread(await res.json());
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const encoded = result.split(",", 2)[1] ?? "";
      if (!encoded) {
        reject(new Error(`Failed to encode ${file.name}`));
        return;
      }
      resolve(encoded);
    };
    reader.readAsDataURL(file);
  });
}

export async function uploadAttachment(file: File): Promise<UploadedAttachment> {
  const data_base64 = await fileToBase64(file);
  const res = await request(`/api/uploads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type,
      data_base64,
    }),
  });
  if (!res.ok) {
    const detail = await responseDetail(res);
    throw new Error(detail || `uploadAttachment: ${res.status}`);
  }
  return res.json();
}

export async function listThreads(limit = 50): Promise<Thread[]> {
  const res = await request(`/api/threads?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`listThreads: ${res.status}`);
  }
  const threads = (await res.json()) as Thread[];
  return threads.map((thread) => normalizeThread(thread));
}

export async function getThread(id: string): Promise<Thread> {
  const res = await request(`/api/threads/${id}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`getThread: ${res.status}`);
  }
  return normalizeThread(await res.json());
}

export async function listThreadRuns(threadId: string, limit = 20): Promise<RunSummary[]> {
  const res = await request(`/api/threads/${threadId}/runs?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`listThreadRuns: ${res.status}`);
  }
  return res.json();
}

export async function createGraphRun(
  threadId: string,
  content: string,
  options: Pick<RunOptions, "engine" | "maxSteps" | "usePlanner" | "attachments"> = {},
): Promise<RunState> {
  const res = await request(`/api/threads/${threadId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      engine: options.engine ?? "",
      max_steps: options.maxSteps ?? 8,
      use_planner: options.usePlanner ?? false,
      attachments: (options.attachments ?? []).map((item) => item.id),
    }),
  });
  if (!res.ok) {
    throw new Error(`createGraphRun: ${res.status}`);
  }
  return res.json();
}

export async function getGraphRun(runId: string): Promise<RunState> {
  const res = await request(`/api/runs/${runId}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`getGraphRun: ${res.status}`);
  }
  return res.json();
}

export async function* streamRunEvents(
  runId: string,
  signal?: AbortSignal,
): AsyncGenerator<RunStreamEvent> {
  const res = await request(`/api/runs/${runId}/events`, {
    cache: "no-store",
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!res.ok) {
    throw new Error(`streamRunEvents: ${res.status}`);
  }

  for await (const event of parseEventStream(res)) {
    if (event.type === "ping") {
      yield { type: "ping" };
      continue;
    }

    if (event.type === "snapshot") {
      const payload = event.payload as Omit<RunSnapshotEvent, "type">;
      yield {
        type: "snapshot",
        run_id: String(payload.run_id),
        status: String(payload.status),
        ts: Number(payload.ts),
        state: payload.state as RunState,
      };
    }
  }
}

export async function resumeGraphRun(runId: string): Promise<RunState> {
  const res = await request(`/api/runs/${runId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`resumeGraphRun: ${res.status}`);
  }
  return res.json();
}

export async function getSearchProviders(): Promise<SearchProviderCatalog> {
  const res = await request(`/api/search/providers`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`getSearchProviders: ${res.status}`);
  }
  return res.json();
}

export async function getEngineCatalog(): Promise<EngineCatalog> {
  const res = await request(`/api/ai/engines`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`getEngineCatalog: ${res.status}`);
  }
  return res.json();
}

export async function getSkillCatalog(): Promise<SkillCatalog> {
  const res = await request(`/skills`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`getSkillCatalog: ${res.status}`);
  }
  return res.json();
}

export async function setSkillEnabled(name: string, enabled: boolean): Promise<SkillInfo> {
  const res = await request(`/skills/${encodeURIComponent(name)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) {
    throw new Error(`setSkillEnabled: ${res.status}`);
  }
  return res.json();
}

export async function getSearchDiagnostics(
  query: string,
  maxResults = 5,
  timelimit = "",
): Promise<SearchDiagnostics> {
  const params = new URLSearchParams({
    q: query,
    max_results: String(maxResults),
  });
  if (timelimit) {
    params.set("timelimit", timelimit);
  }
  const res = await request(`/api/search/diagnostics?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`getSearchDiagnostics: ${res.status}`);
  }
  return res.json();
}

export async function renameThread(id: string, title: string): Promise<void> {
  const res = await request(`/api/threads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) {
    throw new Error(`renameThread: ${res.status}`);
  }
}

export async function deleteThread(id: string): Promise<void> {
  const res = await request(`/api/threads/${id}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`deleteThread: ${res.status}`);
  }
}

async function* parseSSE(response: Response): AsyncGenerator<SSEEvent> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("SSE body not available");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      let eventName = "";
      let dataLine = "";

      for (const line of chunk.split("\n")) {
        if (line.startsWith("event: ")) {
          eventName = line.slice(7).trim();
        }
        if (line.startsWith("data: ")) {
          dataLine = line.slice(6).trim();
        }
      }

      if (!eventName) {
        continue;
      }

      if (!dataLine) {
        yield { type: eventName as SSEEvent["type"] } as SSEEvent;
        continue;
      }

      yield { type: eventName as SSEEvent["type"], ...JSON.parse(dataLine) } as SSEEvent;
    }
  }
}

async function* parseEventStream(
  response: Response,
): AsyncGenerator<{ type: string; payload: Record<string, unknown> }> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("SSE body not available");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      let eventName = "";
      let dataLine = "";

      for (const line of chunk.split("\n")) {
        if (line.startsWith("event: ")) {
          eventName = line.slice(7).trim();
        }
        if (line.startsWith("data: ")) {
          dataLine = line.slice(6).trim();
        }
      }

      if (!eventName) {
        continue;
      }

      yield {
        type: eventName,
        payload: dataLine ? (JSON.parse(dataLine) as Record<string, unknown>) : {},
      };
    }
  }
}

export async function* chatStream(
  threadId: string,
  content: string,
  engine = "",
  attachments: UploadedAttachment[] = [],
): AsyncGenerator<SSEEvent> {
  const response = await request(`/api/threads/${threadId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      engine,
      attachments: attachments.map((item) => item.id),
    }),
  });
  if (!response.ok) {
    throw new Error(`chatStream: ${response.status}`);
  }
  yield* parseSSE(response);
}

export interface RunOptions {
  engine?: string;
  maxSteps?: number;
  skillProfile?: string;
  usePlanner?: boolean;
  attachments?: UploadedAttachment[];
}

export async function* runThreadStream(
  threadId: string,
  content: string,
  options: RunOptions = {},
): AsyncGenerator<SSEEvent> {
  const response = await requestWithPathFallback(
    [
      `/api/threads/${threadId}/research`,
      `/api/threads/${threadId}/run`,
    ],
    {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      engine: options.engine ?? "",
      max_steps: options.maxSteps ?? 8,
      skill_profile: options.skillProfile ?? "react_default",
      use_planner: options.usePlanner ?? false,
      attachments: (options.attachments ?? []).map((item) => item.id),
    }),
    },
  );
  if (!response.ok) {
    throw new Error(`runThreadStream: ${response.status}`);
  }
  yield* parseSSE(response);
}
