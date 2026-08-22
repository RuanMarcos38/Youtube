import type { Metadata } from "next";
import PlatformNavigation from "@/components/PlatformNavigation";
import YoutubeAccountSwitcher from "@/components/YoutubeAccountSwitcher";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShortsFlow AI | Plataforma Completa de Vídeo com IA",
  description: "Criação de Shorts, edição automatizada por IA, projetos, processamento, publicação e exportação para TikTok Shop em uma única plataforma.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>
        {children}
        <PlatformNavigation />
        <YoutubeAccountSwitcher />
        <footer className="border-t border-black/5 bg-white px-6 py-6 pb-24 text-center text-xs text-[#6d776f] xl:pb-6">
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
