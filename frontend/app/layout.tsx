import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Document Processing Agent",
  description: "Local-first invoice extraction and validation (synthetic data only).",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col bg-gray-50 antialiased">
        <header className="border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
            <Link href="/" className="font-semibold text-gray-900">
              Document Processing Agent
            </Link>
            <span className="shrink-0 rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
              Synthetic data only
            </span>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-gray-200 bg-white">
          <p className="mx-auto max-w-6xl px-4 py-3 text-xs text-gray-500">
            This tool extracts and checks invoice data for review. It cannot approve payments,
            send money, or contact vendors.
          </p>
        </footer>
      </body>
    </html>
  );
}
