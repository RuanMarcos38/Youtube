"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import BrandLogo from "./BrandLogo";
import { createPlanCheckout, getBillingPlans, getCurrentUser, registerTrial } from "@/lib/billing-api";
import type { BillingPlan, BillingPlansResponse, UserProfile } from "@/lib/types";

const PAID_PLAN_CODES = new Set(["creator", "pro", "business", "agency"]);

function money(cents: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(cents / 100);
}

function usageText(used: number | undefined, limit: number | null | undefined, unit: string) {
  if (limit == null) return "Ilimitado";
  return `${used || 0} de ${limit} ${unit}`;
}

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export default function PricingPlans() {
  const [catalog, setCatalog] = useState<BillingPlansResponse | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [cycle, setCycle] = useState<"monthly" | "yearly">("monthly");
  const [loadingCode, setLoadingCode] = useState("");
  const [pendingPlan, setPendingPlan] = useState("");
  const [error, setError] = useState("");
  const [paymentNotice, setPaymentNotice] = useState("");
  const [paymentSyncing, setPaymentSyncing] = useState(false);
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [registering, setRegistering] = useState(false);
  const registerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void getBillingPlans().then(setCatalog).catch((err) => setError(err instanceof Error ? err.message : "Não foi possível carregar os planos."));
    void getCurrentUser().then(setUser).catch(() => setUser(null));
  }, []);

  useEffect(() => {
    const checkout = new URLSearchParams(window.location.search).get("checkout");
    if (!checkout) return;

    if (checkout === "cancel") {
      setPaymentNotice("Pagamento cancelado. Nenhuma alteração foi feita no seu plano atual.");
      window.history.replaceState({}, "", "/planos");
      return;
    }
    if (checkout === "expired") {
      setPaymentNotice("O checkout expirou sem pagamento. Seu plano atual foi mantido.");
      window.history.replaceState({}, "", "/planos");
      return;
    }
    if (checkout !== "success") return;

    let stopped = false;
    setPaymentSyncing(true);
    setPaymentNotice("Pagamento concluído. Aguardando a confirmação financeira para liberar seu plano automaticamente...");

    async function synchronizePaidPlan() {
      // O retorno do checkout nunca ativa acesso sozinho. Esta tela apenas
      // consulta o backend até o webhook autenticado do Asaas confirmar o plano.
      for (let attempt = 0; attempt < 60 && !stopped; attempt += 1) {
        try {
          const current = await getCurrentUser();
          if (stopped) return;
          setUser(current);
          const paid = current.billing_provider === "asaas"
            && ["active", "paid"].includes(current.billing_status)
            && PAID_PLAN_CODES.has(current.plan_code);
          if (paid) {
            setPaymentSyncing(false);
            setPaymentNotice(`Pagamento confirmado. Plano ${current.plan_name || current.plan_code} liberado automaticamente.`);
            window.history.replaceState({}, "", "/planos");
            return;
          }
        } catch {
          // Durante o retorno do checkout o deploy/rede pode oscilar por alguns
          // segundos. A próxima consulta continua sem transformar callback em
          // confirmação de pagamento.
        }
        await wait(2000);
      }
      if (!stopped) {
        setPaymentSyncing(false);
        setPaymentNotice("O pagamento foi concluído e a confirmação do Asaas ainda está em processamento. Esta página continuará reconhecendo o plano ao ser atualizada, sem necessidade de um novo pagamento.");
      }
    }

    void synchronizePaidPlan();
    return () => {
      stopped = true;
    };
  }, []);

  const paidPlans = (catalog?.plans || []).filter((plan) => plan.code !== "trial");
  const trial = (catalog?.plans || []).find((plan) => plan.code === "trial");
  const activeAsaas = Boolean(user && user.billing_provider === "asaas" && ["active", "paid", "past_due"].includes(user.billing_status));

  async function openCheckout(plan: BillingPlan, currentUser = user) {
    setError("");
    if (!currentUser) {
      setPendingPlan(plan.code);
      registerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (currentUser.billing_provider === "asaas" && ["active", "paid", "past_due"].includes(currentUser.billing_status)) {
      setError("Sua assinatura Asaas já está vinculada. A troca de plano é bloqueada nesta tela para evitar uma segunda cobrança recorrente.");
      return;
    }
    if (!catalog?.asaas_enabled) {
      setError("O checkout está temporariamente indisponível. A integração de pagamento ainda precisa ser habilitada no servidor.");
      return;
    }
    setLoadingCode(plan.code);
    try {
      const result = await createPlanCheckout(plan.code, cycle);
      window.location.assign(result.checkout_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível abrir o checkout.");
      setLoadingCode("");
    }
  }

  async function createAccount(event: FormEvent) {
    event.preventDefault();
    setError("");
    setRegistering(true);
    try {
      const created = await registerTrial(name, email, password, company);
      setUser(created);
      const selected = paidPlans.find((plan) => plan.code === pendingPlan);
      if (selected) {
        await openCheckout(selected, created);
      } else {
        window.location.assign("/");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar a conta.");
    } finally {
      setRegistering(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f7f7f7] px-4 py-8 text-[#111] md:px-8 md:py-12">
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <a href="/" aria-label="Voltar ao ShortsFlow"><BrandLogo size="sm" /></a>
          <div className="flex items-center gap-3 text-sm font-bold">
            {user ? <span className="hidden text-[#6e7971] sm:inline">{user.display_name} · {user.plan_name || user.plan_code}</span> : <a href="/" className="rounded-xl border border-black/10 bg-white px-4 py-2.5">Já tenho conta</a>}
            <a href="/" className="rounded-xl bg-[#111] px-4 py-2.5 text-white">Abrir ShortsFlow</a>
          </div>
        </header>

        <section className="mx-auto mt-14 max-w-3xl text-center">
          <div className="inline-flex rounded-full bg-red-50 px-3 py-1 text-[11px] font-black uppercase tracking-wide text-red-700">Preço de fundador</div>
          <h1 className="mt-5 text-4xl font-black leading-tight md:text-6xl">Transforme horas de conteúdo em Shorts prontos e publicados automaticamente.</h1>
          <p className="mx-auto mt-5 max-w-2xl text-sm leading-7 text-[#626262] md:text-base">Escolha o volume ideal de processamento, Shorts, canais e usuários. 1 crédito equivale a 1 minuto de vídeo original processado.</p>
          <div className="mt-8 inline-flex rounded-xl border border-black/10 bg-white p-1 shadow-sm">
            <button onClick={() => setCycle("monthly")} className={`rounded-lg px-5 py-2.5 text-sm font-black ${cycle === "monthly" ? "bg-[#111] text-white" : "text-[#666]"}`}>Mensal</button>
            <button onClick={() => setCycle("yearly")} className={`rounded-lg px-5 py-2.5 text-sm font-black ${cycle === "yearly" ? "bg-[#111] text-white" : "text-[#666]"}`}>Anual · pague 10 e use 12</button>
          </div>
        </section>

        {paymentNotice && (
          <div className={`mx-auto mt-8 max-w-3xl rounded-xl border p-4 text-center text-sm font-bold ${paymentSyncing ? "border-amber-200 bg-amber-50 text-amber-800" : "border-[#ddecbb] bg-white text-[#52720f]"}`}>
            {paymentNotice}
          </div>
        )}

        {trial && (
          <section className="mt-10 grid items-center gap-5 rounded-2xl border border-[#ddecbb] bg-white p-6 shadow-sm md:grid-cols-[1fr_auto] md:p-8">
            <div>
              <div className="text-xs font-black uppercase text-[#729b19]">Teste grátis · uso único</div>
              <h2 className="mt-1 text-2xl font-black">{trial.name}: {trial.processing_minutes_limit} min + {trial.shorts_limit} Shorts</h2>
              <p className="mt-2 text-sm leading-6 text-[#666]">Crie sua conta sem cobrança e valide o fluxo antes de escolher um plano pago. A franquia de teste não renova mensalmente.</p>
            </div>
            {!user ? (
              <button onClick={() => registerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })} className="rounded-xl bg-[#b8f238] px-6 py-3 text-sm font-black">Começar grátis</button>
            ) : user.plan_code === "trial" ? (
              <div className="rounded-xl bg-[#edf8d6] px-5 py-3 text-center text-sm font-black text-[#52720f]">Teste grátis ativo</div>
            ) : (
              <div className="max-w-[280px] rounded-xl bg-[#f4f4f4] px-5 py-3 text-center">
                <div className="text-sm font-black">Teste grátis disponível para novas contas</div>
                <div className="mt-1 text-[11px] font-bold leading-4 text-[#777]">Sua conta atual permanece em {user.plan_name || user.plan_code} e não será rebaixada para o teste.</div>
              </div>
            )}
          </section>
        )}

        {user && (
          <section className="mt-6 rounded-2xl border border-[#e6e6e6] bg-white p-6 shadow-sm md:p-8">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <div className="text-xs font-black uppercase text-red-700">Seu consumo</div>
                <h2 className="mt-1 text-2xl font-black">{user.plan_name || user.plan_code}</h2>
              </div>
              <div className="rounded-full bg-[#f4f4f4] px-3 py-1.5 text-xs font-black">Status: {user.billing_status}</div>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Processamento</div><div className="mt-1 text-sm font-black">{usageText(user.processing_minutes_used, user.processing_minutes_limit, "min")}</div></div>
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Shorts</div><div className="mt-1 text-sm font-black">{usageText(user.shorts_used, user.shorts_limit, "Shorts")}</div></div>
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Canais</div><div className="mt-1 text-sm font-black">{usageText(user.channels_used, user.channel_limit, "canais")}</div></div>
              <div className="rounded-xl bg-[#f7f7f7] p-4"><div className="text-[10px] font-black uppercase text-[#777]">Usuários</div><div className="mt-1 text-sm font-black">{usageText(user.users_used, user.user_limit, "usuários")}</div></div>
            </div>
            {activeAsaas && <p className="mt-4 text-xs leading-5 text-[#6e7971]">Para sua segurança, esta tela não cria uma segunda assinatura recorrente enquanto existir uma assinatura Asaas ativa ou pendente de regularização.</p>}
          </section>
        )}

        <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {paidPlans.map((plan) => {
            const price = cycle === "monthly" ? plan.monthly_price_cents : plan.yearly_price_cents;
            const currentPlan = Boolean(user && user.plan_code === plan.code);
            return (
              <article key={plan.code} className={`relative flex min-h-[570px] flex-col rounded-2xl border bg-white p-6 shadow-sm ${plan.featured ? "border-[#111] ring-2 ring-[#b8f238]" : "border-[#e6e6e6]"}`}>
                {plan.featured && <span className="absolute -top-3 left-5 rounded-full bg-[#111] px-3 py-1 text-[10px] font-black uppercase text-white">Mais escolhido</span>}
                <h2 className="text-2xl font-black">{plan.name}</h2>
                <p className="mt-2 min-h-12 text-xs leading-5 text-[#707070]">{plan.description}</p>
                <div className="mt-6">
                  <strong className="text-3xl font-black">{money(price)}</strong>
                  <span className="text-xs font-bold text-[#777]"> /{cycle === "monthly" ? "mês" : "ano"}</span>
                </div>
                {cycle === "yearly" && <div className="mt-1 text-[11px] font-bold text-[#729b19]">Pague 10 meses e use 12. Equivale a {money(Math.round(price / 12))}/mês</div>}
                {plan.featured && <div className="mt-2 text-[11px] font-black text-red-700">Plano âncora de lançamento</div>}

                <div className="mt-6 grid gap-2 rounded-xl bg-[#f7f7f7] p-4 text-xs font-bold">
                  <div>{plan.processing_minutes_limit.toLocaleString("pt-BR")} minutos/mês</div>
                  <div>{plan.shorts_limit.toLocaleString("pt-BR")} Shorts/mês</div>
                  <div>{plan.channel_limit} canal(is) do YouTube</div>
                  <div>{plan.user_limit} usuário(s)</div>
                  <div className="text-[10px] text-[#777]">1 crédito = 1 minuto processado</div>
                </div>

                <div className="mt-5 flex-1 space-y-2 text-xs leading-5 text-[#555]">
                  {plan.features.map((feature) => <div key={feature} className="flex gap-2"><span className="font-black text-[#729b19]">✓</span><span>{feature}</span></div>)}
                </div>

                <button disabled={loadingCode === plan.code || activeAsaas || paymentSyncing} onClick={() => void openCheckout(plan)} className={`mt-6 rounded-xl px-5 py-3 text-sm font-black disabled:opacity-50 ${plan.featured ? "bg-[#111] text-white" : "bg-[#b8f238] text-[#111]"}`}>
                  {paymentSyncing ? "Confirmando pagamento..." : loadingCode === plan.code ? "Abrindo checkout..." : currentPlan ? "Plano atual" : activeAsaas ? "Troca protegida" : user ? `Assinar ${plan.name}` : "Criar conta e assinar"}
                </button>
              </article>
            );
          })}
        </section>

        <div className="mt-5 text-center text-xs font-bold text-[#777]">Canal adicional: + {money(catalog?.extra_channel_price_cents || 2990)}/mês, sujeito à disponibilidade do plano.</div>

        {!user && (
          <section ref={registerRef} className="mx-auto mt-14 max-w-xl rounded-2xl border border-[#e6e6e6] bg-white p-6 shadow-sm md:p-8">
            <div className="text-xs font-black uppercase text-red-700">Criar conta</div>
            <h2 className="mt-2 text-2xl font-black">Comece no teste gratuito</h2>
            <p className="mt-2 text-sm leading-6 text-[#666]">Ao criar a conta você recebe o plano Teste. Se escolheu um plano pago acima, o checkout abre em seguida.</p>
            <form onSubmit={createAccount} className="mt-6 grid gap-3">
              <input required minLength={2} placeholder="Seu nome" value={name} onChange={(e) => setName(e.target.value)} className="rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" />
              <input placeholder="Empresa (opcional)" value={company} onChange={(e) => setCompany(e.target.value)} className="rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" />
              <input required type="email" placeholder="Seu melhor e-mail" value={email} onChange={(e) => setEmail(e.target.value)} className="rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" />
              <input required minLength={8} type="password" placeholder="Crie uma senha (mín. 8 caracteres)" value={password} onChange={(e) => setPassword(e.target.value)} className="rounded-xl border border-black/10 px-4 py-3 text-sm outline-none focus:border-[#91c51d]" />
              <button disabled={registering} className="mt-1 rounded-xl bg-[#111] px-5 py-3.5 text-sm font-black text-white disabled:opacity-50">{registering ? "Criando conta..." : pendingPlan ? "Criar conta e continuar para pagamento" : "Criar conta grátis"}</button>
            </form>
          </section>
        )}

        {error && <div className="mx-auto mt-6 max-w-2xl rounded-xl border border-red-200 bg-red-50 p-4 text-center text-sm font-bold text-red-700">{error}</div>}

        <footer className="py-12 text-center text-xs text-[#777]">Cobrança recorrente segura via Asaas. O acesso pago é liberado somente após a confirmação financeira recebida pelo webhook.</footer>
      </div>
    </main>
  );
}