"use client";

import { FormEvent, useEffect, useState } from "react";
import AdminPanel from "./AdminPanel";
import Dashboard from "./Dashboard";
import { authActivate, authLogin, authLogout, authMe, createTeamUser, listTeam } from "@/lib/api";
import type { TeamUser, UserProfile } from "@/lib/types";

const CHECKOUT = "https://pay.kiwify.com.br/tBv68U5";
const UPGRADE = "https://pay.kiwify.com.br/8n30IZ9";

const ACTIVE_BILLING = new Set(["active", "paid", "trial"]);

export default function SaasApp() {
  const [user, setUser] = useState<UserProfile | null>(null);
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
    return <main className="grid min-h-screen place-items-center bg-[#f8faf5] font-sans text-[#111815]"><div className="text-sm font-bold">Carregando ShortsFlow AI...</div></main>;
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[#f8faf5] px-4 py-10 text-[#111815] md:py-16">
        <div className="mx-auto grid max-w-6xl overflow-hidden rounded-[32px] border border-black/5 bg-white shadow-[0_24px_90px_rgba(25,44,31,.12)] lg:grid-cols-[1.05fr_.95fr]">
          <section className="bg-[#0d241d] p-8 text-white md:p-12">
            <div className="text-2xl font-black">ShortsFlow AI</div>
            <div className="mt-2 text-xs font-bold uppercase tracking-[.18em] text-[#b8f238]">SaaS Multi-Tenant</div>
            <h1 className="mt-12 max-w-lg text-4xl font-black leading-tight md:text-5xl">Um perfil, um canal, seus dados isolados.</h1>
            <p className="mt-5 max-w-lg text-sm leading-7 text-white/70">Cada usuário possui login individual, jobs, cortes e conexão própria com o YouTube. Um perfil não acessa nem publica no canal de outro perfil.</p>
            <div className="mt-8 grid gap-3 text-sm font-bold text-white/85">
              <div>✓ Acesso liberado após pagamento aprovado</div>
              <div>✓ PIX liberado assim que a confirmação de pagamento chegar</div>
              <div>✓ Isolamento de jobs, cortes e arquivos</div>
              <div>✓ OAuth do YouTube separado por perfil</div>
            </div>
            <a href={CHECKOUT} target="_blank" rel="noreferrer" className="mt-10 inline-flex rounded-xl bg-[#b8f238] px-6 py-3.5 text-sm font-black text-[#111815]">Assine já</a>
          </section>

          <section className="p-8 md:p-12">
            <div className="mb-8 inline-flex rounded-full bg-[#edf6d9] px-3 py-1 text-[11px] font-black uppercase tracking-[.12em] text-[#5f8500]">Área do assinante</div>
            <h2 className="text-2xl font-black">Entrar no ShortsFlow</h2>
            <p className="mt-2 text-sm leading-6 text-[#6e7971]">Use o login e a senha liberados após a confirmação da compra.</p>

            <form onSubmit={submit} className="mt-8 space-y-4">
              <label className="block text-xs font-black">E-mail<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" /></label>
              <label className="block text-xs font-black">Senha<input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" /></label>
              {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{error}</div>}
              <button disabled={loading} className="w-full rounded-xl bg-[#111815] px-5 py-3.5 text-sm font-black text-white disabled:opacity-50">{loading ? "Aguarde..." : "Entrar no ShortsFlow"}</button>
            </form>

            <div className="mt-6 grid gap-2 sm:grid-cols-2">
              <a className="rounded-xl bg-[#b8f238] px-5 py-3 text-center text-sm font-black text-[#111815]" href={CHECKOUT} target="_blank" rel="noreferrer">Assine já</a>
              <button onClick={() => setActivationOpen((value) => !value)} className="rounded-xl border border-black/10 bg-white px-5 py-3 text-sm font-black">Já pagou? Ativar acesso</button>
            </div>

            {activationOpen && <form onSubmit={activate} className="mt-5 rounded-2xl border border-[#ddecbb] bg-[#f8faf5] p-5">
              <h3 className="font-black">Ativar compra aprovada</h3>
              <p className="mt-1 text-xs leading-5 text-[#6e7971]">Depois que o pagamento aparecer como aprovado, informe o mesmo e-mail da compra e o código do pedido recebido no comprovante/e-mail da compra. Você escolhe sua própria senha.</p>
              <div className="mt-4 grid gap-3">
                <input required type="email" placeholder="E-mail usado na compra" value={activationEmail} onChange={(e) => setActivationEmail(e.target.value)} className="rounded-xl border border-black/10 bg-white px-3 py-3 text-sm outline-none focus:border-[#91c51d]" />
                <input required placeholder="Código do pedido" value={activationOrder} onChange={(e) => setActivationOrder(e.target.value)} className="rounded-xl border border-black/10 bg-white px-3 py-3 text-sm outline-none focus:border-[#91c51d]" />
                <input required minLength={8} type="password" placeholder="Crie sua senha (mín. 8 caracteres)" value={activationPassword} onChange={(e) => setActivationPassword(e.target.value)} className="rounded-xl border border-black/10 bg-white px-3 py-3 text-sm outline-none focus:border-[#91c51d]" />
                {activationError && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{activationError}</div>}
                <button disabled={activationLoading} className="rounded-xl bg-[#0d241d] px-4 py-3 text-sm font-black text-white disabled:opacity-50">{activationLoading ? "Validando pagamento..." : "Ativar meu acesso"}</button>
              </div>
            </form>}
          </section>
        </div>
      </main>
    );
  }

  const billingActive = user.role === "superadmin" || ACTIVE_BILLING.has(user.billing_status);
  const usageLabel = user.unlimited ? `${user.jobs_used} jobs • ilimitado` : `${user.jobs_used}/${user.monthly_job_limit} jobs`;

  return (
    <div className="min-h-screen bg-[#f8faf5]">
      <div className="sticky top-0 z-50 border-b border-black/5 bg-[#0d241d] px-4 py-2.5 text-white shadow-sm md:px-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-3"><strong>{user.display_name}</strong><span className="rounded-full bg-white/10 px-2.5 py-1 text-white/70">{user.role}</span><span className="hidden text-white/50 sm:inline">{user.email}</span><span className="rounded-full bg-[#b8f238]/15 px-2.5 py-1 font-bold text-[#d9ff7d]">{usageLabel}</span></div>
          <div className="flex items-center gap-2">
            {!billingActive && <a href={user.checkout_url || CHECKOUT} target="_blank" rel="noreferrer" className="rounded-lg bg-[#b8f238] px-3 py-2 font-black text-[#111815]">Assine já</a>}
            {billingActive && !user.unlimited && user.role !== "superadmin" && <a href={user.upgrade_url || UPGRADE} target="_blank" rel="noreferrer" className="rounded-lg bg-[#b8f238] px-3 py-2 font-black text-[#111815]">Upgrade ilimitado</a>}
            {user.role === "superadmin" && <button onClick={() => setAdminOpen((value) => !value)} className="rounded-lg bg-[#b8f238] px-3 py-2 font-black text-[#111815]">Administrador</button>}
            {["owner", "admin", "superadmin"].includes(user.role) && <button onClick={openProfiles} className="rounded-lg bg-white/10 px-3 py-2 font-black">Perfis</button>}
            <button onClick={logout} className="rounded-lg border border-white/15 px-3 py-2 font-black">Sair</button>
          </div>
        </div>
      </div>

      {adminOpen && user.role === "superadmin" && <AdminPanel onClose={() => setAdminOpen(false)} />}

      {profilesOpen && ["owner", "admin", "superadmin"].includes(user.role) && (
        <section className="border-b border-black/5 bg-white px-4 py-6 md:px-8">
          <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[1fr_.8fr]">
            <div><h3 className="font-black">Perfis deste workspace</h3><p className="mt-1 text-xs text-[#6e7971]">Cada perfil entra com sua própria senha e conecta seu próprio canal do YouTube.</p><div className="mt-4 grid gap-2">{team.map((member) => <div key={member.id} className="flex items-center justify-between rounded-xl border border-black/5 bg-[#f8faf5] p-3 text-xs"><div><strong>{member.display_name}</strong><div className="mt-1 text-[#6e7971]">{member.email} • {member.role}</div></div><span className={`rounded-full px-2.5 py-1 font-bold ${member.youtube_connected ? "bg-[#eaf8c8] text-[#4b6a00]" : "bg-[#eef0ec] text-[#667068]"}`}>{member.youtube_connected ? member.youtube_channel_title || "YouTube conectado" : "Sem canal"}</span></div>)}</div></div>
            <form onSubmit={addProfile} className="rounded-2xl bg-[#0d241d] p-5 text-white"><h3 className="font-black">Criar novo perfil</h3><div className="mt-4 grid gap-3"><input required placeholder="Nome" value={teamName} onChange={(e) => setTeamName(e.target.value)} className="rounded-xl bg-white px-3 py-2.5 text-sm text-[#111815]" /><input required type="email" placeholder="E-mail" value={teamEmail} onChange={(e) => setTeamEmail(e.target.value)} className="rounded-xl bg-white px-3 py-2.5 text-sm text-[#111815]" /><input required minLength={8} type="password" placeholder="Senha inicial" value={teamPassword} onChange={(e) => setTeamPassword(e.target.value)} className="rounded-xl bg-white px-3 py-2.5 text-sm text-[#111815]" />{teamError && <div className="rounded-xl bg-red-500/15 p-3 text-xs font-bold text-red-100">{teamError}</div>}<button className="rounded-xl bg-[#b8f238] px-4 py-3 text-sm font-black text-[#111815]">Adicionar perfil</button></div></form>
          </div>
        </section>
      )}

      {!billingActive ? (
        <main className="mx-auto max-w-4xl px-4 py-16 text-center md:px-8">
          <div className="rounded-[28px] border border-[#ddecbb] bg-white p-10 shadow-sm"><div className="text-xs font-black uppercase tracking-[.18em] text-[#6f9700]">Assinatura necessária</div><h1 className="mt-3 text-3xl font-black">Seu acesso será liberado após a confirmação do pagamento.</h1><p className="mx-auto mt-4 max-w-2xl text-sm leading-7 text-[#6e7971]">Assim que o webhook de pagamento confirmar <strong>paid</strong>, a conta fica ativa. Se você já pagou e recebeu o código do pedido, saia e use “Já pagou? Ativar acesso”.</p><a href={user.checkout_url || CHECKOUT} target="_blank" rel="noreferrer" className="mt-7 inline-flex rounded-xl bg-[#b8f238] px-7 py-3.5 text-sm font-black">Assine já</a></div>
        </main>
      ) : <Dashboard />}
    </div>
  );
}
