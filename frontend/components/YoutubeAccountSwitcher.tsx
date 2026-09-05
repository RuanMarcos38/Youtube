"use client";

import { useEffect, useState } from "react";
import { youtubeStatus } from "@/lib/api";

function YoutubeIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><rect x="2.2" y="5.2" width="19.6" height="13.6" rx="4" fill="#ef4444"/><path d="m10 9 5.2 3-5.2 3V9Z" fill="white"/></svg>;
}

export default function YoutubeAccountSwitcher() {
  const [configured, setConfigured] = useState(false);
  const [connected, setConnected] = useState(false);
  const [channelTitle, setChannelTitle] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

  function chooseAccount() {
    setLoading(true);
    // Use a normal same-origin navigation instead of fetch -> redirect. This
    // keeps the ShortsFlow session cookie attached and avoids CORS/network
    // failures when NEXT_PUBLIC_API_URL points to another host.
    window.location.assign("/api/youtube/oauth/authorize");
  }

  if (!configured) return null;

  return (
    <div className="fixed bottom-[70px] left-3 right-3 z-[80] rounded-xl border border-[#e6e6e6] bg-white p-3 shadow-[0_14px_34px_rgba(17,17,17,.10)] xl:bottom-4 xl:left-4 xl:right-auto xl:w-[216px]">
      <div className="flex items-center gap-2">
        <YoutubeIcon />
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-medium text-[#888]">Canal do YouTube</div>
          <div className="mt-0.5 truncate text-xs font-semibold text-[#344054]">
            {connected ? channelTitle || "YouTube conectado" : "Nenhum canal conectado"}
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={chooseAccount}
        disabled={loading}
        className="sf-button sf-button-outline mt-3 w-full text-[11px] disabled:cursor-wait disabled:opacity-60"
      >
        {loading ? "Abrindo Google..." : connected ? "Trocar conta" : "Conectar canal"}
      </button>
    </div>
  );
}
