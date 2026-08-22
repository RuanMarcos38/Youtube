"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type IconProps = { className?: string };

function HomeIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M3 10.8 12 3l9 7.8v9.1a1.1 1.1 0 0 1-1.1 1.1h-5.4v-6H9.5v6H4.1A1.1 1.1 0 0 1 3 19.9v-9.1Z" fill="currentColor" /></svg>;
}

function PlayIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="2.5" y="4" width="19" height="16" rx="3" stroke="currentColor" strokeWidth="1.8"/><path d="m10 8.8 5.8 3.2-5.8 3.2V8.8Z" fill="currentColor"/></svg>;
}

function SparkleIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M12 2.8c.8 4.6 2.6 6.4 7.2 7.2-4.6.8-6.4 2.6-7.2 7.2-.8-4.6-2.6-6.4-7.2-7.2 4.6-.8 6.4-2.6 7.2-7.2Z" fill="currentColor"/><path d="M18.5 15.2c.35 2 1.15 2.8 3.15 3.15-2 .35-2.8 1.15-3.15 3.15-.35-2-1.15-2.8-3.15-3.15 2-.35 2.8-1.15 3.15-3.15Z" fill="currentColor" opacity=".65"/></svg>;
}

function ProjectsIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2.5" stroke="currentColor" strokeWidth="1.8"/><path d="M8 9h8M8 12h8M8 15h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>;
}

function ProcessIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M19 8a7.5 7.5 0 1 0 .7 6.7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><path d="M19 4.5V8h-3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>;
}

function PublishIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M12 20V5m0 0-5 5m5-5 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function TikTokIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M14.7 3.2c.5 2.4 1.8 3.8 4.1 4.4v3.1a9 9 0 0 1-4.1-1.2v5.6a5.8 5.8 0 1 1-5-5.7v3.2a2.7 2.7 0 1 0 1.8 2.5V3.2h3.2Z" fill="currentColor"/></svg>;
}

function YoutubeIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="2.2" y="5.2" width="19.6" height="13.6" rx="4" fill="currentColor"/><path d="m10 9 5.2 3-5.2 3V9Z" fill="#0d241d"/></svg>;
}

const items = [
  { href: "/#automacao", label: "Início", icon: HomeIcon },
  { href: "/#configurar", label: "Criar Shorts", icon: PlayIcon },
  { href: "/editor-ia", label: "Editor IA", icon: SparkleIcon },
  { href: "/projetos", label: "Projetos", icon: ProjectsIcon },
  { href: "/#processamento", label: "Processamento", icon: ProcessIcon },
  { href: "/#cortes", label: "Publicar", icon: PublishIcon },
];

export default function PlatformNavigation() {
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const [hash, setHash] = useState("");

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/auth/me`, { credentials: "include", cache: "no-store" })
      .then((response) => {
        if (active) setVisible(response.ok);
      })
      .catch(() => {
        if (active) setVisible(false);
      });
    return () => {
      active = false;
    };
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
      <nav className="fixed bottom-4 left-4 top-[108px] z-[70] hidden w-[216px] flex-col overflow-hidden rounded-[24px] border border-white/10 bg-[#0d241d] p-3 text-white shadow-[0_24px_70px_rgba(13,36,29,.30)] xl:flex" aria-label="Menu principal da plataforma">
        <div className="px-2 pb-4 pt-2">
          <span className="inline-flex rounded-sm bg-[#b8f238] px-2 py-1 text-[9px] font-black uppercase tracking-[.18em] text-[#0d241d]">ShortsFlow</span>
        </div>
        <div className="grid gap-1.5">
          {items.map((item) => {
            const active = activeHref === item.href;
            const Icon = item.icon;
            return (
              <a
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-3 text-xs font-black transition ${active ? "bg-[#b8f238] text-[#111815] shadow-[0_10px_28px_rgba(184,242,56,.18)]" : "text-white/86 hover:bg-white/10 hover:text-white"}`}
              >
                <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${active ? "bg-[#0d241d]/8" : "bg-white/10"}`}><Icon /></span>
                {item.label}
              </a>
            );
          })}
        </div>
        <div className="mt-auto h-[188px] shrink-0 border-t border-white/8 pt-4">
          <div className="flex items-center gap-2 px-2 text-[10px] font-bold uppercase tracking-[.13em] text-white/45">
            <TikTokIcon className="h-3.5 w-3.5 text-white/65" />
            <YoutubeIcon className="h-3.5 w-3.5 text-[#ff3b30]" />
            Vídeo + IA
          </div>
        </div>
      </nav>

      <nav className="fixed bottom-3 left-3 right-3 z-[70] overflow-x-auto rounded-2xl border border-black/10 bg-[#0d241d]/96 p-2 text-white shadow-[0_18px_55px_rgba(13,36,29,.28)] backdrop-blur-xl xl:hidden" aria-label="Menu principal da plataforma">
        <div className="flex min-w-max items-center gap-1">
          {items.map((item) => {
            const active = activeHref === item.href;
            const Icon = item.icon;
            return (
              <a key={item.href} href={item.href} className={`flex items-center gap-2 rounded-xl px-3 py-2 text-[11px] font-black transition ${active ? "bg-[#b8f238] text-[#111815]" : "text-white/80"}`}>
                <Icon className="h-3.5 w-3.5" />{item.label}
              </a>
            );
          })}
        </div>
      </nav>
    </>
  );
}
