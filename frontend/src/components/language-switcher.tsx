"use client";

import { Languages } from "lucide-react";

import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";

export function LanguageSwitcher() {
  const { locale, setLocale, text } = useLocale();

  return (
    <div className="inline-flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 shadow-[var(--shadow-sm)]">
      <Languages className="size-4 text-[var(--text-3)]" />
      <div className="flex items-center gap-1 rounded-xl bg-[var(--surface-2)] p-1">
        {(["zh", "en"] as const).map((item) => {
          const active = item === locale;
          return (
            <button
              key={item}
              type="button"
              onClick={() => setLocale(item)}
              className={cn(
                "rounded-lg px-2.5 py-1 text-xs font-semibold transition",
                active
                  ? "bg-[var(--accent)] text-white"
                  : "text-[var(--text-2)] hover:bg-white hover:text-[var(--text-1)]",
              )}
            >
              {text.language[item]}
            </button>
          );
        })}
      </div>
    </div>
  );
}
