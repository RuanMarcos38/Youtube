"use client";

import { FormEvent, useEffect, useState } from "react";
import AdminPanel from "./AdminPanel";
import Dashboard from "./Dashboard";
import BrandLogo from "./BrandLogo";
import { authActivate, authLogin, authLogout, authMe, createTeamUser, listTeam, publicConfig } from "@/lib/api";
import type { PublicConfig, TeamUser, UserProfile } from "@/lib/types";

const CHECKOUT = "https://pay.kiwify.com.br/tBv68U5";
const UPGRADE = "https://pay.kiwify.com.br/8n30IZ9";

const DEFAULT_CONFIG: PublicConfig = {
  brand_name: "ShortsFlow AI",
  marketing_badge: "Shorts com Inteligência Artificial",
  marketing_headline: "Transforme vídeos do YouTube em Shorts prontos para publicar.",
  marketing_description: "A IA encontra os melhores momentos do vídeo, cria cortes verticais 9:16, gera legendas, títulos, descrições, copy e tags e deixa cada Short pronto para revisão e publicação.",
  benefits: [
    "Cortes selecionados automaticamente pela IA",
    "Formato vertical 9:16 com legendas",
    "Títulos, descrições, copy e tags gerados por IA",
    "Fluxo de revisão e publicação no YouTube",
  ],
  login_title: "Entrar no ShortsFlow",
  login_description: "Entre para criar, revisar e gerenciar seus Shorts com Inteligência Artificial.",
  checkout_url: CHECKOUT,
  upgrade_url: UPGRADE,
  base_plan_job_limit: 10,
};

const ACTIVE_BILLING = new Set(["active", "paid", "trial"]);

function MarketingHeadline({ text }: { text: string }) {
  const highlight = "Shorts prontos para publicar";
  const index = text.toLowerCase().indexOf(highlight.toLowerCase());
  if (index < 0) return <>{text}</>;
  const before = text.slice(0, index);
  const match = text.slice(index, index + highlight.length);
  const after = text.slice(index + highlight.length);
  return <>{before}<span className="text-[#b8f238]">{match}</span>{after}</>;
}

