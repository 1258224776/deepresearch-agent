"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Eye, Wrench, AlertCircle, Link2 } from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";
import type { Step } from "@/lib/api";

type StepTraceProps = {
  steps: Step[];
  compact?: boolean;
};

export function StepTrace({ steps, compact = false }: StepTraceProps) {
  const { text } = useLocale();
  const [open, setOpen] = useState(false);

  if (!steps.length) {
    return null;
  }

  return (
    <section className="mt-4 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]/84 shadow-[var(--shadow-sm)]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-semibold text-[var(--text-2)] transition hover:bg-[var(--surface-2)]"
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <span>{text.trace.title}</span>
        <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[11px] text-[var(--text-3)]">
          {steps.length} {text.trace.steps}
        </span>
      </button>

      {open && (
        <div className="divide-y divide-[var(--border)]">
          {steps.map((step, index) => (
            <article key={`${step.tool}-${index}`} className="space-y-3 px-4 py-4">
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-[var(--text-3)]">
                <span>
                  {text.trace.step} {index + 1}
                </span>
                <span className="h-px flex-1 bg-[var(--border)]" />
              </div>

              {step.thought && (
                <div className="flex gap-2 text-sm text-[var(--text-2)]">
                  <Eye className="mt-0.5 size-4 shrink-0 text-[var(--text-3)]" />
                  <p className="leading-6">{step.thought}</p>
                </div>
              )}

              <div className="flex items-center gap-2 text-sm text-[var(--accent)]">
                <Wrench className="size-4 shrink-0" />
                <code className="rounded-lg bg-[var(--accent-soft)] px-2.5 py-1 text-[12px] font-medium">
                  {step.tool}
                </code>
              </div>

              {Object.keys(step.args ?? {}).length > 0 && (
                <pre
                  className={cn(
                    "overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--text-2)]",
                    compact && "max-h-28",
                  )}
                >
                  {JSON.stringify(step.args, null, 2)}
                </pre>
              )}

              {step.observation && (
                <div className="rounded-xl bg-[var(--surface-2)] px-3 py-3 text-sm leading-6 text-[var(--text-2)]">
                  {step.observation}
                </div>
              )}

              {!!step.sources?.length && (
                <div className="flex flex-wrap gap-2">
                  {step.sources.slice(0, 4).map((source, sourceIndex) => (
                    <a
                      key={`${source.url}-${sourceIndex}`}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex max-w-full items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs text-[var(--text-2)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
                    >
                      <Link2 className="size-3 shrink-0" />
                      <span className="truncate">{source.title || source.url}</span>
                    </a>
                  ))}
                </div>
              )}

              {step.error_type && (
                <div className="inline-flex items-center gap-2 rounded-full bg-[#fcedea] px-3 py-1 text-xs font-medium text-[var(--danger)]">
                  <AlertCircle className="size-3.5" />
                  <span>{step.error_type}</span>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
