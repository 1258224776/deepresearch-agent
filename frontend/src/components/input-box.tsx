"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  Loader2,
  Paperclip,
  Search,
  Sparkles,
  Telescope,
} from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";

export type SendMode = "chat" | "research" | "planner";

type InputBoxProps = {
  onSend: (content: string, mode: SendMode) => void | Promise<void>;
  loading?: boolean;
  placeholder?: string;
  initialMode?: SendMode;
  mode?: SendMode;
  onModeChange?: (mode: SendMode) => void;
};

export function InputBox({
  onSend,
  loading = false,
  placeholder,
  initialMode = "chat",
  mode,
  onModeChange,
}: InputBoxProps) {
  const { text } = useLocale();
  const [value, setValue] = useState("");
  const [internalMode, setInternalMode] = useState<SendMode>(initialMode);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const activeMode = mode ?? internalMode;

  const modes: Array<{ value: SendMode; label: string; icon: React.ReactNode }> = [
    { value: "chat", label: text.input.modeChat, icon: <Sparkles className="size-3.5" /> },
    { value: "research", label: text.input.modeResearch, icon: <Search className="size-3.5" /> },
    { value: "planner", label: text.input.modePlanner, icon: <Telescope className="size-3.5" /> },
  ];

  const modeMeta = useMemo(() => {
    switch (activeMode) {
      case "research":
        return {
          placeholder: text.input.placeholderResearch,
          helper: text.input.helperResearch,
          quickLabel: text.input.quickResearch,
          icon: <Search className="size-3.5" />,
          minHeight: "min-h-[104px]",
        };
      case "planner":
        return {
          placeholder: text.input.placeholderPlanner,
          helper: text.input.helperPlanner,
          quickLabel: text.input.quickPlanner,
          icon: <Telescope className="size-3.5" />,
          minHeight: "min-h-[112px]",
        };
      default:
        return {
          placeholder: text.input.placeholderChat,
          helper: text.input.helperChat,
          quickLabel: text.input.quickChat,
          icon: <Sparkles className="size-3.5" />,
          minHeight: "min-h-[96px]",
        };
    }
  }, [activeMode, text]);

  const inputPlaceholder = placeholder ?? modeMeta.placeholder;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  }, [value]);

  function updateMode(nextMode: SendMode) {
    if (mode === undefined) {
      setInternalMode(nextMode);
    }
    onModeChange?.(nextMode);
  }

  async function handleSend() {
    const content = value.trim();
    if (!content || loading) {
      return;
    }
    await onSend(content, activeMode);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  return (
    <div className="w-full rounded-[30px] border border-[var(--border)] bg-[var(--surface)]/96 p-3 shadow-[var(--shadow-lg)] backdrop-blur-sm">
      <div className="mb-2 flex flex-wrap items-center gap-2 px-2">
        <div className="inline-flex items-center gap-2 rounded-full bg-[var(--accent-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--accent)]">
          {modeMeta.icon}
          <span>{modeMeta.quickLabel}</span>
        </div>
        <p className="text-xs leading-6 text-[var(--text-3)]">{modeMeta.helper}</p>
      </div>

      <textarea
        ref={textareaRef}
        value={value}
        disabled={loading}
        rows={1}
        placeholder={inputPlaceholder}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void handleSend();
          }
        }}
        className={cn(
          "w-full resize-none border-none bg-transparent px-3 py-2 text-[15px] leading-7 text-[var(--text-1)] outline-none placeholder:text-[var(--text-3)] disabled:cursor-not-allowed disabled:opacity-60",
          modeMeta.minHeight,
        )}
      />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="inline-flex size-10 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-2)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
            title={text.input.attachmentsSoon}
          >
            <Paperclip className="size-4" />
          </button>

          <div className="flex items-center gap-1 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-1">
            {modes.map((item) => {
              const active = item.value === activeMode;
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => updateMode(item.value)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition",
                    active
                      ? "bg-[var(--accent)] text-white shadow-[var(--shadow-sm)]"
                      : "text-[var(--text-2)] hover:bg-white hover:text-[var(--text-1)]",
                  )}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        <button
          type="button"
          disabled={!value.trim() || loading}
          onClick={() => void handleSend()}
          className={cn(
            "inline-flex size-11 items-center justify-center rounded-2xl transition",
            value.trim() && !loading
              ? "bg-[var(--accent)] text-white shadow-[var(--shadow-md)] hover:brightness-95"
              : "bg-[var(--surface-2)] text-[var(--text-3)]",
          )}
          title={text.input.send}
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
        </button>
      </div>
    </div>
  );
}