export default function SaasApp() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [config, setConfig] = useState<PublicConfig>(DEFAULT_CONFIG);
  const [checking, setChecking] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [activationOpen, setActivationOpen] = useState(false);
  const [activationEmail, setActivationEmail] = useState("");
  const [activationOrder, setActivationOrder] = useState("");
  const [activationPassword, setActivationPassword] = useState("");
  const [activationError, setActivationError] = useState("");
  const [activationLoading, setActivationLoading] = useState(false);
  const [profilesOpen, setProfilesOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [team, setTeam] = useState<TeamUser[]>([]);
  const [teamName, setTeamName] = useState("");
  const [teamEmail, setTeamEmail] = useState("");
  const [teamPassword, setTeamPassword] = useState("");
  const [teamError, setTeamError] = useState("");

  useEffect(() => {
    void publicConfig().then(setConfig).catch(() => setConfig(DEFAULT_CONFIG));
    authMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await authLogin(email, password);
      setUser(result);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível acessar sua conta.");
    } finally {
      setLoading(false);
    }
  }

  async function activate(event: FormEvent) {
    event.preventDefault();
    setActivationLoading(true);
    setActivationError("");
    try {
      const result = await authActivate(activationEmail, activationOrder, activationPassword);
      setUser(result);
      setActivationPassword("");
    } catch (err) {
      setActivationError(err instanceof Error ? err.message : "Não foi possível ativar o acesso.");
    } finally {
      setActivationLoading(false);
    }
  }

  async function logout() {
    await authLogout().catch(() => undefined);
    setUser(null);
    setProfilesOpen(false);
    setAdminOpen(false);
  }

  async function openProfiles() {
    const next = !profilesOpen;
    setProfilesOpen(next);
    setTeamError("");
    if (next && user && ["owner", "admin", "superadmin"].includes(user.role)) {
      try {
        setTeam(await listTeam());
      } catch (err) {
        setTeamError(err instanceof Error ? err.message : "Falha ao carregar perfis.");
      }
    }
  }

  async function addProfile(event: FormEvent) {
    event.preventDefault();
    setTeamError("");
    try {
      await createTeamUser(teamName, teamEmail, teamPassword, "member");
      setTeam(await listTeam());
      setTeamName("");
      setTeamEmail("");
      setTeamPassword("");
    } catch (err) {
      setTeamError(err instanceof Error ? err.message : "Falha ao criar perfil.");
    }
  }

  if (checking) {
    return <main className="grid min-h-screen place-items-center bg-[#f7f7f7] font-sans text-[#111]"><div className="text-sm font-semibold">Carregando {config.brand_name}...</div></main>;
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[#f7f7f7] px-4 py-10 text-[#111] md:py-16">
        <div className="mx-auto grid max-w-6xl overflow-hidden rounded-2xl border border-[#e6e6e6] bg-white shadow-[0_24px_90px_rgba(17,17,17,.08)] lg:grid-cols-[1.05fr_.95fr]">
          <section className="border-b border-[#e6e6e6] bg-white p-8 text-[#111] md:p-12 lg:border-b-0 lg:border-r">
            <BrandLogo size="lg" className="max-w-[230px]" />
            <div className="mt-8 text-xs font-bold uppercase leading-5 text-[#ff0000]">{config.marketing_badge}</div>
            <h1 className="mt-12 max-w-lg text-4xl font-black leading-tight md:text-5xl"><MarketingHeadline text={config.marketing_headline} /></h1>
            <p className="mt-5 max-w-lg text-sm leading-7 text-[#5f5f5f]">{config.marketing_description}</p>
            <div className="mt-8 grid gap-3 text-sm font-bold text-[#333]">
              {config.benefits.slice(0, 4).map((benefit) => <div key={benefit}>✓ {benefit}</div>)}
            </div>
            <a href={config.checkout_url || CHECKOUT} target="_blank" rel="noreferrer" className="sf-button sf-button-youtube mt-10">Assine já</a>
          </section>

          <section className="p-8 md:p-12">
            <div className="mb-8 inline-flex rounded-full bg-red-50 px-3 py-1 text-[11px] font-black uppercase leading-4 text-red-700">Área do assinante</div>
            <h2 className="text-2xl font-black">{config.login_title}</h2>
            <p className="mt-2 text-sm leading-6 text-[#6e7971]">{config.login_description}</p>

            <form onSubmit={submit} className="mt-8 space-y-4">
              <label className="block text-xs font-black">E-mail<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" /></label>
              <label className="block text-xs font-black">Senha<input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" /></label>
              {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{error}</div>}
              <button disabled={loading} className="sf-button sf-button-primary w-full disabled:opacity-50">{loading ? "Aguarde..." : "Entrar no ShortsFlow"}</button>
            </form>

            <div className="mt-6 grid gap-2 sm:grid-cols-2">
              <a className="sf-button sf-button-youtube" href={config.checkout_url || CHECKOUT} target="_blank" rel="noreferrer">Assine já</a>
              <button onClick={() => setActivationOpen((value) => !value)} className="sf-button sf-button-outline">Já pagou? Ativar acesso</button>
            </div>

            {activationOpen && <form onSubmit={activate} className="mt-5 rounded-2xl border border-[#ddecbb] bg-[#f8faf5] p-5">
              <h3 className="font-black">Ativar compra aprovada</h3>
              <p className="mt-1 text-xs leading-5 text-[#6e7971]">Depois que o pagamento aparecer como aprovado, informe o mesmo e-mail da compra e o código do pedido recebido no comprovante/e-mail da compra. Você escolhe sua própria senha.</p>
              <div className="mt-4 grid gap-3">
                <input required type="email" placeholder="E-mail usado na compra" value={activationEmail} onChange={(e) => setActivationEmail(e.target.value)} className="rounded-xl border border-black/10 bg-white px-3 py-3 text-sm outline-none focus:border-[#91c51d]" />
                <input required placeholder="Código do pedido" value={activationOrder} onChange={(e) => setActivationOrder(e.target.value)} className="rounded-xl border border-black/10 bg-white px-3 py-3 text-sm outline-none focus:border-[#91c51d]" />
                <input required minLength={8} type="password" placeholder="Crie sua senha (mín. 8 caracteres)" value={activationPassword} onChange={(e) => setActivationPassword(e.target.value)} className="rounded-xl border border-black/10 bg-white px-3 py-3 text-sm outline-none focus:border-[#91c51d]" />
                {activationError && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{activationError}</div>}
                <button disabled={activationLoading} className="rounded-xl bg-[#111] px-4 py-3 text-sm font-black text-white disabled:opacity-50">{activationLoading ? "Validando pagamento..." : "Ativar meu acesso"}</button>
              </div>
            </form>}
          </section>
        </div>
      </main>
    );
  }

  const billingActive = user.role === "superadmin" || ACTIVE_BILLING.has(user.billing_status);
  const usageLabel = user.unlimited ? `${user.jobs_used} processamentos • ilimitado` : `${user.jobs_used}/${user.monthly_job_limit} processamentos`;

  return (
    <div className="min-h-screen bg-[#f7f7f7]">
      <div className="sticky top-0 z-50 border-b border-[#e6e6e6] bg-white px-4 py-2.5 text-[#111] shadow-sm md:px-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 text-xs">
          <a href="/#automacao" className="flex items-center">
            <BrandLogo size="sm" />
          </a>
          <div className="flex items-center gap-2">
            {!billingActive && <a href={user.checkout_url || config.checkout_url || CHECKOUT} target="_blank" rel="noreferrer" className="sf-button sf-button-youtube min-h-9 px-3 py-2">Assine já</a>}
            {billingActive && !user.unlimited && user.role !== "superadmin" && <a href={user.upgrade_url || config.upgrade_url || UPGRADE} target="_blank" rel="noreferrer" className="sf-button sf-button-youtube min-h-9 px-3 py-2">Upgrade ilimitado</a>}
            {user.role === "superadmin" && <button onClick={() => setAdminOpen((value) => !value)} className="sf-button sf-button-primary min-h-9 px-3 py-2">Administrador</button>}
            {["owner", "admin", "superadmin"].includes(user.role) && <button onClick={openProfiles} className="sf-button sf-button-outline min-h-9 px-3 py-2">Perfis e limites</button>}
            <button onClick={logout} className="sf-button sf-button-outline min-h-9 px-3 py-2">Sair</button>
          </div>
        </div>
      </div>

      {adminOpen && user.role === "superadmin" && <AdminPanel onClose={() => setAdminOpen(false)} />}

      {profilesOpen && ["owner", "admin", "superadmin"].includes(user.role) && (
        <section className="border-b border-[#e6e6e6] bg-white px-4 py-6 md:px-8">
          <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[1fr_.8fr]">
            <div>
              <h3 className="font-black">Perfis desta área de trabalho</h3>
              <p className="mt-1 text-xs text-[#6e7971]">Cada perfil entra com sua própria senha e conecta seu próprio canal do YouTube.</p>
              <div className="mt-4 rounded-xl border border-red-100 bg-red-50 p-3 text-xs font-bold text-red-700">Plano atual: {user.plan_code} · uso mensal: {usageLabel}</div>
              <div className="mt-4 grid gap-2">{team.map((member) => <div key={member.id} className="flex items-center justify-between rounded-xl border border-[#e6e6e6] bg-[#f7f7f7] p-3 text-xs"><div><strong>{member.display_name}</strong><div className="mt-1 text-[#6e7971]">{member.email} • {member.role}</div></div><span className={`rounded-full px-2.5 py-1 font-bold ${member.youtube_connected ? "bg-red-50 text-red-700" : "bg-[#eeeeee] text-[#666]"}`}>{member.youtube_connected ? member.youtube_channel_title || "YouTube conectado" : "Sem canal"}</span></div>)}</div>
            </div>
            <form onSubmit={addProfile} className="sf-card p-5 text-[#111]"><h3 className="font-black">Criar novo perfil</h3><div className="mt-4 grid gap-3"><input required placeholder="Nome" value={teamName} onChange={(e) => setTeamName(e.target.value)} className="sf-input px-3 py-2.5" /><input required type="email" placeholder="E-mail" value={teamEmail} onChange={(e) => setTeamEmail(e.target.value)} className="sf-input px-3 py-2.5" /><input required minLength={8} type="password" placeholder="Senha inicial" value={teamPassword} onChange={(e) => setTeamPassword(e.target.value)} className="sf-input px-3 py-2.5" />{teamError && <div className="rounded-xl bg-red-50 p-3 text-xs font-bold text-red-700">{teamError}</div>}<button className="sf-button sf-button-youtube">Adicionar perfil</button></div></form>
          </div>
        </section>
      )}

      {!billingActive ? (
        <main className="mx-auto max-w-4xl px-4 py-16 text-center md:px-8">
          <div className="rounded-[28px] border border-[#ddecbb] bg-white p-10 shadow-sm"><div className="text-xs font-black uppercase leading-5 text-[#6f9700]">Assinatura necessária</div><h1 className="mt-3 text-3xl font-black leading-tight">Seu acesso será liberado após a confirmação do pagamento.</h1><p className="mx-auto mt-4 max-w-2xl text-sm leading-7 text-[#6e7971]">Assim que o pagamento for confirmado, a conta fica ativa. Se você já pagou e recebeu o código do pedido, saia e use “Já pagou? Ativar acesso”.</p><a href={user.checkout_url || config.checkout_url || CHECKOUT} target="_blank" rel="noreferrer" className="mt-7 inline-flex rounded-xl bg-[#b8f238] px-7 py-3.5 text-sm font-black leading-5">Assine já</a></div>
        </main>
      ) : <Dashboard user={user} />}
    </div>
  );
}
