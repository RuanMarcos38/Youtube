import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShortsFlow AI | YouTube Shorts Automation",
  description: "Automação de YouTube Shorts com IA: descoberta, cortes 9:16, legendas, metadata, aprovação e publicação.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>
        {children}
        <footer className="border-t border-black/5 bg-white px-6 py-6 text-center text-xs text-[#6d776f]">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-center gap-x-5 gap-y-2">
            <span>ShortsFlow AI • R2R Marketing Digital</span>
            <a className="font-bold text-[#4f7000] underline" href="/privacidade">Política de Privacidade</a>
            <a className="font-bold text-[#4f7000] underline" href="/termos">Termos de Uso</a>
            <a className="font-bold text-[#4f7000] underline" href="/exclusao-de-dados">Exclusão de Dados</a>
          </div>
        </footer>
      </body>
    </html>
  );
}
