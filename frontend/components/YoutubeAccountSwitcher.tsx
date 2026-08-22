"use client";

import { useEffect, useState } from "react";
import { youtubeStart, youtubeStatus } from "@/lib/api";

export default function YoutubeAccountSwitcher() {
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    youtubeStatus()
      .then((status) => setVisible(Boolean(status.connected)))
      .catch(() => setVisible(false));
  }, []);

  async function switchAccount() {
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

  if (!visible) return null;

  return (
    <div className="fixed bottom-5 left-5 z-[70] max-w-[calc(100vw-2.5rem)]">
      <button
        type="button"
        onClick={switchAccount}
        disabled={loading}
        title="Escolher outro e-mail ou canal do YouTube"
        className="rounded-xl border border-black/10 bg-white px-4 py-3 text-xs font-black text-[#111815] shadow-xl transition hover:-translate-y-0.5 disabled:cursor-wait disabled:opacity-60"
      >
        {loading ? "Abrindo Google..." : "Trocar conta YouTube"}
      </button>
      {error && (
        <div className="mt-2 max-w-sm rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-bold text-red-700 shadow-lg">
          {error}
        </div>
      )}
    </div>
  );
}
