"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

import { generateClipSeo, listClips } from "@/lib/api";
import type { Clip } from "@/lib/types";


const BLOCKED = new Set(["upload_queued", "uploading", "uploaded"]);


export default function ShortsSeoPanel() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

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

        let node = card.querySelector<HTMLElement>("[data-shorts-seo-host]");
        if (!node) {
          node = document.createElement("div");
          node.dataset.shortsSeoHost = "true";
          const publishingHost = card.querySelector<HTMLElement>("[data-publishing-enhancements-host]");
          const header = card.firstElementChild;
          if (publishingHost?.nextSibling) card.insertBefore(node, publishingHost.nextSibling);
          else if (publishingHost) publishingHost.after(node);
          else if (header?.nextSibling) card.insertBefore(node, header.nextSibling);
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
    const timer = window.setInterval(sync, 1000);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      window.removeEventListener("hashchange", sync);
      window.clearInterval(timer);
      currentHost?.remove();
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
    if (!host) return;
    void refresh({ silent: false });
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [host]);

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

  if (!host) return null;

  return createPortal(
    <section className="border-t border-[#e8e8e8] bg-white p-4 md:p-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[.08em] text-[#ff0000]">SEO por Short</div>
          <h3 className="mt-1 text-base font-semibold text-[#111]">Título, descrição e tags específicos para cada corte</h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[#667085]">
            Os novos Shorts já recebem SEO automaticamente com base na própria transcrição. Use “Gerar SEO” para refazer o pacote antes da publicação.
          </p>
        </div>
        <div className="rounded-lg border border-[#e8e8e8] bg-[#fafafa] px-3 py-2 text-[11px] font-semibold text-[#555]">
          {clips.length} Short{clips.length === 1 ? "" : "s"} disponível{clips.length === 1 ? "" : "is"}
        </div>
      </div>

      {notice && <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{notice}</div>}
      {error && <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div>}

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {clips.map((clip) => {
          const blocked = BLOCKED.has(clip.status);
          return (
            <article key={clip.id} className="rounded-xl border border-[#e7e7e7] bg-[#fafafa] p-3.5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="text-[10px] font-semibold uppercase tracking-[.06em] text-[#777]">Short #{clip.id} · {clip.tags.length} tags</div>
                  <div className="mt-1 line-clamp-2 text-sm font-semibold leading-5 text-[#111]">{clip.title || "Título ainda não gerado"}</div>
                  <div className="mt-2 line-clamp-3 text-[11px] leading-5 text-[#667085]">{clip.description || "Descrição ainda não gerada."}</div>
                  {!!clip.tags.length && (
                    <div className="mt-2 line-clamp-2 text-[10px] leading-4 text-[#555]">
                      {clip.tags.slice(0, 8).map((tag) => `#${tag.replace(/\s+/g, "")}`).join(" ")}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => void generate(clip)}
                  disabled={blocked || busyId !== null}
                  className="sf-button sf-button-outline shrink-0 disabled:cursor-not-allowed disabled:opacity-40"
                  title={blocked ? "SEO fica bloqueado depois que o Short entra na fila/publicação." : "Regenerar SEO usando o conteúdo real deste Short"}
                >
                  {busyId === clip.id ? "Gerando SEO..." : "Gerar SEO"}
                </button>
              </div>
            </article>
          );
        })}
      </div>

      {!clips.length && (
        <div className="mt-4 rounded-xl border border-dashed border-[#ddd] bg-[#fafafa] p-6 text-center text-xs text-[#777]">
          Nenhum Short disponível para ajuste de SEO agora.
        </div>
      )}
    </section>,
    host,
  );
}
