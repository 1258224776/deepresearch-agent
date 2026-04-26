"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChatStream } from "@/components/chat-stream";
import { InputBox, type SendMode } from "@/components/input-box";
import { useLocale } from "@/components/locale-provider";
import { WorkspaceShell } from "@/components/workspace-shell";
import { createThread, type UploadedAttachment } from "@/lib/api";

const DRAFT_PREFIX = "deepresearch:draft:";

export default function HomePage() {
  const router = useRouter();
  const { text } = useLocale();
  const [creating, setCreating] = useState(false);
  const [composerMode, setComposerMode] = useState<SendMode>("chat");
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSend(
    content: string,
    mode: SendMode,
    attachments: UploadedAttachment[],
  ) {
    setCreating(true);
    setErrorMessage("");
    try {
      const thread = await createThread(text.sidebar.newChat);
      sessionStorage.setItem(
        `${DRAFT_PREFIX}${thread.id}`,
        JSON.stringify({ content, mode, attachments }),
      );
      window.dispatchEvent(new Event("threads:changed"));
      router.push(`/chat/${thread.id}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : text.thread.unknownStreamError;
      setErrorMessage(message);
    } finally {
      setCreating(false);
    }
  }

  function handleSuggestionClick(suggestion: string) {
    void handleSend(suggestion, composerMode, []);
  }

  return (
    <WorkspaceShell
      title={text.shell.appTitle}
      subtitle={text.shell.appSubtitle}
      composer={
        <div className="space-y-3">
          {errorMessage && (
            <div className="rounded-2xl border border-[var(--danger)]/20 bg-[#fcedea] px-4 py-3 text-sm text-[var(--danger)] shadow-[var(--shadow-sm)]">
              {errorMessage}
            </div>
          )}
          <InputBox
            loading={creating}
            mode={composerMode}
            onModeChange={setComposerMode}
            onSend={handleSend}
          />
        </div>
      }
    >
      <ChatStream
        title={text.home.title[composerMode]}
        subtitle={text.home.subtitle[composerMode]}
        messages={[]}
        currentMode={composerMode}
        onSuggestionClick={handleSuggestionClick}
        suggestions={text.home.suggestions[composerMode]}
      />
    </WorkspaceShell>
  );
}
