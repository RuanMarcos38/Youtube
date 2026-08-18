import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShortsFlow AI | YouTube Shorts Automation",
  description: "Automação de YouTube Shorts com IA: descoberta, cortes 9:16, legendas, metadata, aprovação e publicação.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
