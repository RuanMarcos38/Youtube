"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  adminCredentials,
  adminDownloadAuth,
  adminKiwifySettings,
  adminMarkCredentialDelivered,
  adminMetrics,
  adminRegisterKiwify,
  adminSystemConfig,
  adminTestDownloadAuth,
  adminUpdateDownloadAuth,
  adminUpdatePlan,
  adminUpdateSystemConfig,
  adminUsers,
} from "@/lib/api";
import type { AdminMetrics, AdminUser, DownloadAuthStatus, KiwifyAdminSettings, ProvisionedCredential, PublicConfig } from "@/lib/types";

function money(cents: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format((cents || 0) / 100);
}

type KiwifyFeedback = {
  kind: "idle" | "pending" | "success" | "error";
  text: string;
};

export default function AdminPanel({ onClose }: { onClose: () => void }) {
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [credentials, setCredentials] = useState<ProvisionedCredential[]>([]);
  const [downloadAuth, setDownloadAuth] = useState<DownloadAuthStatus | null>(null);
  const [kiwify, setKiwify] = useState<KiwifyAdminSettings | null>(null);
  const [systemConfig, setSystemConfig] = useState<PublicConfig | null>(null);
  const [cookiesB64, setCookiesB64] = useState("");
  const [proxyUrl, setProxyUrl] = useState("");
  const [kiwifyClientId, setKiwifyClientId] = useState("");
  const [kiwifyClientSecret, setKiwifyClientSecret] = useState("");
  const [kiwifyAccountId, setKiwifyAccountId] = useState("");
  const [kiwifyFeedback, setKiwifyFeedback] = useState<KiwifyFeedback>({ kind: "idle", text: "" });
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [testingDownload, setTestingDownload] = useState(false);
  const [connectingKiwify, setConnectingKiwify] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);

  async function refresh() {
    setLoading(true);
    setMessage("");
    try {
      const [m, u, c, d, k, s] = await Promise.all([
        adminMetrics(),
        adminUsers(),
        adminCredentials(),
        adminDownloadAuth(),
        adminKiwifySettings(),
        adminSystemConfig(),
      ]);
      setMetrics(m);
      setUsers(u);
      setCredentials(c);
      setDownloadAuth(d);
      setKiwify(k);
      setKiwifyClientId(k.client_id || "");
      setKiwifyAccountId(k.account_id || "");
      setSystemConfig(s);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Falha ao carregar o painel administrativo.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function saveSystemConfig(event: FormEvent) {
    event.preventDefault();
    if (!systemConfig) return;
    setSavingConfig(true);
    setMessage("");
    try {
      const saved = await adminUpdateSystemConfig(systemConfig);
      setSystemConfig(saved);
      setKiwify((current) => current ? { ...current, checkout_url: saved.checkout_url, upgrade_url: saved.upgrade_url } : current);
      setMessage("Parametrização salva. A página de entrada, links comerciais e limite padrão foram atualizados sem redeploy.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Falha ao salvar a parametrização.");
    } finally {
      setSavingConfig(false);
    }
  }

  function setBenefit(index: number, value: string) {
    if (!systemConfig) return;
    const benefits = [...systemConfig.benefits];
    benefits[index] = value;
    setSystemConfig({ ...systemConfig, benefits });
  }

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
      setMessage("Autenticação atualizada. Clique em ‘Testar download’ para validar o acesso do YouTube.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Falha ao atualizar a autenticação do YouTube.");
    }
  }

  async function testDownload() {
    setTestingDownload(true);
    setMessage("");
    try {
      const result = await adminTestDownloadAuth();
      const strategy = result.strategy ? ` • ${result.strategy}` : "";
      setMessage(`Download validado com sucesso (${result.mode}${strategy}). A VPS está apta a iniciar novos Shorts.`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "A sessão ainda foi recusada pelo YouTube.");
    } finally {
      setTestingDownload(false);
    }
  }

  async function connectKiwify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (connectingKiwify) return;

    const form = event.currentTarget;
    const data = new FormData(form);
    const clientId = String(data.get("client_id") || kiwifyClientId || "").trim();
    const clientSecret = String(data.get("client_secret") || kiwifyClientSecret || "").trim();
    const accountId = String(data.get("account_id") || kiwifyAccountId || "").trim();

    if (!clientId) {
      setKiwifyFeedback({ kind: "error", text: "Informe o Client ID da API da Kiwify." });
      return;
    }
    if (!accountId || accountId.includes("@")) {
      setKiwifyFeedback({ kind: "error", text: "Informe o Account ID da Kiwify. Esse campo não aceita e-mail." });
      return;
    }
    if (!clientSecret && !kiwify?.client_secret_configured) {
      setKiwifyFeedback({ kind: "error", text: "Informe o Client Secret da API na primeira conexão." });
      return;
    }

    setConnectingKiwify(true);
    setKiwifyFeedback({ kind: "pending", text: "Validando credenciais na Kiwify e sincronizando o webhook..." });
    try {
      const result = await adminRegisterKiwify({
        client_id: clientId,
        ...(clientSecret ? { client_secret: clientSecret } : {}),
        account_id: accountId,
        products: "all",
      });
      setKiwifyClientSecret("");
      const updated = await adminKiwifySettings();
      setKiwify(updated);
      setKiwifyClientId(updated.client_id || result.client_id || clientId);
      setKiwifyAccountId(updated.account_id || result.account_id || accountId);
      setKiwifyFeedback({
        kind: "success",
        text: `Kiwify conectada. API validada e webhook ${result.action === "created" ? "criado" : "atualizado"} com sucesso.`,
      });
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Falha ao conectar a Kiwify.";
      setKiwifyFeedback({ kind: "error", text: detail });
    } finally {
      setConnectingKiwify(false);
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
    <section className="border-b border-[#e6e6e6] bg-[#f7f7f7] px-4 py-7 md:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><div className="sf-kicker">Administração</div><h2 className="mt-1 text-2xl font-semibold">Painel ShortsFlow SaaS</h2></div>
          <div className="flex gap-2"><button onClick={() => void refresh()} className="sf-button sf-button-outline">Atualizar</button><button onClick={onClose} className="sf-button sf-button-primary">Fechar</button></div>
        </div>

        {message && <div className="mt-4 rounded-xl border border-[#e6e6e6] bg-white p-3 text-xs font-semibold">{message}</div>}
        {loading && <div className="mt-5 text-sm font-bold">Carregando...</div>}

        {metrics && <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {[
            ["Usuários", String(metrics.total_users)],
            ["Assinantes", String(metrics.active_subscribers)],
            ["Receita no mês", money(metrics.monthly_revenue_cents)],
            ["Receita total", money(metrics.total_revenue_cents)],
            ["Processamentos no mês", String(metrics.jobs_this_month)],
            ["Ilimitados", String(metrics.unlimited_subscribers)],
          ].map(([label, value]) => <div key={label} className="sf-card-soft p-4"><div className="sf-label">{label}</div><div className="metric-value mt-2 text-xl font-semibold">{value}</div></div>)}
        </div>}

        {systemConfig && <form onSubmit={saveSystemConfig} className="sf-card mt-6 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">Parametrização da ferramenta</h3><p className="mt-1 text-xs text-[#6e7971]">Altere textos comerciais, links e limite padrão diretamente no painel. Não exige alteração de código nem novo deploy.</p></div><button disabled={savingConfig} className="sf-button sf-button-primary disabled:opacity-50">{savingConfig ? "Salvando..." : "Salvar parâmetros"}</button></div>
          <div className="mt-5 grid gap-3 lg:grid-cols-2">
            <label className="text-xs font-black">Nome da ferramenta<input value={systemConfig.brand_name} onChange={(e) => setSystemConfig({ ...systemConfig, brand_name: e.target.value })} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>
            <label className="text-xs font-black">Selo da página de entrada<input value={systemConfig.marketing_badge} onChange={(e) => setSystemConfig({ ...systemConfig, marketing_badge: e.target.value })} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>
            <label className="text-xs font-black lg:col-span-2">Título principal<input value={systemConfig.marketing_headline} onChange={(e) => setSystemConfig({ ...systemConfig, marketing_headline: e.target.value })} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>
            <label className="text-xs font-black lg:col-span-2">Descrição comercial<textarea rows={3} value={systemConfig.marketing_description} onChange={(e) => setSystemConfig({ ...systemConfig, marketing_description: e.target.value })} className="mt-2 w-full rounded-xl border border-black/10 p-3 font-normal" /></label>
            {systemConfig.benefits.slice(0, 4).map((benefit, index) => <label key={index} className="text-xs font-black">Benefício {index + 1}<input value={benefit} onChange={(e) => setBenefit(index, e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>)}
            <label className="text-xs font-black">Título do login<input value={systemConfig.login_title} onChange={(e) => setSystemConfig({ ...systemConfig, login_title: e.target.value })} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>
            <label className="text-xs font-black">Texto do login<input value={systemConfig.login_description} onChange={(e) => setSystemConfig({ ...systemConfig, login_description: e.target.value })} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>
            <label className="text-xs font-black">Checkout assinatura<input value={systemConfig.checkout_url} onChange={(e) => setSystemConfig({ ...systemConfig, checkout_url: e.target.value })} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>
            <label className="text-xs font-black">Checkout Upgrade<input value={systemConfig.upgrade_url} onChange={(e) => setSystemConfig({ ...systemConfig, upgrade_url: e.target.value })} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>
            <label className="text-xs font-black">Limite mensal padrão<input type="number" min={1} max={100000} value={systemConfig.base_plan_job_limit} onChange={(e) => setSystemConfig({ ...systemConfig, base_plan_job_limit: Math.max(1, Number(e.target.value) || 1) })} className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 font-normal" /></label>
          </div>
        </form>}

        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <form onSubmit={saveDownloadAuth} className="sf-card p-5">
            <div className="flex items-center justify-between gap-3"><div><h3 className="font-black">Download YouTube</h3><p className="mt-1 text-xs text-[#6e7971]">O sistema tenta cookies e também fallbacks públicos sem cookies. Se a própria saída da VPS continuar bloqueada, configure um proxy residencial/estático.</p></div><span className={`rounded-full px-3 py-1 text-[11px] font-black ${downloadAuth?.cookie_override || downloadAuth?.cookie_environment ? "bg-[#eaf8c8] text-[#4b6a00]" : "bg-red-50 text-red-700"}`}>{downloadAuth?.cookie_override ? "Cookie renovado" : downloadAuth?.cookie_environment ? "Cookie do servidor" : "Sem cookie"}</span></div>
            <label className="mt-4 block text-xs font-black">YTDLP_COOKIES_B64<textarea value={cookiesB64} onChange={(e) => setCookiesB64(e.target.value)} rows={4} placeholder="Cole o Base64 gerado pelo Firefox. O valor não será exibido depois." className="mt-2 w-full rounded-xl border border-black/10 p-3 text-xs outline-none focus:border-[#91c51d]" /></label>
            <label className="mt-3 block text-xs font-black">Proxy residencial/estático (opcional)<input value={proxyUrl} onChange={(e) => setProxyUrl(e.target.value)} placeholder="http://usuario:senha@host:porta" className="mt-2 w-full rounded-xl border border-black/10 px-3 py-3 text-xs outline-none focus:border-[#91c51d]" /></label>
            <div className="mt-4 flex flex-wrap gap-2"><button className="sf-button sf-button-primary">Atualizar autenticação</button><button type="button" disabled={testingDownload} onClick={() => void testDownload()} className="sf-button sf-button-outline disabled:opacity-50">{testingDownload ? "Testando..." : "Testar download"}</button></div>
          </form>

          <div className="sf-card p-5">
            <div className="flex items-start justify-between gap-3">
              <div><h3 className="font-black">Integração Kiwify</h3><p className="mt-1 text-xs text-[#6e7971]">API + webhook para ativar, renovar e bloquear planos automaticamente conforme os eventos de pagamento.</p></div>
              <span className={`rounded-full px-3 py-1 text-[10px] font-black ${kiwify?.webhook_connected && kiwify?.credentials_configured ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{kiwify?.webhook_connected && kiwify?.credentials_configured ? "Conectada" : "Configurar"}</span>
            </div>
            <div className="mt-4 rounded-xl bg-[#f4f7f0] p-3 text-[11px] font-bold break-all">{kiwify?.webhook_url || "Carregando URL do webhook..."}</div>
            <form onSubmit={connectKiwify} className="mt-4 grid gap-3">
              <label className="text-xs font-black">Client ID da API<input required name="client_id" value={kiwifyClientId} onChange={(e) => setKiwifyClientId(e.target.value)} placeholder="Copie em Kiwify > Apps > API > client_id" className="mt-2 w-full rounded-xl border border-black/10 px-3 py-2.5 text-xs font-normal outline-none focus:border-[#91c51d]" /></label>
              <label className="text-xs font-black">Client Secret da API<input required={!kiwify?.client_secret_configured} name="client_secret" type="password" value={kiwifyClientSecret} onChange={(e) => setKiwifyClientSecret(e.target.value)} placeholder={kiwify?.client_secret_configured ? "Secret já salvo — deixe em branco para reutilizar" : "Copie o client_secret da Kiwify"} autoComplete="current-password" className="mt-2 w-full rounded-xl border border-black/10 px-3 py-2.5 text-xs font-normal outline-none focus:border-[#91c51d]" /></label>
              <label className="text-xs font-black">Account ID <span className="font-normal text-[#7b857e]">(não é e-mail)</span><input required name="account_id" value={kiwifyAccountId} onChange={(e) => setKiwifyAccountId(e.target.value)} placeholder="Copie exatamente o account_id exibido em Apps > API" className="mt-2 w-full rounded-xl border border-black/10 px-3 py-2.5 text-xs font-normal outline-none focus:border-[#91c51d]" /></label>
              <button type="submit" disabled={connectingKiwify} aria-busy={connectingKiwify} className="sf-button sf-button-youtube disabled:cursor-wait disabled:opacity-60">{connectingKiwify ? "Validando API e webhook..." : kiwify?.webhook_connected ? "Validar e sincronizar Kiwify" : "Conectar Kiwify automaticamente"}</button>
            </form>
            {kiwifyFeedback.text && <div role="status" aria-live="polite" className={`mt-3 rounded-xl border p-3 text-xs font-bold ${kiwifyFeedback.kind === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : kiwifyFeedback.kind === "error" ? "border-red-200 bg-red-50 text-red-700" : "border-sky-200 bg-sky-50 text-sky-800"}`}>{kiwifyFeedback.text}</div>}
            <p className="mt-3 text-[10px] leading-4 text-[#7b857e]">Após a primeira conexão, as credenciais ficam no volume privado do servidor. O Client Secret não é exibido novamente no navegador. O sistema valida a conta pela API oficial e cria ou atualiza o webhook existente sem duplicar.</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2"><a href={kiwify?.checkout_url} target="_blank" rel="noreferrer" className="rounded-xl bg-[#b8f238] px-4 py-3 text-center text-xs font-black">Assine já</a><a href={kiwify?.upgrade_url} target="_blank" rel="noreferrer" className="rounded-xl bg-[#0d241d] px-4 py-3 text-center text-xs font-black text-white">Upgrade ilimitado</a></div>
          </div>
        </div>

        <div className="sf-card mt-6 p-5">
          <h3 className="font-black">Usuários e assinaturas</h3><p className="mt-1 text-xs text-[#6e7971]">Controle de plano, consumo e canal conectado.</p>
          <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[900px] text-left text-xs"><thead><tr className="border-b border-black/5 text-[#778078]"><th className="p-2">Usuário</th><th className="p-2">Plano</th><th className="p-2">Status</th><th className="p-2">Uso</th><th className="p-2">Valor</th><th className="p-2">YouTube</th><th className="p-2">Ações</th></tr></thead><tbody>{users.filter((u) => u.role !== "superadmin").map((u) => <tr key={u.id} className="border-b border-black/5"><td className="p-2"><strong>{u.display_name}</strong><div className="text-[#778078]">{u.email}</div></td><td className="p-2 font-bold">{u.plan_code}</td><td className="p-2">{u.billing_status}</td><td className="p-2">{u.unlimited ? `${u.jobs_used} / ilimitado` : `${u.jobs_used} / ${u.monthly_job_limit}`}</td><td className="p-2">{money(u.subscription_value_cents)}</td><td className="p-2">{u.youtube_connected ? u.youtube_channel_title || "Conectado" : "Não conectado"}</td><td className="p-2"><div className="flex flex-wrap gap-1"><button onClick={() => void setUnlimited(u, !u.unlimited)} className="rounded-lg bg-[#f0f3ec] px-2 py-1.5 font-black">{u.unlimited ? "Voltar ao limite" : "Ilimitado"}</button><button onClick={() => { const value = window.prompt("Novo limite mensal de processamentos", String(u.monthly_job_limit)); if (value) void updateLimit(u, Number(value)); }} className="rounded-lg bg-[#f0f3ec] px-2 py-1.5 font-black">Limite</button></div></td></tr>)}</tbody></table></div>
        </div>

        {credentials.length > 0 && <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5"><h3 className="font-black text-amber-950">Credenciais aguardando entrega</h3><p className="mt-1 text-xs text-amber-800">Quando SMTP estiver configurado, essas credenciais são enviadas automaticamente. Enquanto isso, entregue-as ao comprador e marque como entregue.</p><div className="mt-4 grid gap-2">{credentials.map((c) => <div key={c.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-3 text-xs"><div><strong>{c.display_name || c.email}</strong><div className="mt-1">Acesso: {c.email}</div><div>Senha inicial: <span className="font-mono font-black">{c.temporary_password}</span></div></div><button onClick={async () => { await adminMarkCredentialDelivered(c.id); await refresh(); }} className="rounded-lg bg-[#111815] px-3 py-2 font-black text-white">Marcar entregue</button></div>)}</div></div>}
      </div>
    </section>
  );
}
