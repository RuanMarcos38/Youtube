"use client";

import { useEffect, useState } from "react";
import { youtubeStart, youtubeStatus } from "@/lib/api";

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
    <div className="fixed bottom-5 left-5 z-[70] max-w-[calc(100vw-2.5rem)] rounded-2xl border border-black/10 bg-white p-2 shadow-xl">
      <div className="mb-2 max-w-[260px] px-2 pt-1 text-[10px] font-bold text-[#6e7971]">
        {connected
          ? <>Canal atual: <strong className="text-[#111815]">{channelTitle || "YouTube conectado"}</strong></>
          : "Nenhum canal conectado neste perfil."}
      </div>
      <button
        type="button"
        onClick={chooseAccount}
        disabled={loading}
        title="Abrir o Google para escolher outro e-mail ou canal do YouTube"
        className="w-full rounded-xl bg-[#111815] px-4 py-3 text-xs font-black text-white transition hover:-translate-y-0.5 disabled:cursor-wait disabled:opacity-60"
      >
        {loading ? "Abrindo Google..." : connected ? "Escolher outra conta YouTube" : "Conectar conta YouTube"}
      </button>
      <div className="mt-2 max-w-[260px] px-2 pb-1 text-[10px] leading-4 text-[#6e7971]">
        O Google abrirá <strong>Escolher uma conta</strong> / <strong>Usar outra conta</strong>. Cada perfil mantém seu próprio canal isolado.
      </div>
      {error && (
        <div className="mt-2 max-w-[300px] rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-bold text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
