export interface AppSettings {
  apiBaseMode: "env" | "custom";
  apiBase: string;
  apiKey: string;
  chatEngine: string;
  researchEngine: string;
  plannerEngine: string;
  researchProfile: string;
  plannerProfile: string;
}

export const APP_SETTINGS_STORAGE_KEY = "deepresearch:settings";
export const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const DEFAULT_APP_SETTINGS: AppSettings = {
  apiBaseMode: "env",
  apiBase: DEFAULT_API_BASE,
  apiKey: "",
  chatEngine: "",
  researchEngine: "",
  plannerEngine: "",
  researchProfile: "react_default",
  plannerProfile: "planner",
};

export function mergeSettings(
  input: Partial<AppSettings> | null | undefined,
): AppSettings {
  const merged: AppSettings = {
    ...DEFAULT_APP_SETTINGS,
    ...input,
  };

  const rawApiBase = merged.apiBase.trim();
  if (merged.apiBaseMode !== "custom" || !rawApiBase) {
    return {
      ...merged,
      apiBaseMode: "env",
      apiBase: DEFAULT_API_BASE,
    };
  }

  return {
    ...merged,
    apiBase: rawApiBase,
  };
}

export function readStoredSettings(): AppSettings {
  if (typeof window === "undefined") {
    return DEFAULT_APP_SETTINGS;
  }

  try {
    const raw = window.localStorage.getItem(APP_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return DEFAULT_APP_SETTINGS;
    }

    const parsed = JSON.parse(raw) as Partial<AppSettings>;

    if (!parsed.apiBaseMode) {
      const { apiBase, ...rest } = parsed;
      void apiBase;
      return mergeSettings(rest);
    }

    return mergeSettings(parsed);
  } catch {
    return DEFAULT_APP_SETTINGS;
  }
}
