"use client";

import { useEffect, useMemo, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type IconProps = { className?: string };

type Preset = { id: string; label: string; description: string; target: string };
type TimelineItem = { id: string; source: string; source_in: number; source_out: number; timeline_in: number; timeline_out: number; enabled?: boolean };
type TimelineTrack = { id: string; type: string; locked?: boolean; items: Array<TimelineItem | Record<string, unknown>> };
type Timeline = { version: number; duration: number; preset: string; canvas: { width: number; height: number; fps: number; aspect_ratio: string }; tracks: TimelineTrack[] };
type HookVariant = { variant: string; text: string; duration_seconds: number; media_url: string };
type Project = {
  id: string;
  original_filename: string;
  preset: string;
  target_platform: string;
  status: string;
  progress: number;
  error?: string | null;
  timeline?: Timeline | null;
  preview_url?: string | null;
  export_url?: string | null;
  hook_variants?: HookVariant[];
  analysis?: {
    source_duration?: number;
    edited_duration?: number;
    removed_seconds?: number;
    keywords?: string[];
    notes?: string[];
    quality?: Record<string, string | number>;
    auto_reframe?: { enabled?: boolean; mode?: string; tracked_shots?: number; total_shots?: number; aspect_ratio?: string };
    sound_design?: { enabled?: boolean; mood?: string; music_source?: string; cut_sync_points?: number; voice_target_lufs?: number };
    broll?: { enabled?: boolean; strategy?: string; items?: number; concepts?: string[]; rights?: string };
    hook_variations?: HookVariant[];
    social_formats?: Record<string, string>;
  };
};

const workingStatuses = new Set(["queued", "analyzing", "transcribing", "ai_editing", "rendering", "export_queued", "exporting"]);
const statusLabels: Record<string, string> = {
  uploaded: "Vídeo anexado",
  queued: "Na fila do Auto-Edit IA",
  analyzing: "Analisando vídeo e áudio",
  transcribing: "Transcrevendo fala",
  ai_editing: "IA planejando cortes e ritmo",
  rendering: "Renderizando edição",
  ready: "Pronto para revisar",
  export_queued: "Exportação na fila",
  exporting: "Preparando TikTok Shop",
  exported: "Exportado para TikTok Shop",
  failed: "Falha no processamento",
};

function TikTokIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M14.7 3.2c.5 2.4 1.8 3.8 4.1 4.4v3.1a9 9 0 0 1-4.1-1.2v5.6a5.8 5.8 0 1 1-5-5.7v3.2a2.7 2.7 0 1 0 1.8 2.5V3.2h3.2Z" fill="currentColor"/></svg>;
}

function YoutubeIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="2.2" y="5.2" width="19.6" height="13.6" rx="4" fill="#ff2020"/><path d="m10 9 5.2 3-5.2 3V9Z" fill="white"/></svg>;
}

function SparklesIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M12 2.8c.8 4.6 2.6 6.4 7.2 7.2-4.6.8-6.4 2.6-7.2 7.2-.8-4.6-2.6-6.4-7.2-7.2 4.6-.8 6.4-2.6 7.2-7.2Z" fill="currentColor"/><path d="M18.5 15.2c.35 2 1.15 2.8 3.15 3.15-2 .35-2.8 1.15-3.15 3.15-.35-2-1.15-2.8-3.15-3.15 2-.35 2.8-1.15 3.15-3.15Z" fill="currentColor" opacity=".62"/></svg>;
}

function FilmIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2.5" stroke="currentColor" strokeWidth="1.7"/><path d="M7 4v16M17 4v16M3 9h4m10 0h4M3 15h4m10 0h4" stroke="currentColor" strokeWidth="1.5"/></svg>;
}

function ScissorsIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><circle cx="6" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.7"/><circle cx="6" cy="18" r="2.5" stroke="currentColor" strokeWidth="1.7"/><path d="m8 7.7 11 8.1M8 16.3l11-8.1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>;
}

function UploadIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M12 16V5m0 0L8 9m4-4 4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M5 14.5V19h14v-4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>;
}

function FolderIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9Z" stroke="currentColor" strokeWidth="1.8"/></svg>;
}

function BrainIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M9.2 4.5A3.2 3.2 0 0 0 4.8 8a3 3 0 0 0 .1 5.7A3.5 3.5 0 0 0 9 19.5m5.8-15A3.2 3.2 0 0 1 19.2 8a3 3 0 0 1-.1 5.7 3.5 3.5 0 0 1-4.1 5.8M9 5v14m6-14v14M9 9H7.4M15 9h1.6M9 14H7.4M15 14h1.6M12 7v10" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round"/></svg>;
}

function TimelineIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/><rect x="7" y="5" width="4" height="4" rx="1" fill="currentColor"/><rect x="13" y="10" width="4" height="4" rx="1" fill="currentColor"/><rect x="9" y="15" width="4" height="4" rx="1" fill="currentColor"/></svg>;
}

function CaptionsIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.7"/><path d="M10 10.2c-.6-.6-1.2-.9-2-.9-1.6 0-2.7 1.2-2.7 2.7s1.1 2.7 2.7 2.7c.8 0 1.4-.3 2-.9M18.2 10.2c-.6-.6-1.2-.9-2-.9-1.6 0-2.7 1.2-2.7 2.7s1.1 2.7 2.7 2.7c.8 0 1.4-.3 2-.9" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round"/></svg>;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers: { ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(init?.headers || {}) },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { const body = await response.json(); detail = body.detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

export default function EditorIAPage() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [preset, setPreset] = useState("tiktok_shop_sales");
  const [file, setFile] = useState<File | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Preset[]>("/api/editor-ai/presets").then(setPresets).catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar presets."));
  }, []);

  useEffect(() => {
    if (!project?.id || !workingStatuses.has(project.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const fresh = await api<Project>(`/api/editor-ai/projects/${project.id}`);
        setProject(fresh);
        if (fresh.timeline) setTimeline(fresh.timeline);
      } catch {}
    }, 2500);
    return () => window.clearInterval(timer);
  }, [project?.id, project?.status]);

  useEffect(() => { if (project?.timeline) setTimeline(project.timeline); }, [project?.timeline]);

  const videoItems = useMemo(() => {
    const track = timeline?.tracks?.find((item) => item.type === "video");
    return (track?.items || []) as TimelineItem[];
  }, [timeline]);

  const hookVariants = project?.hook_variants || project?.analysis?.hook_variations || [];

  async function upload() {
    if (!file) return setError("Selecione um vídeo para anexar.");
    if (!rightsConfirmed) return setError("Confirme os direitos de uso do vídeo.");
    setBusy(true); setError(""); setMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("preset", preset);
      form.append("target_platform", "tiktok_shop");
      form.append("rights_confirmed", "true");
      const created = await api<Project>("/api/editor-ai/upload", { method: "POST", body: form });
      setProject(created); setTimeline(null); setMessage("Vídeo anexado. Agora acione o Auto-Edit IA.");
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao anexar vídeo."); }
    finally { setBusy(false); }
  }

  async function autoEdit() {
    if (!project) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const queued = await api<Project>(`/api/editor-ai/projects/${project.id}/auto-edit`, { method: "POST", body: JSON.stringify({ preset }) });
      setProject(queued); setMessage("Auto-Edit IA iniciado. O vídeo será entregue pronto e com timeline editável.");
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao iniciar Auto-Edit IA."); }
    finally { setBusy(false); }
  }

  function toggleClip(id: string) {
    if (!timeline) return;
    setTimeline({
      ...timeline,
      tracks: timeline.tracks.map((track) => track.type !== "video" ? track : {
        ...track,
        items: track.items.map((raw) => {
          const item = raw as TimelineItem;
          return item.id === id ? { ...item, enabled: item.enabled === false } : item;
        }),
      }),
    });
  }

  async function saveTimeline() {
    if (!project || !timeline) return;
    setBusy(true); setError("");
    try {
      const queued = await api<Project>(`/api/editor-ai/projects/${project.id}/timeline`, { method: "PUT", body: JSON.stringify({ timeline }) });
      setProject(queued); setMessage("Ajustes salvos. A IA está renderizando novamente sem destruir as camadas.");
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao salvar timeline."); }
    finally { setBusy(false); }
  }

  async function exportTikTok() {
    if (!project) return;
    setBusy(true); setError("");
    try {
      const queued = await api<Project>(`/api/editor-ai/projects/${project.id}/export/tiktok-shop`, { method: "POST" });
      setProject(queued); setMessage("Exportação TikTok Shop iniciada.");
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao exportar."); }
    finally { setBusy(false); }
  }

  return (
    <main className="min-h-screen bg-[#f8faf5] pb-28 text-[#111815] xl:pb-8">
      <header className="sticky top-0 z-40 border-b border-black/5 bg-[#f8faf5]/95 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-5 py-4 md:px-8">
          <div className="flex items-center gap-4">
            <div>
              <div className="text-xl font-black tracking-tight text-[#0d241d]">ShortsFlow AI</div>
              <div className="mt-0.5 text-[10px] font-bold uppercase tracking-[.18em] text-[#6e7b73]">Auto-Edit IA • TikTok Shop</div>
            </div>
            <div className="hidden items-center gap-2 sm:flex">
              <span className="grid h-8 w-8 place-items-center rounded-full border border-black/5 bg-white text-[#111815] shadow-sm"><TikTokIcon /></span>
              <span className="grid h-8 w-8 place-items-center rounded-full border border-black/5 bg-white shadow-sm"><YoutubeIcon /></span>
            </div>
          </div>
          <a href="/" className="rounded-xl border border-black/10 bg-white px-4 py-2.5 text-sm font-black shadow-sm transition hover:-translate-y-0.5">Voltar ao painel</a>
        </div>
      </header>

      <section className="mx-auto max-w-[1400px] px-5 py-8 md:px-8 md:py-10">
        <div className="max-w-[940px]">
          <span className="inline-flex items-center gap-2 rounded-full bg-[#eaf8c8] px-3.5 py-2 text-[10px] font-black uppercase tracking-[.15em] text-[#486300]">
            <SparklesIcon className="h-3.5 w-3.5" /> Edição automatizada por inteligência artificial
          </span>
          <h1 className="mt-5 max-w-[900px] text-[38px] font-black leading-[1.02] tracking-[-.045em] text-[#0d241d] md:text-[54px]">
            Envie seu vídeo e deixe a IA criar a edição para vendas. <FilmIcon className="ml-2 inline h-9 w-9 align-[-2px] text-[#18231f] md:h-10 md:w-10" />
          </h1>
          <p className="mt-5 max-w-[800px] text-sm leading-6 text-[#667169] md:text-[15px]">
            Remove pausas e erros detectáveis, ajusta ritmo, cria legendas cinematográficas, faz auto-reframe 9:16, aplica sound design, B-roll contextual derivado do seu próprio material e gera 3 ganchos de alta retenção.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white px-3 py-2 text-xs font-bold text-[#4f5953] shadow-sm"><TikTokIcon className="h-4 w-4 text-[#111815]" /> Otimizado para TikTok</span>
            <span className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white px-3 py-2 text-xs font-bold text-[#4f5953] shadow-sm"><YoutubeIcon className="h-4 w-4" /> Otimizado para YouTube</span>
            <span className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white px-3 py-2 text-xs font-bold text-[#4f5953] shadow-sm"><ScissorsIcon className="h-4 w-4" /> Edição automática com IA</span>
          </div>
        </div>

        {error && <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-700">{error}</div>}
        {message && <div className="mt-6 rounded-2xl border border-[#b8f238] bg-[#f2fbdc] px-5 py-4 text-sm font-bold text-[#466400]">{message}</div>}

        <div className="mt-8 grid items-stretch gap-5 lg:grid-cols-[minmax(0,.92fr)_minmax(0,1.08fr)]">
          <div className="rounded-[28px] border border-black/5 bg-white p-6 shadow-[0_18px_60px_rgba(31,47,37,.07)] md:p-7">
            <div className="flex items-center gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-[#b8f238] text-[#111815]"><UploadIcon /></span>
              <h2 className="text-2xl font-black tracking-tight text-[#0d241d]">Enviar vídeo</h2>
              <FilmIcon className="h-5 w-5 text-[#5d6861]" />
            </div>

            <label htmlFor="video-upload" className="mt-6 block cursor-pointer rounded-2xl border border-dashed border-black/15 bg-[#fbfcfa] px-5 py-6 text-center transition hover:border-[#8fbd22] hover:bg-[#f8fce9]">
              <input id="video-upload" type="file" accept="video/mp4,video/quicktime,video/webm,video/mpeg,.m4v" onChange={(event) => setFile(event.target.files?.[0] || null)} className="sr-only" />
              <div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-[#eff2ed] text-[#778078]"><UploadIcon className="h-5 w-5" /></div>
              <div className="mt-3 text-sm font-bold text-[#505a54]">Arraste e solte seu vídeo aqui • até 500 MB</div>
              <span className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#b8f238] px-5 py-3 text-sm font-black text-[#111815]"><FolderIcon /> Escolher arquivo</span>
              {file && <div className="mx-auto mt-3 max-w-full truncate text-xs font-bold text-[#5f6a62]">{file.name}</div>}
            </label>

            <div className="mt-6">
              <label className="flex items-center gap-2 text-xs font-black uppercase tracking-[.14em] text-[#24302a]">Preset de IA <FilmIcon className="h-4 w-4 text-[#67716b]" /></label>
              <select value={preset} onChange={(event) => setPreset(event.target.value)} className="mt-3 w-full rounded-xl border border-black/10 bg-[#fbfcf9] px-4 py-3.5 text-sm font-bold outline-none focus:border-[#91c51d]">
                {(presets.length ? presets : [{ id: "tiktok_shop_sales", label: "TikTok Shop Vendas", description: "", target: "" }]).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
              <p className="mt-2 text-xs leading-5 text-[#7a847d]">{presets.find((item) => item.id === preset)?.description || "Ritmo e acabamento otimizados para vídeo vertical de venda."}</p>
            </div>

            <label className="mt-5 flex items-start gap-3 rounded-xl bg-[#f7f9f4] p-3 text-xs leading-5 text-[#68736b]">
              <input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)} className="mt-1 accent-[#75a900]" />
              Confirmo que sou proprietário do vídeo ou tenho autorização para editar e publicar.
            </label>

            <button onClick={upload} disabled={busy || !file} className="mt-5 w-full rounded-xl bg-[#111815] px-5 py-3.5 text-sm font-black text-white transition hover:-translate-y-0.5 disabled:translate-y-0 disabled:opacity-40">{busy ? "Processando..." : "Anexar vídeo"}</button>
            {project && <button onClick={autoEdit} disabled={busy || workingStatuses.has(project.status)} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-[#b8f238] px-5 py-3.5 text-sm font-black text-[#111815] transition hover:-translate-y-0.5 disabled:translate-y-0 disabled:opacity-40"><SparklesIcon /> Auto-Edit IA</button>}
          </div>

          <div className="flex min-h-[520px] flex-col rounded-[28px] bg-[#0d2b22] p-6 text-white shadow-[0_18px_60px_rgba(13,43,34,.18)] md:p-7">
            <div className="flex items-start justify-between gap-4">
              <div>
                <span className="inline-flex rounded-sm bg-[#b8f238] px-2 py-1 text-[10px] font-black uppercase tracking-[.15em] text-[#0d241d]">Processamento</span>
                <h2 className="mt-2 text-2xl font-black text-[#b8f238]">{project ? statusLabels[project.status] || project.status : "Aguardando vídeo"}</h2>
              </div>
              <div className="flex items-center gap-3 text-white/85">
                <FilmIcon className="h-5 w-5" /><ScissorsIcon className="h-5 w-5" /><TimelineIcon className="h-5 w-5" /><SparklesIcon className="h-5 w-5" />
              </div>
            </div>

            <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/12"><div className="h-full rounded-full bg-[#b8f238] transition-all" style={{ width: `${project?.progress || 0}%` }} /></div>

            {!project ? (
              <div className="mt-8 grid min-h-[160px] place-items-center rounded-2xl border border-white/10 bg-white/[.04] p-8 text-center text-sm text-white/58"><span className="inline-flex items-center gap-3"><FilmIcon className="h-5 w-5" /> O vídeo anexado aparecerá aqui para iniciar o Auto-Edit IA.</span></div>
            ) : (
              <div className="mt-6 space-y-4">
                <div className="rounded-2xl bg-white/10 p-4 text-sm"><div className="text-white/50">Arquivo</div><div className="mt-1 break-all font-black">{project.original_filename}</div></div>
                {project.error && <div className="rounded-2xl border border-red-400/30 bg-red-400/10 p-4 text-sm font-bold text-red-100">{project.error}</div>}
                {project.preview_url && <video controls playsInline src={`${API_URL}${project.preview_url}`} className="max-h-[440px] w-full rounded-2xl bg-black object-contain" />}
                {project.analysis && <>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-xl bg-white/10 p-3"><div className="text-[10px] text-white/50">Original</div><div className="mt-1 text-sm font-black">{Math.round(project.analysis.source_duration || 0)}s</div></div>
                    <div className="rounded-xl bg-white/10 p-3"><div className="text-[10px] text-white/50">Editado</div><div className="mt-1 text-sm font-black">{Math.round(project.analysis.edited_duration || 0)}s</div></div>
                    <div className="rounded-xl bg-white/10 p-3"><div className="text-[10px] text-white/50">Removido</div><div className="mt-1 text-sm font-black">{Math.round(project.analysis.removed_seconds || 0)}s</div></div>
                  </div>
                  {(project.analysis.auto_reframe || project.analysis.sound_design || project.analysis.broll) && <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="text-[10px] font-black uppercase tracking-[.15em] text-[#b8f238]">Acabamento IA</div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-xl bg-white/10 p-3"><div className="text-white/50">Auto-reframe</div><div className="mt-1 font-black">9:16 • rosto/ação</div></div>
                      <div className="rounded-xl bg-white/10 p-3"><div className="text-white/50">Sound design</div><div className="mt-1 font-black">{project.analysis.sound_design?.mood || "automático"}</div></div>
                      <div className="rounded-xl bg-white/10 p-3"><div className="text-white/50">B-roll contextual</div><div className="mt-1 font-black">{project.analysis.broll?.items || 0} inserções</div></div>
                      <div className="rounded-xl bg-white/10 p-3"><div className="text-white/50">Ganchos A/B</div><div className="mt-1 font-black">{hookVariants.length} versões</div></div>
                    </div>
                  </div>}
                </>}
                {hookVariants.length > 0 && <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="text-[10px] font-black uppercase tracking-[.15em] text-[#b8f238]">Variações de gancho • 3 segundos</div>
                  <div className="mt-3 space-y-2">{hookVariants.map((item) => <a key={item.variant} href={`${API_URL}${item.media_url}`} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-3 rounded-xl bg-white/10 p-3 text-xs transition hover:bg-white/15"><span><strong>Versão {item.variant}</strong><span className="ml-2 text-white/60">{item.text}</span></span><span className="font-black text-[#b8f238]">Abrir</span></a>)}</div>
                </div>}
                {(project.status === "ready" || project.status === "exported") && <button onClick={exportTikTok} disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-3.5 text-sm font-black text-[#111815] disabled:opacity-40"><TikTokIcon /> Exportar para TikTok Shop</button>}
                {project.export_url && <a href={`${API_URL}${project.export_url}`} className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#b8f238] px-5 py-3.5 text-center text-sm font-black text-[#111815]" download><TikTokIcon /> Baixar MP4 TikTok Shop</a>}
              </div>
            )}

            <div className="mt-auto pt-7">
              <div className="grid grid-cols-5 gap-2 border-t border-white/10 pt-5 text-center text-[10px] text-white/68">
                <div className="grid justify-items-center gap-2"><BrainIcon className="h-5 w-5"/><span>Análise IA</span></div>
                <div className="grid justify-items-center gap-2"><ScissorsIcon className="h-5 w-5"/><span>Edição</span></div>
                <div className="grid justify-items-center gap-2"><TimelineIcon className="h-5 w-5"/><span>Timeline</span></div>
                <div className="grid justify-items-center gap-2"><CaptionsIcon className="h-5 w-5"/><span>Legendas</span></div>
                <div className="grid justify-items-center gap-2"><SparklesIcon className="h-5 w-5"/><span>Finalização</span></div>
              </div>
            </div>
          </div>
        </div>

        {timeline && videoItems.length > 0 && <section className="mt-6 rounded-[28px] border border-black/5 bg-white p-6 shadow-sm md:p-7">
          <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
            <div><span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[.17em] text-[#75a900]"><TimelineIcon /> Timeline editável</span><h2 className="mt-1 text-2xl font-black">Cortes gerados pela IA</h2><p className="mt-2 text-xs text-[#707b73]">Desative um trecho e salve. O backend renderiza novamente preservando trilhas separadas.</p></div>
            <button onClick={saveTimeline} disabled={busy} className="rounded-xl bg-[#111815] px-4 py-2.5 text-sm font-black text-white disabled:opacity-40">Salvar e renderizar</button>
          </div>
          <div className="mt-5 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{videoItems.map((item, index) => <button key={item.id} onClick={() => toggleClip(item.id)} className={`rounded-2xl border p-4 text-left transition ${item.enabled === false ? "border-black/5 bg-[#f4f5f2] opacity-50" : "border-[#dceab9] bg-[#f8fce9]"}`}><div className="flex items-center justify-between gap-3"><span className="text-xs font-black">Corte {index + 1}</span><span className="text-[10px] font-black uppercase tracking-[.12em] text-[#5d8500]">{item.enabled === false ? "Desativado" : "Ativo"}</span></div><div className="mt-2 text-xs text-[#69736c]">Fonte {item.source_in.toFixed(1)}s → {item.source_out.toFixed(1)}s</div></button>)}</div>
        </section>}
      </section>
    </main>
  );
}
