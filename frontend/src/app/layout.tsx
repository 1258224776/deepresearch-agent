import type { Metadata } from "next";
import { LocaleProvider } from "@/components/locale-provider";
import { SettingsProvider } from "@/components/settings-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "DeepResearch",
  description: "Conversation-first local research workspace",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body>
        <LocaleProvider>
          <SettingsProvider>{children}</SettingsProvider>
        </LocaleProvider>
      </body>
    </html>
  );
}
