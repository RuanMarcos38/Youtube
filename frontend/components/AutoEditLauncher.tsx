"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function AutoEditLauncher() {
  const [visible, setVisible] = useState(false);

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
  }, []);

  if (!visible) return null;

  return (
    <a
      href="/editor-ia"
      className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-full border border-black/10 bg-[#111815] px-5 py-3 text-sm font-black text-white shadow-[0_16px_40px_rgba(17,24,21,.24)] transition hover:-translate-y-0.5"
      aria-label="Abrir Auto-Edit IA"
    >
      <span className="text-[#b8f238]">✦</span>
      Auto-Edit IA
    </a>
  );
}
