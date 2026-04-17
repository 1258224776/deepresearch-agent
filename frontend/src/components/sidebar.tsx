"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { MoreHorizontal, PencilLine, Plus, Search, Trash2 } from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import { SettingsDialog } from "@/components/settings-dialog";
import { useSettings } from "@/components/settings-provider";
import { cn } from "@/lib/utils";
import { deleteThread, listThreads, type Thread } from "@/lib/api";

function formatTime(timestamp: number, locale: "zh" | "en") {
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

export function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { locale, text } = useLocale();
  const { settings } = useSettings();
  const activeId = pathname.startsWith("/chat/") ? pathname.split("/").at(-1) : undefined;

  const [threads, setThreads] = useState<Thread[]>([]);
  const [query, setQuery] = useState("");
  const [loadError, setLoadError] = useState("");

  const fetchThreads = useCallback(async () => {
    try {
      setThreads(await listThreads());
      setLoadError("");
    } catch {
      setLoadError(settings.apiBase);
      // keep sidebar usable while backend is unavailable
    }
  }, [settings.apiBase]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        const data = await listThreads();
        if (!cancelled) {
          setThreads(data);
          setLoadError("");
        }
      } catch {
        if (!cancelled) {
          setLoadError(settings.apiBase);
        }
        // keep sidebar usable while backend is unavailable
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [activeId, settings.apiBase]);

  useEffect(() => {
    const handler = () => {
      void fetchThreads();
    };
    window.addEventListener("threads:changed", handler);
    return () => window.removeEventListener("threads:changed", handler);
  }, [fetchThreads]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) {
      return threads;
    }
    return threads.filter((thread) => {
      return [thread.title, thread.preview ?? ""].join(" ").toLowerCase().includes(keyword);
    });
  }, [query, threads]);

  function handleCreateThread() {
    router.push("/");
  }

  async function handleDelete(threadId: string) {
    await deleteThread(threadId);
    window.dispatchEvent(new Event("threads:changed"));
    if (activeId === threadId) {
      router.push("/");
    }
  }

  return (
    <aside className="flex h-full w-[280px] shrink-0 flex-col border-r border-[var(--border)] bg-[var(--sidebar)]">
      <div className="border-b border-[var(--border)] px-4 pb-4 pt-5">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)] shadow-[var(--shadow-sm)]">
            <PencilLine className="size-4.5" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--text-1)]">{text.shell.appTitle}</p>
            <p className="text-xs text-[var(--text-3)]">{text.shell.appSubtitle}</p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleCreateThread}
          className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[var(--accent)] px-4 py-3 text-sm font-semibold text-white shadow-[var(--shadow-sm)] transition hover:brightness-95"
        >
          <Plus className="size-4" />
          <span>{text.sidebar.newChat}</span>
        </button>

        <label className="mt-4 flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 shadow-[var(--shadow-sm)]">
          <Search className="size-4 text-[var(--text-3)]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={text.sidebar.searchChats}
            className="w-full border-none bg-transparent text-sm text-[var(--text-1)] outline-none placeholder:text-[var(--text-3)]"
          />
        </label>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        {loadError && (
          <div className="mb-4 rounded-2xl border border-[var(--danger)]/18 bg-[#fcedea] px-3 py-3 text-xs leading-6 text-[var(--danger)]">
            API unavailable: {loadError}
          </div>
        )}

        <div className="mb-3 px-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-3)]">
          {text.sidebar.recentChats}
        </div>

        <div className="space-y-1.5">
          {filtered.map((thread) => {
            const active = thread.id === activeId;
            return (
              <div
                key={thread.id}
                className={cn(
                  "group rounded-2xl border border-transparent px-3 py-3 transition",
                  active
                    ? "border-[var(--accent-soft)] bg-[var(--surface)] shadow-[var(--shadow-sm)]"
                    : "hover:bg-[var(--surface)]/70",
                )}
              >
                <div className="flex items-start gap-3">
                  <button
                    type="button"
                    onClick={() => router.push(`/chat/${thread.id}`)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="truncate text-sm font-medium text-[var(--text-1)]">{thread.title}</div>
                    <div className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-3)]">
                      {thread.preview || text.sidebar.noMessages}
                    </div>
                    <div className="mt-2 text-[11px] text-[var(--text-3)]">
                      {formatTime(thread.updated_at, locale)}
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => void handleDelete(thread.id)}
                    className="opacity-0 transition group-hover:opacity-100 rounded-xl p-2 text-[var(--text-3)] hover:bg-[var(--surface-2)] hover:text-[var(--danger)]"
                    title={text.sidebar.deleteThread}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </div>
            );
          })}

          {filtered.length === 0 && (
            <div className="rounded-2xl border border-dashed border-[var(--border)] px-4 py-8 text-center text-sm text-[var(--text-3)]">
              {text.sidebar.noChats}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-[var(--border)] px-4 py-4 text-xs text-[var(--text-3)]">
        <SettingsDialog />
        <div className="mb-1 mt-4 flex items-center gap-2 text-[var(--text-2)]">
          <MoreHorizontal className="size-4" />
          <span>{settings.apiBase}</span>
        </div>
        <p>{text.sidebar.stageLabel}</p>
      </div>
    </aside>
  );
}
