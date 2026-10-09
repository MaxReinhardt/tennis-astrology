import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tennis Research",
  description: "Ask betting questions of a clean tennis match and odds database, and browse pre-registered studies.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-[var(--border)]">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3 text-sm">
            <span className="font-semibold">Tennis Research</span>
            <Link href="/" className="text-[var(--ink-2)] hover:text-[var(--ink)]">Ask a question</Link>
            <Link href="/studies" className="text-[var(--ink-2)] hover:text-[var(--ink)]">Studies</Link>
          </nav>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
