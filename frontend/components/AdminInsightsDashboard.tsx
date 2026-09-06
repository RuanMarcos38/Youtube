"use client";

import { useEffect, useMemo, useState } from "react";
import BrandLogo from "./BrandLogo";
import { authMe } from "@/lib/api";

type PlanRow = {
  plan_code: string;
  plan_name: string;
  users: number;
  tenants: number;
  mrr_cents: number;
};

type OnlineRow = {
  user_id: number;
  display_name: string;
  email: string;
  workspace: string;
  plan_code: string;
  plan_name: string;
  last_seen: string;
};

type ChannelRow = {
  user_id: number;
  display_name: string;
  workspace: string;
  plan_code: string;
  channel_id: string | null;
  channel_title: string | null;
  published_shorts: number;
  updated_at: string;
  official_revenue_cents: number | null;
  revenue_status: string;
};

type DiagnosticCheck = {
  name: string;
  ok: boolean;
  detail: string;
  recommendation?: string;
};

type AuditStatus = {
  last_run: string | null;
  next_due: string;
  overdue: boolean;
  result: null | {
    ok: boolean;
    summary: string;
    fixes_applied: string[];
    recommendations: string[];
    checks: DiagnosticCheck[];
  };
};

type Insights = {
  refreshed_at: string;
  total_users: number;
  online_users: number;
  paying_customers: number;
  trial_users: number;
  mrr_cents: number;
  arr_cents: number;
  connected_channels: number;
  plan_distribution: PlanRow[];
  online: OnlineRow[];
  channels: ChannelRow[];
  audit: AuditStatus;
};

type LiveChannel = {
  channel_title?: string;
  subscriber_count?: number;
  view_count?: number;
  video_count?: number;
  views_last_28d?: number | null;
  views_last_90d?: number | null;
  watch_hours_last_365d?: number | null;
  monetization?: {
    eligible_early_estimate?: boolean;
    eligible_full_estimate?: boolean;
    near_monetization?: boolean;
  };
  revenue_status?: string;
};

function money(cents: number | null | undefined) {
  if (cents == null) return "Indisponível via API";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(cents / 100);
}

function dateTime(value: string | null | undefined) {
  if (!value) return "Ainda não executado";
  try {
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value));
  } catch {
    return value;
  }
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: "include", cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json() as { detail?: string };
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}

