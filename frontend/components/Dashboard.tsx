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
    checking_ffmpeg: "Verificando FFmpeg",
    downloading: "Baixando",
    extracting_audio: "Extraindo áudio",
    transcribing: "Transcrevendo",
    selecting_clips: "IA selecionando cortes",
    rendering: "Renderizando",
    ready_for_review: "Pronto para revisão",
    failed: "Falhou",
    ready: "Pronto",
    approved: "Aprovado",
    upload_queued: "Na fila de upload",
    uploading: "Enviando",
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
  const [jobs, setJobs] = useState<Job[]>([]);
  const [clips, setClips] = useState<Clip[]>([]);
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const [privacy, setPrivacy] = useState("private");
  const [loading, setLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [error, setError] = useState("");

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
    try {
      setVideos(await getTrending(keyword, region, days));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao buscar vídeos");
    } finally {
      setLoading(false);
    }
  }

  async function processVideo(video: TrendingVideo) {
    if (!rightsConfirmed) {
      setError("Marque a confirmação de direitos/licença antes de processar um vídeo.");
      return;
    }
    setActionId(`video-${video.video_id}`);
    setError("");
    try {
      await createJob(video, requestedClips);
      await refresh();
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
    try {
      await approveClip(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao aprovar corte");
    } finally {
      setActionId(null);
    }
  }

  async function upload(id: number) {
    setActionId(`upload-${id}`);
    try {
      await uploadClip(id, privacy);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar upload");
    } finally {
      setActionId(null);
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-[1500px] px-4 py-6 md:px-8">
      <header className="mb-6 flex flex-col gap-4 rounded-3xl border border-[var(--border)] bg-[var(--surface)]/90 p-6 shadow-2xl md:flex-row md:items-center md:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[.24em] text-[var(--accent-2)]">R2R • Video Automation</p>
          <h1 className="text-3xl font-black tracking-tight md:text-4xl">YouTube Shorts Automation SaaS</h1>
          <p className="mt-2 max-w-3xl text-sm text-[var(--muted)]">
            Descubra vídeos, gere cortes verticais com IA, revise e publique no seu canal com aprovação manual.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3 text-sm">
            <span className="text-[var(--muted)]">Jobs ativos</span>
            <strong className="ml-3 text-lg">{activeJobs}</strong>
          </div>
          <button
            onClick={connectYoutube}
            disabled={actionId === "youtube"}
            className={`rounded-2xl px-5 py-3 text-sm font-bold transition ${
              youtubeConnected ? "bg-emerald-500/15 text-emerald-300" : "bg-[var(--accent)] text-white hover:opacity-90"
            }`}
          >
            {youtubeConnected ? "YouTube conectado" : actionId === "youtube" ? "Conectando..." : "Conectar YouTube"}
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-6 rounded-2xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-200">{error}</div>
      )}

      <section className="mb-6 grid gap-4 lg:grid-cols-[1.35fr_.65fr]">
        <div className="rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-xl font-black">1. Descobrir vídeos</h2>
              <p className="text-sm text-[var(--muted)]">Sem palavra-chave, usa o ranking “mostPopular” da região.</p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-[1fr_100px_100px_auto]">
            <input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="Palavra-chave: vendas, imóveis, IA..."
              className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3 outline-none focus:border-[var(--accent)]"
            />
            <input
              value={region}
              onChange={(e) => setRegion(e.target.value.toUpperCase().slice(0, 2))}
              className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3 outline-none"
            />
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-3"
            >
              <option value={7}>7 dias</option>
              <option value={14}>14 dias</option>
              <option value={30}>30 dias</option>
              <option value={90}>90 dias</option>
            </select>
            <button onClick={search} disabled={loading} className="rounded-xl bg-white px-5 py-3 font-bold text-black hover:opacity-90">
              {loading ? "Buscando..." : "Buscar"}
            </button>
          </div>
        </div>

        <div className="rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <h2 className="text-xl font-black">Configuração do processamento</h2>
          <div className="mt-4 flex items-center gap-3">
            <label className="text-sm text-[var(--muted)]">Cortes por vídeo</label>
            <select
              value={requestedClips}
              onChange={(e) => setRequestedClips(Number(e.target.value))}
              className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2"
            >
              {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <label className="mt-4 flex items-start gap-3 text-sm leading-6 text-[var(--muted)]">
            <input type="checkbox" checked={rightsConfirmed} onChange={(e) => setRightsConfirmed(e.target.checked)} className="mt-1 size-4" />
            Confirmo que sou proprietário do conteúdo ou tenho licença/permissão para baixar, editar e republicar os vídeos processados.
          </label>
        </div>
      </section>

      <section className="mb-8">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-black">Vídeos encontrados</h2>
            <p className="text-sm text-[var(--muted)]">{videos.length} resultados nesta busca.</p>
          </div>
        </div>
        {videos.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-[var(--border)] p-10 text-center text-[var(--muted)]">Faça uma busca para preencher esta área.</div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {videos.map((video) => (
              <article key={video.video_id} className="overflow-hidden rounded-3xl border border-[var(--border)] bg-[var(--surface)]">
                <img src={video.thumbnail_url} alt="" className="aspect-video w-full object-cover" />
                <div className="p-4">
                  <h3 className="line-clamp-2 min-h-12 font-bold">{video.title}</h3>
                  <p className="mt-2 text-xs text-[var(--muted)]">{video.channel_title}</p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--muted)]">
                    <span>{fmtNumber(video.view_count)} views</span><span>•</span><span>{fmtDuration(video.duration_seconds)}</span>
                  </div>
                  <button
                    onClick={() => processVideo(video)}
                    disabled={actionId === `video-${video.video_id}` || !rightsConfirmed}
                    className="mt-4 w-full rounded-xl bg-[var(--accent)] px-4 py-3 text-sm font-black text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {actionId === `video-${video.video_id}` ? "Iniciando..." : "Gerar Shorts"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="mb-8 rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-black">2. Processamento</h2>
            <p className="text-sm text-[var(--muted)]">O painel atualiza automaticamente a cada 3 segundos.</p>
          </div>
          <button onClick={refresh} className="rounded-xl border border-[var(--border)] px-4 py-2 text-sm font-bold">Atualizar</button>
        </div>
        <div className="space-y-3">
          {jobs.length === 0 && <p className="py-6 text-center text-[var(--muted)]">Nenhum job criado.</p>}
          {jobs.map((job) => (
            <div key={job.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <p className="text-xs font-bold text-[var(--accent-2)]">JOB #{job.id}</p>
                  <p className="truncate font-bold">{job.source_video.title}</p>
                  <p className="text-xs text-[var(--muted)]">{statusLabel(job.status)} • {job.clips.length}/{job.requested_clips} cortes</p>
                </div>
                <div className="w-full md:w-72">
                  <div className="mb-1 flex justify-between text-xs text-[var(--muted)]"><span>{job.progress}%</span><span>{statusLabel(job.status)}</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-black/30"><div className="h-full bg-[var(--accent)] transition-all" style={{ width: `${job.progress}%` }} /></div>
                </div>
              </div>
              {job.error && <p className="mt-3 rounded-xl bg-red-500/10 p-3 text-xs text-red-200">{job.error}</p>}
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="text-2xl font-black">3. Revisar e publicar</h2>
            <p className="text-sm text-[var(--muted)]">Aprove cada corte individualmente antes de enviar para o YouTube.</p>
          </div>
          <label className="flex items-center gap-3 text-sm">
            Privacidade
            <select value={privacy} onChange={(e) => setPrivacy(e.target.value)} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
              <option value="private">Privado</option>
              <option value="unlisted">Não listado</option>
              <option value="public">Público</option>
            </select>
          </label>
        </div>

        {clips.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-[var(--border)] p-10 text-center text-[var(--muted)]">Os cortes gerados aparecerão aqui.</div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
            {clips.map((clip) => (
              <article key={clip.id} className="overflow-hidden rounded-3xl border border-[var(--border)] bg-[var(--surface)]">
                {clip.media_url ? (
                  <video controls preload="metadata" className="aspect-[9/16] max-h-[620px] w-full bg-black object-contain" src={`${API_URL}${clip.media_url}`} />
                ) : <div className="aspect-[9/16] bg-black/40" />}
                <div className="p-5">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <span className="rounded-full bg-white/5 px-3 py-1 text-xs font-bold">{statusLabel(clip.status)}</span>
                    <span className="text-xs text-[var(--muted)]">{(clip.end_seconds - clip.start_seconds).toFixed(1)}s</span>
                  </div>
                  <h3 className="text-lg font-black">{clip.title}</h3>
                  <p className="mt-2 text-sm text-[var(--muted)]">{clip.hook}</p>
                  <p className="mt-3 rounded-xl bg-white/5 p-3 text-xs leading-5 text-[var(--muted)]">{clip.description}</p>
                  <p className="mt-2 rounded-xl border border-[var(--border)] p-3 text-xs leading-5">{clip.copy}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {clip.tags.slice(0, 8).map((tag) => <span key={tag} className="rounded-full border border-[var(--border)] px-2 py-1 text-[11px] text-[var(--muted)]">#{tag}</span>)}
                  </div>
                  {clip.upload_error && <p className="mt-3 rounded-xl bg-red-500/10 p-3 text-xs text-red-200">{clip.upload_error}</p>}
                  {clip.youtube_video_id && (
                    <a href={`https://www.youtube.com/watch?v=${clip.youtube_video_id}`} target="_blank" rel="noreferrer" className="mt-3 block text-sm font-bold text-sky-300 underline">Abrir vídeo publicado</a>
                  )}
                  <div className="mt-4 grid grid-cols-2 gap-2">
                    <button
                      onClick={() => approve(clip.id)}
                      disabled={["approved", "uploading", "uploaded"].includes(clip.status) || actionId === `approve-${clip.id}`}
                      className="rounded-xl border border-[var(--border)] px-4 py-3 text-sm font-bold disabled:opacity-40"
                    >
                      {clip.status === "approved" ? "Aprovado" : "Aprovar"}
                    </button>
                    <button
                      onClick={() => upload(clip.id)}
                      disabled={!youtubeConnected || clip.status !== "approved" || actionId === `upload-${clip.id}`}
                      className="rounded-xl bg-[var(--accent)] px-4 py-3 text-sm font-black text-white disabled:opacity-40"
                    >
                      {clip.status === "uploading" ? "Enviando..." : clip.status === "uploaded" ? "Publicado" : "Enviar YouTube"}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
