"use client";

import { useEffect, useRef } from "react";
import { Compass, Sparkles } from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import type { Message, Step } from "@/lib/api";
import { MessageBubble, StreamingBubble } from "@/components/message-bubble";
import { cn } from "@/lib/utils";
import type { SendMode } from "@/components/input-box";

type ChatStreamProps = {
  title: string;
  subtitle: string;
  messages: Message[];
  streamingContent?: string;
  streamingSteps?: Step[];
  progressText?: string;
  streamingMode?: Message["mode"];
  suggestions?: readonly string[];
  onSuggestionClick?: (suggestion: string) => void;
  currentMode?: SendMode;
  onRunClick?: (runId: string) => void;
};

export function ChatStream({
  title,
  subtitle,
  messages,
  streamingContent = "",
  streamingSteps = [],
  progressText,
  streamingMode,
  suggestions,
  onSuggestionClick,
  currentMode = "chat",
  onRunClick,
}: ChatStreamProps) {
  const { text } = useLocale();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingContent, streamingSteps, progressText]);

  const isEmpty = messages.length === 0 && !streamingContent && streamingSteps.length === 0 && !progressText;
  const emptySuggestions = suggestions ?? text.home.suggestions[currentMode];

  return (
    <div className="flex min-h-full flex-col">
      <div className="mx-auto flex min-h-full w-full max-w-5xl flex-col px-6 pb-12 pt-8">
        {isEmpty ? (
          <div className="flex min-h-[clamp(18rem,42vh,28rem)] flex-1 items-center justify-center">
            <div className="max-w-xl text-center">
              <div className="mx-auto mb-6 flex size-16 items-center justify-center rounded-[28px] bg-[var(--accent-soft)] text-[var(--accent)] shadow-[var(--shadow-md)]">
                <Compass className="size-8" />
              </div>
              <h1 className="text-3xl font-semibold tracking-tight text-[var(--text-1)]">{title}</h1>
              <p className="mt-4 text-base leading-8 text-[var(--text-2)]">{subtitle}</p>
            </div>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 justify-center">
            <div className="w-full max-w-4xl space-y-8">
              {messages.map((message, index) => (
                <MessageBubble
                  key={`${message.role}-${message.ts ?? index}-${index}`}
                  message={message}
                  onRunClick={onRunClick}
                />
              ))}

              {(streamingContent || streamingSteps.length > 0 || progressText) && (
                <StreamingBubble
                  content={streamingContent}
                  mode={streamingMode}
                  steps={streamingSteps}
                  progressText={progressText}
                />
              )}

              <div ref={bottomRef} />
            </div>
          </div>
        )}

        {isEmpty && (
          <div className="mx-auto mt-8 flex w-full max-w-3xl flex-wrap justify-center gap-3">
            {emptySuggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => onSuggestionClick?.(suggestion)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm text-[var(--text-2)] shadow-[var(--shadow-sm)] transition",
                  "hover:border-[var(--accent)] hover:text-[var(--accent)]",
                )}
              >
                <Sparkles className="size-3.5" />
                <span>{suggestion}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
