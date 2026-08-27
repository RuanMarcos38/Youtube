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
  custom_music_original_name?: string | null;
  edit_options?: Record<string, unknown>;
  analysis?: {
    source_duration?: number;
    edited_duration?: number;
    removed_seconds?: number;
    keywords?: string[];
    notes?: string[];
    quality?: Record<string, string | number>;
    auto_reframe?: { enabled?: boolean; mode?: string; tracked_shots?: number; total_shots?: number; aspect_ratio?: string };
    sound_design?: { enabled?: boolean; mood?: string; music_source?: string; music_volume?: number; cut_sync_points?: number; voice_target_lufs?: number; ducking?: boolean };
    captions?: { enabled?: boolean; style?: string; micro_segments?: number; animated?: boolean; safe_zone?: boolean };
    professional_finish?: { enabled?: boolean; edit_intensity?: string; beat_sync?: boolean; voice_cleanup?: boolean; dynamic_punch_in?: boolean; color_grade?: string };
    broll?: { enabled?: boolean; strategy?: string; items?: number; concepts?: string[]; rights?: string };
    hook_variations?: HookVariant[];
    social_formats?: Record<string, string>;
  };
};

const DEFAULT_PRESETS: Preset[] = [
  { id: "tiktok_shop_sales", label: "TikTok Shop Vendas", description: "Ritmo rápido, legenda forte e enquadramento vertical para venda.", target: "TikTok Shop / Social Commerce" },
  { id: "ugc_sales", label: "UGC Conversão", description: "Edição natural, direta e focada na fala.", target: "Social Commerce" },
  { id: "cinematic_product", label: "Produto Cinematográfico", description: "Cortes elegantes, grade visual, áudio tratado e legendas discretas.", target: "Produto / Brand" },
  { id: "fast_retention", label: "Retenção Máxima", description: "Jump cuts, punch-ins e legendas de alto contraste para retenção.", target: "Short-form" },
];

const workingStatuses = new Set(["queued", "analyzing", "transcribing", "ai_editing", "rendering", "export_queued", "exporting"]);
const statusLabels: Record<string, string> = {
  uploaded: "Vídeo anexado",
  queued: "Na fila",
  analyzing: "Analisando vídeo e áudio",
  transcribing: "Transcrevendo fala",
  ai_editing: "Direção criativa por IA",
  rendering: "Finalização profissional",
  ready: "Pronto para publicar",
  export_queued: "Exportação na fila",
  exporting: "Preparando exportação",
  exported: "Exportado",
  failed: "Falha no processamento",
};

function TikTokIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M14.7 3.2c.5 2.4 1.8 3.8 4.1 4.4v3.1a9 9 0 0 1-4.1-1.2v5.6a5.8 5.8 0 1 1-5-5.7v3.2a2.7 2.7 0 1 0 1.8 2.5V3.2h3.2Z" fill="currentColor"/></svg>;
}
function YoutubeIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="2.2" y="5.2" width="19.6" height="13.6" rx="4" fill="#ef4444"/><path d="m10 9 5.2 3-5.2 3V9Z" fill="white"/></svg>;
}
function UploadIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M12 16V5m0 0L8 9m4-4 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/><path d="M5 14.5V19h14v-4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>;
}
function FilmIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2.5" stroke="currentColor" strokeWidth="1.7"/><path d="M7 4v16M17 4v16M3 9h4m10 0h4M3 15h4m10 0h4" stroke="currentColor" strokeWidth="1.4"/></svg>;
}
function ScissorsIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><circle cx="6" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.7"/><circle cx="6" cy="18" r="2.5" stroke="currentColor" strokeWidth="1.7"/><path d="m8 7.7 11 8.1M8 16.3l11-8.1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>;
}
function TimelineIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/><rect x="7" y="5" width="4" height="4" rx="1" fill="currentColor"/><rect x="13" y="10" width="4" height="4" rx="1" fill="currentColor"/><rect x="9" y="15" width="4" height="4" rx="1" fill="currentColor"/></svg>;
}
function CaptionsIcon({ className = "h-5 w-5" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.7"/><path d="M10 10.2c-.6-.6-1.2-.9-2-.9-1.6 0-2.7 1.2-2.7 2.7s1.1 2.7 2.7 2.7c.8 0 1.4-.3 2-.9M18.2 10.2c-.6-.6-1.2-.9-2-.9-1.6 0-2.7 1.2-2.7 2.7s1.1 2.7 2.7 2.7c.8 0 1.4-.3 2-.9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>;
}
function CheckIcon({ className = "h-4 w-4" }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true"><path d="m5 12.5 4.2 4.2L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
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
  const [presets, setPresets] = useState<Preset[]>(DEFAULT_PRESETS);
  const [preset, setPreset] = useState("tiktok_shop_sales");
  const [file, setFile] = useState<File | null>(null);
  const [musicFile, setMusicFile] = useState<File | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [captionsEnabled, setCaptionsEnabled] = useState(true);
  const [captionStyle, setCaptionStyle] = useState("auto");
  const [musicMode, setMusicMode] = useState("auto");
  const [musicMood, setMusicMood] = useState("auto");
  const [musicVolume, setMusicVolume] = useState(18);
  const [editIntensity, setEditIntensity] = useState("high");
  const [project, setProject] = useState<Project | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Preset[]>("/api/editor-ai/presets").then((data) => { if (data.length) setPresets(data); }).catch(() => setPresets(DEFAULT_PRESETS));
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
  const selectedPreset = presets.find((item) => item.id === preset) || DEFAULT_PRESETS[0];

  async function upload() {
    if (!file) return setError("Selecione um vídeo para anexar.");
    if (!rightsConfirmed) return setError("Confirme os direitos de uso do vídeo.");
    if (musicMode === "custom" && !musicFile) return setError("Selecione a música que será usada no vídeo.");
    setBusy(true); setError(""); setMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("preset", preset);
      form.append("target_platform", "all_social");
      form.append("rights_confirmed", "true");
      let created = await api<Project>("/api/editor-ai/upload", { method: "POST", body: form });
      if (musicMode === "custom" && musicFile) {
        const musicForm = new FormData();
        musicForm.append("file", musicFile);
        created = await api<Project>(`/api/editor-ai/projects/${created.id}/music`, { method: "POST", body: musicForm });
      }
      setProject(created);
      setTimeline(null);
      setMessage("Material anexado. A IA está pronta para aplicar o acabamento profissional configurado.");
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao anexar material."); }
    finally { setBusy(false); }
  }

  async function autoEdit() {
    if (!project) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const queued = await api<Project>(`/api/editor-ai/projects/${project.id}/auto-edit`, {
        method: "POST",
        body: JSON.stringify({
          preset,
          captions_enabled: captionsEnabled,
          caption_style: captionStyle,
          music_mode: musicMode,
          music_mood: musicMood,
          music_volume: musicVolume / 100,
          edit_intensity: editIntensity,
          auto_reframe: true,
          hook_variants: true,
        }),
      });
      setProject(queued);
      setMessage("Edição profissional iniciada: cortes, legendas, reenquadramento, áudio, ritmo e finalização serão feitos automaticamente.");
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao iniciar a edição automática."); }
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
      setProject(queued); setMessage("Timeline salva. Uma nova finalização profissional foi iniciada.");
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao salvar timeline."); }
    finally { setBusy(false); }
  }

  async function exportFinal() {
    if (!project) return;
    setBusy(true); setError("");
    try {
      const queued = await api<Project>(`/api/editor-ai/projects/${project.id}/export/tiktok-shop`, { method: "POST" });
      setProject(queued); setMessage("Exportação final iniciada para TikTok, Reels e Shorts.");
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao exportar."); }
    finally { setBusy(false); }
  }

  const stages = [
    { label: "Análise", icon: FilmIcon },
    { label: "Cortes", icon: ScissorsIcon },
    { label: "Timeline", icon: TimelineIcon },
    { label: "Legendas", icon: CaptionsIcon },
    { label: "Finalização", icon: CheckIcon },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] pb-24 text-[#17202a] xl:pb-10">
      <header className="sticky top-0 z-40 border-b border-[#e4e7ec] bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-4 px-5 md:px-8">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-[#b8f238] text-[#111815] shadow-[0_10px_24px_rgba(184,255,32,.22)]"><FilmIcon className="h-5 w-5" /></div>
            <div><div className="text-sm font-semibold tracking-[-.01em] text-[#101828]">ShortsFlow AI</div><div className="text-[10px] font-semibold uppercase tracking-[.16em] text-[#667085]">Editor de vídeo</div></div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-md border border-[#e4e7ec] bg-white px-2.5 py-1.5 text-[11px] text-[#667085] sm:inline-flex"><TikTokIcon /> TikTok</span>
            <span className="hidden items-center gap-1.5 rounded-md border border-[#e4e7ec] bg-white px-2.5 py-1.5 text-[11px] text-[#667085] sm:inline-flex"><YoutubeIcon /> YouTube</span>
            <a href="/" className="rounded-lg border border-[#d0d5dd] bg-white px-3.5 py-2 text-xs font-semibold text-[#344054] shadow-sm hover:bg-[#f9fafb]">Voltar ao painel</a>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-[1440px] px-5 py-7 md:px-8">
        <div className="mb-7 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div>
            <div className="text-xs font-medium text-[#147d72]">Produção de vídeo</div>
            <h1 className="mt-1 text-3xl font-semibold tracking-[-.035em] text-[#101828] md:text-[36px]">Editor automático</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#667085]">A IA faz a edição completa: seleção de cortes, ritmo, punch-ins, reenquadramento, legendas, voz, música, mixagem e acabamento vertical pronto para publicar.</p>
          </div>
          <div className="flex flex-wrap gap-2 text-[11px] text-[#475467]">
            <span className="rounded-md border border-[#e4e7ec] bg-white px-2.5 py-1.5">MP4 · MOV · WEBM</span>
            <span className="rounded-md border border-[#e4e7ec] bg-white px-2.5 py-1.5">Até 500 MB</span>
            <span className="rounded-md border border-[#e4e7ec] bg-white px-2.5 py-1.5">TikTok · Reels · Shorts</span>
          </div>
        </div>

        {error && <div className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div>}
        {message && <div className="mb-5 rounded-lg border border-[#b7d8d3] bg-[#e8f3f1] px-4 py-3 text-sm font-medium text-[#10665e]">{message}</div>}

        <div className="grid gap-5 lg:grid-cols-[420px_minmax(0,1fr)]">
          <section className="rounded-xl border border-[#e4e7ec] bg-white shadow-sm">
            <div className="border-b border-[#e4e7ec] px-5 py-4"><h2 className="text-sm font-semibold text-[#101828]">Novo projeto</h2><p className="mt-1 text-xs text-[#667085]">Configure o material e deixe a IA finalizar o vídeo.</p></div>
            <div className="p-5">
              <label htmlFor="video-upload" className="block cursor-pointer rounded-lg border border-dashed border-[#cfd5dc] bg-[#fafbfc] p-5 transition hover:border-[#88bdb7] hover:bg-[#f6fbfa]">
                <input id="video-upload" type="file" accept="video/mp4,video/quicktime,video/webm,video/mpeg,.m4v" onChange={(event) => setFile(event.target.files?.[0] || null)} className="sr-only" />
                <div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[#e4e7ec] bg-white text-[#475467]"><UploadIcon /></span><div className="min-w-0"><div className="text-sm font-semibold text-[#344054]">Selecionar vídeo</div><div className="mt-1 text-xs leading-5 text-[#667085]">Arraste e solte ou clique para procurar no computador.</div>{file && <div className="mt-2 max-w-[280px] truncate text-xs font-medium text-[#147d72]">{file.name}</div>}</div></div>
              </label>

              <div className="mt-5">
                <label className="text-xs font-medium text-[#344054]">Perfil de edição</label>
                <select value={preset} onChange={(event) => setPreset(event.target.value)} className="mt-2 w-full rounded-lg border border-[#d0d5dd] bg-white px-3 py-2.5 text-sm text-[#344054] shadow-sm outline-none focus:border-[#8abdb7]">{presets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
                <p className="mt-2 text-xs leading-5 text-[#667085]">{selectedPreset.description}</p>
              </div>

              <details className="mt-5 rounded-lg border border-[#e4e7ec] bg-[#fafbfc]" open>
                <summary className="cursor-pointer px-4 py-3 text-xs font-semibold text-[#344054]">Acabamento IA · automático</summary>
                <div className="space-y-4 border-t border-[#e4e7ec] p-4">
                  <div className="flex items-center justify-between gap-4"><div><div className="text-xs font-medium text-[#344054]">Legendas automáticas</div><div className="mt-0.5 text-[11px] text-[#667085]">Frases curtas, animação e palavra-chave em destaque.</div></div><input type="checkbox" checked={captionsEnabled} onChange={(event) => setCaptionsEnabled(event.target.checked)} className="h-4 w-4 accent-[#147d72]" /></div>
                  {captionsEnabled && <div><label className="text-[11px] font-medium text-[#475467]">Estilo da legenda</label><select value={captionStyle} onChange={(event) => setCaptionStyle(event.target.value)} className="mt-1.5 w-full rounded-lg border border-[#d0d5dd] bg-white px-3 py-2 text-xs"><option value="auto">IA decide pelo perfil</option><option value="impact">Impacto / Performance</option><option value="ugc">UGC / Natural</option><option value="cinematic">Cinematográfica</option></select></div>}
                  <div><label className="text-[11px] font-medium text-[#475467]">Música</label><select value={musicMode} onChange={(event) => setMusicMode(event.target.value)} className="mt-1.5 w-full rounded-lg border border-[#d0d5dd] bg-white px-3 py-2 text-xs"><option value="auto">Trilha automática original</option><option value="custom">Usar minha música</option><option value="none">Sem música</option></select></div>
                  {musicMode === "custom" && <label className="block cursor-pointer rounded-lg border border-dashed border-[#cfd5dc] bg-white p-3 text-xs text-[#475467]"><input type="file" accept="audio/mpeg,audio/wav,audio/mp4,audio/aac,audio/ogg,audio/flac,.m4a" onChange={(event) => setMusicFile(event.target.files?.[0] || null)} className="sr-only" /><strong>Selecionar música</strong>{musicFile && <span className="ml-2 text-[#147d72]">{musicFile.name}</span>}</label>}
                  {musicMode !== "none" && <><div><label className="text-[11px] font-medium text-[#475467]">Clima da trilha</label><select value={musicMood} onChange={(event) => setMusicMood(event.target.value)} className="mt-1.5 w-full rounded-lg border border-[#d0d5dd] bg-white px-3 py-2 text-xs"><option value="auto">IA decide</option><option value="energetic">Energética</option><option value="confident">Confiante</option><option value="elegant">Elegante</option><option value="natural">Natural</option></select></div><div><div className="flex justify-between text-[11px] font-medium text-[#475467]"><span>Volume da música</span><span>{musicVolume}%</span></div><input type="range" min="5" max="35" value={musicVolume} onChange={(event) => setMusicVolume(Number(event.target.value))} className="mt-2 w-full accent-[#147d72]" /></div></>}
                  <div><label className="text-[11px] font-medium text-[#475467]">Intensidade da edição</label><select value={editIntensity} onChange={(event) => setEditIntensity(event.target.value)} className="mt-1.5 w-full rounded-lg border border-[#d0d5dd] bg-white px-3 py-2 text-xs"><option value="balanced">Equilibrada</option><option value="high">Alta performance</option><option value="maximum">Máxima retenção</option></select></div>
                  <p className="text-[10px] leading-4 text-[#667085]">Referência de fluxo: corte automático por fala/ritmo, beat sync, legendas automáticas e refinamento de timeline, mantendo a identidade do ShortsFlow.</p>
                </div>
              </details>

              <div className="mt-5 border-t border-[#eef0f2] pt-4"><label className="flex items-start gap-3 text-xs leading-5 text-[#667085]"><input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#147d72]" /><span>Confirmo que sou proprietário dos materiais ou tenho autorização para editar e publicar.</span></label></div>

              <button onClick={upload} disabled={busy || !file} className="mt-5 w-full rounded-lg bg-[#101828] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#1d2939] disabled:cursor-not-allowed disabled:opacity-40">{busy ? "Processando..." : "Anexar vídeo"}</button>
              {project && <button onClick={autoEdit} disabled={busy || workingStatuses.has(project.status)} className="mt-2.5 w-full rounded-lg bg-[#147d72] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#10665e] disabled:cursor-not-allowed disabled:opacity-40">Iniciar edição profissional com IA</button>}
            </div>
          </section>

          <section className="overflow-hidden rounded-xl border border-[#e4e7ec] bg-white shadow-sm">
            <div className="flex flex-col gap-3 border-b border-[#e4e7ec] px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="text-[11px] font-medium text-[#667085]">Status do projeto</div><h2 className="mt-0.5 text-base font-semibold text-[#101828]">{project ? statusLabels[project.status] || project.status : "Aguardando arquivo"}</h2></div>{project && <span className="inline-flex self-start rounded-md bg-[#f2f4f7] px-2.5 py-1.5 text-xs font-semibold text-[#344054] sm:self-auto">{project.progress || 0}%</span>}</div>
            <div className="px-5 pt-5"><div className="h-1.5 overflow-hidden rounded-full bg-[#eef2f6]"><div className="h-full rounded-full bg-[#147d72] transition-all" style={{ width: `${project?.progress || 0}%` }} /></div></div>

            {!project ? <div className="p-5"><div className="grid min-h-[330px] place-items-center rounded-lg border border-[#e4e7ec] bg-[#f8fafc] p-8 text-center"><div><div className="mx-auto grid h-12 w-12 place-items-center rounded-lg border border-[#e4e7ec] bg-white text-[#667085]"><FilmIcon className="h-6 w-6" /></div><div className="mt-4 text-sm font-semibold text-[#344054]">Nenhum vídeo carregado</div><p className="mx-auto mt-2 max-w-sm text-xs leading-5 text-[#667085]">Depois do upload, a prévia, o progresso e as opções de exportação aparecem aqui.</p></div></div></div> : (
              <div className="space-y-4 p-5">
                <div className="flex items-center justify-between gap-4 rounded-lg border border-[#e4e7ec] bg-[#fafbfc] px-4 py-3"><div className="min-w-0"><div className="text-[11px] text-[#667085]">Arquivo</div><div className="mt-0.5 truncate text-sm font-medium text-[#344054]">{project.original_filename}</div></div><span className="shrink-0 rounded-md bg-white px-2 py-1 text-[10px] font-medium text-[#667085] shadow-sm">{selectedPreset.label}</span></div>
                {project.error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">{project.error}</div>}
                {project.preview_url && <div className="overflow-hidden rounded-lg border border-[#e4e7ec] bg-[#101828]"><video controls playsInline src={`${API_URL}${project.preview_url}`} className="max-h-[500px] w-full object-contain" /></div>}

                {project.analysis && <>
                  <div className="grid grid-cols-3 gap-3"><div className="rounded-lg border border-[#e4e7ec] p-3"><div className="text-[10px] text-[#667085]">Original</div><div className="mt-1 text-base font-semibold text-[#101828]">{Math.round(project.analysis.source_duration || 0)}s</div></div><div className="rounded-lg border border-[#e4e7ec] p-3"><div className="text-[10px] text-[#667085]">Editado</div><div className="mt-1 text-base font-semibold text-[#101828]">{Math.round(project.analysis.edited_duration || 0)}s</div></div><div className="rounded-lg border border-[#e4e7ec] p-3"><div className="text-[10px] text-[#667085]">Removido</div><div className="mt-1 text-base font-semibold text-[#101828]">{Math.round(project.analysis.removed_seconds || 0)}s</div></div></div>
                  {(project.analysis.auto_reframe || project.analysis.sound_design || project.analysis.professional_finish) && <div className="rounded-lg border border-[#e4e7ec]"><div className="border-b border-[#eef0f2] px-4 py-3 text-xs font-semibold text-[#344054]">Acabamento profissional aplicado</div><div className="grid grid-cols-2 gap-px bg-[#eef0f2] text-xs"><div className="bg-white p-3"><div className="text-[#667085]">Reenquadramento</div><div className="mt-1 font-medium text-[#344054]">9:16 · rosto/ação</div></div><div className="bg-white p-3"><div className="text-[#667085]">Legendas</div><div className="mt-1 font-medium text-[#344054]">{project.analysis.captions?.enabled === false ? "desativadas" : project.analysis.captions?.style || "automáticas"}</div></div><div className="bg-white p-3"><div className="text-[#667085]">Música + voz</div><div className="mt-1 font-medium text-[#344054]">{project.analysis.sound_design?.enabled === false ? "sem música" : `${project.analysis.sound_design?.mood || "automática"} · ducking`}</div></div><div className="bg-white p-3"><div className="text-[#667085]">Ritmo</div><div className="mt-1 font-medium text-[#344054]">{project.analysis.professional_finish?.edit_intensity || "alta performance"}</div></div></div></div>}
                </>}

                {hookVariants.length > 0 && <div className="rounded-lg border border-[#e4e7ec] p-4"><div className="text-xs font-semibold text-[#344054]">Variações de gancho</div><div className="mt-3 divide-y divide-[#eef0f2]">{hookVariants.map((item) => <a key={item.variant} href={`${API_URL}${item.media_url}`} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-3 py-2.5 text-xs"><span className="min-w-0 truncate text-[#475467]"><strong className="mr-2 text-[#101828]">{item.variant}</strong>{item.text}</span><span className="shrink-0 font-semibold text-[#147d72]">Abrir</span></a>)}</div></div>}
                {(project.status === "ready" || project.status === "exported") && <button onClick={exportFinal} disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#101828] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"><TikTokIcon /> Exportar pronto para TikTok · Reels · Shorts</button>}
                {project.export_url && <a href={`${API_URL}${project.export_url}`} className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#147d72] bg-[#e8f3f1] px-4 py-2.5 text-center text-sm font-semibold text-[#10665e]" download>Baixar MP4 final</a>}
              </div>
            )}

            <div className="border-t border-[#e4e7ec] bg-[#fafbfc] px-5 py-4"><div className="grid grid-cols-5 gap-2">{stages.map(({ label, icon: Icon }, index) => <div key={label} className="flex flex-col items-center gap-1.5 text-center"><span className="grid h-7 w-7 place-items-center rounded-full border border-[#d0d5dd] bg-white text-[#667085]"><Icon className="h-3.5 w-3.5" /></span><span className="text-[9px] font-medium text-[#667085]">{index + 1}. {label}</span></div>)}</div></div>
          </section>
        </div>

        {timeline && videoItems.length > 0 && <section className="mt-5 rounded-xl border border-[#e4e7ec] bg-white shadow-sm"><div className="flex flex-col justify-between gap-3 border-b border-[#e4e7ec] px-5 py-4 md:flex-row md:items-center"><div><h2 className="text-sm font-semibold text-[#101828]">Timeline editável</h2><p className="mt-1 text-xs text-[#667085]">Ative ou desative trechos; a IA refaz o acabamento mantendo as configurações profissionais.</p></div><button onClick={saveTimeline} disabled={busy} className="rounded-lg bg-[#101828] px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-40">Salvar e renderizar</button></div><div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-3">{videoItems.map((item, index) => <button key={item.id} onClick={() => toggleClip(item.id)} className={`rounded-lg border p-4 text-left transition ${item.enabled === false ? "border-[#e4e7ec] bg-[#f9fafb] opacity-55" : "border-[#b7d8d3] bg-[#f6fbfa]"}`}><div className="flex items-center justify-between gap-3"><span className="text-xs font-semibold text-[#344054]">Corte {index + 1}</span><span className={`text-[10px] font-medium ${item.enabled === false ? "text-[#98a2b3]" : "text-[#147d72]"}`}>{item.enabled === false ? "Desativado" : "Ativo"}</span></div><div className="mt-2 text-xs text-[#667085]">{item.source_in.toFixed(1)}s → {item.source_out.toFixed(1)}s</div></button>)}</div></section>}
      </section>
    </main>
  );
}
