import type { Metadata } from "next";
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
      <body className="antialiased">{children}</body>
    </html>
  );
}
