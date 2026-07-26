import type { Metadata } from "next";
import "./globals.css";

const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("paperplane:theme:v1");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}})()`;

export const metadata: Metadata = {
  title: "Paperplane — Document to Markdown",
  description: "Private local PDF parsing with GLM-OCR",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} /></head>
      <body>{children}</body>
    </html>
  );
}
