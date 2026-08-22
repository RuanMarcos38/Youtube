"use client";

import { useEffect, useMemo, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type Preset = {
  id: string;
  label: string;
  description: string;
  target: string;
};

type TimelineItem = {
  id: string;
  source: string;
  source_in: number;
  source_out: number;
  timeline_in: number;
  timeline_out: number;
  enabled?: boolean;
};

type TimelineTrack = {
  id: string;
  type: string;
  locked?: boolean;
  items: Array<TimelineItem | Record<string, unknown>>;
};

type Timeline = {
  version: number;
  duration: number;
  preset: string;
  canvas: { width: number; height: number; fps: number; aspect_ratio: string };
  tracks: TimelineTrack[];
};

type HookVariant = {
  variant: string;
  text: string;
  duration_seconds: number;
  media_url: string;
};

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

const workingStatuses = new Set([
  "queued",
  "analyzing",
  "transcribing",
  "ai_editing",
  "rendering",
  "export_queued",
  "exporting",
]);

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

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {}
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
    api<Preset[]>("/api/editor-ai/presets")
      .then(setPresets)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar presets."));
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

  useEffect(() => {
    if (project?.timeline) setTimeline(project.timeline);
  }, [project?.timeline]);

  const videoItems = useMemo(() => {
    const track = timeline?.tracks?.find((item) => item.type === "video");
    return (track?.items || []) as TimelineItem[];
  }, [timeline]);

  const hookVariants = project?.hook_variants || project?.analysis?.hook_variations || [];

  async function upload() {
    if (!file) {
      setError("Selecione um vídeo para anexar.");
      return;
    }
    if (!rightsConfirmed) {
      setError("Confirme os direitos de uso do vídeo.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("preset", preset);
      form.append("target_platform", "tiktok_shop");
      form.append("rights_confirmed", "true");
      const created = await api<Project>("/api/editor-ai/upload", { method: "POST", body: form });
      setProject(created);
      setTimeline(null);
      setMessage("Vídeo anexado. Agora acione o Auto-Edit IA.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao anexar vídeo.");
    } finally {
      setBusy(false);
    }
  }

  async function autoEdit() {
    if (!project) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const queued = await api<Project>(`/api/editor-ai/projects/${project.id}/auto-edit`, {
        method: "POST",
        body: JSON.stringify({ preset }),
      });
      setProject(queued);
      setMessage("Auto-Edit IA iniciado. O vídeo será entregue pronto e com timeline editável.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar Auto-Edit IA.");
    } finally {
      setBusy(false);
    }
  }

  function toggleClip(id: string) {
    if (!timeline) return;
    const next: Timeline = {
      ...timeline,
      tracks: timeline.tracks.map((track) =>
        track.type !== "video"
          ? track
          : {
              ...track,
              items: track.items.map((raw) => {
                const item = raw as TimelineItem;
                return item.id === id ? { ...item, enabled: item.enabled === false } : item;
              }),
            },
      ),
    };
    setTimeline(next);
  }

  async function saveTimeline() {
    if (!project || !timeline) return;
    setBusy(true);
    setError("");
    try {
      const queued = await api<Project>(`/api/editor-ai/projects/${project.id}/timeline`, {
        method: "PUT",
        body: JSON.stringify({ timeline }),
      });
      setProject(queued);
      setMessage("Ajustes salvos. A IA está renderizando novamente sem destruir as camadas.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar timeline.");
    } finally {
      setBusy(false);
    }
  }

  async function exportTikTok() {
    if (!project) return;
    setBusy(true);
    setError("");
    try {
      const queued = await api<Project>(`/api/editor-ai/projects/${project.id}/export/tiktok-shop`, {
        method: "POST",
      });
      setProject(queued);
      setMessage("Exportação TikTok Shop iniciada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao exportar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f8faf5] text-[#111815]">
      <header className="sticky top-0 z-40 border-b border-black/5 bg-[#f8faf5]/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 md:px-8">
          <div>
            <div className="text-lg font-black tracking-tight">ShortsFlow AI</div>
            <div className="text-[10px] font-bold uppercase tracking-[.18em] text-[#6e7b73]">
              Auto-Edit IA • TikTok Shop
            </div>
          </div>
          <a href="/" className="rounded-xl border border-black/10 bg-white px-4 py-2.5 text-sm font-black shadow-sm">
            Voltar ao painel
          </a>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-4 py-10 md:px-8">
        <div className="mb-8 max-w-3xl">
          <span className="inline-flex rounded-md bg-[#eaf8c8] px-3 py-1.5 text-[11px] font-black uppercase tracking-[.16em] text-[#547300]">
            Edição automatizada por inteligência artificial
          </span>
          <h1 className="mt-5 text-4xl font-black tracking-[-.035em] md:text-5xl">
            Anexe seu vídeo e deixe a IA montar a edição para vendas.
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-[#667169]">
            A ferramenta remove pausas e erros detectáveis, ajusta ritmo, cria legendas cinematográficas, faz auto-reframe 9:16,
            adiciona sound design, B-roll contextual derivado do seu próprio material e gera 3 ganchos para testes A/B.
          </p>
        </div>

        {error && <div className="mb-5 rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-700">{error}</div>}
        {message && <div className="mb-5 rounded-2xl border border-[#b8f238] bg-[#f2fbdc] px-5 py-4 text-sm font-bold text-[#466400]">{message}</div>}

        <div className="grid gap-5 lg:grid-cols-[.9fr_1.1fr]">
          <div className="rounded-[28px] border border-black/5 bg-white p-6 shadow-sm">
            <div className="mb-5">
              <span className="text-[10px] font-black uppercase tracking-[.17em] text-[#75a900]">Entrada</span>
              <h2 className="mt-1 text-xl font-black">Anexar vídeo</h2>
            </div>

            <label className="block rounded-2xl border border-dashed border-black/15 bg-[#fbfcfa] p-5">
              <div className="text-sm font-black">Arquivo bruto</div>
              <div className="mt-1 text-xs text-[#778078]">MP4, MOV, M4V, MPEG ou WEBM • até 500 MB</div>
              <input
                type="file"
                accept="video/mp4,video/quicktime,video/webm,video/mpeg,.m4v"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
                className="mt-4 block w-full text-sm"
              />
              {file && <div className="mt-3 text-xs font-bold text-[#5f6a62]">{file.name}</div>}
            </label>

            <div className="mt-5">
              <label className="text-xs font-black uppercase tracking-[.12em] text-[#68736b]">Preset de IA</label>
              <select
                value={preset}
                onChange={(event) => setPreset(event.target.value)}
                className="mt-2 w-full rounded-xl border border-black/10 bg-[#fbfcf9] px-4 py-3 text-sm font-bold outline-none"
              >
                {(presets.length ? presets : [{ id: "tiktok_shop_sales", label: "TikTok Shop Vendas", description: "", target: "" }]).map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
              <p className="mt-2 text-xs leading-5 text-[#7a847d]">
                {presets.find((item) => item.id === preset)?.description || "Ritmo e acabamento otimizados para vídeo vertical de venda."}
              </p>
            </div>

            <label className="mt-5 flex items-start gap-3 text-xs leading-5 text-[#68736b]">
              <input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)} className="mt-1" />
              Confirmo que sou proprietário do vídeo ou tenho autorização para editar e publicar.
            </label>

            <button
              onClick={upload}
              disabled={busy || !file}
              className="mt-5 w-full rounded-xl bg-[#111815] px-5 py-3.5 text-sm font-black text-white disabled:opacity-40"
            >
              {busy ? "Processando..." : "Anexar vídeo"}
            </button>

            {project && (
              <button
                onClick={autoEdit}
                disabled={busy || workingStatuses.has(project.status)}
                className="mt-3 w-full rounded-xl bg-[#b8f238] px-5 py-3.5 text-sm font-black text-[#111815] disabled:opacity-40"
              >
                ✦ Auto-Edit IA
              </button>
            )}
          </div>

          <div className="rounded-[28px] bg-[#0d241d] p-6 text-white shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <span className="text-[10px] font-black uppercase tracking-[.17em] text-[#b8f238]">Processamento</span>
                <h2 className="mt-1 text-xl font-black">{project ? statusLabels[project.status] || project.status : "Aguardando vídeo"}</h2>
              </div>
              {project && <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-black">{project.progress || 0}%</span>}
            </div>

            <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-[#b8f238] transition-all" style={{ width: `${project?.progress || 0}%` }} />
            </div>

            {!project ? (
              <div className="mt-8 rounded-2xl border border-white/10 bg-white/5 p-8 text-center text-sm text-white/60">
                O vídeo anexado aparecerá aqui para iniciar o Auto-Edit IA.
              </div>
            ) : (
              <div className="mt-6 space-y-4">
                <div className="rounded-2xl bg-white/10 p-4 text-sm">
                  <div className="text-white/50">Arquivo</div>
                  <div className="mt-1 font-black">{project.original_filename}</div>
                </div>

                {project.error && <div className="rounded-2xl border border-red-400/30 bg-red-400/10 p-4 text-sm font-bold text-red-100">{project.error}</div>}

                {project.preview_url && (
                  <video
                    controls
                    playsInline
                    src={`${API_URL}${project.preview_url}`}
                    className="max-h-[520px] w-full rounded-2xl bg-black object-contain"
                  />
                )}

                {project.analysis && (
                  <>
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-xl bg-white/10 p-3"><div className="text-[10px] text-white/50">Original</div><div className="mt-1 text-sm font-black">{Math.round(project.analysis.source_duration || 0)}s</div></div>
                      <div className="rounded-xl bg-white/10 p-3"><div className="text-[10px] text-white/50">Editado</div><div className="mt-1 text-sm font-black">{Math.round(project.analysis.edited_duration || 0)}s</div></div>
                      <div className="rounded-xl bg-white/10 p-3"><div className="text-[10px] text-white/50">Removido</div><div className="mt-1 text-sm font-black">{Math.round(project.analysis.removed_seconds || 0)}s</div></div>
                    </div>

                    {(project.analysis.auto_reframe || project.analysis.sound_design || project.analysis.broll) && (
                      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                        <div className="text-[10px] font-black uppercase tracking-[.15em] text-[#b8f238]">Acabamento IA</div>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                          <div className="rounded-xl bg-white/10 p-3"><div className="text-white/50">Auto-reframe</div><div className="mt-1 font-black">9:16 • rosto/ação</div></div>
                          <div className="rounded-xl bg-white/10 p-3"><div className="text-white/50">Sound design</div><div className="mt-1 font-black">{project.analysis.sound_design?.mood || "automático"}</div></div>
                          <div className="rounded-xl bg-white/10 p-3"><div className="text-white/50">B-roll contextual</div><div className="mt-1 font-black">{project.analysis.broll?.items || 0} inserções</div></div>
                          <div className="rounded-xl bg-white/10 p-3"><div className="text-white/50">Ganchos A/B</div><div className="mt-1 font-black">{hookVariants.length} versões</div></div>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {hookVariants.length > 0 && (
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="text-[10px] font-black uppercase tracking-[.15em] text-[#b8f238]">Variações de gancho • 3 segundos</div>
                    <div className="mt-3 space-y-2">
                      {hookVariants.map((item) => (
                        <a
                          key={item.variant}
                          href={`${API_URL}${item.media_url}`}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center justify-between gap-3 rounded-xl bg-white/10 p-3 text-xs transition hover:bg-white/15"
                        >
                          <span><strong>Versão {item.variant}</strong><span className="ml-2 text-white/60">{item.text}</span></span>
                          <span className="font-black text-[#b8f238]">Abrir</span>
                        </a>
                      ))}
                    </div>
                  </div>
                )}

                {project.status === "ready" || project.status === "exported" ? (
                  <button onClick={exportTikTok} disabled={busy} className="w-full rounded-xl bg-white px-5 py-3.5 text-sm font-black text-[#111815] disabled:opacity-40">
                    Exportar para TikTok Shop
                  </button>
                ) : null}

                {project.export_url && (
                  <a
                    href={`${API_URL}${project.export_url}`}
                    className="block w-full rounded-xl bg-[#b8f238] px-5 py-3.5 text-center text-sm font-black text-[#111815]"
                    download
                  >
                    Baixar MP4 TikTok Shop
                  </a>
                )}
              </div>
            )}
          </div>
        </div>

        {timeline && videoItems.length > 0 && (
          <section className="mt-6 rounded-[28px] border border-black/5 bg-white p-6 shadow-sm">
            <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
              <div>
                <span className="text-[10px] font-black uppercase tracking-[.17em] text-[#75a900]">Timeline editável</span>
                <h2 className="mt-1 text-2xl font-black">Cortes gerados pela IA</h2>
                <p className="mt-2 text-xs text-[#707b73]">Desative um trecho e salve. O backend renderiza novamente preservando trilhas separadas.</p>
              </div>
              <button onClick={saveTimeline} disabled={busy} className="rounded-xl bg-[#111815] px-4 py-2.5 text-sm font-black text-white disabled:opacity-40">
                Salvar e renderizar
              </button>
            </div>

            <div className="mt-5 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {videoItems.map((item, index) => (
                <button
                  key={item.id}
                  onClick={() => toggleClip(item.id)}
                  className={`rounded-2xl border p-4 text-left transition ${item.enabled === false ? "border-black/5 bg-[#f4f5f2] opacity-50" : "border-[#dceab9] bg-[#f8fce9]"}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs font-black">Corte {index + 1}</span>
                    <span className="text-[10px] font-black uppercase tracking-[.12em] text-[#5d8500]">{item.enabled === false ? "Desativado" : "Ativo"}</span>
                  </div>
                  <div className="mt-2 text-xs text-[#69736c]">
                    Fonte {item.source_in.toFixed(1)}s → {item.source_out.toFixed(1)}s
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
