"use client";

import { useEffect, useState } from "react";
import { adminRunDiagnostics, authMe } from "@/lib/api";
import type { DiagnosticResult } from "@/lib/types";

export default function DiagnosticsAssistant() {
  const [allowed, setAllowed] = useState(false);
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DiagnosticResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    authMe()
      .then((user) => setAllowed(user.role === "superadmin"))
      .catch(() => setAllowed(false));
  }, []);

  async function run() {
    setRunning(true);
    setError("");
    try {
      setResult(await adminRunDiagnostics(true));
      setOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível executar o diagnóstico.");
      setOpen(true);
    } finally {
      setRunning(false);
    }
  }

  if (!allowed) return null;

  return (
    <div className="fixed bottom-5 right-5 z-[80] flex max-w-[calc(100vw-2.5rem)] flex-col items-end gap-2">
      {open && (
        <div className="max-h-[65vh] w-[min(430px,calc(100vw-2.5rem))] overflow-auto rounded-2xl border border-black/10 bg-white p-4 shadow-2xl">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[.14em] text-[#6f9700]">Assistente automático</div>
              <h3 className="mt-1 text-sm font-black">Diagnóstico de produção</h3>
            </div>
            <button onClick={() => setOpen(false)} className="rounded-lg border border-black/10 px-2 py-1 text-[10px] font-black">Fechar</button>
          </div>

          {error && <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-[11px] font-bold text-red-700">{error}</div>}

          {result && (
            <>
              <div className={`mt-3 rounded-xl p-3 text-xs font-black ${result.ok ? "bg-[#eaf8c8] text-[#4b6a00]" : "bg-amber-50 text-amber-800"}`}>
                {result.ok ? "Todos os componentes obrigatórios passaram." : result.summary}
              </div>
              {result.fixes_applied.length > 0 && (
                <div className="mt-3 rounded-xl bg-[#f4f7f0] p-3 text-[11px] font-bold">
                  Correções automáticas: {result.fixes_applied.join(" • ")}
                </div>
              )}
              <div className="mt-3 grid gap-2">
                {result.checks.map((check) => (
                  <div key={check.name} className="rounded-xl border border-black/5 bg-[#fafbf8] p-3 text-[11px]">
                    <div className="flex items-center justify-between gap-3 font-black">
                      <span>{check.name}</span>
                      <span className={check.ok ? "text-[#5f8500]" : "text-red-700"}>{check.ok ? "OK" : "ATENÇÃO"}</span>
                    </div>
                    <div className="mt-1 leading-5 text-[#5f6962]">{check.detail}</div>
                    {!check.ok && check.recommendation && <div className="mt-1 font-bold leading-5 text-[#111815]">Ação: {check.recommendation}</div>}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <button
        type="button"
        disabled={running}
        onClick={() => void run()}
        className="rounded-full bg-[#b8f238] px-5 py-3 text-xs font-black text-[#111815] shadow-xl disabled:opacity-60"
      >
        {running ? "Testando plataforma..." : "Testar plataforma"}
      </button>
    </div>
  );
}
