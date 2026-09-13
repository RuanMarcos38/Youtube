"use client";

import { createPortal } from "react-dom";
import { useEffect, useMemo, useState } from "react";

import { API_URL, listClips } from "@/lib/api";
import type { Clip } from "@/lib/types";

const DELETE_ALLOWED_STATUSES = new Set(["ready", "approved", "upload_failed"]);

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    ready: "Pronto",
    approved: "Aprovado, ainda não publicado",
    upload_failed: "Falha no envio",
  };
  return labels[status] || status;
}

function isDeletable(clip: Clip) {
  return DELETE_ALLOWED_STATUSES.has(clip.status || "") && !clip.youtube_video_id;
}

async function responseError(response: Response, fallback: string) {
  try {
    const body = await response.json() as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  } catch {}
  return fallback;
}

async function deleteClip(id: number) {
  const response = await fetch(`${API_URL}/api/clips/${id}`, {
    method: "DELETE",
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "Não foi possível excluir este corte."));
  }
}

async function deleteClipsBatch(ids: number[]) {
  const response = await fetch(`${API_URL}/api/clips/delete-batch`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clip_ids: ids }),
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "Não foi possível excluir os cortes selecionados."));
  }
  return response.json() as Promise<{ deleted: number; skipped: number; clip_ids: number[] }>;
}

export default function ClipDeleteManager() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
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

        let node = card.querySelector<HTMLElement>("[data-clip-delete-manager-host]");
        if (!node) {
          node = document.createElement("div");
          node.dataset.clipDeleteManagerHost = "true";
          const header = card.firstElementChild;
          if (header?.nextSibling) card.insertBefore(node, header.nextSibling);
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
    try {
      const data = await listClips();
      setClips(data);
      const allowed = new Set(data.filter(isDeletable).map((clip) => clip.id));
      setSelected((current) => new Set([...current].filter((id) => allowed.has(id))));
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Não foi possível atualizar os cortes.");
    }
  }

  useEffect(() => {
    if (!host) return;
    void refresh({ silent: false });
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [host]);

  const deletable = useMemo(() => clips.filter(isDeletable), [clips]);
  const selectedClips = useMemo(() => deletable.filter((clip) => selected.has(clip.id)), [deletable, selected]);
  const allSelected = deletable.length > 0 && selectedClips.length === deletable.length;

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(deletable.map((clip) => clip.id)));
  }

  function toggleOne(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function removeOne(clip: Clip) {
    const confirmed = window.confirm(`Excluir definitivamente o corte “${clip.title}”?\n\nEsta ação remove somente o corte não publicado do ShortsFlow. Ela não publica nada.`);
    if (!confirmed) return;

    setBusy(`one-${clip.id}`); setError(""); setNotice("");
    try {
      await deleteClip(clip.id);
      setSelected((current) => {
        const next = new Set(current);
        next.delete(clip.id);
        return next;
      });
      await refresh({ silent: false });
      setNotice("Corte excluído. A grade de Publicações será atualizada automaticamente em poucos segundos.");
      window.dispatchEvent(new CustomEvent("shortsflow:clips-changed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir o corte.");
    } finally {
      setBusy("");
    }
  }

  async function removeSelected() {
    const ids = selectedClips.map((clip) => clip.id);
    if (!ids.length) return;
    const confirmed = window.confirm(`Excluir definitivamente ${ids.length} corte(s) selecionado(s)?\n\nSomente cortes não publicados e fora das filas serão removidos. Nenhum conteúdo será publicado.`);
    if (!confirmed) return;

    setBusy("batch"); setError(""); setNotice("");
    try {
      const result = await deleteClipsBatch(ids);
      setSelected(new Set());
      await refresh({ silent: false });
      const skipped = result.skipped ? ` ${result.skipped} corte(s) foram protegidos por estarem em fila, processamento ou possuir histórico de publicação.` : "";
      setNotice(`${result.deleted} corte(s) excluído(s).${skipped} A grade de Publicações será atualizada automaticamente em poucos segundos.`);
      window.dispatchEvent(new CustomEvent("shortsflow:clips-changed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir os cortes selecionados.");
    } finally {
      setBusy("");
    }
  }

  if (!host) return null;

  return createPortal(
    <div className="border-b border-[#e8e8e8] bg-white px-4 py-3 md:px-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[.08em] text-[#ff0000]">Gerenciar cortes</div>
          <div className="mt-1 text-sm font-semibold text-[#111]">Excluir cortes que você não deseja publicar</div>
          <p className="mt-1 text-[11px] leading-5 text-[#667085]">A exclusão é limitada a cortes ainda não publicados e fora de filas ativas. Processamentos, arquivos de origem e outros cortes permanecem intactos.</p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="sf-button sf-button-outline"
        >
          {open ? "Fechar gerenciador" : `Excluir cortes (${deletable.length})`}
        </button>
      </div>

      {open && (
        <div className="mt-4 rounded-xl border border-[#e7e7e7] bg-[#fafafa] p-3 md:p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <button type="button" onClick={toggleAll} disabled={!deletable.length || Boolean(busy)} className="sf-button sf-button-outline disabled:opacity-40">
              {allSelected ? "Desmarcar todos" : `Selecionar todos (${deletable.length})`}
            </button>
            <button
              type="button"
              onClick={() => void removeSelected()}
              disabled={!selectedClips.length || Boolean(busy)}
              className="rounded-lg bg-red-600 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy === "batch" ? "Excluindo..." : `Excluir selecionados (${selectedClips.length})`}
            </button>
          </div>

          {error && <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs font-medium text-red-700">{error}</div>}
          {notice && <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-xs font-medium text-emerald-800">{notice}</div>}

          <div className="mt-3 max-h-[320px] divide-y divide-[#e8e8e8] overflow-y-auto rounded-lg border border-[#e8e8e8] bg-white">
            {deletable.length === 0 ? (
              <div className="p-6 text-center text-xs text-[#777]">Não há cortes não publicados disponíveis para exclusão.</div>
            ) : deletable.map((clip) => (
              <div key={clip.id} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
                <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(clip.id)}
                    onChange={() => toggleOne(clip.id)}
                    disabled={Boolean(busy)}
                    className="mt-1 h-4 w-4 accent-[#ff0000]"
                  />
                  <span className="min-w-0">
                    <span className="block line-clamp-2 text-xs font-semibold leading-5 text-[#222]">{clip.title}</span>
                    <span className="mt-0.5 block text-[10px] text-[#777]">Corte #{clip.id} · {statusLabel(clip.status)} · {(clip.end_seconds - clip.start_seconds).toFixed(1)}s</span>
                  </span>
                </label>
                <button
                  type="button"
                  onClick={() => void removeOne(clip)}
                  disabled={Boolean(busy)}
                  className="w-fit rounded-lg border border-red-200 bg-white px-3 py-2 text-[11px] font-semibold text-red-700 transition hover:bg-red-50 disabled:opacity-40"
                >
                  {busy === `one-${clip.id}` ? "Excluindo..." : "Excluir"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>,
    host,
  );
}
