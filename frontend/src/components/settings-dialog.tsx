"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Settings2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useLocale } from "@/components/locale-provider";
import { useSettings } from "@/components/settings-provider";
import {
  getSkillCatalog,
  getSearchDiagnostics,
  getSearchProviders,
  type SearchDiagnostics,
  type SearchProviderCatalog,
  type SkillCatalog,
  type SkillInfo,
  setSkillEnabled,
} from "@/lib/api";
import { DEFAULT_API_BASE, DEFAULT_APP_SETTINGS, type AppSettings } from "@/lib/settings";

type SettingsDialogProps = {
  triggerClassName?: string;
};

function Field({
  label,
  hint,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-[var(--text-1)]">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-11 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 text-sm text-[var(--text-1)] outline-none transition focus:border-[var(--accent)]"
      />
      <span className="text-xs leading-5 text-[var(--text-3)]">{hint}</span>
    </label>
  );
}

function formatUsageTimestamp(timestamp: number, locale: "zh" | "en") {
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

export function SettingsDialog({ triggerClassName = "" }: SettingsDialogProps) {
  const { locale, text } = useLocale();
  const { settings, updateSettings, resetSettings } = useSettings();
  const [diagnosticsQuery, setDiagnosticsQuery] = useState("");
  const [diagnostics, setDiagnostics] = useState<SearchDiagnostics | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState("");
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<AppSettings>(settings);
  const [providerCatalog, setProviderCatalog] = useState<SearchProviderCatalog | null>(null);
  const [providerError, setProviderError] = useState("");
  const [skillCatalog, setSkillCatalog] = useState<SkillCatalog | null>(null);
  const [skillError, setSkillError] = useState("");
  const [skillPendingName, setSkillPendingName] = useState("");

  const connectionLabel = useMemo(() => {
    try {
      return new URL(draft.apiBase).host;
    } catch {
      return draft.apiBase || "?";
    }
  }, [draft.apiBase]);

  const providerText = useMemo(() => {
    const isZh = locale === "zh";
    return {
      title: isZh ? "\u641c\u7d22\u6765\u6e90" : "Search providers",
      active: isZh ? "\u5f53\u524d\u987a\u5e8f" : "Active order",
      unavailable: isZh ? "\u6682\u65f6\u65e0\u6cd5\u8bfb\u53d6 provider \u72b6\u6001" : "Provider status unavailable",
      enabled: isZh ? "\u5df2\u542f\u7528" : "Enabled",
      available: isZh ? "\u53ef\u7528" : "Available",
      configured: isZh ? "\u5df2\u914d\u7f6e" : "Configured",
      missing: isZh ? "\u672a\u914d\u7f6e" : "Missing config",
      requested: isZh ? "\u5df2\u8bf7\u6c42" : "Requested",
      fallback: isZh ? "\u81ea\u52a8\u56de\u9000" : "Auto fallback",
      diagnosticsTitle: isZh ? "\u641c\u7d22\u8bca\u65ad" : "Search diagnostics",
      diagnosticsHint: isZh ? "\u8fd0\u884c\u4e00\u6b21\u6d4b\u8bd5\u67e5\u8be2\uff0c\u68c0\u67e5 provider \u56de\u9000\u987a\u5e8f\u548c\u547d\u4e2d\u6570\u91cf\u3002" : "Run a test query to inspect provider fallback and hit counts.",
      diagnosticsPlaceholder: isZh ? "\u4f8b\u5982\uff1a\u7279\u65af\u62c9 2024 \u8d22\u62a5" : "For example: Tesla 2024 earnings",
      diagnosticsRun: isZh ? "\u6d4b\u8bd5\u641c\u7d22" : "Run test",
      diagnosticsRunning: isZh ? "\u6d4b\u8bd5\u4e2d..." : "Running...",
      diagnosticsNoData: isZh ? "\u8fd8\u6ca1\u6709\u8bca\u65ad\u7ed3\u679c" : "No diagnostics yet",
      diagnosticsResults: isZh ? "\u7ed3\u679c" : "Results",
      diagnosticsAttempts: isZh ? "\u5c1d\u8bd5\u8f68\u8ff9" : "Attempt trace",
      diagnosticsError: isZh ? "\u8bca\u65ad\u5931\u8d25" : "Diagnostics failed",
    };
  }, [locale]);

  const skillText = useMemo(() => {
    const isZh = locale === "zh";
    return {
      title: isZh ? "技能治理" : "Skill governance",
      subtitle: isZh ? "统一管理后端已注册技能的启停状态、配置可用性和调用统计。" : "Manage backend skill availability, runtime status, and usage stats.",
      unavailable: isZh ? "暂时无法读取 skill 状态" : "Skill status unavailable",
      enabled: isZh ? "已启用" : "Enabled",
      disabled: isZh ? "已停用" : "Disabled",
      configured: isZh ? "可运行" : "Configured",
      missing: isZh ? "缺少配置" : "Missing config",
      calls: isZh ? "调用" : "Calls",
      success: isZh ? "成功" : "Success",
      failure: isZh ? "失败" : "Failure",
      avgDuration: isZh ? "均时" : "Avg",
      lastUsed: isZh ? "最近调用" : "Last used",
      envHints: isZh ? "环境提示" : "Env hints",
      empty: isZh ? "还没有可显示的技能元数据" : "No skill metadata available.",
      profiles: isZh ? "配置概览" : "Profiles",
      saving: isZh ? "更新中..." : "Updating...",
    };
  }, [locale]);

  useEffect(() => {
    let cancelled = false;
    if (!open) {
      return undefined;
    }

    async function loadProviders() {
      try {
        const data = await getSearchProviders();
        if (!cancelled) {
          setProviderCatalog(data);
          setProviderError("");
        }
      } catch {
        if (!cancelled) {
          setProviderCatalog(null);
          setProviderError(settings.apiBase);
        }
      }
    }

    void loadProviders();
    return () => {
      cancelled = true;
    };
  }, [open, settings.apiBase]);

  useEffect(() => {
    let cancelled = false;
    if (!open) {
      return undefined;
    }

    async function loadSkills() {
      try {
        const data = await getSkillCatalog();
        if (!cancelled) {
          setSkillCatalog(data);
          setSkillError("");
        }
      } catch {
        if (!cancelled) {
          setSkillCatalog(null);
          setSkillError(settings.apiBase);
        }
      }
    }

    void loadSkills();
    return () => {
      cancelled = true;
    };
  }, [open, settings.apiBase]);

  function updateField<Key extends keyof AppSettings>(key: Key, value: AppSettings[Key]) {
    setDraft((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function handleSave() {
    const apiBase = draft.apiBase.trim();
    const useCustomApiBase = apiBase.length > 0 && apiBase !== DEFAULT_API_BASE;

    updateSettings({
      ...draft,
      apiBaseMode: useCustomApiBase ? "custom" : "env",
      apiBase: useCustomApiBase ? apiBase : DEFAULT_API_BASE,
    });
    setOpen(false);
  }

  function handleReset() {
    resetSettings();
    setDraft(DEFAULT_APP_SETTINGS);
  }

  async function handleRunDiagnostics() {
    const query = diagnosticsQuery.trim();
    if (!query) {
      return;
    }
    setDiagnosticsLoading(true);
    setDiagnosticsError("");
    try {
      const data = await getSearchDiagnostics(query, 5);
      setDiagnostics(data);
    } catch (error) {
      setDiagnostics(null);
      setDiagnosticsError(error instanceof Error ? error.message : String(error));
    } finally {
      setDiagnosticsLoading(false);
    }
  }

  async function handleToggleSkill(skill: SkillInfo) {
    const nextEnabled = !skill.enabled;
    setSkillPendingName(skill.name);
    setSkillError("");
    try {
      const updated = await setSkillEnabled(skill.name, nextEnabled);
      setSkillCatalog((current) => {
        if (!current) {
          return current;
        }
        const skills = current.skills.map((item) => (item.name === updated.name ? updated : item));
        return {
          ...current,
          enabled_skills: skills.filter((item) => item.enabled).length,
          skills,
        };
      });
    } catch (error) {
      setSkillError(error instanceof Error ? error.message : String(error));
    } finally {
      setSkillPendingName("");
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (nextOpen) {
          setDraft(settings);
        }
      }}
    >
      <Dialog.Trigger asChild>
        <button
          type="button"
          className={
            triggerClassName ||
            "inline-flex w-full items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-sm font-medium text-[var(--text-2)] shadow-[var(--shadow-sm)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
          }
          title={text.settings.open}
        >
          <Settings2 className="size-4" />
          <span>{text.sidebar.settingsLabel}</span>
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#2f261f]/24 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(720px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-[28px] border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-lg)]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold text-[var(--text-1)]">
                {text.settings.title}
              </Dialog.Title>
              <Dialog.Description className="mt-2 max-w-2xl text-sm leading-7 text-[var(--text-2)]">
                {text.settings.subtitle}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="inline-flex size-10 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-2)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
                title={text.settings.cancel}
              >
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-3)]">
              {text.settings.status}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-[var(--text-2)]">
              <span className="rounded-full bg-[var(--surface)] px-3 py-1 text-[var(--text-1)]">
                {connectionLabel}
              </span>
              <span>{text.settings.statusReady}</span>
            </div>
            <div className="mt-4 border-t border-[var(--border)] pt-4">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-3)]">
                {providerText.title}
              </div>
              {providerError ? (
                <p className="mt-2 text-xs leading-6 text-[var(--danger)]">
                  {providerText.unavailable}: {providerError}
                </p>
              ) : (
                <>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--text-2)]">
                    <span className="text-[var(--text-3)]">{providerText.active}</span>
                    {(providerCatalog?.active_order.length
                      ? providerCatalog.active_order
                      : ["ddgs"]
                    ).map((provider) => (
                      <span
                        key={provider}
                        className="rounded-full bg-[var(--surface)] px-3 py-1 font-medium text-[var(--text-1)]"
                      >
                        {provider}
                      </span>
                    ))}
                    <span className="rounded-full border border-dashed border-[var(--border)] px-3 py-1 text-[var(--text-3)]">
                      {providerText.fallback}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {(providerCatalog?.providers ?? []).map((provider) => (
                      <div
                        key={provider.name}
                        className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-medium text-[var(--text-1)]">{provider.name}</div>
                          <span
                            className={
                              provider.enabled
                                ? "rounded-full bg-[var(--accent-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--accent)]"
                                : "rounded-full bg-[var(--surface-2)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-3)]"
                            }
                          >
                            {provider.enabled
                              ? providerText.enabled
                              : provider.configured
                                ? providerText.available
                                : providerText.missing}
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--text-3)]">
                          {provider.requested && (
                            <span className="rounded-full border border-[var(--border)] px-2 py-1">
                              {providerText.requested}
                            </span>
                          )}
                          {!provider.configured && provider.env_hints.map((hint) => (
                            <span
                              key={hint}
                              className="rounded-full border border-dashed border-[var(--border)] px-2 py-1"
                            >
                              {hint}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-3)]">
                      {providerText.diagnosticsTitle}
                    </div>
                    <p className="mt-2 text-xs leading-6 text-[var(--text-3)]">
                      {providerText.diagnosticsHint}
                    </p>
                    <div className="mt-3 flex gap-2">
                      <input
                        value={diagnosticsQuery}
                        onChange={(event) => setDiagnosticsQuery(event.target.value)}
                        placeholder={providerText.diagnosticsPlaceholder}
                        className="h-11 flex-1 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-4 text-sm text-[var(--text-1)] outline-none transition focus:border-[var(--accent)]"
                      />
                      <button
                        type="button"
                        onClick={handleRunDiagnostics}
                        disabled={diagnosticsLoading || !diagnosticsQuery.trim()}
                        className="inline-flex min-w-28 items-center justify-center rounded-2xl bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-white shadow-[var(--shadow-sm)] transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {diagnosticsLoading ? providerText.diagnosticsRunning : providerText.diagnosticsRun}
                      </button>
                    </div>
                    {diagnosticsError ? (
                      <p className="mt-3 text-xs leading-6 text-[var(--danger)]">
                        {providerText.diagnosticsError}: {diagnosticsError}
                      </p>
                    ) : diagnostics ? (
                      <div className="mt-3 grid gap-3 md:grid-cols-[1.3fr_1fr]">
                        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-3)]">
                            {providerText.diagnosticsAttempts}
                          </div>
                          <div className="mt-2 grid gap-2">
                            {diagnostics.attempts.map((attempt) => (
                              <div
                                key={attempt.provider}
                                className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-xs text-[var(--text-2)]"
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <span className="font-medium text-[var(--text-1)]">{attempt.provider}</span>
                                  <span className="rounded-full bg-[var(--surface-2)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-3)]">
                                    {attempt.status}
                                  </span>
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  <span>results {attempt.result_count}</span>
                                  <span>added {attempt.added_count}</span>
                                  {!attempt.configured && <span>unconfigured</span>}
                                </div>
                                {attempt.error ? (
                                  <div className="mt-2 text-[11px] leading-5 text-[var(--danger)]">
                                    {attempt.error}
                                  </div>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-3)]">
                            {providerText.diagnosticsResults}
                          </div>
                          {diagnostics.results.length ? (
                            <div className="mt-2 grid gap-2">
                              {diagnostics.results.slice(0, 4).map((item) => (
                                <div
                                  key={`${item.provider}-${item.url}`}
                                  className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-xs text-[var(--text-2)]"
                                >
                                  <div className="font-medium text-[var(--text-1)]">{item.title || item.url}</div>
                                  <div className="mt-1 text-[11px] text-[var(--text-3)]">{item.provider}</div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="mt-2 text-xs leading-6 text-[var(--text-3)]">
                              {providerText.diagnosticsNoData}
                            </p>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-3)]">
              {skillText.title}
            </div>
            <p className="mt-2 text-xs leading-6 text-[var(--text-3)]">
              {skillText.subtitle}
            </p>
            {skillError ? (
              <p className="mt-2 text-xs leading-6 text-[var(--danger)]">
                {skillText.unavailable}: {skillError}
              </p>
            ) : (
              <>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-2)]">
                  <span className="rounded-full bg-[var(--surface)] px-3 py-1 text-[var(--text-1)]">
                    {skillCatalog?.enabled_skills ?? 0}/{skillCatalog?.total_skills ?? 0} {skillText.enabled.toLowerCase()}
                  </span>
                  {(skillCatalog?.profiles ?? []).slice(0, 4).map((profile) => (
                    <span
                      key={profile.name}
                      className="rounded-full border border-[var(--border)] px-3 py-1 text-[var(--text-3)]"
                    >
                      {profile.name} {profile.allowed_count}
                    </span>
                  ))}
                </div>
                <div className="mt-3 grid max-h-[320px] gap-2 overflow-y-auto pr-1 md:grid-cols-2">
                  {(skillCatalog?.skills ?? []).map((skill) => (
                    <div
                      key={skill.name}
                      className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-[var(--text-1)]">{skill.name}</div>
                          <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-[var(--text-3)]">
                            {skill.category}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleToggleSkill(skill)}
                          disabled={skillPendingName === skill.name}
                          className={
                            skill.enabled
                              ? "inline-flex min-w-20 items-center justify-center rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[11px] font-semibold text-[var(--accent)] disabled:opacity-60"
                              : "inline-flex min-w-20 items-center justify-center rounded-full bg-[var(--surface-2)] px-3 py-1 text-[11px] font-semibold text-[var(--text-3)] disabled:opacity-60"
                          }
                        >
                          {skillPendingName === skill.name
                            ? skillText.saving
                            : skill.enabled
                              ? skillText.enabled
                              : skillText.disabled}
                        </button>
                      </div>
                      <p className="mt-2 text-xs leading-6 text-[var(--text-2)]">{skill.description}</p>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-[var(--text-3)]">
                        <span className="rounded-full border border-[var(--border)] px-2 py-1">
                          {skill.configured ? skillText.configured : skillText.missing}
                        </span>
                        <span className="rounded-full border border-[var(--border)] px-2 py-1">
                          {skillText.calls} {skill.stats.call_count ?? 0}
                        </span>
                        <span className="rounded-full border border-[var(--border)] px-2 py-1">
                          {skillText.success} {skill.stats.success_count ?? 0}
                        </span>
                        <span className="rounded-full border border-[var(--border)] px-2 py-1">
                          {skillText.failure} {skill.stats.failure_count ?? 0}
                        </span>
                        <span className="rounded-full border border-[var(--border)] px-2 py-1">
                          {skillText.avgDuration} {Math.round(skill.stats.average_duration_ms ?? 0)} ms
                        </span>
                      </div>
                      {skill.env_hints.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--text-3)]">
                          <span className="text-[var(--text-3)]">{skillText.envHints}:</span>
                          {skill.env_hints.map((hint) => (
                            <span
                              key={`${skill.name}-${hint}`}
                              className="rounded-full border border-dashed border-[var(--border)] px-2 py-1"
                            >
                              {hint}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="mt-2 text-[11px] text-[var(--text-3)]">
                        {skillText.lastUsed}: {formatUsageTimestamp(skill.stats.last_used_at ?? 0, locale)}
                      </div>
                    </div>
                  ))}
                  {skillCatalog && skillCatalog.skills.length === 0 && (
                    <p className="text-sm text-[var(--text-3)]">{skillText.empty}</p>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="mt-6 grid gap-5 md:grid-cols-2">
            <div className="md:col-span-2">
              <Field
                label={text.settings.apiBase}
                hint={text.settings.apiBaseHint}
                value={draft.apiBase}
                onChange={(value) => updateField("apiBase", value)}
                placeholder="http://127.0.0.1:8000"
              />
            </div>

            <div className="md:col-span-2">
              <Field
                label={locale === "zh" ? "API Key" : "API key"}
                hint={
                  locale === "zh"
                    ? "可选。后端启用 DEEPRESEARCH_API_KEY 时，请在这里填写相同的值。"
                    : "Optional. Fill this when the backend enables DEEPRESEARCH_API_KEY."
                }
                value={draft.apiKey}
                onChange={(value) => updateField("apiKey", value)}
                placeholder={locale === "zh" ? "留空表示不发送 X-API-Key" : "Leave blank to omit X-API-Key"}
              />
            </div>

            <Field
              label={text.settings.chatEngine}
              hint={text.settings.chatEngineHint}
              value={draft.chatEngine}
              onChange={(value) => updateField("chatEngine", value)}
            />
            <Field
              label={text.settings.researchEngine}
              hint={text.settings.researchEngineHint}
              value={draft.researchEngine}
              onChange={(value) => updateField("researchEngine", value)}
            />
            <Field
              label={text.settings.plannerEngine}
              hint={text.settings.plannerEngineHint}
              value={draft.plannerEngine}
              onChange={(value) => updateField("plannerEngine", value)}
            />
            <Field
              label={text.settings.researchProfile}
              hint={text.settings.researchProfileHint}
              value={draft.researchProfile}
              onChange={(value) => updateField("researchProfile", value)}
            />
            <Field
              label={text.settings.plannerProfile}
              hint={text.settings.plannerProfileHint}
              value={draft.plannerProfile}
              onChange={(value) => updateField("plannerProfile", value)}
            />
          </div>

          <div className="mt-8 flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-2.5 text-sm font-medium text-[var(--text-2)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
            >
              {text.settings.reset}
            </button>

            <div className="flex items-center gap-3">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="inline-flex items-center rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-medium text-[var(--text-2)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
                >
                  {text.settings.cancel}
                </button>
              </Dialog.Close>
              <button
                type="button"
                onClick={handleSave}
                className="inline-flex items-center rounded-2xl bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-white shadow-[var(--shadow-sm)] transition hover:brightness-95"
              >
                {text.settings.save}
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
