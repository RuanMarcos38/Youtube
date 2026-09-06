"use client";

import { useEffect, useState } from "react";
import { adminRunDiagnostics, authMe } from "@/lib/api";
import type { DiagnosticResult } from "@/lib/types";

type DailyAudit = {
  last_run: string | null;
  next_due: string;
  overdue: boolean;
  result: null | {
    ok: boolean;
    summary: string;
    fixes_applied: string[];
    recommendations: string[];
  };
};

function when(value: string | null | undefined) {
  if (!value) return "aguardando primeira varredura";
  try {
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
  } catch {
    return value;
  }
}

export default function DiagnosticsAssistant() {
  const [allowed, setAllowed] = useState(false);
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DiagnosticResult | null>(null);
  const [daily, setDaily] = useState<DailyAudit | null>(null);
  const [error, setError] = useState("");

  async function loadDaily() {
    try {
      const response = await fetch("/api/admin/insights/audit", { credentials: "include", cache: "no-store" });
      if (response.ok) setDaily(await response.json());
    } catch {
      // O assistente manual continua disponível mesmo se a leitura automática oscilar.
    }
  }

  useEffect(() => {
    authMe()
      .then((user) => {
        const isAdmin = user.role === "superadmin";
        setAllowed(isAdmin);
        if (isAdmin) void loadDaily();
      })
      .catch(() => setAllowed(false));
  }, []);

  async function run() {
    setRunning(true);
    setError("");
    try {
      setResult(await adminRunDiagnostics(true));
      await loadDaily();
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
        <div className="max-h-[70vh] w-[min(450px,calc(100vw-2.5rem))] overflow-auto rounded-2xl border border-black/10 bg-white p-4 shadow-2xl">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[.14em] text-[#6f9700]">Assistente exclusivo do administrador</div>
              <h3 className="mt-1 text-sm font-black">Saúde e melhorias da plataforma</h3>
            </div>
            <button onClick={() => setOpen(false)} className="rounded-lg border border-black/10 px-2 py-1 text-[10px] font-black">Fechar</button>
          </div>

          <div className="mt-3 rounded-xl border border-[#e7edd9] bg-[#fafcf5] p-3 text-[11px] leading-5">
            <div className="font-black">Varredura automática diária</div>
            <div className="mt-1 text-[#5f6962]">Última: {when(daily?.last_run)} · Próxima: {when(daily?.next_due)}</div>
            {daily?.result && <div className={`mt-2 font-bold ${daily.result.ok ? "text-[#52720f]" : "text-amber-800"}`}>{daily.result.summary}</div>}
            {daily?.result?.recommendations?.length ? <div className="mt-2 text-[#5f6962]">Melhoria prioritária: {daily.result.recommendations[0]}</div> : null}
          </div>

          <a href="/admin-dashboard" className="mt-3 flex w-full items-center justify-between rounded-xl bg-[#111] px-4 py-3 text-xs font-black text-white">
            <span>Abrir Dashboard Executivo</span><span>→</span>
          </a>

          {error && <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-[11px] font-bold text-red-700">{error}</div>}

          {result && (
            <>
              <div className={`mt-3 rounded-xl p-3 text-xs font-black ${result.ok ? "bg-[#eaf8c8] text-[#4b6a00]" : "bg-amber-50 text-amber-800"}`}>
                {result.ok ? "Todos os componentes obrigatórios passaram." : result.summary}
              </div>
              {result.fixes_applied.length > 0 && (
                <div className="mt-3 rounded-xl bg-[#f4f7f0] p-3 text-[11px] font-bold">
                  Correções automáticas seguras: {result.fixes_applied.join(" • ")}
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
        onClick={() => open ? setOpen(false) : void run()}
        className="rounded-full bg-[#b8f238] px-5 py-3 text-xs font-black text-[#111815] shadow-xl disabled:opacity-60"
      >
        {running ? "Testando plataforma..." : open ? "Fechar assistente" : "Assistente Admin"}
      </button>
    </div>
  );
}
