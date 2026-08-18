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
  SparklesIcon,
  TagsIcon,
  UploadIcon,
  YoutubeIcon,
} from "./Icons";

const pipeline = [
  "Preparando",
  "Baixando vídeo",
  "Extraindo áudio",
  "Transcrevendo",
  "IA selecionando cortes",
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
    checking_ffmpeg: "Preparando FFmpeg",
    downloading: "Baixando vídeo",
    extracting_audio: "Extraindo áudio",
    transcribing: "Transcrevendo",
    selecting_clips: "IA selecionando cortes",
    rendering: "Renderizando 9:16",
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

  const activeJobs = useMemo(
    () => jobs.filter((job) => !["ready_for_review", "failed"].includes(job.status)).length,
    [jobs],
  );

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
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await getTrending(keyword, region, days);
      setVideos(result);
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao buscar vídeos");
    } finally {
      setLoading(false);
    }
  }

  async function processSelected() {
    if (!selected) {
      setError("Escolha um vídeo para continuar.");
      return;
    }
    if (!rightsConfirmed) {
      setError("Confirme que você possui direitos ou autorização para reutilizar o conteúdo.");
      return;
    }
    setActionId(`video-${selected.video_id}`);
    setError("");
    setMessage("");
    try {
      await createJob(selected, requestedClips);
      await refresh();
      setMessage("Processamento iniciado. Acompanhe cada etapa em tempo real abaixo.");
      document.getElementById("processamento")?.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar processamento");
    } finally {
      setActionId(null);
    }
  }

  async function connectYoutube() {
    setActionId("youtube");
    setError("");
    try {
      const result = await youtubeStart();
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar OAuth do YouTube");
      setActionId(null);
    }
  }

  async function approve(id: number) {
    setActionId(`approve-${id}`);
    setError("");
    try {
      await approveClip(id);
      await refresh();
      setMessage("Corte aprovado para publicação.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao aprovar corte");
    } finally {
      setActionId(null);
    }
  }

  async function upload(id: number) {
    setActionId(`upload-${id}`);
    setError("");
    try {
      await uploadClip(id, privacy);
      await refresh();
      setMessage("Upload enviado para a fila do YouTube.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar upload");
    } finally {
      setActionId(null);
    }
  }

  return (
    <main className="min-h-screen bg-[#f8faf5] text-[#111815]">
      <header className="sticky top-0 z-40 border-b border-black/5 bg-[#f8faf5]/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 md:px-8">
          <a href="#topo" className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-red-600 text-white shadow-sm">
              <YoutubeIcon className="h-7 w-7" />
            </div>
            <div>
              <div className="text-lg font-black tracking-tight">ShortsFlow AI</div>
              <div className="text-[10px] font-bold uppercase tracking-[.18em] text-[#6e7b73]">Shorts Automation</div>
            </div>
          </a>
          <nav className="hidden items-center gap-8 text-sm font-bold lg:flex">
            <a href="#automacao" className="hover:text-[#75a900]">Automação</a>
            <a href="#configurar" className="hover:text-[#75a900]">Criar Shorts</a>
            <a href="#processamento" className="hover:text-[#75a900]">Processamento</a>
            <a href="#cortes" className="hover:text-[#75a900]">Cortes</a>
          </nav>
          <button
            onClick={connectYoutube}
            disabled={actionId === "youtube" || youtubeConnected}
            className={`flex items-center gap-2 rounded-xl px-4 py-3 text-xs font-black transition sm:text-sm ${youtubeConnected ? "bg-[#eaf8c8] text-[#476700]" : "bg-[#111815] text-white hover:-translate-y-0.5"}`}
          >
            <YoutubeIcon className={`h-4 w-4 ${youtubeConnected ? "text-red-600" : "text-[#b8f238]"}`} />
            {youtubeConnected ? "YouTube conectado" : actionId === "youtube" ? "Conectando..." : "Conectar YouTube"}
            {!youtubeConnected && <ArrowIcon className="h-4 w-4 text-[#b8f238]" />}
          </button>
        </div>
      </header>

      <section id="automacao" className="mx-auto grid max-w-7xl items-center gap-12 px-4 pb-16 pt-12 md:px-8 lg:grid-cols-[1.05fr_.95fr] lg:pt-20">
        <div>
          <span className="inline-flex rounded-md bg-[#eaf8c8] px-3 py-1.5 text-[11px] font-black uppercase tracking-[.16em] text-[#547300]">Automação de conteúdo com IA</span>
          <h1 className="mt-7 max-w-3xl text-5xl font-black leading-[.98] tracking-[-.045em] md:text-7xl">
            Transforme vídeos em <span className="text-[#75a900]">Shorts prontos para publicar.</span>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-[#5c665f]">
            Escolha um vídeo, defina quantos cortes deseja e deixe a IA cuidar dos melhores momentos, transcrição, formato 9:16, legendas, título, descrição, copy, tags e publicação.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button onClick={() => document.getElementById("configurar")?.scrollIntoView({ behavior: "smooth" })} className="flex items-center gap-2 rounded-xl bg-[#111815] px-5 py-3.5 text-sm font-black text-white shadow-sm transition hover:-translate-y-0.5">
              Criar meus Shorts <ArrowIcon className="h-4 w-4 text-[#b8f238]" />
            </button>
            <button onClick={connectYoutube} disabled={youtubeConnected} className="flex items-center gap-2 rounded-xl border border-black/10 bg-white px-5 py-3.5 text-sm font-black shadow-sm">
              {youtubeConnected ? "Canal conectado" : "Conectar meu canal"} <YoutubeIcon className="h-4 w-4 text-red-600" />
            </button>
          </div>
          <div className="mt-8 flex flex-wrap gap-x-5 gap-y-2 text-xs font-semibold text-[#6d776f]">
            {["9:16 automático", "Legendas", "Metadata por IA", "Aprovação", "Upload em 1 fluxo"].map((item) => (
              <span key={item} className="flex items-center gap-1.5"><CheckIcon className="h-4 w-4 text-[#75a900]" />{item}</span>
            ))}
          </div>
        </div>

        <div className="relative min-h-[470px] overflow-hidden rounded-[32px] border border-black/5 bg-white p-7 shadow-[0_24px_80px_rgba(27,42,31,.10)]">
          <div className="absolute left-1/2 top-1/2 grid h-56 w-72 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[34px] bg-red-600 shadow-2xl shadow-red-100">
            <YoutubeIcon className="h-28 w-28 text-white" />
          </div>
          {["Descobrir", "Cortar", "Gerar IA", "Publicar"].map((label, index) => {
            const pos = ["left-8 top-10", "right-6 top-32", "right-7 bottom-28", "left-10 bottom-10"][index];
            return <div key={label} className={`absolute ${pos} flex items-center gap-3`}><div className="grid h-12 w-12 place-items-center rounded-full bg-[#b8f238]">{index === 0 ? <SearchIcon className="h-5 w-5" /> : index === 1 ? <FilmIcon className="h-5 w-5" /> : index === 2 ? <SparklesIcon className="h-5 w-5" /> : <UploadIcon className="h-5 w-5" />}</div><span className="rounded-full bg-white px-3 py-2 text-xs font-black shadow-sm">{label}</span></div>;
          })}
        </div>
      </section>

      <section className="border-y border-black/5 bg-white">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-2 px-4 py-6 md:grid-cols-4 md:px-8">
          {[["01", "Conecte seu canal"], ["02", "Escolha o vídeo"], ["03", "Defina a quantidade"], ["04", "Aprove e publique"]].map(([number, title]) => (
            <div key={number} className="flex items-center gap-3 rounded-2xl px-3 py-3"><span className="text-xs font-black text-[#75a900]">{number}</span><span className="text-sm font-black">{title}</span></div>
          ))}
        </div>
      </section>

      {error && <div className="mx-auto mt-6 max-w-7xl px-4 md:px-8"><div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-700">{error}</div></div>}
      {message && <div className="mx-auto mt-6 max-w-7xl px-4 md:px-8"><div className="rounded-2xl border border-[#b8f238] bg-[#f2fbdc] px-5 py-4 text-sm font-bold text-[#466400]">{message}</div></div>}

      <section id="configurar" className="mx-auto max-w-7xl px-4 py-16 md:px-8">
        <div className="mb-8 text-center">
          <span className="text-[11px] font-black uppercase tracking-[.18em] text-[#75a900]">Seu fluxo</span>
          <h2 className="mt-2 text-3xl font-black tracking-tight md:text-4xl">Do vídeo ao Short em poucos cliques</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-[#68736b]">Busque tendências reais do YouTube, escolha o conteúdo e acompanhe o processamento pelo worker.</p>
        </div>

        <div className="grid gap-5 lg:grid-cols-[1.15fr_.85fr]">
          <div className="rounded-[28px] border border-black/5 bg-white p-6 shadow-sm">
            <div className="mb-5 flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef9d5]"><SearchIcon className="h-5 w-5 text-[#5d8500]" /></div>
              <div><h3 className="font-black">1. Escolha o vídeo</h3><p className="text-xs text-[#7b857e]">Pesquise tendências usando a YouTube Data API</p></div>
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_80px_110px_auto]">
              <input value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} className="min-w-0 rounded-xl border border-black/10 bg-[#fbfcf9] px-4 py-3 text-sm outline-none focus:border-[#8fbd18]" placeholder="Ex.: marketing digital, imóveis, vendas" />
              <input value={region} onChange={(e) => setRegion(e.target.value.toUpperCase().slice(0, 2))} className="rounded-xl border border-black/10 bg-[#fbfcf9] px-3 py-3 text-center text-sm font-bold outline-none" />
              <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-xl border border-black/10 bg-[#fbfcf9] px-3 py-3 text-sm font-bold outline-none"><option value={7}>7 dias</option><option value={14}>14 dias</option><option value={30}>30 dias</option><option value={90}>90 dias</option></select>
              <button onClick={search} disabled={loading} className="flex items-center justify-center gap-2 rounded-xl bg-[#111815] px-5 py-3 text-sm font-black text-white disabled:opacity-50"><SearchIcon className="h-4 w-4 text-[#b8f238]" />{loading ? "Buscando..." : "Buscar"}</button>
            </div>

            <div className="mt-5 grid max-h-[520px] gap-3 overflow-y-auto pr-1">
              {videos.length === 0 && <div className="rounded-2xl border border-dashed border-black/10 bg-[#fbfcfa] p-8 text-center text-sm text-[#7b857e]">Faça uma busca para encontrar vídeos.</div>}
              {videos.map((video) => (
                <button key={video.video_id} onClick={() => setSelected(video)} className={`flex items-center gap-4 rounded-2xl border p-3 text-left transition ${selected?.video_id === video.video_id ? "border-[#8fbd18] bg-[#f3fbdc]" : "border-black/5 bg-[#fbfcfa] hover:border-black/10"}`}>
                  <div className="relative h-20 w-32 flex-none overflow-hidden rounded-xl bg-[#111815]"><img src={video.thumbnail_url} alt="" className="h-full w-full object-cover" /><span className="absolute inset-0 grid place-items-center bg-black/20"><span className="grid h-9 w-9 place-items-center rounded-full bg-white/95"><PlayIcon className="ml-0.5 h-4 w-4 text-[#111815]" /></span></span></div>
                  <div className="min-w-0 flex-1"><div className="line-clamp-2 text-sm font-black leading-5">{video.title}</div><div className="mt-1 text-[11px] text-[#707b73]">{video.channel_title} • {fmtNumber(video.view_count)} views • {fmtDuration(video.duration_seconds)}</div></div>
                  {selected?.video_id === video.video_id && <span className="grid h-7 w-7 flex-none place-items-center rounded-full bg-[#b8f238]"><CheckIcon className="h-4 w-4" /></span>}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-[28px] bg-[#0d241d] p-6 text-white shadow-sm">
            <div className="mb-6"><span className="text-[10px] font-black uppercase tracking-[.17em] text-[#b8f238]">Configuração</span><h3 className="mt-1 text-xl font-black">2. Quantos Shorts?</h3></div>
            <div className="grid grid-cols-5 gap-2">{[1, 2, 3, 5, 10].map((n) => <button key={n} onClick={() => setRequestedClips(n)} className={`rounded-xl py-3 text-sm font-black ${requestedClips === n ? "bg-[#b8f238] text-[#111815]" : "bg-white/10 text-white"}`}>{n}</button>)}</div>
            <div className="mt-6 space-y-3 rounded-2xl bg-white/10 p-4 text-sm"><div className="flex justify-between"><span className="text-white/60">Formato</span><strong>9:16 vertical</strong></div><div className="flex justify-between"><span className="text-white/60">Duração</span><strong>15–60s</strong></div><div className="flex justify-between"><span className="text-white/60">Legendas</span><strong className="text-[#b8f238]">Automáticas</strong></div><div className="flex justify-between"><span className="text-white/60">Metadata</span><strong className="text-[#b8f238]">IA automática</strong></div></div>
            <label className="mt-5 flex items-start gap-3 text-xs leading-5 text-white/70"><input type="checkbox" checked={rightsConfirmed} onChange={(e) => setRightsConfirmed(e.target.checked)} className="mt-1" />Confirmo que sou proprietário do conteúdo ou tenho licença/permissão para baixar, editar e republicar.</label>
            {selected && <div className="mt-5 rounded-xl border border-white/10 bg-white/5 p-3 text-xs"><span className="text-white/50">Selecionado:</span><div className="mt-1 line-clamp-2 font-bold">{selected.title}</div></div>}
            <button onClick={processSelected} disabled={Boolean(actionId?.startsWith("video-")) || !selected} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-[#b8f238] px-5 py-3.5 text-sm font-black text-[#111815] disabled:opacity-40"><SparklesIcon className="h-4 w-4" />{actionId?.startsWith("video-") ? "Iniciando..." : `Gerar ${requestedClips} Shorts com IA`}</button>
          </div>
        </div>
      </section>

      <section id="processamento" className="border-y border-black/5 bg-white py-16">
        <div className="mx-auto max-w-7xl px-4 md:px-8">
          <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
            <div><span className="text-[11px] font-black uppercase tracking-[.18em] text-[#75a900]">Processamento em tempo real</span><h2 className="mt-2 text-3xl font-black">Acompanhe cada etapa</h2><p className="mt-2 text-sm text-[#68736b]">{activeJobs} job(s) ativo(s). Atualização automática a cada 3 segundos.</p></div>
            <button onClick={refresh} className="flex w-fit items-center gap-2 rounded-xl border border-black/10 bg-[#f8faf5] px-4 py-2.5 text-sm font-black"><RefreshIcon className="h-4 w-4" />Atualizar</button>
          </div>

          {jobs.length === 0 ? <div className="rounded-[28px] border border-dashed border-black/10 bg-[#fbfcfa] p-12 text-center"><FilmIcon className="mx-auto h-9 w-9 text-[#9cab9f]" /><p className="mt-3 text-sm text-[#758078]">Seus processamentos aparecerão aqui.</p></div> : <div className="space-y-5">{jobs.map((job) => {
            const current = stageIndex[job.status] ?? 0;
            return <article key={job.id} className="rounded-[28px] border border-black/5 bg-[#fbfcfa] p-6 shadow-sm">
              <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div className="flex min-w-0 items-center gap-4">{job.source_video.thumbnail_url ? <img src={job.source_video.thumbnail_url} alt="" className="h-16 w-24 rounded-xl object-cover" /> : <div className="grid h-16 w-24 place-items-center rounded-xl bg-[#111815]"><YoutubeIcon className="h-8 w-8 text-red-500" /></div>}<div className="min-w-0"><div className="text-[10px] font-black uppercase tracking-[.14em] text-[#75a900]">Job #{job.id}</div><h3 className="line-clamp-2 font-black">{job.source_video.title}</h3><p className="mt-1 text-xs text-[#748078]">{job.clips.length}/{job.requested_clips} cortes • {statusLabel(job.status)}</p></div></div><div className={`w-fit rounded-full px-4 py-2 text-xs font-black ${job.status === "failed" ? "bg-red-50 text-red-700" : "bg-[#f1f8df] text-[#557700]"}`}>{job.progress}% • {statusLabel(job.status)}</div></div>
              <div className="mt-5 h-3 overflow-hidden rounded-full bg-[#edf0ea]"><div className={`h-full rounded-full transition-all duration-700 ${job.status === "failed" ? "bg-red-500" : "bg-[#9fd91f]"}`} style={{ width: `${job.progress}%` }} /></div>
              <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{pipeline.map((stage, index) => { const active = job.status !== "failed" && (current >= index || job.status === "ready_for_review"); return <div key={stage} className={`rounded-xl border p-3 ${active ? "border-[#b8f238] bg-[#f4fbdc]" : "border-black/5 bg-white"}`}><div className={`text-[10px] font-black ${active ? "text-[#6f9700]" : "text-[#a1aaa4]"}`}>0{index + 1}</div><div className="mt-1 text-xs font-bold">{stage}</div></div>; })}</div>
              {job.error && <p className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{job.error}</p>}
            </article>;
          })}</div>}
        </div>
      </section>

      <section id="cortes" className="mx-auto max-w-7xl px-4 py-16 md:px-8">
        <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div><span className="text-[11px] font-black uppercase tracking-[.18em] text-[#75a900]">Resultados</span><h2 className="mt-2 text-3xl font-black">Cortes prontos para revisar</h2><p className="mt-2 text-sm text-[#68736b]">Aprove individualmente antes do upload automático.</p></div>
          <label className="flex w-fit items-center gap-3 rounded-xl border border-black/10 bg-white px-4 py-3 text-sm font-bold">Privacidade<select value={privacy} onChange={(e) => setPrivacy(e.target.value)} className="bg-transparent font-black outline-none"><option value="private">Privado</option><option value="unlisted">Não listado</option><option value="public">Público</option></select></label>
        </div>

        {clips.length === 0 ? <div className="rounded-[28px] border border-dashed border-black/10 bg-white p-12 text-center"><FilmIcon className="mx-auto h-9 w-9 text-[#9cab9f]" /><p className="mt-3 text-sm text-[#758078]">Os cortes gerados aparecerão aqui.</p></div> : <div className="grid gap-5 lg:grid-cols-2">{clips.map((clip) => (
          <article key={clip.id} className="grid gap-4 overflow-hidden rounded-[28px] border border-black/5 bg-white p-4 shadow-sm sm:grid-cols-[190px_1fr]">
            <div className="overflow-hidden rounded-2xl bg-[#0d241d]">{clip.media_url ? <video controls preload="metadata" className="aspect-[9/16] max-h-[420px] w-full object-contain" src={`${API_URL}${clip.media_url}`} /> : <div className="grid aspect-[9/16] place-items-center"><PlayIcon className="h-10 w-10 text-[#b8f238]" /></div>}</div>
            <div className="min-w-0 p-1 sm:py-2"><div className="flex flex-wrap items-center justify-between gap-2"><span className="rounded-full bg-[#eef9d5] px-3 py-1 text-[10px] font-black uppercase text-[#5d8500]">{statusLabel(clip.status)}</span><span className="text-xs text-[#7b857e]">{(clip.end_seconds - clip.start_seconds).toFixed(1)}s</span></div><h3 className="mt-3 text-lg font-black leading-6">{clip.title}</h3>{clip.hook && <p className="mt-2 text-sm font-bold text-[#536157]">{clip.hook}</p>}<p className="mt-3 text-xs leading-5 text-[#6d786f]">{clip.description}</p><div className="mt-3 flex gap-2 rounded-xl bg-[#f8faf5] p-3 text-[11px] leading-5"><CopyIcon className="h-4 w-4 flex-none text-[#75a900]" />{clip.copy}</div><div className="mt-2 flex gap-2 rounded-xl bg-[#f8faf5] p-3 text-[11px] leading-5"><TagsIcon className="h-4 w-4 flex-none text-[#75a900]" /><span>{clip.tags.slice(0, 8).map((tag) => `#${tag}`).join(" ")}</span></div>{clip.upload_error && <p className="mt-3 rounded-xl bg-red-50 p-3 text-xs font-bold text-red-700">{clip.upload_error}</p>}{clip.youtube_video_id && <a href={`https://www.youtube.com/watch?v=${clip.youtube_video_id}`} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-xs font-black text-red-600">Abrir no YouTube <ArrowIcon className="h-3.5 w-3.5" /></a>}<div className="mt-4 flex flex-wrap gap-2"><button onClick={() => approve(clip.id)} disabled={["approved", "upload_queued", "uploading", "uploaded"].includes(clip.status) || actionId === `approve-${clip.id}`} className="rounded-xl bg-[#111815] px-4 py-2.5 text-xs font-black text-white disabled:opacity-40">{clip.status === "approved" ? "Aprovado" : "Aprovar"}</button><button onClick={() => upload(clip.id)} disabled={!youtubeConnected || clip.status !== "approved" || actionId === `upload-${clip.id}`} className="flex items-center gap-2 rounded-xl bg-[#b8f238] px-4 py-2.5 text-xs font-black text-[#111815] disabled:opacity-40"><UploadIcon className="h-4 w-4" />{clip.status === "uploading" ? "Enviando..." : clip.status === "uploaded" ? "Publicado" : "Enviar YouTube"}</button></div></div>
          </article>
        ))}</div>}
      </section>

      <footer className="border-t border-black/5 bg-white"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-4 px-4 py-8 text-xs text-[#6d776f] md:flex-row md:items-center md:px-8"><div className="flex items-center gap-2 font-black text-[#111815]"><YoutubeIcon className="h-5 w-5 text-red-600" />ShortsFlow AI</div><div>Automação de YouTube Shorts com IA • R2R Marketing Digital</div></div></footer>
    </main>
  );
}
