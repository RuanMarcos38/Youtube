"use client";

import { useEffect, useMemo, useState } from "react";
import {
  API_URL,
  approveClip,
  createJob,
  getTrending,
  listClips,
  listJobs,
  uploadClip,
  youtubeStart,
  youtubeStatus,
} from "@/lib/api";
import type { Clip, Job, TrendingVideo } from "@/lib/types";
import {
  ArrowIcon,
  CheckIcon,
  CopyIcon,
  FilmIcon,
  PlayIcon,
  RefreshIcon,
  SearchIcon,
  TagsIcon,
  UploadIcon,
  YoutubeIcon,
} from "./Icons";

const pipeline = [
  "Preparando",
  "Baixando vídeo",
  "Extraindo áudio",
  "Transcrevendo",
  "Selecionando cortes",
  "Renderizando 9:16",
  "Gerando legendas",
  "Pronto para revisar",
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

function fmtDuration(seconds: number) {
  const min = Math.floor(seconds / 60);
  const sec = Math.round(seconds % 60);
  return `${min}:${String(sec).padStart(2, "0")}`;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: "Na fila",
    checking_ffmpeg: "Preparando",
    downloading: "Baixando vídeo",
    extracting_audio: "Extraindo áudio",
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

function StatusBadge({ status }: { status: string }) {
  const ready = ["ready_for_review", "ready", "approved", "uploaded"].includes(status);
  const failed = ["failed", "upload_failed"].includes(status);
  const cls = failed ? "border-red-200 bg-red-50 text-red-700" : ready ? "border-[#b7d8d3] bg-[#e8f3f1] text-[#10665e]" : "border-[#e4e7ec] bg-[#f9fafb] text-[#475467]";
  return <span className={`inline-flex rounded-md border px-2 py-1 text-[10px] font-medium ${cls}`}>{statusLabel(status)}</span>;
}

export default function Dashboard() {
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
  const [privacy, setPrivacy] = useState("private");
  const [loading, setLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const activeJobs = useMemo(() => jobs.filter((job) => !["ready_for_review", "failed"].includes(job.status)).length, [jobs]);
  const readyClips = useMemo(() => clips.filter((clip) => ["ready", "approved", "uploaded"].includes(clip.status)).length, [clips]);

  async function refresh() {
    try {
      const [jobData, clipData, yt] = await Promise.all([listJobs(), listClips(), youtubeStatus()]);
      setJobs(jobData);
      setClips(clipData);
      setYoutubeConnected(yt.connected);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar o dashboard");
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, []);

  async function search() {
    setLoading(true); setError(""); setMessage("");
    try {
      const result = await getTrending(keyword, region, days);
      setVideos(result); setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao buscar vídeos");
    } finally { setLoading(false); }
  }

  async function processSelected() {
    if (!selected) return setError("Escolha um vídeo para continuar.");
    if (!rightsConfirmed) return setError("Confirme que você possui direitos ou autorização para reutilizar o conteúdo.");
    setActionId(`video-${selected.video_id}`); setError(""); setMessage("");
    try {
      await createJob(selected, requestedClips);
      await refresh();
      setMessage("Processamento iniciado. Acompanhe o andamento abaixo.");
      document.getElementById("processamento")?.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar processamento");
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
      await approveClip(id); await refresh(); setMessage("Corte aprovado para publicação.");
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
    <main className="min-h-screen bg-[#f4f6f8] text-[#17202a]">
      <header className="sticky top-0 z-40 border-b border-[#e4e7ec] bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-4 px-5 md:px-8">
          <a href="#automacao" className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-[#101828] text-white"><FilmIcon className="h-5 w-5" /></div>
            <div><div className="text-sm font-semibold text-[#101828]">ShortsFlow</div><div className="text-[11px] text-[#667085]">Shorts workspace</div></div>
          </a>
          <button onClick={connectYoutube} disabled={actionId === "youtube" || youtubeConnected} className={`flex items-center gap-2 rounded-lg border px-3.5 py-2 text-xs font-semibold shadow-sm ${youtubeConnected ? "border-[#b7d8d3] bg-[#e8f3f1] text-[#10665e]" : "border-[#d0d5dd] bg-white text-[#344054] hover:bg-[#f9fafb]"}`}>
            <YoutubeIcon className="h-4 w-4 text-red-600" />
            {youtubeConnected ? "YouTube conectado" : actionId === "youtube" ? "Conectando..." : "Conectar YouTube"}
          </button>
        </div>
      </header>

      <section id="automacao" className="mx-auto max-w-[1440px] px-5 py-7 md:px-8">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div><div className="text-xs font-medium text-[#147d72]">Visão geral</div><h1 className="mt-1 text-3xl font-semibold tracking-[-.035em] text-[#101828]">Produção de Shorts</h1><p className="mt-2 text-sm text-[#667085]">Pesquise conteúdos, gere cortes verticais e acompanhe a publicação em um único fluxo.</p></div>
          <div className="flex gap-2"><button onClick={() => document.getElementById("configurar")?.scrollIntoView({ behavior: "smooth" })} className="rounded-lg bg-[#101828] px-3.5 py-2 text-xs font-semibold text-white">Novo processamento</button><a href="/editor-ia" className="rounded-lg border border-[#d0d5dd] bg-white px-3.5 py-2 text-xs font-semibold text-[#344054]">Editor de vídeo</a></div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            ["Jobs ativos", activeJobs],
            ["Cortes disponíveis", readyClips],
            ["Processamentos", jobs.length],
            ["Canal", youtubeConnected ? "Conectado" : "Pendente"],
          ].map(([label, value]) => <div key={String(label)} className="rounded-xl border border-[#e4e7ec] bg-white p-4 shadow-sm"><div className="text-xs text-[#667085]">{label}</div><div className="mt-2 text-2xl font-semibold tracking-[-.02em] text-[#101828]">{value}</div></div>)}
        </div>

        {error && <div className="mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div>}
        {message && <div className="mt-5 rounded-lg border border-[#b7d8d3] bg-[#e8f3f1] px-4 py-3 text-sm font-medium text-[#10665e]">{message}</div>}
      </section>

      <section id="configurar" className="mx-auto max-w-[1440px] px-5 pb-8 md:px-8">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_360px]">
          <div className="rounded-xl border border-[#e4e7ec] bg-white shadow-sm">
            <div className="border-b border-[#e4e7ec] px-5 py-4"><h2 className="text-sm font-semibold text-[#101828]">Buscar conteúdo</h2><p className="mt-1 text-xs text-[#667085]">Pesquise tendências usando a YouTube Data API.</p></div>
            <div className="p-5">
              <div className="grid gap-3 md:grid-cols-[1fr_80px_110px_auto]">
                <input value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} className="min-w-0 rounded-lg border border-[#d0d5dd] bg-white px-3 py-2.5 text-sm outline-none focus:border-[#8abdb7]" placeholder="Ex.: marketing digital, imóveis, vendas" />
                <input value={region} onChange={(e) => setRegion(e.target.value.toUpperCase().slice(0, 2))} className="rounded-lg border border-[#d0d5dd] bg-white px-3 py-2.5 text-center text-sm font-medium outline-none" />
                <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-[#d0d5dd] bg-white px-3 py-2.5 text-sm outline-none"><option value={7}>7 dias</option><option value={14}>14 dias</option><option value={30}>30 dias</option><option value={90}>90 dias</option></select>
                <button onClick={search} disabled={loading} className="flex items-center justify-center gap-2 rounded-lg bg-[#101828] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"><SearchIcon className="h-4 w-4" />{loading ? "Buscando..." : "Buscar"}</button>
              </div>

              <div className="mt-5 max-h-[520px] divide-y divide-[#eef0f2] overflow-y-auto rounded-lg border border-[#e4e7ec]">
                {videos.length === 0 && <div className="p-10 text-center text-sm text-[#667085]">Faça uma busca para encontrar vídeos.</div>}
                {videos.map((video) => (
                  <button key={video.video_id} onClick={() => setSelected(video)} className={`flex w-full items-center gap-4 p-3 text-left transition ${selected?.video_id === video.video_id ? "bg-[#f2f8f7]" : "bg-white hover:bg-[#f9fafb]"}`}>
                    <div className="relative h-16 w-28 flex-none overflow-hidden rounded-md bg-[#101828]"><img src={video.thumbnail_url} alt="" className="h-full w-full object-cover" /><span className="absolute inset-0 grid place-items-center bg-black/15"><span className="grid h-8 w-8 place-items-center rounded-full bg-white/95"><PlayIcon className="ml-0.5 h-3.5 w-3.5 text-[#101828]" /></span></span></div>
                    <div className="min-w-0 flex-1"><div className="line-clamp-2 text-sm font-semibold leading-5 text-[#344054]">{video.title}</div><div className="mt-1 text-[11px] text-[#667085]">{video.channel_title} · {fmtNumber(video.view_count)} views · {fmtDuration(video.duration_seconds)}</div></div>
                    {selected?.video_id === video.video_id && <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-[#147d72] text-white"><CheckIcon className="h-3.5 w-3.5" /></span>}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-[#e4e7ec] bg-white shadow-sm">
            <div className="border-b border-[#e4e7ec] px-5 py-4"><h2 className="text-sm font-semibold text-[#101828]">Configuração</h2><p className="mt-1 text-xs text-[#667085]">Defina a quantidade de cortes.</p></div>
            <div className="p-5">
              <label className="text-xs font-medium text-[#344054]">Quantidade de Shorts</label>
              <div className="mt-2 grid grid-cols-5 gap-2">{[1, 2, 3, 5, 10].map((n) => <button key={n} onClick={() => setRequestedClips(n)} className={`rounded-lg border py-2.5 text-sm font-semibold ${requestedClips === n ? "border-[#147d72] bg-[#e8f3f1] text-[#10665e]" : "border-[#e4e7ec] bg-white text-[#475467]"}`}>{n}</button>)}</div>
              <div className="mt-5 divide-y divide-[#eef0f2] rounded-lg border border-[#e4e7ec] text-xs"><div className="flex justify-between p-3"><span className="text-[#667085]">Formato</span><strong className="font-medium text-[#344054]">9:16 vertical</strong></div><div className="flex justify-between p-3"><span className="text-[#667085]">Duração</span><strong className="font-medium text-[#344054]">15–60s</strong></div><div className="flex justify-between p-3"><span className="text-[#667085]">Legendas</span><strong className="font-medium text-[#344054]">Automáticas</strong></div></div>
              <label className="mt-5 flex items-start gap-3 text-xs leading-5 text-[#667085]"><input type="checkbox" checked={rightsConfirmed} onChange={(e) => setRightsConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#147d72]" /><span>Confirmo que possuo direitos ou autorização para reutilizar o conteúdo.</span></label>
              {selected && <div className="mt-4 rounded-lg bg-[#f9fafb] p-3 text-xs"><div className="text-[#667085]">Selecionado</div><div className="mt-1 line-clamp-2 font-medium text-[#344054]">{selected.title}</div></div>}
              <button onClick={processSelected} disabled={Boolean(actionId?.startsWith("video-")) || !selected} className="mt-5 w-full rounded-lg bg-[#147d72] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40">{actionId?.startsWith("video-") ? "Iniciando..." : `Gerar ${requestedClips} Shorts`}</button>
            </div>
          </div>
        </div>
      </section>

      <section id="processamento" className="mx-auto max-w-[1440px] px-5 pb-8 md:px-8">
        <div className="rounded-xl border border-[#e4e7ec] bg-white shadow-sm">
          <div className="flex flex-col justify-between gap-3 border-b border-[#e4e7ec] px-5 py-4 md:flex-row md:items-center"><div><h2 className="text-sm font-semibold text-[#101828]">Processamentos</h2><p className="mt-1 text-xs text-[#667085]">{activeJobs} job(s) ativo(s). Atualização automática a cada 3 segundos.</p></div><button onClick={refresh} className="flex w-fit items-center gap-2 rounded-lg border border-[#d0d5dd] bg-white px-3 py-2 text-xs font-semibold text-[#344054]"><RefreshIcon className="h-3.5 w-3.5" />Atualizar</button></div>
          {jobs.length === 0 ? <div className="p-10 text-center text-sm text-[#667085]">Seus processamentos aparecerão aqui.</div> : <div className="divide-y divide-[#eef0f2]">{jobs.map((job) => {
            const current = stageIndex[job.status] ?? 0;
            return <article key={job.id} className="p-5">
              <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div className="flex min-w-0 items-center gap-4">{job.source_video.thumbnail_url ? <img src={job.source_video.thumbnail_url} alt="" className="h-14 w-24 rounded-md object-cover" /> : <div className="grid h-14 w-24 place-items-center rounded-md bg-[#101828]"><YoutubeIcon className="h-7 w-7 text-red-500" /></div>}<div className="min-w-0"><div className="text-[10px] text-[#667085]">Job #{job.id}</div><h3 className="line-clamp-2 text-sm font-semibold text-[#344054]">{job.source_video.title}</h3><p className="mt-1 text-xs text-[#667085]">{job.clips.length}/{job.requested_clips} cortes</p></div></div><div className="flex items-center gap-3"><StatusBadge status={job.status} /><span className="text-xs font-semibold text-[#344054]">{job.progress}%</span></div></div>
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[#eef2f6]"><div className={`h-full rounded-full transition-all duration-700 ${job.status === "failed" ? "bg-red-500" : "bg-[#147d72]"}`} style={{ width: `${job.progress}%` }} /></div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{pipeline.map((stage, index) => { const active = job.status !== "failed" && (current >= index || job.status === "ready_for_review"); return <div key={stage} className={`rounded-lg border px-3 py-2 ${active ? "border-[#b7d8d3] bg-[#f6fbfa]" : "border-[#e4e7ec] bg-white"}`}><div className={`text-[9px] font-medium ${active ? "text-[#147d72]" : "text-[#98a2b3]"}`}>{String(index + 1).padStart(2, "0")}</div><div className="mt-0.5 text-[11px] font-medium text-[#475467]">{stage}</div></div>; })}</div>
              {job.error && <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-700">{job.error}</p>}
            </article>;
          })}</div>}
        </div>
      </section>

      <section id="cortes" className="mx-auto max-w-[1440px] px-5 pb-10 md:px-8">
        <div className="rounded-xl border border-[#e4e7ec] bg-white shadow-sm">
          <div className="flex flex-col justify-between gap-3 border-b border-[#e4e7ec] px-5 py-4 md:flex-row md:items-center"><div><h2 className="text-sm font-semibold text-[#101828]">Cortes para revisão</h2><p className="mt-1 text-xs text-[#667085]">Aprove individualmente antes do upload.</p></div><label className="flex w-fit items-center gap-2 text-xs text-[#667085]">Privacidade<select value={privacy} onChange={(e) => setPrivacy(e.target.value)} className="rounded-lg border border-[#d0d5dd] bg-white px-2.5 py-2 font-medium text-[#344054] outline-none"><option value="private">Privado</option><option value="unlisted">Não listado</option><option value="public">Público</option></select></label></div>
          {clips.length === 0 ? <div className="p-10 text-center text-sm text-[#667085]">Os cortes gerados aparecerão aqui.</div> : <div className="grid gap-4 p-5 xl:grid-cols-2">{clips.map((clip) => (
            <article key={clip.id} className="grid gap-4 rounded-xl border border-[#e4e7ec] bg-white p-4 sm:grid-cols-[160px_1fr]">
              <div className="overflow-hidden rounded-lg bg-[#101828]">{clip.media_url ? <video controls preload="metadata" className="aspect-[9/16] max-h-[340px] w-full object-contain" src={`${API_URL}${clip.media_url}`} /> : <div className="grid aspect-[9/16] place-items-center"><PlayIcon className="h-9 w-9 text-white/70" /></div>}</div>
              <div className="min-w-0"><div className="flex flex-wrap items-center justify-between gap-2"><StatusBadge status={clip.status} /><span className="text-xs text-[#667085]">{(clip.end_seconds - clip.start_seconds).toFixed(1)}s</span></div><h3 className="mt-3 text-base font-semibold leading-6 text-[#101828]">{clip.title}</h3>{clip.hook && <p className="mt-2 text-sm font-medium text-[#475467]">{clip.hook}</p>}<p className="mt-3 text-xs leading-5 text-[#667085]">{clip.description}</p><div className="mt-3 flex gap-2 rounded-lg bg-[#f9fafb] p-3 text-[11px] leading-5 text-[#475467]"><CopyIcon className="h-4 w-4 flex-none text-[#147d72]" />{clip.copy}</div><div className="mt-2 flex gap-2 rounded-lg bg-[#f9fafb] p-3 text-[11px] leading-5 text-[#475467]"><TagsIcon className="h-4 w-4 flex-none text-[#147d72]" /><span>{clip.tags.slice(0, 8).map((tag) => `#${tag}`).join(" ")}</span></div>{clip.upload_error && <p className="mt-3 rounded-lg bg-red-50 p-3 text-xs font-medium text-red-700">{clip.upload_error}</p>}{clip.youtube_video_id && <a href={`https://www.youtube.com/watch?v=${clip.youtube_video_id}`} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-red-600">Abrir no YouTube <ArrowIcon className="h-3.5 w-3.5" /></a>}<div className="mt-4 flex flex-wrap gap-2"><button onClick={() => approve(clip.id)} disabled={["approved", "upload_queued", "uploading", "uploaded"].includes(clip.status) || actionId === `approve-${clip.id}`} className="rounded-lg bg-[#101828] px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-40">{clip.status === "approved" ? "Aprovado" : "Aprovar"}</button><button onClick={() => upload(clip.id)} disabled={!youtubeConnected || clip.status !== "approved" || actionId === `upload-${clip.id}`} className="flex items-center gap-2 rounded-lg bg-[#147d72] px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-40"><UploadIcon className="h-3.5 w-3.5" />{clip.status === "uploading" ? "Enviando..." : clip.status === "uploaded" ? "Publicado" : "Enviar YouTube"}</button></div></div>
            </article>
          ))}</div>}
        </div>
      </section>
    </main>
  );
}
