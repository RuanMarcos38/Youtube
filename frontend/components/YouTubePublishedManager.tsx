"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

import { deleteYouTubePublication, youtubePublishedClips } from "@/lib/publications-api";
import type { Clip } from "@/lib/types";

function fmtDateTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function YouTubePublishedManager() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [published, setPublished] = useState<Clip[]>([]);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let currentHost: HTMLElement | null = null;
    let raf = 0;

    const sync = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const card = document.querySelector<HTMLElement>("#cortes > .sf-card");
        if (!card) {
          setHost(null);
          return;
        }

        let node = card.querySelector<HTMLElement>("[data-youtube-published-manager-host]");
        if (!node) {
          node = document.createElement("div");
          node.dataset.youtubePublishedManagerHost = "true";
          const enhancements = card.querySelector<HTMLElement>("[data-publishing-enhancements-host]");
          if (enhancements?.nextSibling) card.insertBefore(node, enhancements.nextSibling);
          else card.appendChild(node);
        }
        currentHost = node;
        setHost(node);
      });
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", sync);
    const timer = window.setInterval(sync, 1200);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      window.removeEventListener("hashchange", sync);
      window.clearInterval(timer);
      currentHost?.remove();
    };
  }, []);

  async function refresh({ silent = true }: { silent?: boolean } = {}) {
    if (!silent) setLoading(true);
    try {
      const result = await youtubePublishedClips();
      setPublished(result.clips);
      if (!silent) setError("");
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Não foi possível carregar os vídeos publicados.");
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    if (!host) return;
    void refresh({ silent: false });
    const timer = window.setInterval(() => void refresh(), 10000);
    return () => window.clearInterval(timer);
  }, [host]);

  async function removePublishedVideo(clip: Clip) {
    if (!clip.youtube_video_id) return;
    const confirmed = window.confirm(
      `Excluir permanentemente “${clip.title}” do YouTube e removê-lo do ShortsFlow?\n\n` +
      "Esta ação não pode ser desfeita. O vídeo deixará de existir no canal do YouTube."
    );
    if (!confirmed) return;

    setDeletingId(clip.id);
    setError("");
    setNotice("");
    try {
      const result = await deleteYouTubePublication(clip.id);
      setPublished((current) => current.filter((item) => item.id !== clip.id));
      setNotice(
        result.already_missing
          ? "O vídeo já não existia no YouTube e foi removido do histórico do ShortsFlow."
          : "Vídeo excluído do YouTube e removido do ShortsFlow com sucesso."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir o vídeo.");
    } finally {
      setDeletingId(null);
    }
  }

  if (!host) return null;

  const needsReconnect = error.toLowerCase().includes("reconecte o youtube");

  return createPortal(
    <div className="border-t border-[#e8e8e8] bg-white p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[.08em] text-[#ff0000]">Publicados no YouTube</div>
          <h3 className="mt-1 text-base font-semibold text-[#111]">Gerenciar vídeos já enviados</h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[#667085]">
            Use esta área quando um vídeo for publicado por engano ou sair desconfigurado. A exclusão remove o vídeo do canal do YouTube e também da área de publicações do ShortsFlow.
          </p>
        </div>
        <button type="button" onClick={() => void refresh({ silent: false })} disabled={loading || deletingId !== null} className="sf-button sf-button-outline disabled:opacity-40">
          {loading ? "Atualizando..." : `Atualizar (${published.length})`}
        </button>
      </div>

      <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] font-medium leading-5 text-amber-900">
        Exclusão permanente: o botão abaixo só aparece para vídeos que o ShortsFlow confirmou como publicados. Antes de excluir, o sistema solicita uma confirmação adicional.
      </div>

      {notice && <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{notice}</div>}
      {error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">
          <div>{error}</div>
          {needsReconnect && (
            <a href="/api/youtube/oauth/authorize" className="sf-button sf-button-youtube mt-3 inline-flex">Reconectar YouTube para permitir exclusão</a>
          )}
        </div>
      )}

      {published.length ? (
        <div className="mt-4 divide-y divide-[#ededed] overflow-hidden rounded-xl border border-[#e7e7e7]">
          {published.map((clip) => (
            <article key={clip.id} className="grid gap-3 bg-white p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-red-50 px-2 py-1 text-[9px] font-black uppercase text-red-700">Publicado</span>
                  <span className="text-[10px] text-[#777]">{fmtDateTime(clip.updated_at || clip.created_at)}</span>
                </div>
                <h4 className="mt-2 line-clamp-2 text-sm font-black text-[#111]">{clip.title}</h4>
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] text-[#667085]">
                  <span>ID YouTube: {clip.youtube_video_id}</span>
                  <a href={`https://www.youtube.com/watch?v=${clip.youtube_video_id}`} target="_blank" rel="noreferrer" className="font-black text-red-600 hover:underline">Abrir no YouTube</a>
                </div>
              </div>
              <button
                type="button"
                onClick={() => void removePublishedVideo(clip)}
                disabled={deletingId !== null}
                className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs font-black text-red-700 transition hover:bg-red-100 disabled:opacity-40"
              >
                {deletingId === clip.id ? "Excluindo no YouTube..." : "Excluir do ShortsFlow e YouTube"}
              </button>
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-dashed border-[#ddd] bg-[#fafafa] p-6 text-center text-xs text-[#777]">
          Nenhum vídeo publicado pelo ShortsFlow disponível para exclusão.
        </div>
      )}
    </div>,
    host,
  );
}
