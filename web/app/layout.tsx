import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = { title: "Docs Assistant", description: "Ask questions about your own files." };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      {/* Browser extensions such as Grammarly add attributes to <body> before React loads; that is harmless. */}
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
