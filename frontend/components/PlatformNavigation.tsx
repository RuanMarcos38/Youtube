"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

const items = [
  { href: "/#automacao", label: "Início", icon: "⌂" },
  { href: "/#configurar", label: "Criar Shorts", icon: "▶" },
  { href: "/editor-ia", label: "Editor IA", icon: "✦" },
  { href: "/projetos", label: "Projetos", icon: "▣" },
  { href: "/#processamento", label: "Processamento", icon: "◌" },
  { href: "/#cortes", label: "Publicar", icon: "↑" },
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
      <nav className="fixed left-4 top-1/2 z-[70] hidden -translate-y-1/2 rounded-2xl border border-black/10 bg-[#0d241d]/95 p-2 text-white shadow-[0_18px_55px_rgba(13,36,29,.28)] backdrop-blur-xl xl:block" aria-label="Menu principal da plataforma">
        <div className="mb-2 px-2 py-2 text-[9px] font-black uppercase tracking-[.18em] text-[#b8f238]">ShortsFlow</div>
        <div className="grid gap-1">
          {items.map((item) => {
            const active = activeHref === item.href;
            return (
              <a
                key={item.href}
                href={item.href}
                className={`flex min-w-[150px] items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-black transition ${active ? "bg-[#b8f238] text-[#111815]" : "text-white/80 hover:bg-white/10 hover:text-white"}`}
              >
                <span className="grid h-6 w-6 place-items-center rounded-lg bg-white/10 text-sm">{item.icon}</span>
                {item.label}
              </a>
            );
          })}
        </div>
      </nav>

      <nav className="fixed bottom-3 left-3 right-3 z-[70] overflow-x-auto rounded-2xl border border-black/10 bg-[#0d241d]/95 p-2 text-white shadow-[0_18px_55px_rgba(13,36,29,.28)] backdrop-blur-xl xl:hidden" aria-label="Menu principal da plataforma">
        <div className="flex min-w-max items-center gap-1">
          {items.map((item) => {
            const active = activeHref === item.href;
            return (
              <a
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 rounded-xl px-3 py-2 text-[11px] font-black transition ${active ? "bg-[#b8f238] text-[#111815]" : "text-white/80"}`}
              >
                <span>{item.icon}</span>{item.label}
              </a>
            );
          })}
        </div>
      </nav>
    </>
  );
}
