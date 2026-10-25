"use client";

import { useRef, useState } from "react";
import { uploadVideoJob } from "@/lib/api";
import type { Job } from "@/lib/types";

export default function VideoUploadPanel({ onQueued }: { onQueued: (job: Job) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [clips, setClips] = useState(3);
  const [rights, setRights] = useState(false);
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const inFlight = useRef(false);

  async function send() {
    if (inFlight.current || !file || !rights) return;
    if (file.size === 0 || file.size > 500 * 1024 * 1024) {
      setError("Selecione um vídeo com até 500 MB que não esteja vazio.");
      return;
    }
    inFlight.current = true;
    setSending(true);
    setProgress(0);
    setError("");
    try {
      const job = await uploadVideoJob(file, clips, rights, setProgress);
      onQueued(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível enviar o vídeo.");
    } finally {
      inFlight.current = false;
      setSending(false);
    }
  }

  return (
    <section className="sf-card mb-5 p-5" aria-labelledby="upload-video-title">
      <h3 id="upload-video-title" className="text-base font-semibold text-[#111]">Enviar vídeo original</h3>
      <p className="mt-2 text-sm leading-6 text-[#666]">Gere Shorts sem depender do download do YouTube. Após o envio terminar, o servidor continua a transcrição e os cortes mesmo com o computador desligado.</p>
      <fieldset disabled={sending} className="mt-4 grid gap-4 sm:grid-cols-[minmax(0,1fr)_180px]">
        <div>
          <label htmlFor="shorts-source-file" className="text-xs font-medium text-[#222]">Arquivo de vídeo</label>
          <input id="shorts-source-file" type="file" accept=".mp4,.mov,.mkv,.webm,.m4v" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(""); }} className="sf-input mt-2 block w-full min-w-0 p-3 text-sm" />
          <p className="mt-1 text-xs text-[#777]">MP4, MOV, MKV, WebM ou M4V · até 500 MB · com áudio</p>
        </div>
        <div>
          <label htmlFor="upload-clips" className="text-xs font-medium text-[#222]">Quantidade de Shorts</label>
          <select id="upload-clips" value={clips} onChange={(event) => setClips(Number(event.target.value))} className="sf-input mt-2 w-full p-3">
            {[1, 2, 3, 5, 10].map((count) => <option key={count} value={count}>{count}</option>)}
          </select>
        </div>
        <label className="flex items-start gap-3 text-xs leading-5 text-[#666] sm:col-span-2">
          <input type="checkbox" checked={rights} onChange={(event) => setRights(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#ff0000]" />
          <span>Confirmo que possuo direitos ou autorização para reutilizar este vídeo.</span>
        </label>
      </fieldset>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      {sending && <div role="status" aria-live="polite" className="mt-4 text-sm text-[#555]">
        <p>{progress < 100 ? `Enviando vídeo: ${progress}%` : "Envio recebido. Validando o vídeo e preparando a fila..."}</p>
        <progress value={progress} max={100} aria-label="Progresso do envio" className="mt-2 h-2 w-full accent-[#ff0000]" />
        <p className="mt-1 text-xs">Mantenha esta página aberta até a confirmação de que o processamento entrou na fila.</p>
      </div>}
      <button type="button" onClick={() => void send()} disabled={sending || !file || !rights} className="sf-button sf-button-youtube mt-4 disabled:opacity-40">{sending ? "Enviando..." : "Enviar e gerar Shorts"}</button>
    </section>
  );
}
