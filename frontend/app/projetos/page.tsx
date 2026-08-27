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
  ai_editing: "Editando",
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

function StatusBadge({ status }: { status: string }) {
  const ready = ["ready", "exported", "ready_for_review"].includes(status);
  const failed = status === "failed";
  const cls = failed ? "border-red-200 bg-red-50 text-red-700" : ready ? "border-[#b7d8d3] bg-[#e8f3f1] text-[#10665e]" : "border-[#e4e7ec] bg-[#f9fafb] text-[#475467]";
  return <span className={`inline-flex rounded-md border px-2 py-1 text-[10px] font-medium ${cls}`}>{statusLabel[status] || status}</span>;
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
    <main className="min-h-screen bg-[#f4f6f8] pb-24 text-[#17202a] xl:pb-10">
      <header className="border-b border-[#e4e7ec] bg-white">
        <div className="mx-auto flex max-w-[1440px] flex-col justify-between gap-4 px-5 py-7 md:px-8 lg:flex-row lg:items-center">
          <div>
            <div className="text-xs font-medium text-[#147d72]">Área de trabalho</div>
            <h1 className="mt-1 text-3xl font-semibold tracking-[-.03em] text-[#101828]">Projetos</h1>
            <p className="mt-2 text-sm text-[#667085]">Acompanhe edições, Shorts, exportações e processamentos em um único lugar.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="/#configurar" className="rounded-lg border border-[#d0d5dd] bg-white px-3.5 py-2 text-xs font-semibold text-[#344054] shadow-sm hover:bg-[#f9fafb]">Criar Shorts</a>
            <a href="/editor-ia" className="rounded-lg bg-[#101828] px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-[#1d2939]">Novo projeto de vídeo</a>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-[1440px] px-5 py-7 md:px-8">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[["Editor de vídeo", totals.editor], ["Shorts", totals.shorts], ["Prontos", totals.ready], ["Exportações", totals.exports]].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl border border-[#e4e7ec] bg-white p-4 shadow-sm">
              <div className="text-xs text-[#667085]">{label}</div>
              <div className="mt-2 text-2xl font-semibold tracking-[-.02em] text-[#101828]">{value}</div>
            </div>
          ))}
        </div>

        {error && <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700">{error} — <a href="/" className="underline">voltar ao login</a></div>}
        {loading && <div className="mt-5 rounded-xl border border-[#e4e7ec] bg-white p-8 text-center text-sm text-[#667085]">Carregando projetos...</div>}

        {!loading && !error && <>
          <section className="mt-7 rounded-xl border border-[#e4e7ec] bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-[#e4e7ec] px-5 py-4">
              <div><h2 className="text-sm font-semibold text-[#101828]">Editor de vídeo</h2><p className="mt-1 text-xs text-[#667085]">Projetos para TikTok Shop, Reels e Shorts.</p></div>
              <a href="/editor-ia" className="text-xs font-semibold text-[#147d72]">Novo projeto</a>
            </div>

            {editorProjects.length === 0 ? (
              <div className="p-10 text-center"><p className="text-sm text-[#667085]">Nenhum projeto de vídeo criado ainda.</p><a href="/editor-ia" className="mt-4 inline-flex rounded-lg bg-[#101828] px-4 py-2.5 text-xs font-semibold text-white">Criar primeiro projeto</a></div>
            ) : (
              <div className="divide-y divide-[#eef0f2]">
                {editorProjects.map((item) => (
                  <article key={item.id} className="grid gap-4 p-5 lg:grid-cols-[132px_minmax(0,1fr)_auto] lg:items-center">
                    <div className="grid min-h-[96px] place-items-center overflow-hidden rounded-lg border border-[#e4e7ec] bg-[#101828] text-white">
                      {item.preview_url ? <video src={`${API_URL}${item.preview_url}`} controls playsInline className="h-full max-h-36 w-full object-contain" /> : <div className="text-center text-[10px] text-white/55">Prévia<br/>{item.progress || 0}%</div>}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2"><h3 className="max-w-full truncate text-sm font-semibold text-[#101828]">{item.original_filename}</h3><StatusBadge status={item.status} /></div>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#667085]"><span>Perfil: {item.preset}</span><span>Destino: TikTok / Reels / Shorts</span>{item.analysis?.creative_finish?.mood && <span>Clima: {item.analysis.creative_finish.mood}</span>}</div>
                      {item.analysis?.creative_finish?.hooks?.length ? <div className="mt-2 truncate text-xs text-[#667085]">Ganchos: {item.analysis.creative_finish.hooks.slice(0,3).join(" · ")}</div> : null}
                    </div>
                    <div className="flex flex-wrap gap-2 lg:justify-end">
                      <a href="/editor-ia" className="rounded-lg border border-[#d0d5dd] px-3 py-2 text-xs font-semibold text-[#344054]">Abrir editor</a>
                      {item.preview_url && <a href={`${API_URL}${item.preview_url}`} className="rounded-lg border border-[#d0d5dd] px-3 py-2 text-xs font-semibold text-[#344054]">Prévia</a>}
                      {item.export_url && <a href={`${API_URL}${item.export_url}`} download className="rounded-lg bg-[#147d72] px-3 py-2 text-xs font-semibold text-white">Baixar</a>}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="mt-5 rounded-xl border border-[#e4e7ec] bg-white shadow-sm">
            <div className="border-b border-[#e4e7ec] px-5 py-4"><h2 className="text-sm font-semibold text-[#101828]">YouTube Shorts</h2><p className="mt-1 text-xs text-[#667085]">Processamentos, cortes e status de publicação.</p></div>
            {jobs.length === 0 ? <div className="p-10 text-center text-sm text-[#667085]">Nenhum processamento de Shorts ainda.</div> : (
              <div className="divide-y divide-[#eef0f2]">
                {jobs.map((job) => (
                  <article key={job.id} className="flex flex-col justify-between gap-4 px-5 py-4 md:flex-row md:items-center">
                    <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><div className="truncate text-sm font-semibold text-[#101828]">#{job.id} · {job.source_video.title}</div><StatusBadge status={job.status} /></div><div className="mt-1 text-xs text-[#667085]">{job.progress}% · {job.clips.length}/{job.requested_clips} cortes</div></div>
                    <div className="flex gap-2"><a href="/#processamento" className="rounded-lg border border-[#d0d5dd] px-3 py-2 text-xs font-semibold text-[#344054]">Acompanhar</a><a href="/#cortes" className="rounded-lg bg-[#101828] px-3 py-2 text-xs font-semibold text-white">Revisar</a></div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>}
      </section>
    </main>
  );
}