export default function AdminInsightsDashboard() {
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [data, setData] = useState<Insights | null>(null);
  const [live, setLive] = useState<Record<number, LiveChannel>>({});
  const [loadingChannel, setLoadingChannel] = useState<number | null>(null);
  const [runningAudit, setRunningAudit] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try {
      setData(await getJson<Insights>("/api/admin/insights"));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar o dashboard administrativo.");
    }
  }

  useEffect(() => {
    let active = true;
    authMe()
      .then((user) => {
        if (!active) return;
        const ok = user.role === "superadmin";
        setAllowed(ok);
        if (ok) void load();
      })
      .catch(() => active && setAllowed(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!allowed) return;
    const interval = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(interval);
  }, [allowed]);

  const recommendations = useMemo(() => data?.audit.result?.recommendations || [], [data]);

  async function refreshChannel(userId: number) {
    setLoadingChannel(userId);
    try {
      const result = await getJson<LiveChannel>(`/api/admin/insights/channels/${userId}`);
      setLive((current) => ({ ...current, [userId]: result }));
    } catch (err) {
      setLive((current) => ({
        ...current,
        [userId]: { revenue_status: err instanceof Error ? err.message : "Falha ao atualizar métricas." },
      }));
    } finally {
      setLoadingChannel(null);
    }
  }

  async function runAudit() {
    setRunningAudit(true);
    try {
      await getJson<AuditStatus>("/api/admin/insights/audit/run", { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível executar a varredura.");
    } finally {
      setRunningAudit(false);
    }
  }

  if (allowed === null) return <main className="grid min-h-screen place-items-center bg-[#f7f7f7] text-sm font-bold">Validando acesso administrativo...</main>;
  if (!allowed) return <main className="grid min-h-screen place-items-center bg-[#f7f7f7] p-6"><div className="max-w-lg rounded-2xl border border-red-200 bg-white p-7 text-center"><h1 className="text-xl font-black">Acesso restrito</h1><p className="mt-2 text-sm text-[#667085]">Este dashboard é exclusivo do administrador geral do ShortsFlow.</p><a href="/" className="mt-5 inline-flex rounded-xl bg-[#111] px-5 py-3 text-sm font-black text-white">Voltar</a></div></main>;

  return (
    <main className="min-h-screen bg-[#f7f7f7] px-4 py-7 text-[#111] md:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4"><BrandLogo size="sm" /><div><div className="text-[10px] font-black uppercase tracking-[.15em] text-red-600">Somente administrador</div><h1 className="mt-1 text-2xl font-black">Dashboard executivo ShortsFlow</h1></div></div>
          <div className="flex gap-2"><button onClick={() => void load()} className="rounded-xl border border-black/10 bg-white px-4 py-2.5 text-xs font-black">Atualizar</button><a href="/" className="rounded-xl bg-[#111] px-4 py-2.5 text-xs font-black text-white">Voltar à plataforma</a></div>
        </header>

        {error && <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-bold text-red-700">{error}</div>}

        {data && <>
          <section className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-7">
            {[
              ["Usuários", data.total_users.toLocaleString("pt-BR")],
              ["Online agora", data.online_users.toLocaleString("pt-BR")],
              ["Clientes pagantes", data.paying_customers.toLocaleString("pt-BR")],
              ["Em teste", data.trial_users.toLocaleString("pt-BR")],
              ["Canais conectados", data.connected_channels.toLocaleString("pt-BR")],
              ["MRR contratado", money(data.mrr_cents)],
              ["ARR projetado", money(data.arr_cents)],
            ].map(([label, value]) => <div key={label} className="rounded-2xl border border-[#e6e6e6] bg-white p-4 shadow-sm"><div className="text-[10px] font-black uppercase text-[#7a7a7a]">{label}</div><div className="mt-2 text-xl font-black">{value}</div></div>)}
          </section>

          <section className="mt-6 grid gap-5 xl:grid-cols-[1.15fr_.85fr]">
            <div className="rounded-2xl border border-[#e6e6e6] bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-3"><div><h2 className="font-black">Usuários por plano</h2><p className="mt-1 text-xs text-[#667085]">Quantidade de usuários, empresas e receita recorrente mensal equivalente.</p></div><span className="text-[10px] font-bold text-[#667085]">Atualização automática</span></div>
              <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[560px] text-left text-xs"><thead><tr className="border-b border-[#eee] text-[#667085]"><th className="py-3">Plano</th><th>Usuários</th><th>Empresas</th><th>MRR</th></tr></thead><tbody>{data.plan_distribution.map((row) => <tr key={row.plan_code} className="border-b border-[#f1f1f1]"><td className="py-3 font-black">{row.plan_name}</td><td>{row.users}</td><td>{row.tenants}</td><td className="font-bold">{money(row.mrr_cents)}</td></tr>)}</tbody></table></div>
            </div>

            <div className="rounded-2xl border border-[#e6e6e6] bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-3"><div><h2 className="font-black">Usuários online</h2><p className="mt-1 text-xs text-[#667085]">Presença real por heartbeat; sai do online após aproximadamente 90 segundos sem atividade.</p></div><span className="rounded-full bg-[#eaf8c8] px-3 py-1 text-xs font-black text-[#4d6d00]">{data.online_users} online</span></div>
              <div className="mt-4 max-h-[310px] space-y-2 overflow-auto">{data.online.length === 0 ? <div className="rounded-xl bg-[#f7f7f7] p-4 text-xs text-[#667085]">Nenhum usuário ativo neste momento.</div> : data.online.map((row) => <div key={row.user_id} className="rounded-xl border border-[#eee] p-3"><div className="flex items-center justify-between gap-2"><div className="font-black text-sm">{row.display_name}</div><span className="h-2.5 w-2.5 rounded-full bg-[#75b500]" /></div><div className="mt-1 text-[11px] text-[#667085]">{row.workspace} · {row.plan_name}</div><div className="mt-1 text-[10px] text-[#909090]">Último sinal: {dateTime(row.last_seen)}</div></div>)}</div>
            </div>
          </section>

          <section className="mt-6 rounded-2xl border border-[#e6e6e6] bg-white p-5 shadow-sm">
            <div><h2 className="font-black">Canais e monetização</h2><p className="mt-1 max-w-4xl text-xs leading-5 text-[#667085]">Visualize canais vinculados e consulte métricas oficiais sob demanda. O ShortsFlow não inventa receita: quando o YouTube não disponibiliza valor monetário pela autorização/API atual, o painel sinaliza como indisponível.</p></div>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">{data.channels.length === 0 ? <div className="rounded-xl bg-[#f7f7f7] p-4 text-xs text-[#667085]">Nenhum canal conectado por usuários.</div> : data.channels.map((channel) => {
              const metrics = live[channel.user_id];
              return <article key={channel.user_id} className="rounded-2xl border border-[#ececec] p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-[10px] font-black uppercase text-red-600">{channel.plan_code}</div><h3 className="mt-1 font-black">{channel.channel_title || "Canal YouTube"}</h3><div className="mt-1 text-xs text-[#667085]">{channel.display_name} · {channel.workspace}</div></div><button disabled={loadingChannel === channel.user_id} onClick={() => void refreshChannel(channel.user_id)} className="rounded-xl bg-[#111] px-4 py-2.5 text-xs font-black text-white disabled:opacity-50">{loadingChannel === channel.user_id ? "Atualizando..." : "Atualizar métricas"}</button></div>
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4"><div className="rounded-xl bg-[#f7f7f7] p-3"><div className="text-[9px] font-black uppercase text-[#777]">Shorts enviados</div><div className="mt-1 font-black">{channel.published_shorts}</div></div><div className="rounded-xl bg-[#f7f7f7] p-3"><div className="text-[9px] font-black uppercase text-[#777]">Inscritos</div><div className="mt-1 font-black">{metrics?.subscriber_count?.toLocaleString("pt-BR") ?? "—"}</div></div><div className="rounded-xl bg-[#f7f7f7] p-3"><div className="text-[9px] font-black uppercase text-[#777]">Views totais</div><div className="mt-1 font-black">{metrics?.view_count?.toLocaleString("pt-BR") ?? "—"}</div></div><div className="rounded-xl bg-[#f7f7f7] p-3"><div className="text-[9px] font-black uppercase text-[#777]">Receita oficial</div><div className="mt-1 text-xs font-black">Indisponível</div></div></div>
                {metrics && <div className="mt-3 rounded-xl bg-[#fafbf8] p-3 text-[11px] leading-5"><div><b>Views 28 dias:</b> {metrics.views_last_28d?.toLocaleString("pt-BR") ?? "indisponível"} · <b>90 dias:</b> {metrics.views_last_90d?.toLocaleString("pt-BR") ?? "indisponível"}</div><div><b>Horas assistidas/365d:</b> {metrics.watch_hours_last_365d?.toLocaleString("pt-BR") ?? "indisponível"}</div><div><b>Monetização:</b> {metrics.monetization?.eligible_full_estimate ? "indicadores compatíveis com monetização completa" : metrics.monetization?.near_monetization ? "próximo dos marcos principais" : "ainda abaixo dos principais marcos detectáveis"}</div></div>}
                <p className="mt-3 text-[10px] leading-4 text-[#8a4b00]">{metrics?.revenue_status || channel.revenue_status}</p>
              </article>;
            })}</div>
          </section>

          <section className="mt-6 rounded-2xl border border-[#e6e6e6] bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-[10px] font-black uppercase tracking-[.14em] text-[#6f9700]">Assistente exclusivo do administrador</div><h2 className="mt-1 font-black">Varredura automática diária</h2><p className="mt-1 text-xs leading-5 text-[#667085]">Reutiliza os testes de produção já existentes e aplica apenas correções locais seguras e reversíveis. Credenciais e integrações não são modificadas.</p></div><button disabled={runningAudit} onClick={() => void runAudit()} className="rounded-xl bg-[#b8f238] px-4 py-2.5 text-xs font-black disabled:opacity-50">{runningAudit ? "Executando..." : "Executar agora"}</button></div>
            <div className="mt-4 grid gap-3 md:grid-cols-3"><div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[9px] font-black uppercase text-[#777]">Última varredura</div><div className="mt-1 text-xs font-black">{dateTime(data.audit.last_run)}</div></div><div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[9px] font-black uppercase text-[#777]">Próxima</div><div className="mt-1 text-xs font-black">{dateTime(data.audit.next_due)}</div></div><div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[9px] font-black uppercase text-[#777]">Status</div><div className="mt-1 text-xs font-black">{data.audit.result ? (data.audit.result.ok ? "Operacional" : "Atenção necessária") : "Aguardando primeira execução"}</div></div></div>
            {data.audit.result && <div className="mt-4 rounded-xl border border-[#eee] p-4"><div className="text-sm font-black">{data.audit.result.summary}</div>{data.audit.result.fixes_applied.length > 0 && <div className="mt-2 text-xs font-bold text-[#52720f]">Correções seguras aplicadas: {data.audit.result.fixes_applied.join(" • ")}</div>}{recommendations.length > 0 && <div className="mt-3"><div className="text-[10px] font-black uppercase text-[#777]">Melhorias encontradas</div><ul className="mt-2 space-y-1 text-xs text-[#555]">{recommendations.slice(0, 8).map((item, index) => <li key={`${item}-${index}`}>• {item}</li>)}</ul></div>}</div>}
          </section>

          <div className="py-8 text-center text-[10px] text-[#888]">Dados administrativos atualizados em {dateTime(data.refreshed_at)}.</div>
        </>}
      </div>
    </main>
  );
}
