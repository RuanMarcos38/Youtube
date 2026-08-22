"use client";

import { FormEvent, useEffect, useState } from "react";
import Dashboard from "./Dashboard";
import { authLogin, authLogout, authMe, authRegister, createTeamUser, listTeam } from "@/lib/api";
import type { TeamUser, UserProfile } from "@/lib/types";

const CHECKOUT = "https://pay.kiwify.com.br/tBv68U5";

export default function SaasApp() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [checking, setChecking] = useState(true);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [profilesOpen, setProfilesOpen] = useState(false);
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
      const result = mode === "login"
        ? await authLogin(email, password)
        : await authRegister(name, email, password, company);
      setUser(result);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível acessar sua conta.");
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await authLogout().catch(() => undefined);
    setUser(null);
    setProfilesOpen(false);
  }

  async function openProfiles() {
    const next = !profilesOpen;
    setProfilesOpen(next);
    setTeamError("");
    if (next && user && ["owner", "admin"].includes(user.role)) {
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
              <div>✓ Autenticação individual por e-mail e senha</div>
              <div>✓ Isolamento de jobs, cortes e arquivos</div>
              <div>✓ OAuth do YouTube separado por usuário</div>
              <div>✓ Vários usuários simultâneos</div>
            </div>
            <a href={CHECKOUT} target="_blank" rel="noreferrer" className="mt-10 inline-flex rounded-xl bg-[#b8f238] px-5 py-3 text-sm font-black text-[#111815]">Comprar acesso pela Kiwify</a>
          </section>

          <section className="p-8 md:p-12">
            <div className="mb-8 flex rounded-xl bg-[#f1f4ee] p-1">
              <button onClick={() => setMode("login")} className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-black ${mode === "login" ? "bg-white shadow-sm" : "text-[#6d786f]"}`}>Entrar</button>
              <button onClick={() => setMode("register")} className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-black ${mode === "register" ? "bg-white shadow-sm" : "text-[#6d786f]"}`}>Criar conta</button>
            </div>
            <h2 className="text-2xl font-black">{mode === "login" ? "Acesse seu perfil" : "Crie seu ambiente"}</h2>
            <p className="mt-2 text-sm text-[#6e7971]">Sua sessão fica protegida por cookie HttpOnly e os dados são filtrados pelo seu usuário.</p>

            <form onSubmit={submit} className="mt-8 space-y-4">
              {mode === "register" && <>
                <label className="block text-xs font-black">Nome<input required value={name} onChange={(e) => setName(e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" /></label>
                <label className="block text-xs font-black">Empresa / Workspace<input value={company} onChange={(e) => setCompany(e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" /></label>
              </>}
              <label className="block text-xs font-black">E-mail<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" /></label>
              <label className="block text-xs font-black">Senha<input type="password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" /></label>
              {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{error}</div>}
              <button disabled={loading} className="w-full rounded-xl bg-[#111815] px-5 py-3.5 text-sm font-black text-white disabled:opacity-50">{loading ? "Aguarde..." : mode === "login" ? "Entrar no ShortsFlow" : "Criar minha conta"}</button>
            </form>
            <p className="mt-6 text-center text-xs text-[#748078]">Checkout oficial: <a className="font-black text-[#5f8500] underline" href={CHECKOUT} target="_blank" rel="noreferrer">Kiwify</a></p>
          </section>
        </div>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-[#f8faf5]">
      <div className="sticky top-0 z-50 border-b border-black/5 bg-[#0d241d] px-4 py-2.5 text-white shadow-sm md:px-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-3"><strong>{user.display_name}</strong><span className="rounded-full bg-white/10 px-2.5 py-1 text-white/70">{user.role}</span><span className="hidden text-white/50 sm:inline">{user.email}</span></div>
          <div className="flex items-center gap-2">
            <a href={user.checkout_url || CHECKOUT} target="_blank" rel="noreferrer" className="rounded-lg bg-[#b8f238] px-3 py-2 font-black text-[#111815]">Checkout Kiwify</a>
            {["owner", "admin"].includes(user.role) && <button onClick={openProfiles} className="rounded-lg bg-white/10 px-3 py-2 font-black">Perfis</button>}
            <button onClick={logout} className="rounded-lg border border-white/15 px-3 py-2 font-black">Sair</button>
          </div>
        </div>
      </div>

      {profilesOpen && ["owner", "admin"].includes(user.role) && (
        <section className="border-b border-black/5 bg-white px-4 py-6 md:px-8">
          <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[1fr_.8fr]">
            <div><h3 className="font-black">Perfis deste workspace</h3><p className="mt-1 text-xs text-[#6e7971]">Cada perfil entra com sua própria senha e conecta seu próprio canal do YouTube.</p><div className="mt-4 grid gap-2">{team.map((member) => <div key={member.id} className="flex items-center justify-between rounded-xl border border-black/5 bg-[#f8faf5] p-3 text-xs"><div><strong>{member.display_name}</strong><div className="mt-1 text-[#6e7971]">{member.email} • {member.role}</div></div><span className={`rounded-full px-2.5 py-1 font-bold ${member.youtube_connected ? "bg-[#eaf8c8] text-[#4b6a00]" : "bg-[#eef0ec] text-[#667068]"}`}>{member.youtube_connected ? member.youtube_channel_title || "YouTube conectado" : "Sem canal"}</span></div>)}</div></div>
            <form onSubmit={addProfile} className="rounded-2xl bg-[#0d241d] p-5 text-white"><h3 className="font-black">Criar novo perfil</h3><div className="mt-4 grid gap-3"><input required placeholder="Nome" value={teamName} onChange={(e) => setTeamName(e.target.value)} className="rounded-xl bg-white px-3 py-2.5 text-sm text-[#111815]" /><input required type="email" placeholder="E-mail" value={teamEmail} onChange={(e) => setTeamEmail(e.target.value)} className="rounded-xl bg-white px-3 py-2.5 text-sm text-[#111815]" /><input required minLength={8} type="password" placeholder="Senha inicial" value={teamPassword} onChange={(e) => setTeamPassword(e.target.value)} className="rounded-xl bg-white px-3 py-2.5 text-sm text-[#111815]" />{teamError && <div className="rounded-xl bg-red-500/15 p-3 text-xs font-bold text-red-100">{teamError}</div>}<button className="rounded-xl bg-[#b8f238] px-4 py-3 text-sm font-black text-[#111815]">Adicionar perfil</button></div></form>
          </div>
        </section>
      )}

      <Dashboard />
    </div>
  );
}
