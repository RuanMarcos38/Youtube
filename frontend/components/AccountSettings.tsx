"use client";

import { FormEvent, useEffect, useState } from "react";
import AdminPanel from "./AdminPanel";
import BrandLogo from "./BrandLogo";
import { authLogout, authMe, createTeamUser, listTeam } from "@/lib/api";
import type { TeamUser, UserProfile } from "@/lib/types";

const ACTIVE_BILLING = new Set(["active", "paid", "trial"]);
const MANAGER_ROLES = new Set(["owner", "admin", "superadmin"]);

function fmtNumber(value: number | null | undefined) {
  return new Intl.NumberFormat("pt-BR").format(Math.round(value || 0));
}

function usageText(used: number | undefined, limit: number | null | undefined, unit: string) {
  if (limit == null) return "Ilimitado";
  return `${fmtNumber(used)} de ${fmtNumber(limit)} ${unit}`;
}

function statusText(value: string) {
  const labels: Record<string, string> = {
    active: "Ativo",
    paid: "Pago",
    trial: "Teste",
    pending: "Pendente",
    past_due: "Regularização pendente",
    inactive: "Inativo",
    canceled: "Cancelado",
    cancelled: "Cancelado",
  };
  return labels[value] || value || "Indefinido";
}

export default function AccountSettings() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [team, setTeam] = useState<TeamUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [teamLoading, setTeamLoading] = useState(false);
  const [teamName, setTeamName] = useState("");
  const [teamEmail, setTeamEmail] = useState("");
  const [teamPassword, setTeamPassword] = useState("");
  const [error, setError] = useState("");
  const [teamError, setTeamError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const profile = await authMe();
      setUser(profile);
      if (MANAGER_ROLES.has(profile.role)) {
        setTeamLoading(true);
        try {
          setTeam(await listTeam());
        } finally {
          setTeamLoading(false);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar sua conta.");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function logout() {
    await authLogout().catch(() => undefined);
    window.location.assign("/");
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

  if (loading) {
    return <main className="grid min-h-screen place-items-center bg-[#f7f7f7] text-sm font-semibold text-[#111]">Carregando configurações...</main>;
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[#f7f7f7] px-4 py-10 text-[#111] md:px-8">
        <div className="mx-auto max-w-3xl rounded-2xl border border-[#e6e6e6] bg-white p-8 shadow-sm">
          <BrandLogo size="md" />
          <h1 className="mt-8 text-3xl font-black">Entre para acessar configurações</h1>
          <p className="mt-3 text-sm leading-6 text-[#666]">{error || "As configurações de conta, planos e assinaturas ficam disponíveis depois do login."}</p>
          <a href="/" className="sf-button sf-button-primary mt-6 w-fit">Entrar no ShortsFlow</a>
        </div>
      </main>
    );
  }

  const canManageTeam = MANAGER_ROLES.has(user.role);
  const isSuperadmin = user.role === "superadmin";
  const billingActive = user.role === "superadmin" || ACTIVE_BILLING.has(user.billing_status);
  const unlimitedAccess = user.unlimited || isSuperadmin;
  const usageLabel = unlimitedAccess ? "Ilimitado" : `${fmtNumber(user.jobs_used)} de ${fmtNumber(user.monthly_job_limit)} processamentos`;
  const usageDetail = unlimitedAccess ? `${fmtNumber(user.jobs_used)} processamentos usados no mês` : "Franquia mensal do plano";

  return (
    <main className="sf-page-main pb-24 xl:pb-10">
      <section className="border-b border-[#e6e6e6] bg-white">
        <div className="sf-container flex flex-col gap-4 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <BrandLogo size="md" />
            <div className="hidden h-10 w-px bg-[#ececec] sm:block" />
            <div className="min-w-0">
              <div className="sf-kicker">Conta e cobrança</div>
              <h1 className="mt-1 text-xl font-semibold leading-tight text-[#111] sm:text-[26px]">Assinaturas, planos e configurações</h1>
            </div>
          </div>
          <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-3 lg:w-auto">
            <a href="/#automacao" className="sf-button sf-button-outline">Abrir dashboard</a>
            <a href="/planos" className="sf-button sf-button-primary">Ver planos</a>
            <button onClick={logout} className="sf-button sf-button-outline">Sair</button>
          </div>
        </div>
      </section>

      <section className="sf-container py-6">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section id="assinatura" className="sf-card p-5">
            <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
              <div>
                <div className="sf-kicker">Assinatura atual</div>
                <h2 className="mt-1 text-2xl font-semibold leading-tight text-[#111]">{user.plan_name || user.plan_code || "Plano atual"}</h2>
                <p className="mt-2 text-sm leading-6 text-[#666]">Esta área concentra cobrança, planos e limites fora do dashboard operacional.</p>
              </div>
              <span className={`w-fit rounded-full px-3 py-1 text-[11px] font-black ${billingActive ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>{statusText(user.billing_status)}</span>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Envios de vídeos</div><div className="mt-1 text-sm font-black">{usageLabel}</div><div className="mt-1 text-[11px] leading-4 text-[#777]">{usageDetail}</div></div>
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Processamento</div><div className="mt-1 text-sm font-black">{usageText(user.processing_minutes_used, user.processing_minutes_limit, "min")}</div></div>
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Shorts</div><div className="mt-1 text-sm font-black">{usageText(user.shorts_used, user.shorts_limit, "Shorts")}</div></div>
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Canais</div><div className="mt-1 text-sm font-black">{usageText(user.channels_used, user.channel_limit, "canais")}</div></div>
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Usuários</div><div className="mt-1 text-sm font-black">{usageText(user.users_used, user.user_limit, "usuários")}</div></div>
            </div>

            <div className="mt-6 grid gap-2 sm:grid-cols-2 lg:flex lg:flex-wrap">
              <a href="/planos" className="sf-button sf-button-primary">Planos e checkout Asaas</a>
              <a href="/#cortes" className="sf-button sf-button-outline">Voltar para publicações</a>
            </div>
          </section>

          <aside className="sf-card p-5">
            <div className="sf-kicker">Acesso</div>
            <h2 className="mt-1 text-xl font-semibold text-[#111]">{user.display_name}</h2>
            <p className="mt-2 break-words text-sm leading-6 text-[#666]">{user.email}</p>
            <div className="mt-5 grid gap-2 text-xs font-bold">
              <div className="flex items-center justify-between rounded-lg bg-[#f7f7f7] px-3 py-2"><span>Perfil</span><span>{user.role}</span></div>
              <div className="flex items-center justify-between rounded-lg bg-[#f7f7f7] px-3 py-2"><span>YouTube</span><span>{user.channels_used || 0} canal(is)</span></div>
              <div className="flex items-center justify-between rounded-lg bg-[#f7f7f7] px-3 py-2"><span>Provedor</span><span>{user.billing_provider || "ShortsFlow"}</span></div>
            </div>
          </aside>
        </div>

        {canManageTeam && (
          <section id="configuracoes" className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
            <div className="sf-card p-5">
              <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
                <div>
                  <div className="sf-kicker">Configurações de perfis</div>
                  <h2 className="mt-1 text-xl font-semibold text-[#111]">Perfis desta área de trabalho</h2>
                  <p className="mt-1 text-xs leading-5 text-[#6e7971]">Cada perfil entra com sua própria senha e conecta seu próprio canal do YouTube.</p>
                </div>
                {teamLoading && <span className="text-xs font-bold text-[#777]">Carregando...</span>}
              </div>
              <div className="mt-4 grid gap-2">
                {team.map((member) => (
                  <div key={member.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#e6e6e6] bg-[#f7f7f7] p-3 text-xs">
                    <div><strong>{member.display_name}</strong><div className="mt-1 text-[#6e7971]">{member.email} · {member.role}</div></div>
                    <span className={`rounded-full px-2.5 py-1 font-bold ${member.youtube_connected ? "bg-red-50 text-red-700" : "bg-[#eeeeee] text-[#666]"}`}>{member.youtube_connected ? member.youtube_channel_title || "YouTube conectado" : "Sem canal"}</span>
                  </div>
                ))}
                {!teamLoading && team.length === 0 && <div className="rounded-xl bg-[#f7f7f7] p-4 text-sm text-[#777]">Nenhum perfil adicional cadastrado.</div>}
              </div>
            </div>

            <form onSubmit={addProfile} className="sf-card p-5 text-[#111]">
              <h3 className="font-black">Criar novo perfil</h3>
              <div className="mt-4 grid gap-3">
                <input required placeholder="Nome" value={teamName} onChange={(e) => setTeamName(e.target.value)} className="sf-input px-3 py-2.5" />
                <input required type="email" placeholder="E-mail" value={teamEmail} onChange={(e) => setTeamEmail(e.target.value)} className="sf-input px-3 py-2.5" />
                <input required minLength={8} type="password" placeholder="Senha inicial" value={teamPassword} onChange={(e) => setTeamPassword(e.target.value)} className="sf-input px-3 py-2.5" />
                {teamError && <div className="rounded-xl bg-red-50 p-3 text-xs font-bold text-red-700">{teamError}</div>}
                <button className="sf-button sf-button-youtube">Adicionar perfil</button>
              </div>
            </form>
          </section>
        )}
      </section>

      {isSuperadmin && <AdminPanel onClose={() => window.location.assign("/#automacao")} />}
    </main>
  );
}
