"use client";

import type { ReactNode } from "react";
import { Activity, Share2 } from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Sidebar } from "@/components/sidebar";
import { cn } from "@/lib/utils";

type WorkspaceShellProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  composer: ReactNode;
  inspector?: ReactNode;
  inspectorOpen?: boolean;
  inspectorBusy?: boolean;
  onInspectorToggle?: () => void;
};

export function WorkspaceShell({
  title,
  subtitle,
  children,
  composer,
  inspector,
  inspectorOpen = false,
  inspectorBusy = false,
  onInspectorToggle,
}: WorkspaceShellProps) {
  const { text } = useLocale();

  return (
    <div className="relative flex h-dvh bg-[var(--bg)] text-[var(--text-1)]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b border-[var(--border)] bg-[var(--surface)]/90 px-6 backdrop-blur-sm">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-[var(--text-1)]">{title}</div>
            <div className="truncate text-xs text-[var(--text-3)]">{subtitle}</div>
          </div>
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <button
              type="button"
              onClick={onInspectorToggle}
              className={cn(
                "relative inline-flex size-10 items-center justify-center rounded-2xl border bg-[var(--surface)] shadow-[var(--shadow-sm)] transition",
                inspectorOpen || inspectorBusy
                  ? "border-[var(--accent)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--text-2)] hover:border-[var(--accent)] hover:text-[var(--accent)]",
              )}
              title={text.shell.runStatus}
            >
              <Activity className="size-4" />
              {inspectorBusy && (
                <span className="absolute right-2 top-2 size-2 rounded-full bg-[var(--accent)] shadow-[0_0_0_3px_rgba(194,87,26,0.16)]" />
              )}
            </button>
            <button
              type="button"
              className="inline-flex size-10 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--surface)] text-[var(--text-2)] shadow-[var(--shadow-sm)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
              title={text.shell.share}
            >
              <Share2 className="size-4" />
            </button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          <div className="min-h-full">{children}</div>
          <div className="sticky bottom-0 z-10 bg-gradient-to-t from-[var(--bg)] via-[var(--bg)]/94 to-transparent px-6 pb-6 pt-8">
            <div className="mx-auto w-full max-w-4xl">{composer}</div>
          </div>
        </main>
      </div>

      {inspector && (
        <>
          <button
            type="button"
            aria-label={text.runs.close}
            onClick={onInspectorToggle}
            className={cn(
              "absolute inset-0 z-20 bg-[#261812]/18 transition",
              inspectorOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
            )}
          />
          <aside
            className={cn(
              "absolute inset-y-0 right-0 z-30 w-full max-w-[26rem] border-l border-[var(--border)] bg-[var(--sidebar)] shadow-[-24px_0_60px_rgba(37,24,18,0.14)] transition-transform duration-200",
              inspectorOpen ? "translate-x-0" : "translate-x-full",
            )}
          >
            {inspector}
          </aside>
        </>
      )}
    </div>
  );
}
