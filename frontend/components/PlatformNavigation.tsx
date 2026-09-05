"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import BrandLogo from "./BrandLogo";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type IconProps = { className?: string };

function HomeIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M4 10.4 12 4l8 6.4v8.1A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5v-8.1Z" stroke="currentColor" strokeWidth="1.7"/><path d="M9.5 20v-6h5v6" stroke="currentColor" strokeWidth="1.7"/></svg>;
}

function ShortsIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="3" stroke="currentColor" strokeWidth="1.7"/><path d="m10 8.5 5.5 3.5-5.5 3.5v-7Z" fill="currentColor"/></svg>;
}

function EditIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M4.5 16.8V20h3.2L18.6 9.1l-3.2-3.2L4.5 16.8Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/><path d="m13.8 7.5 3.2 3.2M5 5h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>;
}

function ProjectsIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M4 7.5A1.5 1.5 0 0 1 5.5 6H10l1.7 2H18.5A1.5 1.5 0 0 1 20 9.5v8A1.5 1.5 0 0 1 18.5 19h-13A1.5 1.5 0 0 1 4 17.5v-10Z" stroke="currentColor" strokeWidth="1.7"/></svg>;
}

function ProcessIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M18.4 8.2A7 7 0 1 0 19 15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/><path d="M18.5 4.5v4h-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function PublishIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M12 16V4m0 0-4 4m4-4 4 4M5 14v5h14v-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function MetricsIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M5 19V11m7 8V5m7 14v-6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/><path d="M3.5 20h17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>;
}

function TikTokIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M14.7 3.2c.5 2.4 1.8 3.8 4.1 4.4v3.1a9 9 0 0 1-4.1-1.2v5.6a5.8 5.8 0 1 1-5-5.7v3.2a2.7 2.7 0 1 0 1.8 2.5V3.2h3.2Z" fill="currentColor"/></svg>;
}

function YoutubeIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="2.2" y="5.2" width="19.6" height="13.6" rx="4" fill="#ef4444"/><path d="m10 9 5.2 3-5.2 3V9Z" fill="white"/></svg>;
}

const items = [
  { href: "/#automacao", label: "Painel ao vivo", icon: HomeIcon },
  { href: "/#configurar", label: "Criar Shorts", icon: ShortsIcon },
  { href: "/editor-ia", label: "Editor de vídeo", icon: EditIcon },
  { href: "/projetos", label: "Projetos", icon: ProjectsIcon },
  { href: "/#processamento", label: "Processamentos", icon: ProcessIcon },
  { href: "/#cortes", label: "Publicações", icon: PublishIcon },
  { href: "/metricas-tiktok", label: "Métricas TikTok", icon: MetricsIcon },
];

export default function PlatformNavigation() {
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const [hash, setHash] = useState("");

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/auth/me`, { credentials: "include", cache: "no-store" })
      .then((response) => { if (active) setVisible(response.ok); })
      .catch(() => { if (active) setVisible(false); });
    return () => { active = false; };
  }, [pathname]);

  useEffect(() => {
    if (!visible) {
      document.body.classList.remove("platform-nav-open");
      return;
    }
    document.body.classList.add("platform-nav-open");
    return () => document.body.classList.remove("platform-nav-open");
  }, [visible]);

  useEffect(() => {
    const sync = () => setHash(window.location.hash || "");
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [pathname]);

  const activeHref = useMemo(() => {
    if (pathname === "/editor-ia") return "/editor-ia";
    if (pathname === "/projetos") return "/projetos";
    if (pathname === "/metricas-tiktok") return "/metricas-tiktok";
    if (pathname === "/") {
      if (hash === "#configurar") return "/#configurar";
      if (hash === "#processamento") return "/#processamento";
      if (hash === "#cortes") return "/#cortes";
      return "/#automacao";
    }
    return "";
  }, [pathname, hash]);

  if (!visible) return null;

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-[70] hidden w-[248px] flex-col border-r border-[#e6e6e6] bg-white text-[#111] shadow-[8px_0_30px_rgba(17,17,17,.03)] xl:flex" aria-label="Menu principal da plataforma">
        <div className="border-b border-[#e6e6e6] px-5 py-5">
          <a href="/#automacao" className="flex items-center">
            <BrandLogo size="md" />
          </a>
        </div>

        <nav className="flex-1 px-3 py-5">
          <div className="mb-3 px-3 text-[10px] font-semibold uppercase leading-4 text-[#8a8a8a]">Área de trabalho</div>
          <div className="space-y-1">
            {items.map((item) => {
              const active = activeHref === item.href;
              const Icon = item.icon;
              return (
                <a
                  key={item.href}
                  href={item.href}
                  className={`relative flex min-h-11 items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-colors ${active ? "bg-red-50 text-[#e00000] shadow-sm" : "text-[#555] hover:bg-[#f6f6f6] hover:text-[#111]"}`}
                >
                  {active && <span className="absolute -left-3 h-6 w-[3px] rounded-r bg-[#ff0000]" />}
                  <Icon className={`h-[18px] w-[18px] ${active ? "text-[#ff0000]" : "text-[#999]"}`} />
                  <span className={`min-w-0 leading-5 ${active ? "font-semibold" : "font-medium"}`}>{item.label}</span>
                </a>
              );
            })}
          </div>
        </nav>

        <div className="mb-[154px] border-t border-[#e6e6e6] px-5 py-4">
          <div className="flex items-center gap-2 text-[11px] text-[#777]">
            <TikTokIcon className="h-4 w-4 text-[#111]" />
            <YoutubeIcon className="h-4 w-4" />
            <span>TikTok · YouTube</span>
          </div>
        </div>
      </aside>

      <nav className="fixed bottom-0 left-0 right-0 z-[70] border-t border-[#e4e7ec] bg-white/98 px-2 pb-[max(8px,env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_24px_rgba(16,24,40,.06)] backdrop-blur xl:hidden" aria-label="Menu principal da plataforma">
        <div className="mx-auto flex max-w-2xl items-start justify-start gap-1 overflow-x-auto sm:justify-around">
          {items.map((item) => {
            const active = activeHref === item.href;
            const Icon = item.icon;
            return (
              <a key={item.href} href={item.href} className={`flex min-w-[62px] flex-col items-center gap-1 rounded-lg px-2 py-1.5 text-center text-[9px] font-medium leading-tight ${active ? "bg-red-50 text-[#e00000]" : "text-[#667085]"}`}>
                <Icon className="h-[18px] w-[18px]" />
                <span>{item.label.replace("Processamentos", "Processar").replace("Publicações", "Publicar").replace("Painel ao vivo", "Painel").replace("Editor de vídeo", "Editor").replace("Métricas TikTok", "Métricas")}</span>
              </a>
            );
          })}
        </div>
      </nav>
    </>
  );
}
