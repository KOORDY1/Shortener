import type { Metadata } from "next";
import Link from "next/link";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "드라마 쇼츠 코파일럿",
  description: "업로드·분석·후보·스크립트 초안까지 한 번에 보는 운영 UI"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <Providers>
          <div className="app-shell">
            <header className="topbar">
              <div>
                <strong>드라마 쇼츠 코파일럿</strong>
              </div>
              <nav className="nav">
                <Link href="/episodes">에피소드</Link>
                <Link href="/episodes/new">새 업로드</Link>
              </nav>
            </header>
            {children}
          </div>
        </Providers>
      </body>
    </html>
  );
}
