"use client";

import { useEffect, useMemo, useState } from "react";
import {
  API_URL,
  approveClip,
  createJob,
  getTrending,
  listClips,
  listJobs,
  retryJob,
  uploadClip,
  youtubeLiveMetrics,
  youtubeStart,
  youtubeStatus,
} from "@/lib/api";
import type { Clip, Job, TrendingVideo, UserProfile, YouTubeDashboardAlert, YouTubeLiveMetrics } from "@/lib/types";
import {
  ArrowIcon,
  CheckIcon,
  CopyIcon,
  PlayIcon,
  RefreshIcon,
  SearchIcon,
  TagsIcon,
  UploadIcon,
  YoutubeIcon,
} from "./Icons";

type SectionId = "automacao" | "configurar" | "processamento" | "cortes";

const pipeline = [
  "Preparando",
  "Baixando video",
  "Extraindo audio",
  "Transcrevendo",
  "Selecionando cortes",
  "Renderizando 9:16",
  "Gerando legendas",
  "Pronto para revisar",
];

const sections: Array<{ id: SectionId; label: string; description: string }> = [
  { id: "automacao", label: "Painel ao vivo", description: "Metricas, alertas e destaque do canal" },
  { id: "configurar", label: "Criar Shorts", description: "Busca e configuracao de cortes" },
  { id: "processamento", label: "Processamentos", description: "Fila e andamento dos jobs" },
  { id: "cortes", label: "Publicacoes", description: "Revisao e envio ao YouTube" },
];

const stageIndex: Record<string, number> = {
  queued: 0,
  checking_ffmpeg: 0,
  downloading: 1,
  extracting_audio: 2,
  transcribing: 3,
  selecting_clips: 4,
  rendering: 5,
  ready_for_review: 7,
  failed: -1,
};

function fmtNumber(value: number) {
  return new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
}

function fmtExact(value: number) {
  return new Intl.NumberFormat("pt-BR").format(Math.round(value || 0));
}

function fmtDuration(seconds: number) {
  const min = Math.floor(seconds / 60);
  const sec = Math.round(seconds % 60);
  return `${min}:${String(sec).padStart(2, "0")}`;
}

function fmtDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function sectionFromHash(): SectionId {
  if (typeof window === "undefined") return "automacao";
  const hash = window.location.hash.replace("#", "");
  return sections.some((item) => item.id === hash) ? (hash as SectionId) : "automacao";
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: "Na fila",
    checking_ffmpeg: "Preparando",
    downloading: "Baixando video",
    extracting_audio: "Extraindo audio",
    transcribing: "Transcrevendo",
    selecting_clips: "Selecionando cortes",
    rendering: "Renderizando",
    ready_for_review: "Pronto para revisar",
    failed: "Falhou",
    ready: "Pronto",
    approved: "Aprovado",
    upload_queued: "Na fila de upload",
    uploading: "Enviando ao YouTube",
    uploaded: "Publicado",
    upload_failed: "Falha no upload",
  };
  return labels[status] || status;
}

function youtubeOauthErrorMessage(reason: string) {
  const normalized = reason.trim().toLowerCase();
  if (normalized === "access_denied") {
    return "Google bloqueou o acesso desta conta. O app OAuth ainda esta em modo de teste/nao verificado para esse e-mail; adicione o e-mail em Test users no Google Cloud Console ou publique/verifique o app.";
  }
  if (normalized === "oauth_nao_concluido") {
    return "Nao foi possivel concluir a conexao com o YouTube. Tente novamente escolhendo a conta Google que possui o canal.";
  }
  if (normalized === "oauth_callback_incompleto") {
    return "O Google retornou uma autorizacao incompleta. Inicie a conexao do YouTube novamente.";
  }
  return reason ? `Google nao autorizou a conexao do YouTube: ${reason}.` : "Google nao autorizou a conexao do YouTube.";
}

function jobErrorMessage(error: string) {
  const normalized = error.toLowerCase();
  if (
    normalized.includes("rate_limit_exceeded") ||
    normalized.includes("tokens per min") ||
    normalized.includes("request too large")
  ) {
    return "Este processamento foi criado antes da correcao para videos longos e excedeu o limite da OpenAI. Clique em Tentar novamente para recriar o job usando o transcript otimizado.";
  }
  if (normalized.includes("sign in to confirm") || normalized.includes("cookies") || normalized.includes("not a bot")) {
    return "O YouTube recusou a sessao de download usada neste processamento antigo. A autenticacao atual ja foi renovada; tente novamente para baixar com a configuracao corrigida.";
  }
  return error;
}

