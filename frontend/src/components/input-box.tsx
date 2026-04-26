"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Tooltip from "@radix-ui/react-tooltip";
import {
  ArrowUp,
  ChevronDown,
  Code2,
  FileText,
  Loader2,
  Paperclip,
  Search,
  Sparkles,
  Telescope,
  X,
} from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import { type UploadedAttachment, uploadAttachment } from "@/lib/api";
import { cn } from "@/lib/utils";

export type SendMode = "chat" | "research" | "planner";
const MAX_ATTACHMENTS = 5;
const DOCUMENT_ACCEPT = ".pdf,.docx,.txt,.md,.csv";
const CODE_ACCEPT = ".py,.js,.jsx,.ts,.tsx,.json,.yaml,.yml,.html,.css,.sql,.sh,.xml";

type InputBoxProps = {
  onSend: (
    content: string,
    mode: SendMode,
    attachments: UploadedAttachment[],
  ) => void | Promise<void>;
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
  const [attachments, setAttachments] = useState<UploadedAttachment[]>([]);
  const [uploadError, setUploadError] = useState("");
  const [uploadingAttachments, setUploadingAttachments] = useState(false);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const documentInputRef = useRef<HTMLInputElement | null>(null);
  const codeInputRef = useRef<HTMLInputElement | null>(null);
  const activeMode = mode ?? internalMode;
  const busy = loading || uploadingAttachments;

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
    if (!content || busy) {
      return;
    }
    await onSend(content, activeMode, attachments);
    setValue("");
    setAttachments([]);
    setUploadError("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  async function uploadFiles(selectedFiles: File[]) {
    if (!selectedFiles.length) {
      return;
    }

    setUploadError("");
    const availableSlots = Math.max(0, MAX_ATTACHMENTS - attachments.length);
    if (!availableSlots) {
      setUploadError(text.input.attachmentsLimit);
      return;
    }

    const filesToUpload = selectedFiles.slice(0, availableSlots);
    setUploadingAttachments(true);
    try {
      const uploaded: UploadedAttachment[] = [];
      for (const file of filesToUpload) {
        uploaded.push(await uploadAttachment(file));
      }
      setAttachments((current) => [...current, ...uploaded]);
      if (selectedFiles.length > filesToUpload.length) {
        setUploadError(text.input.attachmentsLimit);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : text.input.attachmentUploadFailed;
      setUploadError(`${text.input.attachmentUploadFailed}: ${message}`);
    } finally {
      setUploadingAttachments(false);
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files ?? []);
    event.target.value = "";
    void uploadFiles(selectedFiles);
  }

  function removeAttachment(attachmentId: string) {
    setAttachments((current) => current.filter((item) => item.id !== attachmentId));
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
        disabled={busy}
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

      {(attachments.length > 0 || uploadingAttachments || uploadError) && (
        <div className="mt-3 space-y-2 px-2">
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {attachments.map((attachment) => (
                <span
                  key={attachment.id}
                  className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1 text-xs text-[var(--text-2)]"
                >
                  <Paperclip className="size-3.5" />
                  <span className="max-w-[12rem] truncate">{attachment.filename}</span>
                  <button
                    type="button"
                    onClick={() => removeAttachment(attachment.id)}
                    className="inline-flex size-4 items-center justify-center rounded-full text-[var(--text-3)] transition hover:bg-white hover:text-[var(--text-1)]"
                    title={text.input.removeAttachment}
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
            </div>
          )}

          {uploadingAttachments && (
            <p className="text-xs text-[var(--text-3)]">{text.input.uploadingAttachments}</p>
          )}
          {uploadError && (
            <p className="text-xs text-[var(--danger)]">{uploadError}</p>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex flex-wrap items-center gap-2">
          <Tooltip.Provider delayDuration={180}>
            <Tooltip.Root>
              <DropdownMenu.Root open={attachmentMenuOpen} onOpenChange={setAttachmentMenuOpen}>
                <Tooltip.Trigger asChild>
                  <DropdownMenu.Trigger asChild>
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={text.input.attachFiles}
                      className="inline-flex h-10 items-center gap-1 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text-2)] transition hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <Paperclip className="size-4" />
                      <ChevronDown className="size-3.5" />
                    </button>
                  </DropdownMenu.Trigger>
                </Tooltip.Trigger>

                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    side="top"
                    align="start"
                    sideOffset={10}
                    className="z-50 w-[18.5rem] rounded-[22px] border border-[var(--border)] bg-[var(--surface)] p-2 shadow-[var(--shadow-lg)] backdrop-blur-md"
                  >
                    <div className="px-3 pb-2 pt-1">
                      <div className="text-sm font-semibold text-[var(--text-1)]">
                        {text.input.attachMenuTitle}
                      </div>
                      <div className="mt-1 text-xs leading-5 text-[var(--text-3)]">
                        {text.input.attachMenuHint}
                      </div>
                    </div>

                    <DropdownMenu.Item
                      onSelect={(event) => {
                        event.preventDefault();
                        documentInputRef.current?.click();
                      }}
                      className="flex cursor-pointer items-start gap-3 rounded-2xl px-3 py-3 text-left outline-none transition data-[highlighted]:bg-[var(--surface-2)]"
                    >
                      <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)]">
                        <FileText className="size-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold text-[var(--text-1)]">
                          {text.input.attachDocument}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-[var(--text-3)]">
                          {text.input.attachDocumentHint}
                        </span>
                      </span>
                    </DropdownMenu.Item>

                    <DropdownMenu.Item
                      onSelect={(event) => {
                        event.preventDefault();
                        codeInputRef.current?.click();
                      }}
                      className="flex cursor-pointer items-start gap-3 rounded-2xl px-3 py-3 text-left outline-none transition data-[highlighted]:bg-[var(--surface-2)]"
                    >
                      <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)]">
                        <Code2 className="size-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold text-[var(--text-1)]">
                          {text.input.attachCode}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-[var(--text-3)]">
                          {text.input.attachCodeHint}
                        </span>
                      </span>
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>

              <Tooltip.Portal>
                <Tooltip.Content
                  side="top"
                  sideOffset={10}
                  className="z-50 rounded-full border border-[var(--border)] bg-[var(--text-1)] px-3 py-1.5 text-xs font-medium text-white shadow-[var(--shadow-sm)]"
                >
                  {text.input.attachTooltip}
                  <Tooltip.Arrow className="fill-[var(--text-1)]" />
                </Tooltip.Content>
              </Tooltip.Portal>
            </Tooltip.Root>
          </Tooltip.Provider>
          <input
            ref={documentInputRef}
            type="file"
            multiple
            accept={DOCUMENT_ACCEPT}
            className="hidden"
            onChange={handleFileChange}
          />
          <input
            ref={codeInputRef}
            type="file"
            multiple
            accept={CODE_ACCEPT}
            className="hidden"
            onChange={handleFileChange}
          />

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
          disabled={!value.trim() || busy}
          onClick={() => void handleSend()}
          className={cn(
            "inline-flex size-11 items-center justify-center rounded-2xl transition",
            value.trim() && !busy
              ? "bg-[var(--accent)] text-white shadow-[var(--shadow-md)] hover:brightness-95"
              : "bg-[var(--surface-2)] text-[var(--text-3)]",
          )}
          title={text.input.send}
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
        </button>
      </div>
    </div>
  );
}
