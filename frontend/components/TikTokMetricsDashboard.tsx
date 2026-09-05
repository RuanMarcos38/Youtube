"use client";

import { useEffect, useMemo, useState } from "react";

import { tiktokStatus, type TikTokStatus } from "@/lib/api";
import { tiktokMetrics, type TikTokDashboardAlert, type TikTokMetrics } from "@/lib/publications-api";

function fmtNumber(value?: number | null) {
  return new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
}

function fmtExact(value?: number | null) {
  return new Intl.NumberFormat("pt-BR").format(Math.round(value || 0));
}

function fmtPercent(value?: number | null) {
  return `${Number(value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`;
}

function fmtSigned(value?: number | null) {
  const safe = Number(value || 0);
  return `${safe > 0 ? "+" : ""}${new Intl.NumberFormat("pt-BR").format(safe)}`;
}

function fmtDateTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-[#ececec] bg-[#fafafa] p-4">
      <div className="text-[10px] font-semibold uppercase text-[#777]">{label}</div>
      <div className="mt-2 text-2xl font-black text-[#111]">{value}</div>
      {detail && <div className="mt-1 text-[10px] leading-4 text-[#777]">{detail}</div>}
    </div>
  );
}

function Alert({ alert }: { alert: TikTokDashboardAlert }) {
  const cls = alert.kind === "success"
    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
    : alert.kind === "danger"
      ? "border-red-200 bg-red-50 text-red-800"
      : alert.kind === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : "border-blue-100 bg-blue-50 text-blue-900";
  return (
    <div className={`rounded-xl border p-3 ${cls}`}>
      <div className="text-xs font-black">{alert.title}</div>
      <div className="mt-1 text-[10px] leading-4 opacity-80">{alert.detail}</div>
    </div>
  );
}

const HIDDEN_ALERT_TITLES = new Set([
  "Métricas oficiais limitadas pelo TikTok",
  "Operação local continua ativa",
  "Nenhum vídeo no período",
]);

