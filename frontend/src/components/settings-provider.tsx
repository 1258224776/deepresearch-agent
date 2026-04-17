"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  APP_SETTINGS_STORAGE_KEY,
  DEFAULT_APP_SETTINGS,
  type AppSettings,
  mergeSettings,
  readStoredSettings,
} from "@/lib/settings";

type SettingsContextValue = {
  settings: AppSettings;
  updateSettings: (next: Partial<AppSettings>) => void;
  resetSettings: () => void;
};

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(() => readStoredSettings());
  const hasMountedRef = useRef(false);

  useEffect(() => {
    window.localStorage.setItem(APP_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    if (hasMountedRef.current) {
      window.dispatchEvent(new Event("settings:changed"));
    } else {
      hasMountedRef.current = true;
    }
  }, [settings]);

  const value = useMemo<SettingsContextValue>(
    () => ({
      settings,
      updateSettings: (next) =>
        setSettings((current) => mergeSettings({ ...current, ...next })),
      resetSettings: () => setSettings(DEFAULT_APP_SETTINGS),
    }),
    [settings],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used inside SettingsProvider");
  }
  return context;
}
