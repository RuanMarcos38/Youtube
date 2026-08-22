"use client";

import { useEffect, useMemo, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type EditorProject = {
  id: string;
  original_filename: string;
  preset: string;
  target_platform: string;
  status: string;
  progress: number;
  preview_url?: string | null;
  export_url?: string | null;
  created_at?: string;
  analysis?: {
    edited_duration?: number;
    removed_seconds?: number;
    creative_finish?: { mood?: string; hooks?: string[]; broll_items?: number };
  };
};

type Job = {
  id: number;
  status: string;
  progress: number;
  requested_clips: number;
  created_at: string;
  source_video: { title: string; thumbnail_url?: string };
  clips: Array<{ id: number; status: string; media_url: string; title: string }>;
};

const statusLabel: Record<string, string> = {
  uploaded: "Vídeo anexado",
  queued: "Na fila",
  analyzing: "Analisando",
  transcribing: "Transcrevendo",
  ai_editing: "Editando com IA",
  rendering: "Renderizando",
  ready: "Pronto para revisar",
  export_queued: "Exportação na fila",
  exporting: "Exportando",
  exported: "Exportado",
  failed: "Falhou",
  ready_for_review: "Pronto para revisar",
};

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { credentials: "include", cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

export default function ProjectsPage() {
  const [editorProjects, setEditorProjects] = useState<EditorProject[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [projectsData, jobsData] = await Promise.all([
        request<EditorProject[]>("/api/editor-ai/projects"),
        request<Job[]>("/api/jobs"),
      ]);
      setEditorProjects(projectsData);
      setJobs(jobsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar seus projetos.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  const totals = useMemo(() => ({
    editor: editorProjects.length,
    shorts: jobs.length,
    ready: editorProjects.filter((item) => ["ready", "exported"].includes(item.status)).length + jobs.filter((item) => item.status === "ready_for_review").length,
    exports: editorProjects.filter((item) => Boolean(item.export_url)).length,
  }), [editorProjects, jobs]);

  return (
    <main className="min-h-screen bg-[#f8faf5] pb-28 text-[#111815] xl:pb-10">
      <header className="border-b border-black/5 bg-white px-4 py-7 md:px-8">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <span className="text-[10px] font-black uppercase tracking-[.18em] text-[#75a900]">Central da plataforma</span>
            <h1 className="mt-2 text-3xl font-black tracking-tight md:text-4xl">Meus Projetos</h1>
            <p className="mt-2 text-sm text-[#68736b]">Todos os vídeos, Shorts, edições por IA e exports no mesmo ambiente.</p>
          </div>
          <div className="flex gap-2">
            <a href="/#configurar" className="rounded-xl border border-black/10 bg-white px-4 py-3 text-sm font-black">+ Criar Shorts</a>
            <a href="/editor-ia" className="rounded-xl bg-[#111815] px-4 py-3 text-sm font-black text-white">✦ Novo Editor IA</a>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-4 py-8 md:px-8">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[["Projetos IA", totals.editor], ["Jobs Shorts", totals.shorts], ["Prontos", totals.ready], ["Exports", totals.exports]].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl border border-black/5 bg-white p-5 shadow-sm">
              <div className="text-[10px] font-black uppercase tracking-[.14em] text-[#78827b]">{label}</div>
              <div className="mt-2 text-3xl font-black">{value}</div>
            </div>
          ))}
        </div>

        {error && <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-bold text-red-700">{error} — <a href="/" className="underline">voltar ao login</a></div>}
        {loading && <div className="mt-6 rounded-2xl border border-black/5 bg-white p-8 text-center text-sm font-bold">Carregando projetos...</div>}

        {!loading && !error && (
          <>
            <section className="mt-8">
              <div className="mb-4 flex items-end justify-between"><div><span className="text-[10px] font-black uppercase tracking-[.16em] text-[#75a900]">Editor IA</span><h2 className="mt-1 text-2xl font-black">Vídeos para TikTok Shop e Social Commerce</h2></div></div>
              {editorProjects.length === 0 ? (
                <div className="rounded-[24px] border border-dashed border-black/10 bg-white p-10 text-center"><p className="text-sm text-[#6e7971]">Nenhum projeto de Editor IA ainda.</p><a href="/editor-ia" className="mt-4 inline-flex rounded-xl bg-[#b8f238] px-4 py-3 text-sm font-black">Criar primeiro projeto</a></div>
              ) : (
                <div className="grid gap-4 lg:grid-cols-2">
                  {editorProjects.map((item) => (
                    <article key={item.id} className="overflow-hidden rounded-[24px] border border-black/5 bg-white shadow-sm">
                      <div className="grid gap-4 p-5 md:grid-cols-[150px_1fr]">
                        <div className="grid min-h-48 place-items-center overflow-hidden rounded-2xl bg-[#0d241d] text-white">
                          {item.preview_url ? <video src={`${API_URL}${item.preview_url}`} controls playsInline className="h-full max-h-64 w-full object-contain" /> : <div className="text-center text-xs text-white/60">Preview<br/>{item.progress || 0}%</div>}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-start justify-between gap-3"><h3 className="truncate text-base font-black">{item.original_filename}</h3><span className="rounded-full bg-[#eef9d5] px-2.5 py-1 text-[10px] font-black text-[#5d8500]">{statusLabel[item.status] || item.status}</span></div>
                          <div className="mt-3 grid gap-2 text-xs text-[#68736b]"><div><strong>Preset:</strong> {item.preset}</div><div><strong>Destino:</strong> TikTok Shop / Reels / Shorts</div>{item.analysis?.creative_finish?.mood && <div><strong>Mood:</strong> {item.analysis.creative_finish.mood}</div>}</div>
                          {item.analysis?.creative_finish?.hooks?.length ? <div className="mt-3 rounded-xl bg-[#f8faf5] p-3 text-xs"><strong>Ganchos A/B/C:</strong><div className="mt-1 text-[#68736b]">{item.analysis.creative_finish.hooks.slice(0,3).join(" • ")}</div></div> : null}
                          <div className="mt-4 flex flex-wrap gap-2">
                            <a href="/editor-ia" className="rounded-lg border border-black/10 px-3 py-2 text-xs font-black">Abrir Editor IA</a>
                            {item.preview_url && <a href={`${API_URL}${item.preview_url}`} className="rounded-lg border border-black/10 px-3 py-2 text-xs font-black">Abrir preview</a>}
                            {item.export_url && <a href={`${API_URL}${item.export_url}`} download className="rounded-lg bg-[#b8f238] px-3 py-2 text-xs font-black">Baixar export</a>}
                          </div>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="mt-10">
              <div className="mb-4"><span className="text-[10px] font-black uppercase tracking-[.16em] text-[#75a900]">YouTube Shorts</span><h2 className="mt-1 text-2xl font-black">Processamentos e cortes</h2></div>
              {jobs.length === 0 ? <div className="rounded-[24px] border border-dashed border-black/10 bg-white p-10 text-center text-sm text-[#6e7971]">Nenhum job de Shorts ainda.</div> : (
                <div className="grid gap-3">
                  {jobs.map((job) => (
                    <article key={job.id} className="flex flex-col justify-between gap-4 rounded-2xl border border-black/5 bg-white p-5 shadow-sm md:flex-row md:items-center">
                      <div className="min-w-0"><div className="text-sm font-black">#{job.id} • {job.source_video.title}</div><div className="mt-1 text-xs text-[#6e7971]">{statusLabel[job.status] || job.status} • {job.progress}% • {job.clips.length}/{job.requested_clips} cortes</div></div>
                      <div className="flex gap-2"><a href="/#processamento" className="rounded-lg border border-black/10 px-3 py-2 text-xs font-black">Acompanhar</a><a href="/#cortes" className="rounded-lg bg-[#111815] px-3 py-2 text-xs font-black text-white">Revisar/Publicar</a></div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </section>
    </main>
  );
}
