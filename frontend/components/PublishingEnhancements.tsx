"use client";

import { createPortal } from "react-dom";
import { useEffect, useMemo, useState } from "react";

import {
  listClips,
  tiktokCreatorInfo,
  tiktokStatus,
  tiktokUploadBatch,
  updateClipCaptions,
  uploadClipsBatch,
  type TikTokCreatorInfo,
  type TikTokStatus,
} from "@/lib/api";
import type { Clip } from "@/lib/types";

function privacyLabel(value: string) {
  const labels: Record<string, string> = {
    PUBLIC_TO_EVERYONE: "Todos (público)",
    MUTUAL_FOLLOW_FRIENDS: "Amigos mútuos",
    FOLLOWER_OF_CREATOR: "Seguidores",
    SELF_ONLY: "Somente eu",
  };
  return labels[value] || value;
}

export default function PublishingEnhancements() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [ttStatus, setTtStatus] = useState<TikTokStatus | null>(null);
  const [creator, setCreator] = useState<TikTokCreatorInfo | null>(null);
  const [privacy, setPrivacy] = useState("");
  const [allowComment, setAllowComment] = useState(false);
  const [allowDuet, setAllowDuet] = useState(false);
  const [allowStitch, setAllowStitch] = useState(false);
  const [musicConfirmed, setMusicConfirmed] = useState(false);

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
        let node = card.querySelector<HTMLElement>("[data-publishing-enhancements-host]");
        if (!node) {
          node = document.createElement("div");
          node.dataset.publishingEnhancementsHost = "true";
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
    const timer = window.setInterval(sync, 1000);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      window.removeEventListener("hashchange", sync);
      window.clearInterval(timer);
      currentHost?.remove();
    };
  }, []);

  async function refreshClips() {
    try {
      const data = await listClips();
      setClips(data);
      const visible = new Set(data.map((clip) => clip.id));
      setSelected((current) => new Set([...current].filter((id) => visible.has(id))));
    } catch {
      // Dashboard already owns the global error state. Keep this panel quiet on
      // transient polling failures and let the next refresh recover.
    }
  }

  async function refreshTikTok() {
    try {
      const status = await tiktokStatus();
      setTtStatus(status);
      if (!status.connected) {
        setCreator(null);
        setPrivacy("");
      }
      return status;
    } catch {
      setTtStatus(null);
      return null;
    }
  }

  useEffect(() => {
    if (!host) return;
    void refreshClips();
    void refreshTikTok();
    const timer = window.setInterval(() => void refreshClips(), 3000);
    return () => window.clearInterval(timer);
  }, [host]);

  const selectedClips = useMemo(() => clips.filter((clip) => selected.has(clip.id)), [clips, selected]);
  const allSelected = clips.length > 0 && selected.size === clips.length;

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(clips.map((clip) => clip.id)));
  }

  function toggleOne(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function removeGeneratedCaptions() {
    if (!selectedClips.length) return setError("Selecione pelo menos um corte.");
    setBusy("captions"); setError(""); setNotice("");
    try {
      let changed = 0;
      for (const clip of selectedClips) {
        if (!(clip.subtitle_srt || "").trim()) continue;
        await updateClipCaptions(clip.id, {
          caption_position: clip.caption_position || "bottom",
          caption_margin_v: clip.caption_margin_v || 120,
          caption_font_size: clip.caption_font_size || 18,
          subtitle_srt: "",
        });
        changed += 1;
      }
      await refreshClips();
      setNotice(changed ? `Legenda gerada removida de ${changed} corte(s).` : "Os cortes selecionados já estão sem legenda gerada pelo ShortsFlow.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível remover as legendas.");
    } finally {
      setBusy("");
    }
  }

  async function publishYouTube() {
    if (!selected.size) return setError("Selecione pelo menos um corte.");
    setBusy("youtube"); setError(""); setNotice("");
    try {
      const result = await uploadClipsBatch([...selected]);
      const queued = new Set(result.clip_ids);
      setClips((current) => current.filter((clip) => !queued.has(clip.id)));
      setSelected(new Set());
      setNotice(`${result.queued} corte(s) colocado(s) na fila pública do YouTube. O envio ocorre um por vez.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar a fila do YouTube.");
    } finally {
      setBusy("");
    }
  }

  function connectTikTok() {
    setBusy("tiktok-connect"); setError(""); setNotice("");
    // Use the same-origin redirect route for both the first connection and
    // account switching. The current token is only replaced after a successful
    // TikTok callback, so cancelling the picker does not delete the old account.
    window.location.assign("/api/tiktok/oauth/authorize");
  }

  async function loadCreatorOptions() {
    setBusy("tiktok-options"); setError(""); setNotice("");
    try {
      const info = await tiktokCreatorInfo();
      setCreator(info);
      setPrivacy("");
      setAllowComment(false);
      setAllowDuet(false);
      setAllowStitch(false);
      return info;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar as opções do TikTok.");
      return null;
    } finally {
      setBusy("");
    }
  }

  async function publishTikTok() {
    if (!selected.size) return setError("Selecione pelo menos um corte.");
    if (!privacy) return setError("Selecione manualmente a privacidade do TikTok.");
    if (!musicConfirmed) return setError("Confirme a declaração de uso de música exigida pelo TikTok.");
    setBusy("tiktok"); setError(""); setNotice("");
    try {
      const latest = await tiktokCreatorInfo();
      setCreator(latest);
      if (!latest.privacy_level_options.includes(privacy)) {
        setPrivacy("");
        throw new Error("As opções de privacidade do TikTok mudaram. Selecione novamente.");
      }
      const result = await tiktokUploadBatch([...selected], {
        privacy_level: privacy,
        allow_comment: allowComment,
        allow_duet: allowDuet,
        allow_stitch: allowStitch,
        music_usage_confirmed: musicConfirmed,
      });
      setNotice(`${result.queued} corte(s) colocado(s) na fila do TikTok.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar a fila do TikTok.");
    } finally {
      setBusy("");
    }
  }

  if (!host) return null;

  return createPortal(
    <div className="border-b border-[#e8e8e8] bg-[#fbfbfb] p-4 md:p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[.08em] text-[#ff0000]">Publicação em lote</div>
          <h3 className="mt-1 text-base font-semibold text-[#111]">Selecione os cortes e publique sem repetir o processo</h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[#667085]">
            YouTube é sempre público. A fila envia um vídeo por vez e pausa automaticamente se o próprio YouTube informar que o limite diário do canal foi atingido.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={toggleAll} disabled={!clips.length || Boolean(busy)} className="sf-button sf-button-outline disabled:opacity-40">
            {allSelected ? "Desmarcar todos" : `Selecionar todos (${clips.length})`}
          </button>
          <button type="button" onClick={removeGeneratedCaptions} disabled={!selected.size || Boolean(busy)} className="sf-button sf-button-outline disabled:opacity-40">
            {busy === "captions" ? "Removendo legenda..." : "Remover legenda gerada"}
          </button>
          <button type="button" onClick={publishYouTube} disabled={!selected.size || Boolean(busy)} className="sf-button sf-button-youtube disabled:opacity-40">
            {busy === "youtube" ? "Criando fila..." : `Publicar ${selected.size || ""} no YouTube`}
          </button>
        </div>
      </div>

      {clips.length > 0 && (
        <div className="mt-4 max-h-44 overflow-y-auto rounded-xl border border-[#e7e7e7] bg-white">
          {clips.map((clip) => (
            <label key={clip.id} className="flex cursor-pointer items-center gap-3 border-b border-[#eeeeee] px-3 py-2.5 last:border-b-0">
              <input type="checkbox" checked={selected.has(clip.id)} onChange={() => toggleOne(clip.id)} className="h-4 w-4 accent-[#ff0000]" />
              <span className="min-w-0 flex-1 truncate text-xs font-medium text-[#222]">{clip.title}</span>
              <span className="text-[10px] text-[#777]">{Math.round(clip.end_seconds - clip.start_seconds)}s</span>
            </label>
          ))}
        </div>
      )}

      <div className="mt-4 grid gap-3 rounded-xl border border-[#e7e7e7] bg-white p-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <div>
          <div className="text-xs font-semibold text-[#111]">TikTok</div>
          <div className="mt-1 text-[11px] leading-5 text-[#667085]">
            {ttStatus?.connected
              ? `Conectado${ttStatus.display_name ? ` · ${ttStatus.display_name}` : ""}`
              : ttStatus?.configured
                ? "Pronto para conectar uma conta."
                : "Integração preparada; falta cadastrar o app aprovado do TikTok no servidor."}
          </div>
          {!ttStatus?.connected && (
            <button type="button" onClick={connectTikTok} disabled={!ttStatus?.configured || Boolean(busy)} className="sf-button sf-button-outline mt-3 disabled:opacity-40">
              {busy === "tiktok-connect" ? "Abrindo TikTok..." : "Conectar TikTok"}
            </button>
          )}
          {ttStatus?.connected && (
            <button type="button" onClick={connectTikTok} disabled={Boolean(busy)} className="sf-button sf-button-outline mt-3 disabled:opacity-40">
              {busy === "tiktok-connect" ? "Abrindo TikTok..." : "Trocar conta TikTok"}
            </button>
          )}
          {ttStatus?.connected && !creator && (
            <button type="button" onClick={loadCreatorOptions} disabled={Boolean(busy)} className="sf-button sf-button-outline mt-3 disabled:opacity-40">
              {busy === "tiktok-options" ? "Carregando..." : "Carregar opções de postagem"}
            </button>
          )}
        </div>

        {ttStatus?.connected && creator && (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(180px,1fr)_auto_auto] xl:items-end">
            <label className="text-[11px] font-medium text-[#555]">
              Privacidade do TikTok
              <select value={privacy} onChange={(event) => setPrivacy(event.target.value)} className="sf-input mt-1 w-full px-3 py-2.5">
                <option value="">Selecione manualmente</option>
                {creator.privacy_level_options.map((value) => <option key={value} value={value}>{privacyLabel(value)}</option>)}
              </select>
            </label>
            <div className="flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-[#555]">
              <label className={creator.comment_disabled ? "opacity-40" : ""}><input type="checkbox" checked={allowComment} disabled={creator.comment_disabled} onChange={(e) => setAllowComment(e.target.checked)} className="mr-1 accent-[#111]" />Comentários</label>
              <label className={creator.duet_disabled ? "opacity-40" : ""}><input type="checkbox" checked={allowDuet} disabled={creator.duet_disabled} onChange={(e) => setAllowDuet(e.target.checked)} className="mr-1 accent-[#111]" />Dueto</label>
              <label className={creator.stitch_disabled ? "opacity-40" : ""}><input type="checkbox" checked={allowStitch} disabled={creator.stitch_disabled} onChange={(e) => setAllowStitch(e.target.checked)} className="mr-1 accent-[#111]" />Stitch</label>
            </div>
            <div>
              <label className="flex max-w-md items-start gap-2 text-[10px] leading-4 text-[#667085]">
                <input type="checkbox" checked={musicConfirmed} onChange={(e) => setMusicConfirmed(e.target.checked)} className="mt-0.5 accent-[#111]" />
                <span>Ao publicar, concordo com a confirmação de uso de música exigida pelo TikTok.</span>
              </label>
              <button type="button" onClick={publishTikTok} disabled={!selected.size || !privacy || !musicConfirmed || Boolean(busy)} className="sf-button sf-button-primary mt-2 disabled:opacity-40">
                {busy === "tiktok" ? "Criando fila..." : `Publicar ${selected.size || ""} no TikTok`}
              </button>
            </div>
          </div>
        )}
      </div>

      <p className="mt-3 text-[10px] leading-4 text-[#667085]">
        Para ajustes individuais, use “Editar vídeo” em cada corte. “Remover legenda gerada” remove a legenda adicionada pelo ShortsFlow; texto já gravado dentro do vídeo original precisa ser tratado no editor por recorte/requadramento.
      </p>
      {error && <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</div>}
      {notice && <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800">{notice}</div>}
    </div>,
    host,
  );
}