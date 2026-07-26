import type { Metadata } from "next";
import "./globals.css";
import "./v2-tools.css";

const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("paperplane:theme:v1");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}})()`;

export const metadata: Metadata = {
  title: "Paperplane — Grounded Document Extraction",
  description: "Auditable OpenAI document extraction with visual grounding",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} /></head>
      <body>{children}</body>
    </html>
  );
}
