"use client";

import { AlertTriangle, Clock3, FileText, ImageIcon, Layers3, Loader2, Waypoints, X } from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import type { ArtifactRecord, NodeResultRecord, RunState, RunSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

type RunDrawerProps = {
  open: boolean;
  summaries: RunSummary[];
  activeRunId?: string | null;
  activeRun?: RunState | null;
  loading?: boolean;
  onClose: () => void;
  onSelectRun: (runId: string) => void;
};

function formatTimestamp(timestamp: number | null | undefined, locale: "zh" | "en") {
  if (!timestamp) {
    return "-";
  }

  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

function maybeFormatJson(content: string) {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

type MemoryHitItem = {
  id?: string;
  thread_id?: string;
  thread_title?: string;
  question?: string;
  title?: string;
  content?: string;
  created_at?: number;
  semantic_score?: number;
  rank_score?: number;
};

type MemoryHitsPayload = {
  count?: number;
  items?: MemoryHitItem[];
};

type MemoryWritebackPayload = {
  item_count?: number;
  written_count?: number;
  items?: string[];
  error?: string;
};

function parseArtifactPayload<T>(content: string): T | null {
  try {
    return JSON.parse(content) as T;
  } catch {
    return null;
  }
}

function formatScore(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(2);
}

function MemoryHitsArtifact({ artifact }: { artifact: ArtifactRecord }) {
  const payload = parseArtifactPayload<MemoryHitsPayload>(artifact.content);
  const items = payload?.items ?? [];

  if (items.length === 0) {
    return (
      <div className="border-t border-[var(--border)] bg-[var(--surface-2)] px-4 py-4 text-sm text-[var(--text-3)]">
        No prior memory hits.
      </div>
    );
  }

  return (
    <div className="space-y-3 border-t border-[var(--border)] bg-[var(--surface-2)] px-4 py-4">
      {items.map((item, index) => (
        <div key={item.id || `${item.thread_id || "memory"}-${index}`} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold text-[var(--text-1)]">{item.thread_title || item.thread_id || "Unknown thread"}</div>
            <div className="inline-flex items-center rounded-full bg-[var(--accent-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--accent)]">
              Score {formatScore(item.rank_score ?? item.semantic_score)}
            </div>
          </div>
          {(item.title || item.question) && (
            <div className="mt-2 text-xs text-[var(--text-3)]">{item.title || item.question}</div>
          )}
          <p className="mt-2 text-sm leading-6 text-[var(--text-2)]">{item.content || "-"}</p>
        </div>
      ))}
    </div>
  );
}

function MemoryWritebackArtifact({ artifact }: { artifact: ArtifactRecord }) {
  const payload = parseArtifactPayload<MemoryWritebackPayload>(artifact.content);
  const items = payload?.items ?? [];
  const itemCount = payload?.item_count ?? items.length;
  const writtenCount = payload?.written_count ?? 0;

  return (
    <div className="space-y-3 border-t border-[var(--border)] bg-[var(--surface-2)] px-4 py-4">
      <div className="flex flex-wrap gap-2">
        <div className="inline-flex items-center rounded-full bg-[var(--surface)] px-3 py-1 text-[11px] font-semibold text-[var(--text-2)]">
          Extracted {itemCount}
        </div>
        <div className="inline-flex items-center rounded-full bg-[#e8f6ef] px-3 py-1 text-[11px] font-semibold text-[#0f8a58]">
          Written {writtenCount}
        </div>
      </div>
      {payload?.error && (
        <div className="rounded-2xl border border-[#f4d3cd] bg-[#fcedea] px-4 py-3 text-sm text-[var(--danger)]">
          {payload.error}
        </div>
      )}
      {items.length > 0 && (
        <div className="space-y-2">
          {items.map((item, index) => (
            <div key={`${artifact.artifact_id}-item-${index}`} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm leading-6 text-[var(--text-2)]">
              {item}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ImageArtifact({ artifact }: { artifact: ArtifactRecord }) {
  return (
    <div className="border-t border-[var(--border)] bg-[var(--surface-2)] px-4 py-4">
      <img
        src={artifact.content}
        alt={artifact.title || artifact.kind}
        className="w-full rounded-2xl border border-[var(--border)] bg-white object-contain"
      />
    </div>
  );
}

function useRunLabels() {
  const { text } = useLocale();

  function statusLabel(status: string) {
    switch ((status || "").toLowerCase()) {
      case "done":
        return text.runs.statusDone;
      case "failed":
        return text.runs.statusFailed;
      case "paused":
        return text.runs.statusPaused;
      case "running":
        return text.runs.statusRunning;
      default:
        return text.runs.statusPending;
    }
  }

  function routeLabel(routeKind: string) {
    if (routeKind === "planned_research") {
      return text.runs.routePlanned;
    }
    if (routeKind === "code_research") {
      return text.runs.routeCode;
    }
    return text.runs.routeDirect;
  }

  return { routeLabel, statusLabel };
}

function StatusBadge({ status }: { status: string }) {
  const { statusLabel } = useRunLabels();

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold",
        status === "done" && "bg-[#e8f6ef] text-[#0f8a58]",
        status === "running" && "bg-[var(--accent-soft)] text-[var(--accent)]",
        status === "failed" && "bg-[#fcedea] text-[var(--danger)]",
        status !== "done" &&
          status !== "running" &&
          status !== "failed" &&
          "bg-[var(--surface-2)] text-[var(--text-3)]",
      )}
    >
      {statusLabel(status)}
    </span>
  );
}

function NodeCard({ nodeId, result }: { nodeId: string; result?: NodeResultRecord }) {
  const { locale, text } = useLocale();
  const status = result?.status ?? "pending";
  const summary = result?.error || result?.summary || text.runs.nodePending;

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-[var(--shadow-sm)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[var(--text-1)]">{nodeId}</div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-3)]">
            {result?.node_type || "node"}
          </div>
        </div>
        <StatusBadge status={status} />
      </div>

      <p className="text-sm leading-6 text-[var(--text-2)]">{summary}</p>

      {(result?.started_at || result?.finished_at) && (
        <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-[var(--text-3)]">
          <span>{text.runs.createdAt}: {formatTimestamp(result?.started_at, locale)}</span>
          <span>{text.runs.updatedAt}: {formatTimestamp(result?.finished_at, locale)}</span>
        </div>
      )}
    </div>
  );
}

function ArtifactCard({ artifact }: { artifact: ArtifactRecord }) {
  const isImage = artifact.kind === "image_png" && artifact.content.startsWith("data:image/png;base64,");
  const detailsOpen = artifact.kind === "report" || artifact.kind === "memory_hits" || isImage;

  return (
    <details
      className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-sm)]"
      open={detailsOpen}
    >
      <summary className="cursor-pointer list-none px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-[var(--text-1)]">{artifact.title || artifact.kind}</div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-3)]">{artifact.kind}</div>
          </div>
          {isImage ? (
            <ImageIcon className="size-4 text-[var(--text-3)]" />
          ) : (
            <FileText className="size-4 text-[var(--text-3)]" />
          )}
        </div>
      </summary>
      {artifact.kind === "memory_hits" ? (
        <MemoryHitsArtifact artifact={artifact} />
      ) : artifact.kind === "memory_writeback" ? (
        <MemoryWritebackArtifact artifact={artifact} />
      ) : isImage ? (
        <ImageArtifact artifact={artifact} />
      ) : (
        <div className="border-t border-[var(--border)] bg-[var(--surface-2)] px-4 py-4">
          <pre className="whitespace-pre-wrap text-xs leading-6 text-[var(--text-2)]">
            {maybeFormatJson(artifact.content)}
          </pre>
        </div>
      )}
    </details>
  );
}

export function RunDrawer({
  open,
  summaries,
  activeRunId,
  activeRun,
  loading = false,
  onClose,
  onSelectRun,
}: RunDrawerProps) {
  const { locale, text } = useLocale();
  const { routeLabel } = useRunLabels();
  const artifacts = activeRun
    ? Object.values(activeRun.artifacts).sort((a, b) => a.created_at - b.created_at)
    : [];

  return (
    <div className="flex h-full flex-col bg-[var(--sidebar)]" data-open={open}>
      <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
        <div>
          <div className="text-sm font-semibold text-[var(--text-1)]">{text.runs.title}</div>
          <div className="text-xs text-[var(--text-3)]">
            {activeRun ? text.runs.active : text.runs.latest}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex size-9 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--surface)] text-[var(--text-2)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
          title={text.runs.close}
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <section>
          <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">
            <Clock3 className="size-3.5" />
            <span>{text.runs.recent}</span>
          </div>
          <div className="space-y-2">
            {summaries.length === 0 && (
              <div className="rounded-2xl border border-dashed border-[var(--border)] px-4 py-8 text-sm text-[var(--text-3)]">
                {text.runs.empty}
              </div>
            )}

            {summaries.map((summary) => (
              <button
                key={summary.run_id}
                type="button"
                onClick={() => onSelectRun(summary.run_id)}
                className={cn(
                  "w-full rounded-2xl border px-4 py-3 text-left transition",
                  summary.run_id === activeRunId
                    ? "border-[var(--accent)] bg-[var(--surface)] shadow-[var(--shadow-sm)]"
                    : "border-[var(--border)] bg-[var(--surface)]/72 hover:border-[var(--border-hover)]",
                )}
              >
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div className="line-clamp-2 text-sm font-medium leading-6 text-[var(--text-1)]">
                    {summary.question}
                  </div>
                  <StatusBadge status={summary.status} />
                </div>
                <div className="flex flex-wrap gap-3 text-[11px] text-[var(--text-3)]">
                  <span>{routeLabel(summary.route_kind)}</span>
                  <span>{formatTimestamp(summary.updated_at, locale)}</span>
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="mt-6">
          {loading && (
            <div className="flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 text-sm text-[var(--text-2)]">
              <Loader2 className="size-4 animate-spin" />
              <span>{text.thread.loading}</span>
            </div>
          )}

          {!loading && activeRun && (
            <div className="space-y-6">
              <div className="rounded-3xl border border-[var(--border)] bg-[var(--surface)] px-5 py-5 shadow-[var(--shadow-sm)]">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-[var(--text-1)]">{activeRun.question}</div>
                  <StatusBadge status={activeRun.status} />
                </div>
                <div className="grid gap-3 text-sm text-[var(--text-2)]">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-3)]">{text.runs.route}</div>
                    <div className="mt-1">{routeLabel(activeRun.route_kind)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-3)]">{text.runs.currentNode}</div>
                    <div className="mt-1">{activeRun.current_node || "-"}</div>
                  </div>
                  <div className="flex flex-wrap gap-4 text-[12px] text-[var(--text-3)]">
                    <span>{text.runs.createdAt}: {formatTimestamp(activeRun.created_at, locale)}</span>
                    <span>{text.runs.updatedAt}: {formatTimestamp(activeRun.updated_at, locale)}</span>
                  </div>
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">
                  <Waypoints className="size-3.5" />
                  <span>{text.runs.nodes}</span>
                </div>
                <div className="space-y-3">
                  {activeRun.node_order.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-[var(--border)] px-4 py-6 text-sm text-[var(--text-3)]">
                      {text.runs.noNodes}
                    </div>
                  )}
                  {activeRun.node_order.map((nodeId) => (
                    <NodeCard key={nodeId} nodeId={nodeId} result={activeRun.node_results[nodeId]} />
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">
                  <Layers3 className="size-3.5" />
                  <span>{text.runs.artifacts}</span>
                </div>
                <div className="space-y-3">
                  {artifacts.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-[var(--border)] px-4 py-6 text-sm text-[var(--text-3)]">
                      {text.runs.noArtifacts}
                    </div>
                  )}
                  {artifacts.map((artifact) => (
                    <ArtifactCard key={artifact.artifact_id} artifact={artifact} />
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">
                  <AlertTriangle className="size-3.5" />
                  <span>{text.runs.checkpoints}</span>
                </div>
                <div className="space-y-2">
                  {activeRun.checkpoints.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-[var(--border)] px-4 py-6 text-sm text-[var(--text-3)]">
                      {text.runs.noCheckpoints}
                    </div>
                  )}
                  {activeRun.checkpoints.map((checkpoint) => (
                    <div
                      key={checkpoint.checkpoint_id}
                      className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-2)] shadow-[var(--shadow-sm)]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium text-[var(--text-1)]">{checkpoint.node_id}</div>
                        <StatusBadge status={checkpoint.status} />
                      </div>
                      <div className="mt-2 text-[12px] text-[var(--text-3)]">
                        {formatTimestamp(checkpoint.created_at, locale)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {!loading && !activeRun && summaries.length > 0 && (
            <div className="rounded-2xl border border-dashed border-[var(--border)] px-4 py-8 text-sm text-[var(--text-3)]">
              {text.runs.select}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
