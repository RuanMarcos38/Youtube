"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

type LiveAudience = {
  concurrent_viewers: number;
  active_live_broadcasts: number;
  available: boolean;
  refreshed_at: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const ACTIVE_REFRESH_MS = 15_000;
const IDLE_REFRESH_MS = 60_000;

async function loadLiveAudience(): Promise<LiveAudience> {
  const response = await fetch(`${API_URL}/api/youtube/live-audience`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`live-audience ${response.status}`);
  return response.json();
}

function audienceDetail(audience: LiveAudience | null, failed: boolean) {
  if (failed) return "Não foi possível atualizar agora. Nova tentativa automática em instantes.";
  if (!audience) return "Atualizando a audiência ao vivo...";
  if (!audience.available) return "Sem permissão para consultar a audiência das transmissões ao vivo deste canal.";
  if (audience.active_live_broadcasts === 0) {
    return "Nenhuma transmissão ao vivo agora. O YouTube não fornece audiência simultânea dos vídeos gravados.";
  }
  const lives = audience.active_live_broadcasts === 1 ? "1 transmissão ao vivo" : `${audience.active_live_broadcasts} transmissões ao vivo`;
  return `${lives} · soma de espectadores simultâneos · atualização automática a cada 15s`;
}

export default function LiveAudienceCard() {
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [audience, setAudience] = useState<LiveAudience | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const locateTarget = () => {
      const next = document.querySelector<HTMLElement>(".sf-metric-grid");
      setTarget((current) => current === next ? current : next);
    };

    locateTarget();
    const observer = new MutationObserver(locateTarget);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!target) {
      setAudience(null);
      setFailed(false);
      return;
    }

    let stopped = false;
    let timer: number | null = null;

    const schedule = (delay: number) => {
      if (stopped) return;
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(() => void refresh(), delay);
    };

    const refresh = async () => {
      if (stopped) return;
      if (document.visibilityState !== "visible") {
        schedule(IDLE_REFRESH_MS);
        return;
      }

      try {
        const next = await loadLiveAudience();
        if (stopped) return;
        setAudience(next);
        setFailed(false);
        schedule(next.active_live_broadcasts > 0 ? ACTIVE_REFRESH_MS : IDLE_REFRESH_MS);
      } catch {
        if (stopped) return;
        setFailed(true);
        schedule(IDLE_REFRESH_MS);
      }
    };

    const handleVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };

    document.addEventListener("visibilitychange", handleVisibility);
    void refresh();

    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [target]);

  if (!target) return null;

  const active = Boolean(audience?.available && audience.active_live_broadcasts > 0);
  const value = audience?.available ? new Intl.NumberFormat("pt-BR").format(audience.concurrent_viewers) : "—";

  return createPortal(
    <div className="sf-card-soft flex min-h-[156px] min-w-0 flex-col justify-between p-4 sm:p-5" aria-live="polite">
      <div className="flex items-center justify-between gap-2">
        <div className="sf-label">Assistindo agora</div>
        {active && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-2 py-1 text-[9px] font-semibold uppercase text-red-700">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#ff0000]" />
            Ao vivo
          </span>
        )}
      </div>
      <div>
        <div className="metric-value sf-metric-number mt-3">{failed && !audience ? "—" : value}</div>
        <div className="mt-2 text-xs leading-5 text-[#666]">{audienceDetail(audience, failed)}</div>
      </div>
    </div>,
    target,
  );
}