export default function TikTokMetricsDashboard() {
  const [status, setStatus] = useState<TikTokStatus | null>(null);
  const [days, setDays] = useState(30);
  const [data, setData] = useState<TikTokMetrics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function refresh(nextDays = days) {
    setError("");
    try {
      const [connection, metrics] = await Promise.all([tiktokStatus(), tiktokMetrics(nextDays)]);
      setStatus(connection);
      setData(metrics);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar as métricas do TikTok.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    void refresh(days);
    const timer = window.setInterval(() => void refresh(days), 60000);
    return () => window.clearInterval(timer);
  }, [days]);

  const alerts = useMemo(
    () => (data?.alerts || []).filter((alert) => !HIDDEN_ALERT_TITLES.has(alert.title)),
    [data?.alerts],
  );

  return (
    <main className="sf-page-main min-h-screen py-7 text-[#111]">
      <div className="sf-container">
        <div className="mb-5 flex flex-col justify-between gap-3 md:flex-row md:items-end">
          <div>
            <div className="sf-kicker">TikTok</div>
            <h1 className="mt-1 text-[28px] font-semibold leading-tight">Métricas TikTok</h1>
            {status?.connected && <div className="mt-1 text-xs text-[#777]">{status.display_name || "Conta conectada"}</div>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {[7, 30, 90].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setDays(value)}
                className={`rounded-lg px-3 py-2 text-[11px] font-black ${days === value ? "bg-[#111] text-white" : "border border-[#e5e5e5] bg-white text-[#555]"}`}
              >
                {value} dias
              </button>
            ))}
            <button type="button" onClick={() => void refresh(days)} className="sf-button sf-button-outline">Atualizar</button>
          </div>
        </div>

        {loading && !data && <div className="sf-card p-8 text-sm text-[#777]">Carregando...</div>}
        {error && <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

        {!loading && status && !status.connected && (
          <div className="sf-card p-6">
            <div className="text-sm font-semibold">TikTok não conectado.</div>
            <a href="/#cortes" className="sf-button sf-button-primary mt-4">Ir para Publicações</a>
          </div>
        )}

        {data && (
          <div className="space-y-5">
            <section className="sf-card p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-base font-semibold">Visão geral</h2>
                {data.refreshed_at && <div className="text-[10px] text-[#999]">Atualizado em {fmtDateTime(data.refreshed_at)}</div>}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
                <Metric label="Seguidores" value={fmtNumber(data.profile?.followers)} detail={`Δ ${fmtSigned(data.growth?.followers_delta)}`} />
                <Metric label="Visualizações" value={fmtNumber(data.period?.views)} detail={`${days} dias`} />
                <Metric label="Vídeos" value={fmtExact(data.period?.videos)} detail={`Conta: ${fmtExact(data.profile?.video_count)}`} />
                <Metric label="Curtidas" value={fmtNumber(data.period?.likes)} detail={`Conta: ${fmtNumber(data.profile?.likes_total)}`} />
                <Metric label="Comentários" value={fmtNumber(data.period?.comments)} />
                <Metric label="Compartilhamentos" value={fmtNumber(data.period?.shares)} />
                <Metric label="Engajamento" value={fmtPercent(data.period?.engagement_rate)} detail={`${fmtNumber(data.period?.engagement_total)} interações`} />
                <Metric label="Média de views" value={fmtNumber(data.period?.avg_views_per_video)} />
              </div>
            </section>

            <section className="grid gap-5 lg:grid-cols-[1.1fr_.9fr]">
              <div className="sf-card p-5">
                <h2 className="text-sm font-semibold">Operação de publicação</h2>
                <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  <Metric label="Publicados" value={String(data.local_publications.published_confirmed)} />
                  <Metric label="Processando" value={String(data.local_publications.processing)} />
                  <Metric label="Fila" value={String(data.local_publications.queued)} />
                  <Metric label="Falhas" value={String(data.local_publications.failed)} />
                  <Metric label="Pausados" value={String(data.local_publications.paused_limit)} />
                </div>
              </div>

              <div className="sf-card p-5">
                <h2 className="text-sm font-semibold">Monetização / Creator Rewards</h2>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <Metric
                    label="Receita oficial"
                    value={data.monetization?.official_revenue_available ? fmtNumber(data.monetization.official_revenue) : "Não disponível"}
                  />
                  <Metric
                    label="Vídeos ≥ 60s"
                    value={String(data.monetization?.duration_eligible_videos || 0)}
                    detail={`${data.monetization?.duration_ineligible_videos || 0} abaixo de 60s`}
                  />
                </div>
              </div>
            </section>

            {!!alerts.length && (
              <section className="sf-card p-5">
                <h2 className="text-sm font-semibold">Alertas e oportunidades</h2>
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {alerts.map((alert, index) => <Alert key={`${alert.title}-${index}`} alert={alert} />)}
                </div>
              </section>
            )}

            <section className="grid gap-5 lg:grid-cols-[1.1fr_.9fr]">
              <div className="sf-card p-5">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold">Melhores vídeos do período</h2>
                  <div className="text-[10px] text-[#888]">por visualizações</div>
                </div>
                <div className="mt-4 space-y-2">
                  {(data.top_videos || []).slice(0, 5).map((video, index) => (
                    <div key={video.id || index} className="grid grid-cols-[1fr_auto] gap-3 rounded-lg border border-[#eee] bg-[#fafafa] p-3">
                      <div className="min-w-0">
                        <div className="truncate text-[11px] font-black">{index + 1}. {video.title || "Vídeo TikTok"}</div>
                        <div className="mt-1 text-[9px] text-[#777]">{video.duration}s · {fmtNumber(video.like_count)} curtidas · {fmtNumber(video.comment_count)} comentários · {fmtNumber(video.share_count)} compartilhamentos</div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-black">{fmtNumber(video.view_count)}</div>
                        <div className="text-[9px] text-[#888]">views</div>
                      </div>
                    </div>
                  ))}
                  {!data.top_videos?.length && <div className="rounded-lg border border-dashed border-[#ddd] p-6 text-center text-xs text-[#777]">Sem vídeos no período.</div>}
                </div>
              </div>

              <div className="sf-card p-5">
                <h2 className="text-sm font-semibold">Histórico e crescimento</h2>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <Metric label="Δ Seguidores" value={fmtSigned(data.growth?.followers_delta)} />
                  <Metric label="Δ Curtidas" value={fmtSigned(data.growth?.likes_total_delta)} />
                  <Metric label="Δ Vídeos" value={fmtSigned(data.growth?.video_count_delta)} />
                  <Metric label="Snapshots" value={String(data.history?.length || 0)} />
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
