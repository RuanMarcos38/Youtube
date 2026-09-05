"use client";

import { createPortal } from "react-dom";
import { useEffect, useMemo, useState } from "react";

import {
  createEditorProjectFromClip,
  tiktokCreatorInfo,
  tiktokStatus,
  tiktokUploadBatch,
  updateClipCaptions,
  uploadClipsBatch,
  type TikTokCreatorInfo,
  type TikTokStatus,
} from "@/lib/api";
import {
  tiktokMetrics,
  tiktokPublicationClips,
  youtubePublicationClips,
  type TikTokDashboardAlert,
  type TikTokMetrics,
  type TikTokPublicationClip,
  type YouTubeAvailability,
} from "@/lib/publications-api";
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

function fmtNumber(value?: number | null) {
  return new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
}

function fmtExact(value?: number | null) {
  return new Intl.NumberFormat("pt-BR").format(Math.round(value || 0));
}

function fmtPercent(value?: number | null) {
  return `${Number(value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`;
}

function fmtSigned(value?: number | null) {
  const safe = Number(value || 0);
  return `${safe > 0 ? "+" : ""}${new Intl.NumberFormat("pt-BR").format(safe)}`;
}

function fmtDateTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

function fmtCountdown(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function tiktokStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    ready: "Pronto para TikTok",
    queued: "Na fila do TikTok",
    uploading: "Enviando ao TikTok",
    processing: "TikTok processando",
    submitted: "TikTok processando",
    failed: "Falhou no TikTok",
    paused_limit: "TikTok pausado",
  };
  return labels[status || "ready"] || status || "Pronto";
}

function youtubeStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    ready: "Pronto para YouTube",
    approved: "Aprovado",
    upload_queued: "Na fila do YouTube",
    uploading: "Enviando ao YouTube",
    upload_failed: "Falhou no YouTube",
  };
  return labels[status || "ready"] || status || "Pronto";
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-[#ececec] bg-[#fafafa] p-3">
      <div className="text-[10px] font-semibold uppercase tracking-[.06em] text-[#777]">{label}</div>
      <div className="mt-1 text-xl font-black text-[#111]">{value}</div>
      {detail && <div className="mt-1 text-[10px] leading-4 text-[#777]">{detail}</div>}
    </div>
  );
}

function Alert({ alert }: { alert: TikTokDashboardAlert }) {
  const cls = alert.kind === "success"
    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
    : alert.kind === "danger"
      ? "border-red-200 bg-red-50 text-red-800"
      : alert.kind === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : "border-blue-100 bg-blue-50 text-blue-900";
  return (
    <div className={`rounded-xl border p-3 ${cls}`}>
      <div className="text-xs font-black">{alert.title}</div>
      <div className="mt-1 text-[10px] leading-4 opacity-80">{alert.detail}</div>
    </div>
  );
}

