"use client";

import { useEffect, useState } from "react";
import { youtubeStart, youtubeStatus } from "@/lib/api";

function YoutubeIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><rect x="2.2" y="5.2" width="19.6" height="13.6" rx="4" fill="#ef4444"/><path d="m10 9 5.2 3-5.2 3V9Z" fill="white"/></svg>;
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

  useEffect(() => { void refreshStatus(); }, []);

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
    <div className="fixed bottom-[70px] left-3 right-3 z-[80] rounded-xl border border-[#e4e7ec] bg-white p-3 shadow-[0_8px_24px_rgba(16,24,40,.10)] xl:bottom-4 xl:left-4 xl:right-auto xl:w-[216px] xl:border-white/10 xl:bg-[#1d2939] xl:text-white xl:shadow-none">
      <div className="flex items-center gap-2">
        <YoutubeIcon />
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-medium text-[#98a2b3] xl:text-white/45">Canal do YouTube</div>
          <div className="mt-0.5 truncate text-xs font-semibold text-[#344054] xl:text-white">
            {connected ? channelTitle || "YouTube conectado" : "Nenhum canal conectado"}
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={chooseAccount}
        disabled={loading}
        className="mt-3 w-full rounded-lg border border-[#d0d5dd] bg-white px-3 py-2 text-[11px] font-semibold text-[#344054] transition hover:bg-[#f9fafb] disabled:cursor-wait disabled:opacity-60 xl:border-white/15 xl:bg-white/[.06] xl:text-white xl:hover:bg-white/10"
      >
        {loading ? "Abrindo Google..." : connected ? "Trocar conta" : "Conectar canal"}
      </button>
      {error && <div className="mt-2 rounded-lg bg-red-50 px-2.5 py-2 text-[10px] font-medium text-red-700 xl:bg-red-500/10 xl:text-red-100">{error}</div>}
    </div>
  );
}
