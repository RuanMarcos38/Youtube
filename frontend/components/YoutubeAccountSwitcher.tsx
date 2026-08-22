"use client";

import { useEffect, useState } from "react";
import { youtubeStart, youtubeStatus } from "@/lib/api";

function YoutubeIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><rect x="2.2" y="5.2" width="19.6" height="13.6" rx="4" fill="currentColor"/><path d="m10 9 5.2 3-5.2 3V9Z" fill="#0d241d"/></svg>;
}

export default function YoutubeAccountSwitcher() {
  const [configured, setConfigured] = useState(false);
  const [connected, setConnected] = useState(false);
  const [channelTitle, setChannelTitle] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function refreshStatus() {
    try {
      const status = await youtubeStatus();
      setConfigured(Boolean(status.configured ?? true));
      setConnected(Boolean(status.connected));
      setChannelTitle(status.channel_title ?? null);
    } catch {
      setConfigured(false);
      setConnected(false);
      setChannelTitle(null);
    }
  }

  useEffect(() => {
    void refreshStatus();
  }, []);

  async function chooseAccount() {
    setLoading(true);
    setError("");
    try {
      const result = await youtubeStart();
      window.location.assign(result.authorization_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível abrir o seletor de contas do Google.");
      setLoading(false);
    }
  }

  if (!configured) return null;

  return (
    <div className="fixed bottom-[92px] left-3 right-3 z-[80] rounded-2xl border border-white/10 bg-[#122e25] p-3 text-white shadow-[0_18px_55px_rgba(13,36,29,.30)] xl:bottom-6 xl:left-6 xl:right-auto xl:w-[196px]">
      <div className="flex items-center gap-2 text-[10px] font-bold text-white/55">
        <YoutubeIcon />
        <span>Canal atual</span>
      </div>
      <div className="mt-1 truncate text-xs font-black text-white">
        {connected ? channelTitle || "YouTube conectado" : "Nenhum canal conectado"}
      </div>
      <button
        type="button"
        onClick={chooseAccount}
        disabled={loading}
        title="Abrir o Google para escolher outro e-mail ou canal do YouTube"
        className="mt-3 w-full rounded-xl bg-[#b8f238] px-3 py-2.5 text-[11px] font-black text-[#111815] transition hover:-translate-y-0.5 disabled:cursor-wait disabled:opacity-60"
      >
        {loading ? "Abrindo Google..." : connected ? "Escolher outra conta" : "Conectar YouTube"}
      </button>
      <div className="mt-2 text-[9px] leading-4 text-white/45">
        Cada perfil mantém seu próprio canal isolado.
      </div>
      {error && <div className="mt-2 rounded-xl border border-red-300/20 bg-red-500/10 px-2 py-2 text-[10px] font-bold text-red-100">{error}</div>}
    </div>
  );
}
