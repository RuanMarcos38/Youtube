"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

import { generateClipSeo, listClips } from "@/lib/api";
import type { Clip } from "@/lib/types";

const BLOCKED = new Set(["upload_queued", "uploading", "uploaded"]);

export default function ShortsSeoPanel() {
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [open, setOpen] = useState(false);
  const [clips, setClips] = useState<Clip[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setMounted(true);

    const syncVisibility = () => {
      const active = Boolean(document.getElementById("cortes"));
      setVisible(active);
      if (!active) setOpen(false);
    };

    syncVisibility();
    const observer = new MutationObserver(syncVisibility);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", syncVisibility);
    const timer = window.setInterval(syncVisibility, 800);

    return () => {
      observer.disconnect();
      window.removeEventListener("hashchange", syncVisibility);
      window.clearInterval(timer);
    };
  }, []);

  async function refresh({ silent = true }: { silent?: boolean } = {}) {
    try {
      setClips(await listClips());
      if (!silent) setError("");
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Não foi possível carregar os Shorts para SEO.");
    }
  }

  useEffect(() => {
    if (!visible) return;
    void refresh({ silent: false });
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [visible]);

  async function generate(clip: Clip) {
    if (BLOCKED.has(clip.status)) return;
    setBusyId(clip.id);
    setNotice("");
    setError("");
    try {
      const updated = await generateClipSeo(clip.id);
      setClips((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice(`SEO do Short #${clip.id} regenerado com título, descrição e tags específicos do corte.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível gerar o SEO deste Short.");
    } finally {
      setBusyId(null);
    }
  }

  if (!mounted || !visible) return null;

  return createPortal(
    <>
      <button
        type="button"
        data-shorts-seo-trigger="true"
        onClick={() => setOpen((current) => !current)}
        className="fixed right-5 top-[156px] z-[120] flex items-center gap-2 rounded-xl border border-[#ff0000] bg-white px-4 py-3 text-sm font-bold text-[#d90000] shadow-lg transition hover:bg-[#fff5f5]"
        aria-expanded={open}
        aria-controls="shorts-seo-panel"
      >
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#ff0000]" />
        SEO Shorts
        {!!clips.length && <span className="rounded-full bg-[#ff0000] px-2 py-0.5 text-[10px] text-white">{clips.length}</span>}
      </button>

      {open && (
        <aside
          id="shorts-seo-panel"
          data-shorts-seo-panel="true"
          className="fixed right-5 top-[212px] z-[120] flex max-h-[calc(100vh-232px)] w-[min(470px,calc(100vw-32px))] flex-col overflow-hidden rounded-2xl border border-[#e5e5e5] bg-white shadow-2xl"
        >
          <div className="flex items-start justify-between gap-4 border-b border-[#ededed] p-4">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[.08em] text-[#ff0000]">SEO por Short</div>
              <h3 className="mt-1 text-base font-bold text-[#111]">Título, descrição e tags</h3>
              <p className="mt-1 text-xs leading-5 text-[#667085]">
                Novos Shorts recebem SEO automaticamente. Use “Gerar SEO” somente quando quiser refazer antes de publicar.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="shrink-0 rounded-lg border border-[#e5e5e5] px-2.5 py-1.5 text-xs font-semibold text-[#555] hover:bg-[#f7f7f7]"
              aria-label="Fechar painel de SEO"
            >
              Fechar
            </button>
          </div>

          {notice && <div className="mx-4 mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{notice}</div>}
          {error && <div className="mx-4 mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div>}

          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {clips.map((clip) => {
              const blocked = BLOCKED.has(clip.status);
              return (
                <article key={clip.id} className="rounded-xl border border-[#e7e7e7] bg-[#fafafa] p-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-[10px] font-bold uppercase tracking-[.06em] text-[#777]">
                        Short #{clip.id} · {clip.tags.length} tags
                      </div>
                      <div className="mt-1 text-sm font-bold leading-5 text-[#111]">{clip.title || "Título ainda não gerado"}</div>
                      <div className="mt-2 text-[11px] leading-5 text-[#667085]">{clip.description || "Descrição ainda não gerada."}</div>
                      {!!clip.tags.length && (
                        <div className="mt-2 text-[10px] leading-4 text-[#555]">
                          {clip.tags.slice(0, 10).map((tag) => `#${tag.replace(/\s+/g, "")}`).join(" ")}
                        </div>
                      )}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => void generate(clip)}
                    disabled={blocked || busyId !== null}
                    className="mt-3 w-full rounded-lg border border-[#d9d9d9] bg-white px-3 py-2 text-xs font-bold text-[#222] transition hover:border-[#ff0000] hover:text-[#d90000] disabled:cursor-not-allowed disabled:opacity-40"
                    title={blocked ? "SEO fica bloqueado depois que o Short entra na fila/publicação." : "Regenerar SEO usando o conteúdo real deste Short"}
                  >
                    {busyId === clip.id ? "Gerando SEO..." : blocked ? "SEO bloqueado após envio" : "Gerar SEO"}
                  </button>
                </article>
              );
            })}

            {!clips.length && !error && (
              <div className="rounded-xl border border-dashed border-[#ddd] bg-[#fafafa] p-6 text-center text-xs text-[#777]">
                Nenhum Short disponível para ajuste de SEO agora.
              </div>
            )}
          </div>
        </aside>
      )}
    </>,
    document.body,
  );
}
