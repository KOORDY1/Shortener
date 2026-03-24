import type { Metadata } from "next";
import Link from "next/link";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Drama Shorts Copilot",
  description: "Operations UI for upload, analysis, candidates, and script drafts"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <Providers>
          <div className="app-shell">
            <header className="topbar">
              <div>
                <strong>Drama Shorts Copilot</strong>
              </div>
              <nav className="nav">
                <Link href="/episodes">Episodes</Link>
                <Link href="/episodes/new">New Upload</Link>
              </nav>
            </header>
            {children}
          </div>
        </Providers>
      </body>
    </html>
  );
}
