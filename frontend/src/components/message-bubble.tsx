"use client";

import { Bot, Paperclip, Sparkles, Waypoints } from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import { StepTrace } from "@/components/step-trace";
import type { Message, Step } from "@/lib/api";
import { cn } from "@/lib/utils";

function AttachmentChips({
  attachments,
  variant = "surface",
}: {
  attachments?: Message["attachments"];
  variant?: "surface" | "accent";
}) {
  if (!attachments?.length) {
    return null;
  }

  const chipClass =
    variant === "accent"
      ? "border-white/20 bg-white/10 text-white"
      : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-2)]";

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {attachments.map((attachment) => (
        <span
          key={attachment.id}
          className={cn(
            "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium",
            chipClass,
          )}
        >
          <Paperclip className="size-3" />
          <span className="max-w-[12rem] truncate">{attachment.filename}</span>
        </span>
      ))}
    </div>
  );
}

function escapeHtml(input: string) {
  return input
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdown(input: string) {
  const safe = escapeHtml(input);
  return safe
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/^\- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[hupol]|<\/)(.+)$/gm, "<p>$1</p>");
}

function ModeBadge({
  mode,
  plannerLabel,
  researchLabel,
}: {
  mode?: Message["mode"];
  plannerLabel: string;
  researchLabel: string;
}) {
  if (!mode || mode === "chat") {
    return null;
  }

  const label = mode === "planner" ? plannerLabel : researchLabel;
  return (
    <span className="inline-flex items-center rounded-full bg-[var(--accent-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--accent)]">
      {label}
    </span>
  );
}

export function MessageBubble({
  message,
  onRunClick,
}: {
  message: Message;
  onRunClick?: (runId: string) => void;
}) {
  const { text } = useLocale();

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-3xl rounded-[24px] rounded-br-md bg-[var(--accent)] px-4 py-3 text-sm leading-7 text-white shadow-[var(--shadow-sm)]">
          {message.content}
          <AttachmentChips attachments={message.attachments} variant="accent" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-4">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-2xl bg-[var(--surface-2)] text-[var(--accent)] shadow-[var(--shadow-sm)]">
        <Bot className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-3 flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--text-1)]">{text.chat.assistant}</span>
          <ModeBadge
            mode={message.mode}
            plannerLabel={text.chat.planner}
            researchLabel={text.chat.research}
          />
          {message.runId && (
            <button
              type="button"
              onClick={() => onRunClick?.(message.runId as string)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-2)] transition",
                "hover:border-[var(--accent)] hover:text-[var(--accent)]",
              )}
            >
              <Waypoints className="size-3" />
              <span>{message.runId.slice(0, 8)}</span>
            </button>
          )}
        </div>
        <div
          className="prose-warm max-w-none text-sm leading-7 text-[var(--text-1)]"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
        />
        <AttachmentChips attachments={message.attachments} />
        {!!message.steps?.length && <StepTrace steps={message.steps} />}
      </div>
    </div>
  );
}

export function StreamingBubble({
  content,
  steps,
  progressText,
  mode,
}: {
  content: string;
  steps: Step[];
  progressText?: string;
  mode?: Message["mode"];
}) {
  const { text } = useLocale();

  return (
    <div className="flex gap-4">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)] shadow-[var(--shadow-sm)]">
        <Sparkles className="h-4 w-4 animate-pulse" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-3 flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--text-1)]">{text.chat.assistant}</span>
          <ModeBadge mode={mode} plannerLabel={text.chat.planner} researchLabel={text.chat.research} />
        </div>

        {progressText && <p className="mb-3 text-xs text-[var(--text-3)]">{progressText}</p>}

        {!content && !steps.length && (
          <div className="flex items-center gap-1.5 py-2">
            {[0, 1, 2].map((index) => (
              <span
                key={index}
                className="size-2 animate-bounce rounded-full bg-[var(--accent)]"
                style={{ animationDelay: `${index * 120}ms` }}
              />
            ))}
          </div>
        )}

        {content && (
          <div className="prose-warm max-w-none text-sm leading-7 text-[var(--text-1)]">
            <div dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
            <span className="inline-block animate-pulse text-[var(--accent)]">|</span>
          </div>
        )}

        {!!steps.length && <StepTrace steps={steps} compact />}
      </div>
    </div>
  );
}
