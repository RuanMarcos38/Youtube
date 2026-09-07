"use client";

import { useEffect, useMemo, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type AutoConfig = {
  enabled: boolean;
  keyword: string;
  region: string;
  days: number;
  min_views: number;
  min_likes: number;
  clips_per_source: number;
  daily_target: number;
  publish_youtube: boolean;
  publish_tiktok: boolean;
  publish_start_hour: number;
  publish_end_hour: number;
  timezone: string;
  rights_confirmed: boolean;
  music_usage_confirmed: boolean;
  tiktok_privacy_level: string;
  allow_comment: boolean;
  allow_duet: boolean;
  allow_stitch: boolean;
  max_active_jobs: number;
  last_discovery_at?: string | null;
  last_run_at?: string | null;
  last_selected_video_id?: string | null;
  last_selected_video_title?: string | null;
  last_error?: string | null;
};

type AutoStatus = {
  enabled: boolean;
  active_jobs: number;
  clean_ready: number;
  waiting_caption_removal: number;
  youtube_today: number;
  tiktok_today: number;
  expected_now: number;
  daily_target: number;
  last_run_at?: string | null;
  last_discovery_at?: string | null;
  last_selected_video_id?: string | null;
  last_selected_video_title?: string | null;
  last_error?: string | null;
};

type AutoResponse = { config: AutoConfig; status: AutoStatus };

const fallback: AutoConfig = {
  enabled: false,
  keyword: "marketing digital",
  region: "BR",
  days: 14,
  min_views: 0,
  min_likes: 0,
  clips_per_source: 10,
  daily_target: 15,
  publish_youtube: true,
  publish_tiktok: true,
  publish_start_hour: 8,
  publish_end_hour: 22,
  timezone: "America/Sao_Paulo",
  rights_confirmed: false,
  music_usage_confirmed: false,
  tiktok_privacy_level: "PUBLIC_TO_EVERYONE",
  allow_comment: true,
  allow_duet: false,
  allow_stitch: false,
  max_active_jobs: 2,
};

function formatDate(value?: string | null) {
  if (!value) return "Ainda não executado";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}/api${path}`, {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (response.status === 401) {
    window.location.href = "/";
    throw new Error("Sessão expirada.");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Não foi possível concluir a operação.");
  return payload as T;
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="sf-card-soft min-h-[130px] p-4">
      <div className="sf-label">{label}</div>
      <div className="mt-3 text-3xl font-semibold text-[#111]">{value}</div>
      <div className="mt-2 text-xs leading-5 text-[#777]">{detail}</div>
    </div>
  );
}

function Toggle({ checked, onChange, label, description }: { checked: boolean; onChange: (value: boolean) => void; label: string; description: string }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 rounded-xl border border-[#e6e6e6] bg-white p-4">
      <span>
        <span className="block text-sm font-semibold text-[#111]">{label}</span>
        <span className="mt-1 block text-xs leading-5 text-[#777]">{description}</span>
      </span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="mt-1 h-5 w-5 accent-[#ff0000]" />
    </label>
  );
}

export default function AutomaticModePanel() {
  const [config, setConfig] = useState<AutoConfig>(fallback);
  const [status, setStatus] = useState<AutoStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const activeLabel = config.enabled ? "ATIVADO" : "DESATIVADO";
  const readiness = useMemo(() => {
    if (!config.rights_confirmed) return "Confirme os direitos/licença dos conteúdos para ativar.";
    if (config.publish_tiktok && !config.music_usage_confirmed) return "Confirme a declaração de música do TikTok para ativar.";
    return "Pronto para operar automaticamente.";
  }, [config.rights_confirmed, config.music_usage_confirmed, config.publish_tiktok]);

  async function load(silent = false) {
    if (!silent) setLoading(true);
    try {
      const data = await request<AutoResponse>("/automation");
      setConfig(data.config);
      setStatus(data.status);
      if (!silent) setError("");
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Falha ao carregar o modo automático.");
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), 15000);
    return () => window.clearInterval(timer);
  }, []);

  async function save(nextConfig: AutoConfig = config) {
    setSaving(true); setError(""); setMessage("");
    try {
      const data = await request<AutoResponse>("/automation", {
        method: "PUT",
        body: JSON.stringify({
          enabled: nextConfig.enabled,
          keyword: nextConfig.keyword,
          region: nextConfig.region,
          days: nextConfig.days,
          min_views: nextConfig.min_views,
          min_likes: nextConfig.min_likes,
          daily_target: nextConfig.daily_target,
          publish_youtube: nextConfig.publish_youtube,
          publish_tiktok: nextConfig.publish_tiktok,
          publish_start_hour: nextConfig.publish_start_hour,
          publish_end_hour: nextConfig.publish_end_hour,
          timezone: nextConfig.timezone,
          rights_confirmed: nextConfig.rights_confirmed,
          music_usage_confirmed: nextConfig.music_usage_confirmed,
          tiktok_privacy_level: nextConfig.tiktok_privacy_level,
          allow_comment: nextConfig.allow_comment,
          allow_duet: nextConfig.allow_duet,
          allow_stitch: nextConfig.allow_stitch,
          max_active_jobs: nextConfig.max_active_jobs,
        }),
      });
      setConfig(data.config);
      setStatus(data.status);
      setMessage(data.config.enabled ? "Modo automático salvo e ativo." : "Configuração salva. Modo automático desativado.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar a automação.");
    } finally { setSaving(false); }
  }

  async function toggleEnabled() {
    const next = { ...config, enabled: !config.enabled };
    setConfig(next);
    await save(next);
  }

  async function runNow() {
    setRunning(true); setError(""); setMessage("");
    try {
      await request("/automation/run-now", { method: "POST", body: "{}" });
      await load(true);
      setMessage("Execução automática iniciada. A fila continuará trabalhando sem intervenção manual.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao executar agora.");
    } finally { setRunning(false); }
  }

  if (loading) {
    return <main className="sf-page-main"><section className="sf-container py-10 text-sm font-semibold text-[#555]">Carregando Modo Automático...</section></main>;
  }

  return (
    <main className="sf-page-main pb-24 xl:pb-10">
      <section className="border-b border-[#e6e6e6] bg-white">
        <div className="sf-container flex flex-col gap-4 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="sf-kicker">Automação de ponta a ponta</div>
            <h1 className="mt-1 text-[28px] font-semibold leading-tight text-[#111]">Modo Automático</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#666]">Pesquisa tendências, cria 10 Shorts por vídeo-fonte, remove as legendas geradas pelo ShortsFlow, valida os arquivos e distribui até 15 publicações por dia.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-4 py-2 text-xs font-black ${config.enabled ? "bg-emerald-100 text-emerald-800" : "bg-[#f1f1f1] text-[#666]"}`}>{activeLabel}</span>
            <button onClick={toggleEnabled} disabled={saving} className={`sf-button ${config.enabled ? "sf-button-outline" : "sf-button-youtube"}`}>{saving ? "Salvando..." : config.enabled ? "Desativar" : "Ativar modo automático"}</button>
          </div>
        </div>
      </section>

      {(error || message) && <section className="sf-container pt-5">{error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}{message && <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">{message}</div>}</section>}

      <section className="sf-container py-6">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <Metric label="Meta diária" value={status?.daily_target ?? config.daily_target} detail="Shorts por plataforma/dia" />
          <Metric label="YouTube hoje" value={status?.youtube_today ?? 0} detail={`Esperado até agora: ${status?.expected_now ?? 0}`} />
          <Metric label="TikTok hoje" value={status?.tiktok_today ?? 0} detail={`Esperado até agora: ${status?.expected_now ?? 0}`} />
          <Metric label="Prontos sem legenda" value={status?.clean_ready ?? 0} detail={`${status?.waiting_caption_removal ?? 0} aguardando limpeza`} />
          <Metric label="Processamentos" value={status?.active_jobs ?? 0} detail="Jobs automáticos ativos" />
        </div>

        <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_420px]">
          <div className="space-y-5">
            <div className="sf-card overflow-hidden">
              <div className="border-b border-[#e8e8e8] px-5 py-4">
                <h2 className="text-lg font-semibold text-[#111]">Parâmetros da busca automática</h2>
                <p className="mt-1 text-xs leading-5 text-[#777]">O sistema escolhe os vídeos mais fortes dentro destes filtros e evita reutilizar uma fonte já processada.</p>
              </div>
              <div className="grid gap-4 p-5 md:grid-cols-2">
                <label className="text-xs font-semibold text-[#333] md:col-span-2">Tema ou palavras-chave
                  <input value={config.keyword} onChange={(e) => setConfig({ ...config, keyword: e.target.value })} className="sf-input mt-2 w-full px-3 py-2.5" placeholder="Ex.: marketing digital, negócios, imóveis" />
                </label>
                <label className="text-xs font-semibold text-[#333]">Região
                  <input value={config.region} onChange={(e) => setConfig({ ...config, region: e.target.value.toUpperCase().slice(0, 2) })} className="sf-input mt-2 w-full px-3 py-2.5" />
                </label>
                <label className="text-xs font-semibold text-[#333]">Período analisado
                  <select value={config.days} onChange={(e) => setConfig({ ...config, days: Number(e.target.value) })} className="sf-input mt-2 w-full px-3 py-2.5"><option value={7}>7 dias</option><option value={14}>14 dias</option><option value={30}>30 dias</option><option value={90}>90 dias</option></select>
                </label>
                <label className="text-xs font-semibold text-[#333]">Visualizações mínimas
                  <input type="number" min={0} value={config.min_views} onChange={(e) => setConfig({ ...config, min_views: Math.max(0, Number(e.target.value)) })} className="sf-input mt-2 w-full px-3 py-2.5" />
                </label>
                <label className="text-xs font-semibold text-[#333]">Curtidas mínimas
                  <input type="number" min={0} value={config.min_likes} onChange={(e) => setConfig({ ...config, min_likes: Math.max(0, Number(e.target.value)) })} className="sf-input mt-2 w-full px-3 py-2.5" />
                </label>
                <label className="text-xs font-semibold text-[#333]">Shorts por vídeo-fonte
                  <input value="10" disabled className="sf-input mt-2 w-full bg-[#f5f5f5] px-3 py-2.5 text-[#777]" />
                </label>
                <label className="text-xs font-semibold text-[#333]">Meta diária por plataforma
                  <input type="number" min={1} max={15} value={config.daily_target} onChange={(e) => setConfig({ ...config, daily_target: Math.max(1, Math.min(15, Number(e.target.value))) })} className="sf-input mt-2 w-full px-3 py-2.5" />
                </label>
              </div>
            </div>

            <div className="sf-card overflow-hidden">
              <div className="border-b border-[#e8e8e8] px-5 py-4"><h2 className="text-lg font-semibold text-[#111]">Distribuição automática</h2><p className="mt-1 text-xs leading-5 text-[#777]">As publicações são espaçadas ao longo da janela, em vez de enviar tudo de uma vez.</p></div>
              <div className="grid gap-4 p-5 md:grid-cols-2">
                <Toggle checked={config.publish_youtube} onChange={(value) => setConfig({ ...config, publish_youtube: value })} label="Publicar no YouTube" description="Usa a conexão OAuth já existente. Nenhuma credencial é substituída." />
                <Toggle checked={config.publish_tiktok} onChange={(value) => setConfig({ ...config, publish_tiktok: value })} label="Publicar no TikTok" description="Só publica quando o Direct Post da conta estiver liberado pelo TikTok." />
                <label className="text-xs font-semibold text-[#333]">Começar às
                  <input type="number" min={0} max={23} value={config.publish_start_hour} onChange={(e) => setConfig({ ...config, publish_start_hour: Number(e.target.value) })} className="sf-input mt-2 w-full px-3 py-2.5" />
                </label>
                <label className="text-xs font-semibold text-[#333]">Encerrar até
                  <input type="number" min={1} max={24} value={config.publish_end_hour} onChange={(e) => setConfig({ ...config, publish_end_hour: Number(e.target.value) })} className="sf-input mt-2 w-full px-3 py-2.5" />
                </label>
                <label className="text-xs font-semibold text-[#333]">Processamentos simultâneos automáticos
                  <select value={config.max_active_jobs} onChange={(e) => setConfig({ ...config, max_active_jobs: Number(e.target.value) })} className="sf-input mt-2 w-full px-3 py-2.5"><option value={1}>1 vídeo-fonte</option><option value={2}>2 vídeos-fonte</option></select>
                </label>
                <label className="text-xs font-semibold text-[#333]">Privacidade TikTok
                  <select value={config.tiktok_privacy_level} onChange={(e) => setConfig({ ...config, tiktok_privacy_level: e.target.value })} className="sf-input mt-2 w-full px-3 py-2.5"><option value="PUBLIC_TO_EVERYONE">Público</option><option value="MUTUAL_FOLLOW_FRIENDS">Amigos</option><option value="SELF_ONLY">Somente eu</option></select>
                </label>
              </div>
            </div>

            <div className="sf-card p-5">
              <h2 className="text-lg font-semibold text-[#111]">Autorizações para operação sem intervenção</h2>
              <p className="mt-1 text-xs leading-5 text-[#777]">Estas confirmações são feitas uma vez na ativação. O ShortsFlow não altera tokens, Client ID, Client Secret ou chaves existentes.</p>
              <div className="mt-4 grid gap-3">
                <Toggle checked={config.rights_confirmed} onChange={(value) => setConfig({ ...config, rights_confirmed: value })} label="Direitos/licença/autorização confirmados" description="Confirmo que os conteúdos encontrados pelos parâmetros configurados podem ser reutilizados por mim." />
                <Toggle checked={config.music_usage_confirmed} onChange={(value) => setConfig({ ...config, music_usage_confirmed: value })} label="Declaração de música do TikTok confirmada" description="Confirmo a declaração exigida para os conteúdos que serão publicados automaticamente no TikTok." />
              </div>
              <div className="mt-4 rounded-xl bg-[#f7f7f7] p-4 text-xs font-medium leading-5 text-[#555]">{readiness}</div>
            </div>
          </div>

          <aside className="space-y-5">
            <div className="sf-card p-5">
              <div className="sf-kicker">Fluxo protegido</div>
              <h2 className="mt-1 text-lg font-semibold text-[#111]">Ordem obrigatória</h2>
              <div className="mt-4 space-y-3 text-sm leading-6 text-[#555]">
                <div>1. Buscar vídeos em alta conforme os filtros.</div>
                <div>2. Criar até 10 Shorts por fonte.</div>
                <div>3. Remover a legenda gerada pelo ShortsFlow.</div>
                <div>4. Validar arquivo limpo antes da fila.</div>
                <div>5. Distribuir YouTube e TikTok durante o dia.</div>
                <div>6. Se uma etapa falhar, o vídeo não avança.</div>
              </div>
            </div>

            <div className="sf-card p-5">
              <div className="sf-kicker">Última execução</div>
              <div className="mt-3 text-sm font-semibold text-[#111]">{formatDate(status?.last_run_at)}</div>
              <div className="mt-4 border-t border-[#ededed] pt-4">
                <div className="text-[11px] font-semibold uppercase text-[#777]">Última fonte selecionada</div>
                <div className="mt-1 text-sm font-semibold leading-5 text-[#222]">{status?.last_selected_video_title || "Nenhuma ainda"}</div>
              </div>
              {status?.last_error && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-semibold leading-5 text-amber-900">{status.last_error}</div>}
            </div>

            <div className="sf-card p-5">
              <button onClick={() => save()} disabled={saving} className="sf-button sf-button-primary w-full justify-center">{saving ? "Salvando..." : "Salvar configurações"}</button>
              <button onClick={runNow} disabled={running || !config.enabled} className="sf-button sf-button-outline mt-2 w-full justify-center disabled:opacity-40">{running ? "Executando..." : "Executar agora"}</button>
              <p className="mt-3 text-[11px] leading-5 text-[#777]">O botão “Executar agora” não é necessário no uso normal; o worker verifica o modo automático continuamente.</p>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