function StatusBadge({ status }: { status: string }) {
  const ready = ["ready_for_review", "ready", "approved", "uploaded"].includes(status);
  const failed = ["failed", "upload_failed"].includes(status);
  const cls = failed
    ? "border-red-200 bg-red-50 text-red-700"
    : ready
      ? "border-red-100 bg-red-50 text-red-700"
      : "border-[#e6e6e6] bg-[#f7f7f7] text-[#555]";
  return <span className={`inline-flex rounded-md border px-2 py-1 text-[10px] font-medium ${cls}`}>{statusLabel(status)}</span>;
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-[#e8e8e8] bg-white p-4 shadow-sm">
      <div className="text-[11px] font-semibold uppercase tracking-[.08em] text-[#777]">{label}</div>
      <div className="mt-2 text-2xl font-semibold tracking-[-.02em] text-[#111]">{value}</div>
      {detail && <div className="mt-1 text-xs text-[#666]">{detail}</div>}
    </div>
  );
}

function ProgressBar({ label, value, target, progress }: { label: string; value: string; target: string; progress: number }) {
  const width = Math.min(100, Math.max(0, progress || 0));
  return (
    <div>
      <div className="flex items-end justify-between gap-3 text-xs">
        <span className="font-semibold text-[#222]">{label}</span>
        <span className="text-[#666]">{value} / {target}</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#ececec]">
        <div className="h-full rounded-full bg-[#ff0000] transition-all duration-700" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function AlertCard({ alert }: { alert: YouTubeDashboardAlert }) {
  const cls = alert.kind === "success"
    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
    : alert.kind === "warning"
      ? "border-amber-200 bg-amber-50 text-amber-900"
      : "border-[#e8e8e8] bg-white text-[#222]";
  return (
    <div className={`rounded-xl border p-4 ${cls}`}>
      <div className="text-sm font-semibold">{alert.title}</div>
      <div className="mt-1 text-xs leading-5 opacity-80">{alert.detail}</div>
    </div>
  );
}

export default function Dashboard({ user }: { user: UserProfile }) {
  const [activeSection, setActiveSection] = useState<SectionId>("automacao");
  const [keyword, setKeyword] = useState("marketing digital");
  const [region, setRegion] = useState("BR");
  const [days, setDays] = useState(14);
  const [requestedClips, setRequestedClips] = useState(3);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [videos, setVideos] = useState<TrendingVideo[]>([]);
  const [selected, setSelected] = useState<TrendingVideo | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [clips, setClips] = useState<Clip[]>([]);
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const [youtubeChannelTitle, setYoutubeChannelTitle] = useState<string | null>(null);
  const [liveMetrics, setLiveMetrics] = useState<YouTubeLiveMetrics | null>(null);
  const [privacy, setPrivacy] = useState("private");
  const [loading, setLoading] = useState(false);
  const [liveLoading, setLiveLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [liveError, setLiveError] = useState("");
  const [message, setMessage] = useState("");

  const activeJobs = useMemo(() => jobs.filter((job) => !["ready_for_review", "failed"].includes(job.status)).length, [jobs]);
  const readyClips = useMemo(() => clips.filter((clip) => ["ready", "approved", "uploaded"].includes(clip.status)).length, [clips]);
  const usagePercent = user.unlimited ? 100 : Math.min(100, Math.round((user.jobs_used / Math.max(1, user.monthly_job_limit)) * 100));
  const topVideo = liveMetrics?.top_video;
  const monetization = liveMetrics?.monetization;

  useEffect(() => {
    const syncSection = () => setActiveSection(sectionFromHash());
    syncSection();
    window.addEventListener("hashchange", syncSection);
    return () => window.removeEventListener("hashchange", syncSection);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const youtube = params.get("youtube");
    if (!youtube) return;

    const reason = params.get("reason") || "";
    if (youtube === "connected") {
      setMessage("Canal do YouTube conectado com sucesso.");
    } else if (youtube === "error") {
      setError(youtubeOauthErrorMessage(reason));
    }

    params.delete("youtube");
    params.delete("reason");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  }, []);

  async function refreshLive({ silent = false }: { silent?: boolean } = {}) {
    if (!silent) setLiveLoading(true);
    setLiveError("");
    try {
      const metrics = await youtubeLiveMetrics();
      setLiveMetrics(metrics);
    } catch (err) {
      setLiveMetrics(null);
      if (!silent) setLiveError(err instanceof Error ? err.message : "Falha ao carregar metricas ao vivo do YouTube.");
    } finally {
      if (!silent) setLiveLoading(false);
    }
  }

  async function refresh({ silent = false }: { silent?: boolean } = {}) {
    try {
      const [jobData, clipData, yt] = await Promise.all([listJobs(), listClips(), youtubeStatus()]);
      setJobs(jobData);
      setClips(clipData);
      setYoutubeConnected(yt.connected);
      setYoutubeChannelTitle(yt.channel_title ?? null);
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Falha ao atualizar o dashboard");
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => void refresh({ silent: true }), 3000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!youtubeConnected) return;
    void refreshLive();
    const timer = window.setInterval(() => void refreshLive({ silent: true }), 60000);
    return () => window.clearInterval(timer);
  }, [youtubeConnected]);

  function openSection(id: SectionId) {
    setActiveSection(id);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${id}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function search() {
    setLoading(true); setError(""); setMessage("");
    try {
      const result = await getTrending(keyword, region, days);
      setVideos(result); setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao buscar videos");
    } finally { setLoading(false); }
  }

  async function processSelected() {
    if (!selected) return setError("Escolha um video para continuar.");
    if (!rightsConfirmed) return setError("Confirme que voce possui direitos ou autorizacao para reutilizar o conteudo.");
    setActionId(`video-${selected.video_id}`); setError(""); setMessage("");
    try {
      await createJob(selected, requestedClips);
      await refresh();
      setMessage("Processamento iniciado. Acompanhe o andamento abaixo.");
      openSection("processamento");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar processamento");
    } finally { setActionId(null); }
  }

  async function retryFailedJob(id: number) {
    setActionId(`retry-${id}`); setError(""); setMessage("");
    try {
      await retryJob(id);
      await refresh();
      setMessage("Novo processamento criado a partir do job falhado. Acompanhe o andamento abaixo.");
      openSection("processamento");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao reenviar processamento");
    } finally { setActionId(null); }
  }

  async function connectYoutube() {
    setActionId("youtube"); setError("");
    try {
      const result = await youtubeStart();
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar OAuth do YouTube");
      setActionId(null);
    }
  }

  async function approve(id: number) {
    setActionId(`approve-${id}`); setError("");
    try {
      await approveClip(id); await refresh(); setMessage("Corte aprovado para publicacao.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao aprovar corte");
    } finally { setActionId(null); }
  }

  async function upload(id: number) {
    setActionId(`upload-${id}`); setError("");
    try {
      await uploadClip(id, privacy); await refresh(); setMessage("Upload enviado para a fila do YouTube.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar upload");
    } finally { setActionId(null); }
  }

  return (
    <main className="min-h-screen bg-[#f7f7f7] pb-24 text-[#171717] xl:pb-10">
      <section className="border-b border-[#e6e6e6] bg-white">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-5 py-5 md:px-8 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <img src="/Logo.png" alt="ShortsFlow AI" className="h-12 w-auto max-w-[230px] object-contain" />
            <div className="hidden h-10 w-px bg-[#ececec] sm:block" />
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[.16em] text-[#ff0000]">Workspace ao vivo</div>
              <h1 className="mt-1 truncate text-2xl font-semibold tracking-[-.03em] text-[#111]">Painel ShortsFlow</h1>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={connectYoutube} disabled={actionId === "youtube"} className={`inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-xs font-semibold shadow-sm ${youtubeConnected ? "border-red-100 bg-red-50 text-red-700" : "border-[#d8d8d8] bg-white text-[#222] hover:bg-[#f4f4f4]"}`}>
              <YoutubeIcon className="h-4 w-4 text-[#ff0000]" />
              {youtubeConnected ? youtubeChannelTitle || "YouTube conectado" : actionId === "youtube" ? "Conectando..." : "Conectar YouTube"}
            </button>
            <button onClick={() => openSection("configurar")} className="rounded-lg bg-[#111] px-3.5 py-2 text-xs font-semibold text-white shadow-sm">Novo processamento</button>
          </div>
        </div>
      </section>

      <section className="border-b border-[#e6e6e6] bg-white/95 backdrop-blur">
        <div className="mx-auto grid max-w-[1440px] gap-2 px-5 py-3 md:px-8 lg:grid-cols-4">
          {sections.map((item) => {
            const active = activeSection === item.id;
            return (
              <button key={item.id} onClick={() => openSection(item.id)} className={`rounded-xl border px-4 py-3 text-left transition ${active ? "border-red-200 bg-red-50 shadow-sm" : "border-[#ededed] bg-white hover:border-[#d8d8d8]"}`}>
                <span className={`block text-sm font-semibold ${active ? "text-[#e00000]" : "text-[#222]"}`}>{item.label}</span>
                <span className="mt-1 block text-[11px] text-[#777]">{item.description}</span>
              </button>
            );
          })}
        </div>
      </section>

      {(error || message) && (
        <section className="mx-auto max-w-[1440px] px-5 pt-5 md:px-8">
          {error && <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div>}
          {message && <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">{message}</div>}
        </section>
      )}

      {activeSection === "automacao" && (
        <section id="automacao" className="mx-auto max-w-[1440px] px-5 py-6 md:px-8">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_420px]">
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <MetricCard label="Inscritos" value={liveMetrics?.hidden_subscriber_count ? "Oculto" : fmtNumber(liveMetrics?.subscriber_count || 0)} detail={liveMetrics?.channel_title || "Canal conectado"} />
                <MetricCard label="Visualizacoes" value={fmtNumber(liveMetrics?.view_count || 0)} detail={liveMetrics?.views_last_28d != null ? `${fmtNumber(liveMetrics.views_last_28d)} em 28 dias` : "Total do canal"} />
                <MetricCard label="Videos no canal" value={fmtExact(liveMetrics?.video_count || 0)} detail={`${activeJobs} jobs ativos`} />
                <MetricCard label="Uso do plano" value={user.unlimited ? `${fmtExact(user.jobs_used)} / ilimitado` : `${fmtExact(user.jobs_used)} / ${fmtExact(user.monthly_job_limit)}`} detail={user.plan_code || "starter"} />
              </div>

              <div className="overflow-hidden rounded-xl border border-[#e8e8e8] bg-white shadow-sm">
                <div className="flex flex-col gap-3 border-b border-[#e8e8e8] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#ff0000]">Video em destaque</div>
                    <h2 className="mt-1 text-xl font-semibold tracking-[-.02em] text-[#111]">{topVideo?.title || "Conecte o canal para exibir o destaque ao vivo"}</h2>
                  </div>
                  <button onClick={() => void refreshLive()} disabled={!youtubeConnected || liveLoading} className="inline-flex w-fit items-center gap-2 rounded-lg border border-[#d8d8d8] bg-white px-3 py-2 text-xs font-semibold text-[#222] shadow-sm disabled:opacity-50">
                    <RefreshIcon className="h-3.5 w-3.5" />{liveLoading ? "Atualizando..." : "Atualizar metricas"}
                  </button>
                </div>

                <div className="grid gap-0 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,.65fr)]">
                  <div className="bg-[#151515] p-4">
                    <div className="relative aspect-video overflow-hidden rounded-lg bg-[#101010]">
                      {topVideo?.thumbnail_url ? <img src={topVideo.thumbnail_url} alt="" className="h-full w-full object-cover opacity-70" /> : <div className="h-full w-full bg-[radial-gradient(circle_at_center,#343434,#111)]" />}
                      <div className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/10 to-black/60" />
                      <div className="absolute left-5 top-5 flex items-center gap-3">
                        <img src="/Logo.png" alt="" className="h-10 w-auto rounded-md bg-white object-contain shadow" />
                      </div>
                      <div className="absolute inset-0 grid place-items-center">
                        <span className="grid h-16 w-16 place-items-center rounded-full bg-white/95 text-[#111] shadow-2xl">
                          <PlayIcon className="ml-1 h-8 w-8" />
                        </span>
                      </div>
                      <div className="absolute bottom-0 left-0 right-0 p-5">
                        <div className="h-1.5 overflow-hidden rounded-full bg-white/25"><div className="h-full w-[42%] rounded-full bg-[#ff0000]" /></div>
                        <div className="mt-3 flex items-center gap-5 text-xs font-semibold text-white/90">
                          <span>{topVideo ? fmtDuration(topVideo.duration_seconds) : "0:00"}</span>
                          <span>{topVideo ? fmtNumber(topVideo.view_count) : "0"} views</span>
                          <span>{topVideo ? fmtNumber(topVideo.like_count) : "0"} likes</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="p-5">
                    {liveError && <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs font-semibold leading-5 text-amber-900">{liveError}</div>}
                    {!youtubeConnected && <div className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm font-semibold text-red-700">Conecte o YouTube para carregar o painel ao vivo deste perfil.</div>}
                    {topVideo && (
                      <div className="space-y-4">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-[.12em] text-[#777]">Canal</div>
                          <div className="mt-1 text-lg font-semibold text-[#111]">{liveMetrics?.channel_title || youtubeChannelTitle}</div>
                          <div className="mt-1 text-xs text-[#777]">Atualizado {liveMetrics?.refreshed_at ? fmtDate(liveMetrics.refreshed_at) : "agora"}</div>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-center">
                          <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold">{fmtNumber(topVideo.view_count)}</div><div className="text-[10px] text-[#777]">views</div></div>
                          <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold">{fmtNumber(topVideo.like_count)}</div><div className="text-[10px] text-[#777]">likes</div></div>
                          <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold">{fmtNumber(topVideo.comment_count)}</div><div className="text-[10px] text-[#777]">comentarios</div></div>
                        </div>
                        <a href={topVideo.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-lg bg-[#ff0000] px-4 py-2.5 text-xs font-semibold text-white shadow-sm">Abrir no YouTube <ArrowIcon className="h-3.5 w-3.5" /></a>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-[#e8e8e8] bg-white p-5 shadow-sm">
                <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#ff0000]">Videos recentes</div>
                    <h2 className="mt-1 text-xl font-semibold tracking-[-.02em] text-[#111]">Ranking do canal conectado</h2>
                  </div>
                  <span className="text-xs text-[#777]">{liveMetrics?.recent_videos.length || 0} videos analisados</span>
                </div>
                <div className="mt-4 divide-y divide-[#ededed]">
                  {(liveMetrics?.recent_videos || []).slice(0, 6).map((video, index) => (
                    <a key={video.video_id} href={video.url} target="_blank" rel="noreferrer" className="grid gap-3 py-3 sm:grid-cols-[32px_96px_minmax(0,1fr)_auto] sm:items-center">
                      <div className="text-sm font-semibold text-[#999]">#{index + 1}</div>
                      <img src={video.thumbnail_url} alt="" className="h-14 w-24 rounded-md bg-[#111] object-cover" />
                      <div className="min-w-0">
                        <div className="line-clamp-2 text-sm font-semibold text-[#222]">{video.title}</div>
                        <div className="mt-1 text-[11px] text-[#777]">{fmtDate(video.published_at)} · {fmtDuration(video.duration_seconds)}</div>
                      </div>
                      <div className="grid grid-cols-3 gap-3 text-right text-xs text-[#666]">
                        <span>{fmtNumber(video.view_count)} views</span>
                        <span>{fmtNumber(video.like_count)} likes</span>
                        <span>{fmtNumber(video.comment_count)} com.</span>
                      </div>
                    </a>
                  ))}
                  {youtubeConnected && !liveLoading && liveMetrics?.recent_videos.length === 0 && <div className="py-8 text-center text-sm text-[#777]">Nenhum video recente retornado pela API do YouTube.</div>}
                  {liveLoading && <div className="py-8 text-center text-sm font-semibold text-[#777]">Carregando metricas ao vivo...</div>}
                </div>
              </div>
            </div>

            <aside className="space-y-5">
              <div className="rounded-xl border border-[#e8e8e8] bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#ff0000]">Monetizacao</div>
                    <h2 className="mt-1 text-lg font-semibold text-[#111]">{monetization?.eligible_full_estimate ? "Pronto para YPP" : monetization?.near_monetization ? "Perto dos marcos" : "Em evolucao"}</h2>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-[10px] font-semibold ${monetization?.near_monetization ? "bg-red-50 text-red-700" : "bg-[#f1f1f1] text-[#666]"}`}>{monetization?.eligible_full_estimate ? "Elegivel" : monetization?.near_monetization ? "Alerta" : "Monitorando"}</span>
                </div>
                <div className="mt-5 space-y-5">
                  <ProgressBar label="Inscritos" value={liveMetrics?.hidden_subscriber_count ? "Oculto" : fmtExact(liveMetrics?.subscriber_count || 0)} target={fmtExact(monetization?.subscriber_target_full || 1000)} progress={monetization?.subscriber_progress_full || 0} />
                  <ProgressBar label="Horas assistidas" value={fmtExact(monetization?.watch_hours_last_365d || 0)} target={fmtExact(monetization?.watch_hours_target_full || 4000)} progress={monetization?.watch_hours_progress_full || 0} />
                  <ProgressBar label="Shorts views 90d" value={fmtNumber(monetization?.shorts_views_90d_estimate || 0)} target={fmtNumber(monetization?.shorts_views_target_full || 10_000_000)} progress={monetization?.shorts_views_progress_full || 0} />
                </div>
                <div className="mt-5 rounded-lg bg-[#f7f7f7] p-3 text-xs leading-5 text-[#666]">
                  {liveMetrics?.analytics_available ? "Watch hours carregadas pela API de Analytics do YouTube." : "Watch hours oficiais dependem do YouTube Analytics/Studio; o painel mantém estimativas com videos recentes."}
                </div>
              </div>

              <div className="rounded-xl border border-[#e8e8e8] bg-white p-5 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#ff0000]">Alertas</div>
                <div className="mt-4 grid gap-3">
                  {(liveMetrics?.alerts || [{ kind: "info", title: "Aguardando YouTube", detail: "Conecte ou atualize o canal para receber alertas ao vivo." }]).map((alert) => <AlertCard key={`${alert.title}-${alert.detail}`} alert={alert} />)}
                </div>
              </div>

              <div className="rounded-xl border border-[#e8e8e8] bg-white p-5 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#ff0000]">Perfis e limites</div>
                <h2 className="mt-1 text-lg font-semibold text-[#111]">Plano {user.plan_code || "starter"}</h2>
                <div className="mt-4">
                  <div className="flex items-center justify-between text-xs"><span className="font-semibold text-[#222]">Uso mensal</span><span className="text-[#666]">{user.unlimited ? `${fmtExact(user.jobs_used)} jobs` : `${fmtExact(user.jobs_used)} de ${fmtExact(user.monthly_job_limit)}`}</span></div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#ececec]"><div className="h-full rounded-full bg-[#ff0000]" style={{ width: `${usagePercent}%` }} /></div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold text-[#111]">{fmtExact(jobs.length)}</div><div className="text-[#777]">jobs</div></div>
                  <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold text-[#111]">{fmtExact(readyClips)}</div><div className="text-[#777]">cortes</div></div>
                  <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold text-[#111]">{user.unlimited ? "∞" : fmtExact(user.jobs_remaining ?? 0)}</div><div className="text-[#777]">restantes</div></div>
                </div>
              </div>
            </aside>
          </div>
        </section>
      )}

      {activeSection === "configurar" && (
        <section id="configurar" className="mx-auto max-w-[1440px] px-5 py-6 md:px-8">
          <div className="mb-5 flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#ff0000]">Criar Shorts</div>
              <h2 className="mt-1 text-3xl font-semibold tracking-[-.03em] text-[#111]">Pesquisa e corte automatico</h2>
              <p className="mt-2 text-sm text-[#666]">Pesquise tendencias usando a YouTube Data API e gere cortes verticais.</p>
            </div>
            <button onClick={() => openSection("automacao")} className="w-fit rounded-lg border border-[#d8d8d8] bg-white px-3.5 py-2 text-xs font-semibold text-[#222] shadow-sm">Voltar ao painel</button>
          </div>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_360px]">
            <div className="rounded-xl border border-[#e8e8e8] bg-white shadow-sm">
              <div className="border-b border-[#e8e8e8] px-5 py-4"><h3 className="text-sm font-semibold text-[#111]">Buscar conteudo</h3><p className="mt-1 text-xs text-[#666]">Encontre videos com potencial para cortes.</p></div>
              <div className="p-5">
                <div className="grid gap-3 md:grid-cols-[1fr_80px_110px_auto]">
                  <input value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} className="min-w-0 rounded-lg border border-[#d8d8d8] bg-white px-3 py-2.5 text-sm outline-none focus:border-[#ff0000]" placeholder="Ex.: marketing digital, imoveis, vendas" />
                  <input value={region} onChange={(e) => setRegion(e.target.value.toUpperCase().slice(0, 2))} className="rounded-lg border border-[#d8d8d8] bg-white px-3 py-2.5 text-center text-sm font-medium outline-none" />
                  <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-[#d8d8d8] bg-white px-3 py-2.5 text-sm outline-none"><option value={7}>7 dias</option><option value={14}>14 dias</option><option value={30}>30 dias</option><option value={90}>90 dias</option></select>
                  <button onClick={search} disabled={loading} className="flex items-center justify-center gap-2 rounded-lg bg-[#111] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"><SearchIcon className="h-4 w-4" />{loading ? "Buscando..." : "Buscar"}</button>
                </div>

                <div className="mt-5 max-h-[520px] divide-y divide-[#ededed] overflow-y-auto rounded-lg border border-[#e8e8e8]">
                  {videos.length === 0 && <div className="p-10 text-center text-sm text-[#777]">Faça uma busca para encontrar videos.</div>}
                  {videos.map((video) => (
                    <button key={video.video_id} onClick={() => setSelected(video)} className={`flex w-full items-center gap-4 p-3 text-left transition ${selected?.video_id === video.video_id ? "bg-red-50" : "bg-white hover:bg-[#f7f7f7]"}`}>
                      <div className="relative h-16 w-28 flex-none overflow-hidden rounded-md bg-[#111]"><img src={video.thumbnail_url} alt="" className="h-full w-full object-cover" /><span className="absolute inset-0 grid place-items-center bg-black/15"><span className="grid h-8 w-8 place-items-center rounded-full bg-white/95"><PlayIcon className="ml-0.5 h-3.5 w-3.5 text-[#111]" /></span></span></div>
                      <div className="min-w-0 flex-1"><div className="line-clamp-2 text-sm font-semibold leading-5 text-[#222]">{video.title}</div><div className="mt-1 text-[11px] text-[#777]">{video.channel_title} · {fmtNumber(video.view_count)} views · {fmtDuration(video.duration_seconds)}</div></div>
                      {selected?.video_id === video.video_id && <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-[#ff0000] text-white"><CheckIcon className="h-3.5 w-3.5" /></span>}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-[#e8e8e8] bg-white shadow-sm">
              <div className="border-b border-[#e8e8e8] px-5 py-4"><h3 className="text-sm font-semibold text-[#111]">Configuracao</h3><p className="mt-1 text-xs text-[#666]">Defina a quantidade de cortes.</p></div>
              <div className="p-5">
                <label className="text-xs font-medium text-[#222]">Quantidade de Shorts</label>
                <div className="mt-2 grid grid-cols-5 gap-2">{[1, 2, 3, 5, 10].map((n) => <button key={n} onClick={() => setRequestedClips(n)} className={`rounded-lg border py-2.5 text-sm font-semibold ${requestedClips === n ? "border-red-200 bg-red-50 text-red-700" : "border-[#e8e8e8] bg-white text-[#555]"}`}>{n}</button>)}</div>
                <div className="mt-5 divide-y divide-[#ededed] rounded-lg border border-[#e8e8e8] text-xs"><div className="flex justify-between p-3"><span className="text-[#777]">Formato</span><strong className="font-medium text-[#222]">9:16 vertical</strong></div><div className="flex justify-between p-3"><span className="text-[#777]">Duracao</span><strong className="font-medium text-[#222]">15-60s</strong></div><div className="flex justify-between p-3"><span className="text-[#777]">Legendas</span><strong className="font-medium text-[#222]">Automaticas</strong></div></div>
                <label className="mt-5 flex items-start gap-3 text-xs leading-5 text-[#666]"><input type="checkbox" checked={rightsConfirmed} onChange={(e) => setRightsConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#ff0000]" /><span>Confirmo que possuo direitos ou autorizacao para reutilizar o conteudo.</span></label>
                {selected && <div className="mt-4 rounded-lg bg-[#f7f7f7] p-3 text-xs"><div className="text-[#777]">Selecionado</div><div className="mt-1 line-clamp-2 font-medium text-[#222]">{selected.title}</div></div>}
                <button onClick={processSelected} disabled={Boolean(actionId?.startsWith("video-")) || !selected} className="mt-5 w-full rounded-lg bg-[#ff0000] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40">{actionId?.startsWith("video-") ? "Iniciando..." : `Gerar ${requestedClips} Shorts`}</button>
              </div>
            </div>
          </div>
        </section>
      )}

      {activeSection === "processamento" && (
        <section id="processamento" className="mx-auto max-w-[1440px] px-5 py-6 md:px-8">
          <div className="rounded-xl border border-[#e8e8e8] bg-white shadow-sm">
            <div className="flex flex-col justify-between gap-3 border-b border-[#e8e8e8] px-5 py-4 md:flex-row md:items-center"><div><div className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#ff0000]">Processamentos</div><h2 className="mt-1 text-xl font-semibold text-[#111]">Fila de criacao dos Shorts</h2><p className="mt-1 text-xs text-[#777]">{activeJobs} job(s) ativo(s). Atualizacao automatica a cada 3 segundos.</p></div><button onClick={() => void refresh()} className="flex w-fit items-center gap-2 rounded-lg border border-[#d8d8d8] bg-white px-3 py-2 text-xs font-semibold text-[#222]"><RefreshIcon className="h-3.5 w-3.5" />Atualizar</button></div>
            {jobs.length === 0 ? <div className="p-10 text-center text-sm text-[#777]">Seus processamentos aparecerao aqui.</div> : <div className="divide-y divide-[#ededed]">{jobs.map((job) => {
              const current = stageIndex[job.status] ?? 0;
              return <article key={job.id} className="p-5">
                <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div className="flex min-w-0 items-center gap-4">{job.source_video.thumbnail_url ? <img src={job.source_video.thumbnail_url} alt="" className="h-14 w-24 rounded-md object-cover" /> : <div className="grid h-14 w-24 place-items-center rounded-md bg-[#111]"><YoutubeIcon className="h-7 w-7 text-red-500" /></div>}<div className="min-w-0"><div className="text-[10px] text-[#777]">Job #{job.id}</div><h3 className="line-clamp-2 text-sm font-semibold text-[#222]">{job.source_video.title}</h3><p className="mt-1 text-xs text-[#777]">{job.clips.length}/{job.requested_clips} cortes</p></div></div><div className="flex items-center gap-3"><StatusBadge status={job.status} /><span className="text-xs font-semibold text-[#222]">{job.progress}%</span></div></div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[#ececec]"><div className={`h-full rounded-full transition-all duration-700 ${job.status === "failed" ? "bg-red-500" : "bg-[#ff0000]"}`} style={{ width: `${job.progress}%` }} /></div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{pipeline.map((stage, index) => { const active = job.status !== "failed" && (current >= index || job.status === "ready_for_review"); return <div key={stage} className={`rounded-lg border px-3 py-2 ${active ? "border-red-100 bg-red-50" : "border-[#e8e8e8] bg-white"}`}><div className={`text-[9px] font-medium ${active ? "text-red-700" : "text-[#999]"}`}>{String(index + 1).padStart(2, "0")}</div><div className="mt-0.5 text-[11px] font-medium text-[#555]">{stage}</div></div>; })}</div>
                {job.error && <div className="mt-4 flex flex-col gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-700 sm:flex-row sm:items-center sm:justify-between">
                  <p className="leading-5">{jobErrorMessage(job.error)}</p>
                  {job.status === "failed" && <button onClick={() => retryFailedJob(job.id)} disabled={actionId === `retry-${job.id}`} className="inline-flex w-fit flex-none items-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"><RefreshIcon className="h-3.5 w-3.5" />{actionId === `retry-${job.id}` ? "Recriando..." : "Tentar novamente"}</button>}
                </div>}
              </article>;
            })}</div>}
          </div>
        </section>
      )}

      {activeSection === "cortes" && (
        <section id="cortes" className="mx-auto max-w-[1440px] px-5 py-6 md:px-8">
          <div className="rounded-xl border border-[#e8e8e8] bg-white shadow-sm">
            <div className="flex flex-col justify-between gap-3 border-b border-[#e8e8e8] px-5 py-4 md:flex-row md:items-center"><div><div className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#ff0000]">Publicacoes</div><h2 className="mt-1 text-xl font-semibold text-[#111]">Cortes para revisao</h2><p className="mt-1 text-xs text-[#777]">Aprove individualmente antes do upload.</p></div><label className="flex w-fit items-center gap-2 text-xs text-[#777]">Privacidade<select value={privacy} onChange={(e) => setPrivacy(e.target.value)} className="rounded-lg border border-[#d8d8d8] bg-white px-2.5 py-2 font-medium text-[#222] outline-none"><option value="private">Privado</option><option value="unlisted">Nao listado</option><option value="public">Publico</option></select></label></div>
            {clips.length === 0 ? <div className="p-10 text-center text-sm text-[#777]">Os cortes gerados aparecerao aqui.</div> : <div className="grid gap-4 p-5 xl:grid-cols-2">{clips.map((clip) => (
              <article key={clip.id} className="grid gap-4 rounded-xl border border-[#e8e8e8] bg-white p-4 sm:grid-cols-[160px_1fr]">
                <div className="overflow-hidden rounded-lg bg-[#111]">{clip.media_url ? <video controls preload="metadata" className="aspect-[9/16] max-h-[340px] w-full object-contain" src={`${API_URL}${clip.media_url}`} /> : <div className="grid aspect-[9/16] place-items-center"><PlayIcon className="h-9 w-9 text-white/70" /></div>}</div>
                <div className="min-w-0"><div className="flex flex-wrap items-center justify-between gap-2"><StatusBadge status={clip.status} /><span className="text-xs text-[#777]">{(clip.end_seconds - clip.start_seconds).toFixed(1)}s</span></div><h3 className="mt-3 text-base font-semibold leading-6 text-[#111]">{clip.title}</h3>{clip.hook && <p className="mt-2 text-sm font-medium text-[#444]">{clip.hook}</p>}<p className="mt-3 text-xs leading-5 text-[#666]">{clip.description}</p><div className="mt-3 flex gap-2 rounded-lg bg-[#f7f7f7] p-3 text-[11px] leading-5 text-[#555]"><CopyIcon className="h-4 w-4 flex-none text-[#ff0000]" />{clip.copy}</div><div className="mt-2 flex gap-2 rounded-lg bg-[#f7f7f7] p-3 text-[11px] leading-5 text-[#555]"><TagsIcon className="h-4 w-4 flex-none text-[#ff0000]" /><span>{clip.tags.slice(0, 8).map((tag) => `#${tag}`).join(" ")}</span></div>{clip.upload_error && <p className="mt-3 rounded-lg bg-red-50 p-3 text-xs font-medium text-red-700">{clip.upload_error}</p>}{clip.youtube_video_id && <a href={`https://www.youtube.com/watch?v=${clip.youtube_video_id}`} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-red-600">Abrir no YouTube <ArrowIcon className="h-3.5 w-3.5" /></a>}<div className="mt-4 flex flex-wrap gap-2"><button onClick={() => approve(clip.id)} disabled={["approved", "upload_queued", "uploading", "uploaded"].includes(clip.status) || actionId === `approve-${clip.id}`} className="rounded-lg bg-[#111] px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-40">{clip.status === "approved" ? "Aprovado" : "Aprovar"}</button><button onClick={() => upload(clip.id)} disabled={!youtubeConnected || clip.status !== "approved" || actionId === `upload-${clip.id}`} className="flex items-center gap-2 rounded-lg bg-[#ff0000] px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-40"><UploadIcon className="h-3.5 w-3.5" />{clip.status === "uploading" ? "Enviando..." : clip.status === "uploaded" ? "Publicado" : "Enviar YouTube"}</button></div></div>
              </article>
            ))}</div>}
          </div>
        </section>
      )}
    </main>
  );
}
