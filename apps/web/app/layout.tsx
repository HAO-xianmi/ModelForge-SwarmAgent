import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "ModelForge-Swarm",
  description: "An auditable multi-agent copilot for mathematical modeling",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <header className="border-b bg-white">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
              <Link href="/" className="text-lg font-semibold">
                ModelForge-Swarm
              </Link>
              <nav className="flex gap-4 text-sm text-slate-600">
                <Link href="/">New Run</Link>
                <Link href="/methods">Methods</Link>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
          <footer className="mx-auto max-w-6xl px-6 py-8 text-xs text-slate-400">
            Human-supervised modeling copilot · evidence-constrained · auditable.
          </footer>
        </Providers>
      </body>
    </html>
  );
}
