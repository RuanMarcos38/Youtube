"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  adminCredentials,
  adminDownloadAuth,
  adminKiwifySettings,
  adminMarkCredentialDelivered,
  adminMetrics,
  adminUpdateDownloadAuth,
  adminUpdatePlan,
  adminUsers,
} from "@/lib/api";
import type { AdminMetrics, AdminUser, DownloadAuthStatus, KiwifyAdminSettings, ProvisionedCredential } from "@/lib/types";

function money(cents: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format((cents || 0) / 100);
}

export default function AdminPanel({ onClose }: { onClose: () => void }) {
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [credentials, setCredentials] = useState<ProvisionedCredential[]>([]);
  const [downloadAuth, setDownloadAuth] = useState<DownloadAuthStatus | null>(null);
  const [kiwify, setKiwify] = useState<KiwifyAdminSettings | null>(null);
  const [cookiesB64, setCookiesB64] = useState("");
  const [proxyUrl, setProxyUrl] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    setMessage("");
    try {
      const [m, u, c, d, k] = await Promise.all([
        adminMetrics(),
        adminUsers(),
        adminCredentials(),
        adminDownloadAuth(),
        adminKiwifySettings(),
      ]);
      setMetrics(m);
      setUsers(u);
      setCredentials(c);
      setDownloadAuth(d);
      setKiwify(k);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Falha ao carregar o painel administrativo.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function saveDownloadAuth(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      const status = await adminUpdateDownloadAuth({
        ...(cookiesB64.trim() ? { cookies_b64: cookiesB64.trim() } : {}),
        ...(proxyUrl.trim() ? { proxy_url: proxyUrl.trim() } : {}),
      });
      setDownloadAuth(status);
      setCookiesB64("");
      setProxyUrl("");
      setMessage("Autenticação de download atualizada. Novos jobs usarão a nova sessão sem precisar de redeploy.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Falha ao atualizar a autenticação do YouTube.");
    }
  }

  async function setUnlimited(user: AdminUser, unlimited: boolean) {
    await adminUpdatePlan(user.id, {
      unlimited,
      plan_code: unlimited ? "unlimited" : "starter",
      billing_status: "active",
    });
    await refresh();
  }

  async function updateLimit(user: AdminUser, limit: number) {
    await adminUpdatePlan(user.id, { monthly_job_limit: Math.max(1, limit), unlimited: false, plan_code: "starter" });
    await refresh();
  }

  return (
    <section className="border-b border-black/5 bg-[#f4f7f0] px-4 py-7 md:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><div className="text-xs font-black uppercase tracking-[.18em] text-[#6f9700]">Administração</div><h2 className="mt-1 text-2xl font-black">Dashboard ShortsFlow SaaS</h2></div>
          <div className="flex gap-2"><button onClick={() => void refresh()} className="rounded-xl bg-white px-4 py-2 text-xs font-black shadow-sm">Atualizar</button><button onClick={onClose} className="rounded-xl bg-[#111815] px-4 py-2 text-xs font-black text-white">Fechar</button></div>
        </div>

        {message && <div className="mt-4 rounded-xl border border-black/5 bg-white p-3 text-xs font-bold">{message}</div>}
        {loading && <div className="mt-5 text-sm font-bold">Carregando...</div>}

        {metrics && <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {[
            ["Usuários", String(metrics.total_users)],
            ["Assinantes", String(metrics.active_subscribers)],
            ["MRR / mês", money(metrics.monthly_revenue_cents)],
            ["Receita total", money(metrics.total_revenue_cents)],
            ["Jobs no mês", String(metrics.jobs_this_month)],
            ["Ilimitados", String(metrics.unlimited_subscribers)],
          ].map(([label, value]) => <div key={label} className="rounded-2xl bg-white p-4 shadow-sm"><div className="text-[10px] font-black uppercase tracking-[.12em] text-[#7a847d]">{label}</div><div className="mt-2 text-xl font-black">{value}</div></div>)}
        </div>}

        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <form onSubmit={saveDownloadAuth} className="rounded-2xl bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between gap-3"><div><h3 className="font-black">Download YouTube</h3><p className="mt-1 text-xs text-[#6e7971]">Renove os cookies aqui quando o YouTube recusar a sessão da VPS.</p></div><span className={`rounded-full px-3 py-1 text-[11px] font-black ${downloadAuth?.cookie_override || downloadAuth?.cookie_environment ? "bg-[#eaf8c8] text-[#4b6a00]" : "bg-red-50 text-red-700"}`}>{downloadAuth?.cookie_override ? "Cookie renovado" : downloadAuth?.cookie_environment ? "Cookie do servidor" : "Sem cookie"}</span></div>
            <label className="mt-4 block text-xs font-black">YTDLP_COOKIES_B64<textarea value={cookiesB64} onChange={(e) => setCookiesB64(e.target.value)} rows={4} placeholder="Cole o Base64 gerado pelo Firefox. O valor não será exibido depois." className="mt-2 w-full rounded-xl border border-black/10 p-3 text-xs outline-none focus:border-[#91c51d]" /></label>
            <label className="mt-3 block text-xs font-black">Proxy residencial/estático (opcional)<input value={proxyUrl} onChange={(e) => setProxyUrl(e.target.value)} placeholder="http://usuario:senha@host:porta" className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 text-xs outline-none focus:border-[#91c51d]" /></label>
            <button className="mt-4 rounded-xl bg-[#111815] px-4 py-3 text-xs font-black text-white">Atualizar autenticação</button>
          </form>

          <div className="rounded-2xl bg-white p-5 shadow-sm">
            <h3 className="font-black">Integração Kiwify</h3>
            <p className="mt-1 text-xs text-[#6e7971]">Cadastre esta URL em Apps → Webhooks na Kiwify e selecione compra aprovada, reembolso, chargeback e eventos de assinatura.</p>
            <div className="mt-4 rounded-xl bg-[#f4f7f0] p-3 text-[11px] font-bold break-all">{kiwify?.webhook_url || "Carregando URL..."}</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2"><a href={kiwify?.checkout_url} target="_blank" rel="noreferrer" className="rounded-xl bg-[#b8f238] px-4 py-3 text-center text-xs font-black">Assine já</a><a href={kiwify?.upgrade_url} target="_blank" rel="noreferrer" className="rounded-xl bg-[#0d241d] px-4 py-3 text-center text-xs font-black text-white">Upgrade ilimitado</a></div>
          </div>
        </div>

        <div className="mt-6 rounded-2xl bg-white p-5 shadow-sm">
          <h3 className="font-black">Usuários e assinaturas</h3><p className="mt-1 text-xs text-[#6e7971]">Controle de plano, consumo e canal conectado.</p>
          <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[900px] text-left text-xs"><thead><tr className="border-b border-black/5 text-[#778078]"><th className="p-2">Usuário</th><th className="p-2">Plano</th><th className="p-2">Status</th><th className="p-2">Uso</th><th className="p-2">Valor</th><th className="p-2">YouTube</th><th className="p-2">Ações</th></tr></thead><tbody>{users.filter((u) => u.role !== "superadmin").map((u) => <tr key={u.id} className="border-b border-black/5"><td className="p-2"><strong>{u.display_name}</strong><div className="text-[#778078]">{u.email}</div></td><td className="p-2 font-bold">{u.plan_code}</td><td className="p-2">{u.billing_status}</td><td className="p-2">{u.unlimited ? `${u.jobs_used} / ilimitado` : `${u.jobs_used} / ${u.monthly_job_limit}`}</td><td className="p-2">{money(u.subscription_value_cents)}</td><td className="p-2">{u.youtube_connected ? u.youtube_channel_title || "Conectado" : "Não conectado"}</td><td className="p-2"><div className="flex flex-wrap gap-1"><button onClick={() => void setUnlimited(u, !u.unlimited)} className="rounded-lg bg-[#f0f3ec] px-2 py-1.5 font-black">{u.unlimited ? "Voltar ao limite" : "Ilimitado"}</button><button onClick={() => { const value = window.prompt("Novo limite mensal de jobs", String(u.monthly_job_limit)); if (value) void updateLimit(u, Number(value)); }} className="rounded-lg bg-[#f0f3ec] px-2 py-1.5 font-black">Limite</button></div></td></tr>)}</tbody></table></div>
        </div>

        {credentials.length > 0 && <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5"><h3 className="font-black text-amber-950">Credenciais aguardando entrega</h3><p className="mt-1 text-xs text-amber-800">Quando SMTP estiver configurado, essas credenciais são enviadas automaticamente. Enquanto isso, entregue-as ao comprador e marque como entregue.</p><div className="mt-4 grid gap-2">{credentials.map((c) => <div key={c.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-3 text-xs"><div><strong>{c.display_name || c.email}</strong><div className="mt-1">Login: {c.email}</div><div>Senha inicial: <span className="font-mono font-black">{c.temporary_password}</span></div></div><button onClick={async () => { await adminMarkCredentialDelivered(c.id); await refresh(); }} className="rounded-lg bg-[#111815] px-3 py-2 font-black text-white">Marcar entregue</button></div>)}</div></div>}
      </div>
    </section>
  );
}