export default function PublishingEnhancements() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [tab, setTab] = useState<"youtube" | "tiktok">("youtube");
  const [youtubeClips, setYoutubeClips] = useState<Clip[]>([]);
  const [tiktokClips, setTiktokClips] = useState<TikTokPublicationClip[]>([]);
  const [youtubeSelected, setYoutubeSelected] = useState<Set<number>>(new Set());
  const [tiktokSelected, setTiktokSelected] = useState<Set<number>>(new Set());
  const [availability, setAvailability] = useState<YouTubeAvailability>({ blocked: false, seconds_remaining: 0, message: "" });
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [ttStatus, setTtStatus] = useState<TikTokStatus | null>(null);
  const [creator, setCreator] = useState<TikTokCreatorInfo | null>(null);
  const [creatorError, setCreatorError] = useState("");
  const [privacy, setPrivacy] = useState("");
  const [allowComment, setAllowComment] = useState(false);
  const [allowDuet, setAllowDuet] = useState(false);
  const [allowStitch, setAllowStitch] = useState(false);
  const [musicConfirmed, setMusicConfirmed] = useState(false);
  const [metricDays, setMetricDays] = useState(30);
  const [metricData, setMetricData] = useState<TikTokMetrics | null>(null);

  useEffect(() => {
    let currentHost: HTMLElement | null = null;
    let raf = 0;
    const sync = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const card = document.querySelector<HTMLElement>("#cortes > .sf-card");
        if (!card) return setHost(null);
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

  async function refreshQueues() {
    try {
      const [youtube, tiktok] = await Promise.all([youtubePublicationClips(), tiktokPublicationClips()]);
      setYoutubeClips(youtube.clips);
      setTiktokClips(tiktok.clips);
      setAvailability(youtube.availability);
      setRemaining(youtube.availability.seconds_remaining || 0);
      const yVisible = new Set(youtube.clips.map((clip) => clip.id));
      const tVisible = new Set(tiktok.clips.map((clip) => clip.id));
      setYoutubeSelected((current) => new Set([...current].filter((id) => yVisible.has(id))));
      setTiktokSelected((current) => new Set([...current].filter((id) => tVisible.has(id))));
    } catch {
      // Keep the last good queue visible during a transient refresh failure.
    }
  }

  async function refreshTikTok() {
    try {
      const status = await tiktokStatus();
      setTtStatus(status);
      if (status.connected) {
        try {
          const info = await tiktokCreatorInfo();
          setCreator(info);
          setCreatorError("");
          setPrivacy((current) => {
            if (info.privacy_level_options.includes(current)) return current;
            if (info.public_posting_blocked && info.privacy_level_options.includes("SELF_ONLY")) return "SELF_ONLY";
            return "";
          });
        } catch (err) {
          // Preserve the last valid creator info during a transient TikTok/API
          // failure. This avoids making the controls disappear after one 5xx.
          setCreatorError(err instanceof Error ? err.message : "Não foi possível atualizar as opções do TikTok.");
        }
      } else {
        setCreator(null);
        setCreatorError("");
        setPrivacy("");
      }
    } catch (err) {
      setCreatorError(err instanceof Error ? err.message : "Não foi possível verificar a conexão do TikTok.");
    }
  }

  async function refreshMetrics(days = metricDays) {
    if (!ttStatus?.connected) return;
    try {
      setMetricData(await tiktokMetrics(days));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível atualizar as métricas do TikTok.");
    }
  }

  useEffect(() => {
    if (!host) return;
    void refreshQueues();
    void refreshTikTok();
    const queueTimer = window.setInterval(() => void refreshQueues(), 5000);
    return () => window.clearInterval(queueTimer);
  }, [host]);

  useEffect(() => {
    if (!ttStatus?.connected) return;
    void refreshMetrics(metricDays);
    const timer = window.setInterval(() => void refreshMetrics(metricDays), 60000);
    return () => window.clearInterval(timer);
  }, [ttStatus?.connected, metricDays]);

  useEffect(() => {
    if (!availability.blocked) return;
    setRemaining(availability.seconds_remaining || 0);
    const timer = window.setInterval(() => setRemaining((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [availability.blocked, availability.blocked_until, availability.seconds_remaining]);

  const clips = tab === "youtube" ? youtubeClips : tiktokClips;
  const selected = tab === "youtube" ? youtubeSelected : tiktokSelected;
  const setSelected = tab === "youtube" ? setYoutubeSelected : setTiktokSelected;
  const selectedClips = useMemo(() => clips.filter((clip) => selected.has(clip.id)), [clips, selected]);
  const allSelected = clips.length > 0 && selected.size === clips.length;

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(clips.map((clip) => clip.id)));
  }

  function toggleOne(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
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
      await refreshQueues();
      setNotice(changed ? `Legenda gerada removida de ${changed} corte(s).` : "Os cortes selecionados já estão sem legenda gerada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível remover as legendas.");
    } finally { setBusy(""); }
  }

  async function editClip(clip: Clip) {
    setBusy(`edit-${clip.id}`); setError("");
    try {
      const project = await createEditorProjectFromClip(clip.id);
      const params = new URLSearchParams({ project: project.id, clip: String(clip.id), return: "/#cortes" });
      window.location.assign(`/editor-ia?${params.toString()}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível abrir o editor.");
      setBusy("");
    }
  }

  async function publishYouTube() {
    if (!youtubeSelected.size) return setError("Selecione pelo menos um corte para o YouTube.");
    if (availability.blocked && remaining > 0) return setError(`YouTube bloqueado temporariamente. Nova tentativa estimada em ${fmtCountdown(remaining)}.`);
    setBusy("youtube"); setError(""); setNotice("");
    try {
      const result = await uploadClipsBatch([...youtubeSelected]);
      setNotice(`${result.queued} corte(s) colocado(s) na fila do YouTube. Eles somem desta aba somente após a publicação ser confirmada.`);
      await refreshQueues();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar a fila do YouTube.");
    } finally { setBusy(""); }
  }

  function connectTikTok(metrics = false) {
    setBusy(metrics ? "tiktok-metrics-auth" : "tiktok-connect"); setError(""); setNotice("");
    window.location.assign(metrics ? "/api/tiktok/oauth/authorize?metrics=true" : "/api/tiktok/oauth/authorize");
  }

  async function publishTikTok() {
    if (!tiktokSelected.size) return setError("Selecione pelo menos um corte para o TikTok.");
    if (!privacy) return setError("Selecione manualmente a privacidade do TikTok.");
    if (privacy === "PUBLIC_TO_EVERYONE" && creator?.public_posting_blocked) return setError(creator.public_posting_block_reason || "Publicação pública ainda aguarda liberação do TikTok.");
    if (!musicConfirmed) return setError("Confirme a declaração de uso de música exigida pelo TikTok.");
    setBusy("tiktok"); setError(""); setNotice("");
    try {
      // The backend validates Creator Info immediately before queueing. Do not
      // make a duplicate TikTok Creator Info request from the browser.
      const result = await tiktokUploadBatch([...tiktokSelected], {
        privacy_level: privacy,
        allow_comment: allowComment,
        allow_duet: allowDuet,
        allow_stitch: allowStitch,
        music_usage_confirmed: musicConfirmed,
      });
      setNotice(`${result.queued} corte(s) enviados para a fila. O ShortsFlow aguarda PUBLISH_COMPLETE do TikTok antes de considerar publicado e remover da aba.`);
      await refreshQueues();
      void refreshMetrics(metricDays);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar a fila do TikTok.");
      void refreshTikTok();
    } finally { setBusy(""); }
  }

  if (!host) return null;

  return createPortal(
    <div className="bg-[#fbfbfb] p-4 md:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e8e8e8] pb-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[.08em] text-[#ff0000]">Publicações separadas</div>
          <h3 className="mt-1 text-base font-semibold text-[#111]">Cada plataforma tem sua própria fila</h3>
          <p className="mt-1 text-xs text-[#667085]">O mesmo Short aparece nas duas abas sem duplicar o arquivo no servidor. Ao publicar em uma rede, ele continua disponível na outra.</p>
        </div>
        <div className="inline-flex rounded-xl border border-[#e5e5e5] bg-white p-1">
          <button type="button" onClick={() => setTab("youtube")} className={`rounded-lg px-4 py-2 text-xs font-black ${tab === "youtube" ? "bg-[#ff0000] text-white" : "text-[#555]"}`}>YouTube · {youtubeClips.length}</button>
          <button type="button" onClick={() => setTab("tiktok")} className={`rounded-lg px-4 py-2 text-xs font-black ${tab === "tiktok" ? "bg-[#111] text-white" : "text-[#555]"}`}>TikTok · {tiktokClips.length}</button>
        </div>
      </div>

      {tab === "youtube" && availability.blocked && remaining > 0 && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="font-black">Uploads do YouTube temporariamente bloqueados</div>
          <div className="mt-1 text-xs leading-5">{availability.message}</div>
          <div className="mt-2 text-lg font-black">Nova tentativa estimada em {fmtCountdown(remaining)}</div>
          <div className="mt-1 text-[10px]">O ShortsFlow não fará novas tentativas durante esta janela. O prazo é estimado; a liberação final depende do próprio YouTube.</div>
        </div>
      )}

      {tab === "tiktok" && (
        <div className="mt-4 rounded-xl border border-[#e7e7e7] bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xs font-black text-[#111]">TikTok {ttStatus?.connected ? `· ${ttStatus.display_name || "conectado"}` : ""}</div>
              <div className="mt-1 text-[11px] text-[#667085]">A publicação só é concluída quando o TikTok confirma o status final. “Arquivo enviado” não é tratado como “post publicado”.</div>
            </div>
            <button type="button" onClick={() => connectTikTok(false)} disabled={!ttStatus?.configured || Boolean(busy)} className="sf-button sf-button-outline disabled:opacity-40">
              {ttStatus?.connected ? "Trocar conta TikTok" : "Conectar TikTok"}
            </button>
          </div>

          {ttStatus?.connected && creator && (
            <>
              {creator.public_posting_blocked && (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-semibold leading-5 text-amber-900">
                  {creator.public_posting_block_reason || "Publicação pública ainda aguarda auditoria do TikTok. O envio automático disponível agora é Somente eu."}
                </div>
              )}
              <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(180px,1fr)_auto_auto] lg:items-end">
                <label className="text-[11px] font-medium text-[#555]">Privacidade do TikTok
                  <select value={privacy} onChange={(e) => setPrivacy(e.target.value)} className="sf-input mt-1 w-full px-3 py-2.5">
                    <option value="">Selecione manualmente</option>
                    {creator.privacy_level_options.map((value) => <option key={value} value={value}>{privacyLabel(value)}</option>)}
                  </select>
                </label>
                <div className="flex flex-wrap gap-3 text-[11px] text-[#555]">
                  <label className={creator.comment_disabled ? "opacity-40" : ""}><input type="checkbox" checked={allowComment} disabled={creator.comment_disabled} onChange={(e) => setAllowComment(e.target.checked)} className="mr-1" />Comentários</label>
                  <label className={creator.duet_disabled ? "opacity-40" : ""}><input type="checkbox" checked={allowDuet} disabled={creator.duet_disabled} onChange={(e) => setAllowDuet(e.target.checked)} className="mr-1" />Dueto</label>
                  <label className={creator.stitch_disabled ? "opacity-40" : ""}><input type="checkbox" checked={allowStitch} disabled={creator.stitch_disabled} onChange={(e) => setAllowStitch(e.target.checked)} className="mr-1" />Stitch</label>
                </div>
                <label className="flex max-w-md items-start gap-2 text-[10px] leading-4 text-[#667085]"><input type="checkbox" checked={musicConfirmed} onChange={(e) => setMusicConfirmed(e.target.checked)} className="mt-0.5" /><span>Confirmo o uso de música conforme exigido pelo TikTok.</span></label>
              </div>
            </>
          )}

          {ttStatus?.connected && !creator && (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              <div className="font-black">Opções de publicação ainda não carregadas</div>
              <div className="mt-1 leading-5">{creatorError || "O TikTok ainda não retornou as opções de privacidade desta conta."}</div>
              <button type="button" onClick={() => void refreshTikTok()} disabled={Boolean(busy)} className="sf-button sf-button-outline mt-3">Recarregar opções TikTok</button>
            </div>
          )}
          {ttStatus?.connected && creator && creatorError && <div className="mt-3 text-[10px] text-amber-700">Última atualização do TikTok teve uma falha temporária; as últimas opções válidas foram preservadas. {creatorError}</div>}
        </div>
      )}

      {tab === "tiktok" && ttStatus?.connected && (
        <div className="mt-4 rounded-xl border border-[#e7e7e7] bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-black">Dashboard TikTok</div>
              <div className="mt-1 text-[10px] text-[#777]">Métricas oficiais disponíveis pela API, atualização automática a cada 60 segundos e histórico salvo pelo ShortsFlow.</div>
              {metricData?.refreshed_at && <div className="mt-1 text-[9px] text-[#999]">Atualizado em {fmtDateTime(metricData.refreshed_at)}</div>}
            </div>
            <div className="flex gap-1">
              {[7, 30, 90].map((days) => <button key={days} type="button" onClick={() => setMetricDays(days)} className={`rounded-lg px-3 py-1.5 text-[10px] font-black ${metricDays === days ? "bg-[#111] text-white" : "bg-[#f2f2f2]"}`}>{days} dias</button>)}
            </div>
          </div>

          {metricData && !metricData.available ? (
            <div className="mt-4">
              <div className="rounded-xl bg-[#f7f7f7] p-4 text-xs leading-5 text-[#555]">
                <div className="font-black text-[#111]">Métricas oficiais aguardando autorização</div>
                <div className="mt-1">{metricData.reason}</div>
                <button type="button" onClick={() => connectTikTok(true)} className="sf-button sf-button-primary mt-3">Ativar métricas TikTok</button>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                <Metric label="Fila local" value={String(metricData.local_publications.queued)} />
                <Metric label="Processando" value={String(metricData.local_publications.processing)} />
                <Metric label="Publicados confirmados" value={String(metricData.local_publications.published_confirmed)} />
                <Metric label="Falhas" value={String(metricData.local_publications.failed)} />
                <Metric label="Pausados" value={String(metricData.local_publications.paused_limit)} />
              </div>
              {!!metricData.alerts?.length && <div className="mt-3 grid gap-2 md:grid-cols-2">{metricData.alerts.map((alert, index) => <Alert key={`${alert.title}-${index}`} alert={alert} />)}</div>}
            </div>
          ) : metricData?.available ? (
            <>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
                <Metric label="Seguidores" value={fmtNumber(metricData.profile?.followers)} detail={`Δ ${fmtSigned(metricData.growth?.followers_delta)}`} />
                <Metric label="Visualizações" value={fmtNumber(metricData.period?.views)} detail={`${metricDays} dias`} />
                <Metric label="Vídeos" value={fmtExact(metricData.period?.videos)} detail={`Conta: ${fmtExact(metricData.profile?.video_count)}`} />
                <Metric label="Curtidas" value={fmtNumber(metricData.period?.likes)} detail={`Conta: ${fmtNumber(metricData.profile?.likes_total)}`} />
                <Metric label="Comentários" value={fmtNumber(metricData.period?.comments)} />
                <Metric label="Compartilhamentos" value={fmtNumber(metricData.period?.shares)} />
                <Metric label="Engajamento" value={fmtPercent(metricData.period?.engagement_rate)} detail={`${fmtNumber(metricData.period?.engagement_total)} interações`} />
                <Metric label="Média de views" value={fmtNumber(metricData.period?.avg_views_per_video)} detail="por vídeo no período" />
              </div>

              <div className="mt-4 grid gap-3 lg:grid-cols-[1.15fr_.85fr]">
                <div className="rounded-xl border border-[#ececec] bg-[#fafafa] p-4">
                  <div className="text-xs font-black">Operação de publicação</div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
                    <Metric label="Publicados" value={String(metricData.local_publications.published_confirmed)} />
                    <Metric label="Processando" value={String(metricData.local_publications.processing)} />
                    <Metric label="Fila" value={String(metricData.local_publications.queued)} />
                    <Metric label="Falhas" value={String(metricData.local_publications.failed)} />
                    <Metric label="Pausados" value={String(metricData.local_publications.paused_limit)} />
                  </div>
                </div>

                <div className="rounded-xl border border-[#ececec] bg-[#fafafa] p-4">
                  <div className="text-xs font-black">Monetização / Creator Rewards</div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <Metric label="Receita oficial" value={metricData.monetization?.official_revenue_available ? fmtNumber(metricData.monetization.official_revenue) : "Não disponível via API"} />
                    <Metric label="Vídeos ≥ 60s" value={String(metricData.monetization?.duration_eligible_videos || 0)} detail={`${metricData.monetization?.duration_ineligible_videos || 0} abaixo de 60s`} />
                  </div>
                  <div className="mt-3 text-[10px] leading-5 text-[#666]">{metricData.monetization?.note}</div>
                </div>
              </div>

              {!!metricData.alerts?.length && (
                <div className="mt-4">
                  <div className="mb-2 text-xs font-black">Alertas e oportunidades</div>
                  <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">{metricData.alerts.map((alert, index) => <Alert key={`${alert.title}-${index}`} alert={alert} />)}</div>
                </div>
              )}

              <div className="mt-4 grid gap-3 lg:grid-cols-[1.15fr_.85fr]">
                <div className="rounded-xl border border-[#ececec] bg-white p-4">
                  <div className="flex items-center justify-between gap-2"><div className="text-xs font-black">Melhores vídeos do período</div><div className="text-[9px] text-[#888]">por visualizações</div></div>
                  <div className="mt-3 space-y-2">
                    {(metricData.top_videos || []).slice(0, 5).map((video, index) => (
                      <div key={video.id || index} className="grid grid-cols-[1fr_auto] gap-3 rounded-lg border border-[#eee] bg-[#fafafa] p-3">
                        <div className="min-w-0">
                          <div className="truncate text-[11px] font-black">{index + 1}. {video.title || "Vídeo TikTok"}</div>
                          <div className="mt-1 text-[9px] text-[#777]">{video.duration}s · {fmtNumber(video.like_count)} curtidas · {fmtNumber(video.comment_count)} comentários · {fmtNumber(video.share_count)} compartilhamentos</div>
                        </div>
                        <div className="text-right"><div className="text-sm font-black">{fmtNumber(video.view_count)}</div><div className="text-[9px] text-[#888]">views</div></div>
                      </div>
                    ))}
                    {!metricData.top_videos?.length && <div className="text-[10px] text-[#777]">Nenhum vídeo retornado para o período.</div>}
                  </div>
                </div>

                <div className="rounded-xl border border-[#ececec] bg-white p-4">
                  <div className="text-xs font-black">Histórico e crescimento</div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <Metric label="Δ Seguidores" value={fmtSigned(metricData.growth?.followers_delta)} />
                    <Metric label="Δ Curtidas da conta" value={fmtSigned(metricData.growth?.likes_total_delta)} />
                    <Metric label="Δ Vídeos" value={fmtSigned(metricData.growth?.video_count_delta)} />
                    <Metric label="Snapshots" value={String(metricData.history.length)} detail="histórico horário preservado" />
                  </div>
                  <div className="mt-3 text-[10px] leading-5 text-[#777]">O histórico passa a ser armazenado por até 120 dias. Os deltas usam o primeiro snapshot disponível dentro do período selecionado.</div>
                </div>
              </div>
            </>
          ) : <div className="mt-3 text-xs text-[#777]">Carregando métricas...</div>}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={toggleAll} disabled={!clips.length || Boolean(busy)} className="sf-button sf-button-outline disabled:opacity-40">{allSelected ? "Desmarcar todos" : `Selecionar todos (${clips.length})`}</button>
          <button type="button" onClick={removeGeneratedCaptions} disabled={!selected.size || Boolean(busy)} className="sf-button sf-button-outline disabled:opacity-40">{busy === "captions" ? "Removendo..." : "Remover legenda gerada"}</button>
        </div>
        {tab === "youtube" ? (
          <button type="button" onClick={publishYouTube} disabled={!youtubeSelected.size || Boolean(busy) || (availability.blocked && remaining > 0)} className="sf-button sf-button-youtube disabled:opacity-40">{busy === "youtube" ? "Criando fila..." : `Publicar ${youtubeSelected.size || ""} no YouTube`}</button>
        ) : (
          <button type="button" onClick={publishTikTok} disabled={!tiktokSelected.size || !privacy || !musicConfirmed || Boolean(busy) || !ttStatus?.connected || !creator} className="sf-button sf-button-primary disabled:opacity-40">{busy === "tiktok" ? "Criando fila..." : `Publicar ${tiktokSelected.size || ""} no TikTok`}</button>
        )}
      </div>

      {notice && <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{notice}</div>}
      {error && <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div>}

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {clips.map((clip) => {
          const tt = clip as TikTokPublicationClip;
          const statusText = tab === "youtube" ? youtubeStatusLabel(clip.status) : tiktokStatusLabel(tt.tiktok_status);
          const clipError = tab === "youtube" ? clip.upload_error : tt.tiktok_error;
          return (
            <article key={`${tab}-${clip.id}`} className="rounded-xl border border-[#e7e7e7] bg-white p-3 shadow-sm">
              <div className="flex items-start gap-3">
                <input type="checkbox" checked={selected.has(clip.id)} onChange={() => toggleOne(clip.id)} className="mt-1 h-4 w-4 accent-[#ff0000]" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2"><span className="rounded-md bg-[#f5f5f5] px-2 py-1 text-[9px] font-black">{statusText}</span><span className="text-[10px] text-[#777]">{Math.round(clip.end_seconds - clip.start_seconds)}s</span></div>
                  <h4 className="mt-2 line-clamp-2 text-sm font-black text-[#111]">{clip.title}</h4>
                </div>
              </div>
              <video src={clip.media_url} controls preload="metadata" className="mt-3 aspect-[9/16] max-h-[420px] w-full rounded-xl bg-black object-contain" />
              {clipError && <div className="mt-3 rounded-lg border border-red-100 bg-red-50 p-2 text-[10px] leading-4 text-red-700">{clipError}</div>}
              <button type="button" onClick={() => void editClip(clip)} disabled={Boolean(busy)} className="sf-button sf-button-outline mt-3 w-full disabled:opacity-40">{busy === `edit-${clip.id}` ? "Abrindo editor..." : "Editar vídeo"}</button>
            </article>
          );
        })}
      </div>
      {!clips.length && <div className="mt-6 rounded-xl border border-dashed border-[#ddd] bg-white p-8 text-center text-sm text-[#777]">Não há Shorts pendentes nesta plataforma.</div>}
    </div>,
    host,
  );
}
