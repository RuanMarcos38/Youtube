import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { LanguageRuntime } from "@/components/LanguageSelector";
import LiveAudienceCard from "@/components/LiveAudienceCard";
import PlatformNavigation from "@/components/PlatformNavigation";
import YoutubeAccountSwitcher from "@/components/YoutubeAccountSwitcher";
import "./globals.css";
import "./publication-policy.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "ShortsFlow | Produção e distribuição de vídeo",
  description: "Área de trabalho para criar Shorts, editar vídeos, acompanhar processamentos e publicar conteúdo em uma única plataforma.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className={inter.variable}>
      <body>
        <LanguageRuntime />
        {children}
        <LiveAudienceCard />
        <PlatformNavigation />
        <YoutubeAccountSwitcher />
        <footer className="border-t border-[#e4e7ec] bg-white px-6 py-5 pb-24 text-center text-[11px] text-[#667085] xl:pb-5">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-center gap-x-5 gap-y-2">
            <span>ShortsFlow · R2R Marketing Digital</span>
            <a className="font-medium hover:text-[#344054]" href="/privacidade">Privacidade</a>
            <a className="font-medium hover:text-[#344054]" href="/termos">Termos</a>
            <a className="font-medium hover:text-[#344054]" href="/exclusao-de-dados">Exclusão de dados</a>
          </div>
        </footer>
      </body>
    </html>
  );
}
