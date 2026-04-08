import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Document Extraction",
  description: "Intelligent document data extraction powered by AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <header className="border-b bg-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600 text-white font-bold text-sm">
                DE
              </div>
              <h1 className="text-xl font-semibold text-gray-900">
                Document Extraction
              </h1>
            </div>
            <nav className="flex gap-6 text-sm font-medium text-gray-600">
              <Link href="/" className="hover:text-primary-600 transition-colors">
                Extract
              </Link>
              <Link
                href="/schemas"
                className="hover:text-primary-600 transition-colors"
              >
                Templates
              </Link>
              <Link
                href="/history"
                className="hover:text-primary-600 transition-colors"
              >
                History
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
