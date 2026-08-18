import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shorts Automation SaaS",
  description: "Dashboard para descoberta, geração, aprovação e publicação de YouTube Shorts.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
