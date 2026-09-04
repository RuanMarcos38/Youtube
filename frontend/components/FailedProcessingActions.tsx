"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { deleteJob, listJobs } from "@/lib/api";
import type { Job } from "@/lib/types";

function isProcessingSection() {
  if (typeof window === "undefined") return false;
  return window.location.hash.replace("#", "") === "processamento";
}

export default function FailedProcessingActions() {
  const [visible, setVisible] = useState(false);
  const [open, setOpen] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const failedJobs = useMemo(() => jobs.filter((job) => job.status === "failed"), [jobs]);

  const refresh = useCallback(async () => {
    try {
      const data = await listJobs();
      setJobs(data);
    } catch {
      setJobs([]);
    }
  }, []);

  useEffect(() => {
    const sync = () => {
      const nextVisible = isProcessingSection();
      setVisible(nextVisible);
      if (!nextVisible) setOpen(false);
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (!visible) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [refresh, visible]);

  async function removeFailedJob(job: Job) {
    const confirmed = window.confirm(
      `Excluir o processamento #${job.id} que falhou?\n\nEsta ação remove somente este processamento e seus arquivos temporários. O vídeo de origem, seu canal, login e demais configurações não serão alterados.`,
    );
    if (!confirmed) return;

    setDeletingId(job.id);
    setError("");
    try {
      await deleteJob(job.id);
      setJobs((current) => current.filter((item) => item.id !== job.id));
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir este processamento.");
    } finally {
      setDeletingId(null);
    }
  }

  if (!visible || failedJobs.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 z-[80] flex flex-col items-end gap-2">
      {open && (
        <div className="w-[min(92vw,420px)] overflow-hidden rounded-xl border border-[#e6e6e6] bg-white shadow-[0_18px_55px_rgba(17,17,17,.18)]">
          <div className="flex items-start justify-between gap-4 border-b border-[#ededed] px-4 py-3.5">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#ff0000]">Limpeza da fila</div>
              <h3 className="mt-1 text-sm font-semibold text-[#111]">Processamentos não concluídos</h3>
              <p className="mt-1 text-[11px] leading-4 text-[#777]">Exclua somente as tentativas que terminaram com falha.</p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-lg border border-[#e4e4e4] bg-white px-2.5 py-1.5 text-[11px] font-semibold text-[#555] hover:bg-[#f7f7f7]"
            >
              Fechar
            </button>
          </div>

          {error && <div className="m-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-medium leading-5 text-red-700">{error}</div>}

          <div className="max-h-[320px] divide-y divide-[#ededed] overflow-y-auto">
            {failedJobs.map((job) => (
              <div key={job.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="text-[10px] text-[#777]">Processamento #{job.id}</div>
                  <div className="mt-0.5 line-clamp-2 text-xs font-semibold leading-4 text-[#222]">{job.source_video.title}</div>
                </div>
                <button
                  type="button"
                  onClick={() => void removeFailedJob(job)}
                  disabled={deletingId !== null}
                  className="inline-flex flex-none items-center justify-center rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {deletingId === job.id ? "Excluindo..." : "Excluir"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-10 items-center justify-center rounded-lg border border-red-200 bg-white px-4 py-2.5 text-xs font-semibold text-red-700 shadow-[0_8px_24px_rgba(17,17,17,.12)] transition hover:bg-red-50"
        aria-expanded={open}
      >
        Excluir falhas ({failedJobs.length})
      </button>
    </div>
  );
}
