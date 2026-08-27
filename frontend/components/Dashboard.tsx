"use client";

import { useEffect, useMemo, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import {
  API_URL,
  approveClip,
  createEditorProjectFromClip,
  createJob,
  getTrending,
  listClips,
  listJobs,
  retryJob,
  updateClipCaptions,
  uploadClip,
  youtubeLiveMetrics,
  youtubeStart,
  youtubeStatus,
} from "@/lib/api";
import type { Clip, Job, TrendingVideo, UserProfile, YouTubeDashboardAlert, YouTubeLiveMetrics } from "@/lib/types";
import BrandLogo from "./BrandLogo";
import LanguageSelector from "./LanguageSelector";
import {
  ArrowIcon,
  CheckIcon,
  CopyIcon,
  PlayIcon,
  RefreshIcon,
  SearchIcon,
  TagsIcon,
  UploadIcon,
  YoutubeIcon,
} from "./Icons";

type SectionId = "automacao" | "configurar" | "processamento" | "cortes";
type CaptionDraft = {
  caption_position: "top" | "middle" | "bottom";
  caption_margin_v: number;
  caption_font_size: number;
  subtitle_srt: string;
};

const captionPositions: Array<{ value: CaptionDraft["caption_position"]; label: string }> = [
  { value: "bottom", label: "Base" },
  { value: "middle", label: "Centro" },
  { value: "top", label: "Topo" },
];

const DEFAULT_CAPTION_POSITION: CaptionDraft["caption_position"] = "bottom";
const DEFAULT_CAPTION_MARGIN = 120;
const DEFAULT_CAPTION_FONT_SIZE = 18;
const CAPTION_MARGIN_MIN = 40;
const CAPTION_MARGIN_MAX = 760;
const ASS_CANVAS_HEIGHT = 1920;

const pipeline = [
  "Preparando",
  "Baixando vídeo",
  "Extraindo áudio",
  "Transcrevendo",
  "Selecionando cortes",
  "Renderizando em 9:16",
  "Gerando legendas",
  "Pronto para revisão",
];

const sections: Array<{ id: SectionId; label: string; description: string }> = [
  { id: "automacao", label: "Painel ao vivo", description: "Métricas, alertas e destaque do canal" },
  { id: "configurar", label: "Criar Shorts", description: "Busca e configuração de cortes" },
  { id: "processamento", label: "Processamentos", description: "Fila e andamento dos processamentos" },
  { id: "cortes", label: "Publicações", description: "Revisão e envio ao YouTube" },
];

const stageIndex: Record<string, number> = {
  queued: 0,
  checking_ffmpeg: 0,
  downloading: 1,
  extracting_audio: 2,
  transcribing: 3,
  selecting_clips: 4,
  rendering: 5,
  ready_for_review: 7,
  failed: -1,
};

function fmtNumber(value: number) {
  return new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
}

function fmtExact(value: number) {
  return new Intl.NumberFormat("pt-BR").format(Math.round(value || 0));
}

function fmtDuration(seconds: number) {
  const min = Math.floor(seconds / 60);
  const sec = Math.round(seconds % 60);
  return `${min}:${String(sec).padStart(2, "0")}`;
}

function fmtDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function sectionFromHash(): SectionId {
  if (typeof window === "undefined") return "automacao";
  const hash = window.location.hash.replace("#", "");
  return sections.some((item) => item.id === hash) ? (hash as SectionId) : "automacao";
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: "Na fila",
    checking_ffmpeg: "Preparando",
    downloading: "Baixando vídeo",
    extracting_audio: "Extraindo áudio",
    transcribing: "Transcrevendo",
    selecting_clips: "Selecionando cortes",
    rendering: "Renderizando",
    ready_for_review: "Pronto para revisão",
    failed: "Falhou",
    ready: "Pronto",
    approved: "Aprovado",
    upload_queued: "Na fila de envio",
    uploading: "Enviando ao YouTube",
    uploaded: "Publicado",
    upload_failed: "Falha no envio",
  };
  return labels[status] || status;
}

function youtubeOauthErrorMessage(reason: string) {
  const normalized = reason.trim().toLowerCase();
  if (normalized === "access_denied") {
    return "Google bloqueou o acesso desta conta. O app OAuth ainda está em modo de teste/não verificado para esse e-mail; adicione o e-mail em usuários de teste no Google Cloud Console ou publique/verifique o app.";
  }
  if (normalized === "oauth_nao_concluido") {
    return "Não foi possível concluir a conexão com o YouTube. Tente novamente escolhendo a conta Google que possui o canal.";
  }
  if (normalized === "oauth_callback_incompleto") {
    return "O Google retornou uma autorização incompleta. Inicie a conexão do YouTube novamente.";
  }
  return reason ? `Google não autorizou a conexão do YouTube: ${reason}.` : "Google não autorizou a conexão do YouTube.";
}

function jobErrorMessage(error: string) {
  const normalized = error.toLowerCase();
  if (
    normalized.includes("rate_limit_exceeded") ||
    normalized.includes("tokens per min") ||
    normalized.includes("request too large")
  ) {
    return "Este processamento foi criado antes da correção para vídeos longos e excedeu o limite da OpenAI. Clique em Tentar novamente para recriar o processamento usando a transcrição otimizada.";
  }
  if (normalized.includes("sign in to confirm") || normalized.includes("cookies") || normalized.includes("not a bot")) {
    return "O YouTube recusou a sessão de download usada neste processamento antigo. A autenticação atual já foi renovada; tente novamente para baixar com a configuração corrigida.";
  }
  return error;
}

function StatusBadge({ status }: { status: string }) {
  const ready = ["ready_for_review", "ready", "approved", "uploaded"].includes(status);
  const failed = ["failed", "upload_failed"].includes(status);
  const cls = failed
    ? "border-red-200 bg-red-50 text-red-700"
    : ready
      ? "border-red-100 bg-red-50 text-red-700"
      : "border-[#e6e6e6] bg-[#f7f7f7] text-[#555]";
  return <span className={`inline-flex rounded-md border px-2 py-1 text-[10px] font-medium ${cls}`}>{statusLabel(status)}</span>;
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="sf-card-soft flex min-h-[156px] min-w-0 flex-col justify-between p-4 sm:p-5">
      <div className="sf-label">{label}</div>
      <div>
        <div className="metric-value sf-metric-number mt-3">{value}</div>
        {detail && <div className="mt-2 text-xs leading-5 text-[#666]">{detail}</div>}
      </div>
    </div>
  );
}

function ProgressBar({ label, value, target, progress }: { label: string; value: string; target: string; progress: number }) {
  const width = Math.min(100, Math.max(0, progress || 0));
  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-1 text-xs leading-5">
        <span className="font-semibold text-[#222]">{label}</span>
        <span className="text-right text-[#666]">{value} / {target}</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#ececec]">
        <div className="h-full rounded-full bg-[#ff0000] transition-all duration-700" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function AlertCard({ alert }: { alert: YouTubeDashboardAlert }) {
  const cls = alert.kind === "success"
    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
    : alert.kind === "warning"
      ? "border-amber-200 bg-amber-50 text-amber-900"
      : "border-[#e8e8e8] bg-white text-[#222]";
  return (
    <div className={`rounded-xl border p-4 ${cls}`}>
      <div className="text-sm font-semibold">{alert.title}</div>
      <div className="mt-1 text-xs leading-5 opacity-80">{alert.detail}</div>
    </div>
  );
}

function captionDraftFromClip(clip: Clip): CaptionDraft {
  const position = captionPositions.some((item) => item.value === clip.caption_position)
    ? clip.caption_position as CaptionDraft["caption_position"]
    : DEFAULT_CAPTION_POSITION;
  return {
    caption_position: position,
    caption_margin_v: Number.isFinite(clip.caption_margin_v) ? clip.caption_margin_v : DEFAULT_CAPTION_MARGIN,
    caption_font_size: Number.isFinite(clip.caption_font_size) ? clip.caption_font_size : DEFAULT_CAPTION_FONT_SIZE,
    subtitle_srt: clip.subtitle_srt || "",
  };
}

function defaultCaptionDraft(clip: Clip): CaptionDraft {
  return {
    caption_position: DEFAULT_CAPTION_POSITION,
    caption_margin_v: DEFAULT_CAPTION_MARGIN,
    caption_font_size: DEFAULT_CAPTION_FONT_SIZE,
    subtitle_srt: clip.subtitle_srt || "",
  };
}

function clampNumber(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function snapCaptionMargin(value: number) {
  return clampNumber(Math.round(value / 20) * 20, CAPTION_MARGIN_MIN, CAPTION_MARGIN_MAX);
}

function captionVerticalPercent(draft: CaptionDraft) {
  if (draft.caption_position === "top") return clampNumber((draft.caption_margin_v / ASS_CANVAS_HEIGHT) * 100, 4, 42);
  if (draft.caption_position === "middle") return 50;
  return clampNumber(100 - (draft.caption_margin_v / ASS_CANVAS_HEIGHT) * 100, 58, 96);
}

function captionPreviewStyle(draft: CaptionDraft): CSSProperties {
  const margin = clampNumber((draft.caption_margin_v / ASS_CANVAS_HEIGHT) * 100, 4, 42);
  if (draft.caption_position === "top") return { top: `${margin}%` };
  if (draft.caption_position === "middle") return { top: "50%", transform: "translateY(-50%)" };
  return { bottom: `${margin}%` };
}

function previewCaptionText(source: string) {
  const text = source
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !/^\d+$/.test(line) && !line.includes("-->"))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  return text.length > 110 ? `${text.slice(0, 107)}...` : text || "Arraste a legenda para ajustar";
}

function CaptionLivePreview({
  draft,
  blocked,
  onChange,
}: {
  draft: CaptionDraft;
  blocked: boolean;
  onChange: (patch: Partial<CaptionDraft>) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const previewText = previewCaptionText(draft.subtitle_srt);

  function updateFromPointer(event: ReactPointerEvent<HTMLDivElement>) {
    if (blocked) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = clampNumber((event.clientY - rect.top) / Math.max(1, rect.height), 0.07, 0.93);
    let caption_position: CaptionDraft["caption_position"] = "middle";
    let caption_margin_v = DEFAULT_CAPTION_MARGIN;

    if (ratio < 0.35) {
      caption_position = "top";
      caption_margin_v = ratio * ASS_CANVAS_HEIGHT;
    } else if (ratio > 0.65) {
      caption_position = "bottom";
      caption_margin_v = (1 - ratio) * ASS_CANVAS_HEIGHT;
    }

    onChange({ caption_position, caption_margin_v: snapCaptionMargin(caption_margin_v) });
  }

  function moveWithKeyboard(direction: -1 | 1) {
    if (blocked) return;
    if (draft.caption_position === "middle") {
      onChange({ caption_position: direction < 0 ? "top" : "bottom", caption_margin_v: DEFAULT_CAPTION_MARGIN });
      return;
    }
    const delta = direction < 0 ? 20 : -20;
    const nextMargin = draft.caption_position === "top" ? draft.caption_margin_v - delta : draft.caption_margin_v + delta;
    onChange({ caption_margin_v: snapCaptionMargin(nextMargin) });
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#667085]">Prévia segura 9:16</span>
        <span className="text-[11px] font-medium text-[#667085]">{Math.round(captionVerticalPercent(draft))}%</span>
      </div>
      <div
        role="slider"
        aria-label="Posição vertical da legenda"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(captionVerticalPercent(draft))}
        tabIndex={blocked ? -1 : 0}
        onPointerDown={(event) => {
          if (blocked) return;
          setDragging(true);
          event.currentTarget.setPointerCapture(event.pointerId);
          updateFromPointer(event);
        }}
        onPointerMove={(event) => {
          if (dragging) updateFromPointer(event);
        }}
        onPointerUp={(event) => {
          setDragging(false);
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => setDragging(false)}
        onKeyDown={(event) => {
          if (event.key === "ArrowUp") {
            event.preventDefault();
            moveWithKeyboard(-1);
          }
          if (event.key === "ArrowDown") {
            event.preventDefault();
            moveWithKeyboard(1);
          }
        }}
        className={`relative mx-auto aspect-[9/16] w-full max-w-[140px] touch-none overflow-hidden rounded-xl border border-[#222] bg-[linear-gradient(180deg,#222,#0b0b0b)] shadow-inner 2xl:max-w-[170px] ${blocked ? "opacity-70" : "cursor-grab active:cursor-grabbing"}`}
      >
        <div className="absolute inset-x-[11%] bottom-[17%] top-[10%] rounded-[10px] border border-dashed border-white/30" />
        <div className="absolute inset-x-[16%] bottom-[18%] h-px bg-white/25" />
        <div className="absolute inset-x-[16%] top-[12%] h-px bg-white/20" />
        <div
          className="absolute left-[10%] right-[10%] rounded-lg bg-black/80 px-2.5 py-1.5 text-center font-black leading-tight text-white shadow-[0_2px_0_rgba(0,0,0,0.8)]"
          style={{ ...captionPreviewStyle(draft), fontSize: `${clampNumber(draft.caption_font_size * 0.72, 11, 22)}px` }}
        >
          {previewText}
        </div>
      </div>
    </div>
  );
}

function CaptionControls({
  clip,
  draft,
  busy,
  onChange,
  onReset,
  onSave,
}: {
  clip: Clip;
  draft: CaptionDraft;
  busy: boolean;
  onChange: (patch: Partial<CaptionDraft>) => void;
  onReset: () => void;
  onSave: () => void;
}) {
  const blocked = ["upload_queued", "uploading", "uploaded"].includes(clip.status);
  return (
    <details className="mt-3 rounded-xl border border-[#e8e8e8] bg-white shadow-sm group">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3.5 py-3 text-xs font-semibold text-[#222] [&::-webkit-details-marker]:hidden">
        <span className="shrink-0">Ajustar legenda</span>
        <span className="hidden rounded-full bg-[#f5f5f5] px-2 py-1 text-[10px] font-medium text-[#667085] group-open:bg-red-50 group-open:text-red-700 2xl:inline-flex">
          Texto, posição e tamanho
        </span>
      </summary>
      <div className="grid max-h-[440px] gap-3 overflow-y-auto border-t border-[#ededed] p-3.5 2xl:max-h-none 2xl:grid-cols-[170px_minmax(0,1fr)] 2xl:overflow-visible">
        <CaptionLivePreview draft={draft} blocked={blocked} onChange={onChange} />
        <div className="min-w-0 space-y-3">
          <div>
            <div className="mb-2 flex items-center justify-between gap-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#667085]">
              <span>Posição vertical</span>
              <span>{draft.caption_position === "bottom" ? "Base" : draft.caption_position === "top" ? "Topo" : "Centro"}</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              {captionPositions.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  disabled={blocked}
                  onClick={() => onChange({ caption_position: item.value })}
                  className={`rounded-lg border px-3 py-2 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-45 ${draft.caption_position === item.value ? "border-red-200 bg-red-50 text-red-700" : "border-[#e8e8e8] bg-[#f7f7f7] text-[#555] hover:border-[#d0d5dd] hover:bg-white"}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <label className="block text-[11px] font-medium leading-5 text-[#555]">
            Distância da borda: {draft.caption_margin_v}px
            <input
              type="range"
              min={CAPTION_MARGIN_MIN}
              max={CAPTION_MARGIN_MAX}
              step={20}
              value={draft.caption_margin_v}
              disabled={blocked}
              onChange={(event) => onChange({ caption_margin_v: Number(event.target.value) })}
              className="mt-1 w-full accent-[#ff0000] disabled:opacity-45"
            />
          </label>
          <label className="block text-[11px] font-medium leading-5 text-[#555]">
            Tamanho da fonte: {draft.caption_font_size}px
            <input
              type="range"
              min={14}
              max={32}
              step={1}
              value={draft.caption_font_size}
              disabled={blocked}
              onChange={(event) => onChange({ caption_font_size: Number(event.target.value) })}
              className="mt-1 w-full accent-[#ff0000] disabled:opacity-45"
            />
          </label>
          <label className="block text-[11px] font-medium leading-5 text-[#555]">
            Texto da legenda
            <textarea
              value={draft.subtitle_srt}
              onChange={(event) => onChange({ subtitle_srt: event.target.value })}
              disabled={blocked}
              rows={4}
              className="mt-1 max-h-[180px] w-full resize-y rounded-lg border border-[#d8d8d8] bg-[#fdfdfd] p-2.5 text-[11px] leading-5 text-[#333] outline-none focus:border-[#ff0000] disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Edite o SRT ou escreva um texto simples para aparecer no corte inteiro."
            />
          </label>
          {blocked && <p className="rounded-lg bg-amber-50 p-2 text-[11px] font-medium leading-5 text-amber-800">Ajustes ficam disponíveis antes do envio ao YouTube.</p>}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onReset}
              disabled={busy || blocked}
              className="inline-flex min-h-9 items-center justify-center rounded-lg border border-[#d8d8d8] bg-white px-3 py-2 text-xs font-semibold text-[#333] transition hover:border-[#c4c4c4] hover:bg-[#fafafa] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Restaurar padrão
            </button>
            <button
              type="button"
              onClick={onSave}
              disabled={busy || blocked}
              className="inline-flex min-h-9 items-center justify-center rounded-lg bg-[#111] px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-[#262626] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? "Salvando..." : "Salvar alterações"}
            </button>
          </div>
        </div>
      </div>
    </details>
  );
}

function ClipPreview({ clip, mediaSrc, draft }: { clip: Clip; mediaSrc: string; draft?: CaptionDraft }) {
  const [failed, setFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  function retryPreview() {
    setFailed(false);
    setRetryKey((value) => value + 1);
  }

  return (
    <div className="w-full">
      <div className="mx-auto w-full max-w-[260px] sm:mx-0 sm:max-w-[240px] 2xl:max-w-[270px]">
        <div className="relative aspect-[9/16] overflow-hidden rounded-xl border border-[#161616] bg-[#080808] shadow-sm">
          {mediaSrc && !failed ? (
            <video
              key={retryKey}
              controls
              playsInline
              preload="metadata"
              onError={() => setFailed(true)}
              className="h-full w-full bg-[#080808] object-contain"
              src={mediaSrc}
            />
          ) : (
            <div className="grid h-full place-items-center p-4 text-center text-white/80">
              <div>
                <PlayIcon className="mx-auto h-9 w-9 text-white/70" />
                <p className="mt-3 text-xs font-semibold">{mediaSrc ? "Não foi possível carregar o preview." : "Preview indisponível."}</p>
                {mediaSrc && (
                  <button
                    type="button"
                    onClick={retryPreview}
                    className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-[11px] font-semibold text-[#111]"
                  >
                    <RefreshIcon className="h-3.5 w-3.5" />
                    Tentar novamente
                  </button>
                )}
              </div>
            </div>
          )}
          {draft && !failed && (
            <>
              <div className="pointer-events-none absolute inset-x-[11%] bottom-[17%] top-[10%] rounded-[10px] border border-dashed border-white/30" />
              <div
                className="pointer-events-none absolute left-[8%] right-[8%] rounded-lg bg-black/80 px-2 py-1.5 text-center font-black leading-tight text-white shadow-[0_2px_0_rgba(0,0,0,0.8)]"
                style={{ ...captionPreviewStyle(draft), fontSize: `${clampNumber(draft.caption_font_size * 0.62, 10, 20)}px` }}
              >
                {previewCaptionText(draft.subtitle_srt)}
              </div>
            </>
          )}
        </div>
        <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-[#777]">
          <span>9:16</span>
          <span>{(clip.end_seconds - clip.start_seconds).toFixed(1)}s</span>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard({ user }: { user: UserProfile }) {
  const [activeSection, setActiveSection] = useState<SectionId>("automacao");
  const [keyword, setKeyword] = useState("marketing digital");
  const [region, setRegion] = useState("BR");
  const [days, setDays] = useState(14);
  const [requestedClips, setRequestedClips] = useState(3);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [videos, setVideos] = useState<TrendingVideo[]>([]);
  const [selected, setSelected] = useState<TrendingVideo | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [clips, setClips] = useState<Clip[]>([]);
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const [youtubeChannelTitle, setYoutubeChannelTitle] = useState<string | null>(null);
  const [liveMetrics, setLiveMetrics] = useState<YouTubeLiveMetrics | null>(null);
  const [captionDrafts, setCaptionDrafts] = useState<Record<number, CaptionDraft>>({});
  const [privacy, setPrivacy] = useState("private");
  const [loading, setLoading] = useState(false);
  const [liveLoading, setLiveLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [liveError, setLiveError] = useState("");
  const [message, setMessage] = useState("");

  const activeJobs = useMemo(() => jobs.filter((job) => !["ready_for_review", "failed"].includes(job.status)).length, [jobs]);
  const readyClips = useMemo(() => clips.filter((clip) => ["ready", "approved", "uploaded"].includes(clip.status)).length, [clips]);
  const usagePercent = user.unlimited ? 100 : Math.min(100, Math.round((user.jobs_used / Math.max(1, user.monthly_job_limit)) * 100));
  const topVideo = liveMetrics?.top_video;
  const monetization = liveMetrics?.monetization;

  useEffect(() => {
    const syncSection = () => setActiveSection(sectionFromHash());
    syncSection();
    window.addEventListener("hashchange", syncSection);
    return () => window.removeEventListener("hashchange", syncSection);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const youtube = params.get("youtube");
    if (!youtube) return;

    const reason = params.get("reason") || "";
    if (youtube === "connected") {
      setMessage("Canal do YouTube conectado com sucesso.");
    } else if (youtube === "error") {
      setError(youtubeOauthErrorMessage(reason));
    }

    params.delete("youtube");
    params.delete("reason");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  }, []);

  async function refreshLive({ silent = false }: { silent?: boolean } = {}) {
    if (!silent) setLiveLoading(true);
    setLiveError("");
    try {
      const metrics = await youtubeLiveMetrics();
      setLiveMetrics(metrics);
    } catch (err) {
      setLiveMetrics(null);
      if (!silent) setLiveError(err instanceof Error ? err.message : "Falha ao carregar métricas ao vivo do YouTube.");
    } finally {
      if (!silent) setLiveLoading(false);
    }
  }

  async function refresh({ silent = false }: { silent?: boolean } = {}) {
    try {
      const [jobData, clipData, yt] = await Promise.all([listJobs(), listClips(), youtubeStatus()]);
      setJobs(jobData);
      setClips(clipData);
      setYoutubeConnected(yt.connected);
      setYoutubeChannelTitle(yt.channel_title ?? null);
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Falha ao atualizar o painel");
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => void refresh({ silent: true }), 3000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!youtubeConnected) return;
    void refreshLive();
    const timer = window.setInterval(() => void refreshLive({ silent: true }), 60000);
    return () => window.clearInterval(timer);
  }, [youtubeConnected]);

  function openSection(id: SectionId) {
    setActiveSection(id);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${id}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function search() {
    setLoading(true); setError(""); setMessage("");
    try {
      const result = await getTrending(keyword, region, days);
      setVideos(result); setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao buscar vídeos");
    } finally { setLoading(false); }
  }

  async function processSelected() {
    if (!selected) return setError("Escolha um vídeo para continuar.");
    if (!rightsConfirmed) return setError("Confirme que você possui direitos ou autorização para reutilizar o conteúdo.");
    setActionId(`video-${selected.video_id}`); setError(""); setMessage("");
    try {
      await createJob(selected, requestedClips);
      await refresh();
      setMessage("Processamento iniciado. Acompanhe o andamento abaixo.");
      openSection("processamento");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar o processamento");
    } finally { setActionId(null); }
  }

  async function retryFailedJob(id: number) {
    setActionId(`retry-${id}`); setError(""); setMessage("");
    try {
      await retryJob(id);
      await refresh();
      setMessage("Novo processamento criado a partir da falha anterior. Acompanhe o andamento abaixo.");
      openSection("processamento");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao reenviar o processamento");
    } finally { setActionId(null); }
  }

  async function connectYoutube() {
    setActionId("youtube"); setError("");
    try {
      const result = await youtubeStart();
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar a conexão OAuth do YouTube");
      setActionId(null);
    }
  }

  async function approve(id: number) {
    setActionId(`approve-${id}`); setError("");
    try {
      await approveClip(id); await refresh(); setMessage("Corte aprovado para publicação.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao aprovar o corte");
    } finally { setActionId(null); }
  }

  async function upload(id: number) {
    setActionId(`upload-${id}`); setError("");
    try {
      await uploadClip(id, privacy); await refresh(); setMessage("Envio colocado na fila do YouTube.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar o envio");
    } finally { setActionId(null); }
  }

  function updateCaptionDraft(id: number, clip: Clip, patch: Partial<CaptionDraft>) {
    setCaptionDrafts((current) => ({
      ...current,
      [id]: { ...(current[id] ?? captionDraftFromClip(clip)), ...patch },
    }));
  }

  async function applyCaptionSettings(clip: Clip) {
    const draft = captionDrafts[clip.id] ?? captionDraftFromClip(clip);
    setActionId(`caption-${clip.id}`); setError(""); setMessage("");
    try {
      await updateClipCaptions(clip.id, draft);
      setCaptionDrafts((current) => {
        const next = { ...current };
        delete next[clip.id];
        return next;
      });
      await refresh();
      setMessage("Legenda atualizada e vídeo recriado com a nova posição.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao ajustar a legenda");
    } finally { setActionId(null); }
  }

  function resetCaptionSettings(clip: Clip) {
    setCaptionDrafts((current) => ({
      ...current,
      [clip.id]: defaultCaptionDraft(clip),
    }));
  }

  async function openClipInEditor(clip: Clip) {
    setActionId(`edit-${clip.id}`); setError(""); setMessage("");
    try {
      const project = await createEditorProjectFromClip(clip.id);
      const params = new URLSearchParams({
        project: project.id,
        clip: String(clip.id),
        return: "/#cortes",
      });
      window.location.href = `/editor-ia?${params.toString()}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao abrir o corte no editor de vídeo");
      setActionId(null);
    }
  }

  return (
    <main className="sf-page-main pb-24 xl:pb-10">
      <section className="border-b border-[#e6e6e6] bg-white">
        <div className="sf-container flex flex-col gap-4 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <BrandLogo size="md" />
            <div className="hidden h-10 w-px bg-[#ececec] sm:block" />
            <div className="min-w-0">
              <div className="sf-kicker">Área de trabalho ao vivo</div>
              <h1 className="mt-1 truncate text-[26px] font-semibold leading-tight text-[#111]">Painel ShortsFlow</h1>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={connectYoutube} disabled={actionId === "youtube"} className={`sf-button max-w-full ${youtubeConnected ? "border-red-100 bg-red-50 text-red-700" : "sf-button-outline"}`}>
              <YoutubeIcon className="h-4 w-4 text-[#ff0000]" />
              <span className="min-w-0 truncate">{youtubeConnected ? youtubeChannelTitle || "YouTube conectado" : actionId === "youtube" ? "Conectando..." : "Conectar YouTube"}</span>
            </button>
            <button onClick={() => openSection("configurar")} className="sf-button sf-button-primary">Novo processamento</button>
          </div>
        </div>
      </section>

      <section className="border-b border-[#e6e6e6] bg-white/95 backdrop-blur">
        <div className="sf-container grid gap-2 py-3 md:grid-cols-2 xl:grid-cols-4">
          {sections.map((item) => {
            const active = activeSection === item.id;
            return (
              <button key={item.id} onClick={() => openSection(item.id)} className={`min-h-[66px] rounded-xl border px-4 py-3 text-left transition ${active ? "border-red-200 bg-red-50 shadow-sm" : "border-[#ededed] bg-white hover:border-[#d8d8d8] hover:shadow-sm"}`}>
                <span className={`block text-sm font-semibold ${active ? "text-[#e00000]" : "text-[#222]"}`}>{item.label}</span>
                <span className="mt-1 block text-[11px] leading-4 text-[#777]">{item.description}</span>
              </button>
            );
          })}
        </div>
      </section>

      {(error || message) && (
        <section className="sf-container pt-5">
          {error && <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div>}
          {message && <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">{message}</div>}
        </section>
      )}

      {activeSection === "automacao" && (
        <section id="automacao" className="sf-container py-6">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_420px]">
            <div className="space-y-5">
              <div className="sf-metric-grid">
                <MetricCard label="Inscritos" value={liveMetrics?.hidden_subscriber_count ? "Oculto" : fmtNumber(liveMetrics?.subscriber_count || 0)} detail={liveMetrics?.channel_title || "Canal conectado"} />
                <MetricCard label="Visualizações" value={fmtNumber(liveMetrics?.view_count || 0)} detail={liveMetrics?.views_last_28d != null ? `${fmtNumber(liveMetrics.views_last_28d)} em 28 dias` : "Total do canal"} />
                <MetricCard label="Vídeos no canal" value={fmtExact(liveMetrics?.video_count || 0)} detail={`${activeJobs} processamentos ativos`} />
                <MetricCard label="Uso do plano" value={fmtExact(user.jobs_used)} detail={user.unlimited ? `Processamentos usados · ilimitado · ${user.plan_code || "admin"}` : `${fmtExact(user.jobs_remaining ?? 0)} restantes · limite ${fmtExact(user.monthly_job_limit)}`} />
              </div>

              <div className="sf-card overflow-hidden">
                <div className="flex flex-col gap-3 border-b border-[#e8e8e8] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase leading-4 text-[#ff0000]">Vídeo em destaque</div>
                    <h2 className="mt-1 max-w-3xl text-xl font-semibold leading-tight text-[#111]">{topVideo?.title || "Conecte o canal para exibir o destaque ao vivo"}</h2>
                  </div>
                  <button onClick={() => void refreshLive()} disabled={!youtubeConnected || liveLoading} style={{ minWidth: 154 }} className="sf-button sf-button-outline w-fit disabled:opacity-50">
                    <RefreshIcon className="h-3.5 w-3.5" />{liveLoading ? "Atualizando..." : "Atualizar métricas"}
                  </button>
                </div>

                <div className="grid gap-0 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,.65fr)]">
                  <div className="bg-[#151515] p-4">
                    <div className="relative aspect-video overflow-hidden rounded-lg bg-[#101010]">
                      {topVideo?.thumbnail_url ? <img src={topVideo.thumbnail_url} alt="" className="h-full w-full object-cover opacity-70" /> : <div className="h-full w-full bg-[radial-gradient(circle_at_center,#343434,#111)]" />}
                      <div className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/10 to-black/60" />
                      <div className="absolute left-5 top-5 flex items-center gap-3">
                        <BrandLogo size="sm" className="rounded-md bg-white shadow" />
                      </div>
                      <div className="absolute inset-0 grid place-items-center">
                        <span className="grid h-16 w-16 place-items-center rounded-full bg-white/95 text-[#111] shadow-2xl">
                          <PlayIcon className="ml-1 h-8 w-8" />
                        </span>
                      </div>
                      <div className="absolute bottom-0 left-0 right-0 p-5">
                        <div className="h-1.5 overflow-hidden rounded-full bg-white/25"><div className="h-full w-[42%] rounded-full bg-[#ff0000]" /></div>
                        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs font-semibold leading-5 text-white/90">
                          <span>{topVideo ? fmtDuration(topVideo.duration_seconds) : "0:00"}</span>
                          <span>{topVideo ? fmtNumber(topVideo.view_count) : "0"} visualizações</span>
                          <span>{topVideo ? fmtNumber(topVideo.like_count) : "0"} curtidas</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="p-5">
                    {liveError && <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs font-semibold leading-5 text-amber-900">{liveError}</div>}
                    {!youtubeConnected && <div className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm font-semibold text-red-700">Conecte o YouTube para carregar o painel ao vivo deste perfil.</div>}
                    {topVideo && (
                      <div className="space-y-4">
                        <div>
                          <div className="text-[11px] font-semibold uppercase leading-4 text-[#777]">Canal</div>
                          <div className="mt-1 break-words text-lg font-semibold leading-tight text-[#111]">{liveMetrics?.channel_title || youtubeChannelTitle}</div>
                          <div className="mt-1 text-xs text-[#777]">Atualizado {liveMetrics?.refreshed_at ? fmtDate(liveMetrics.refreshed_at) : "agora"}</div>
                        </div>
                        <div className="grid gap-2 text-center sm:grid-cols-3">
                          <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold">{fmtNumber(topVideo.view_count)}</div><div className="text-[10px] text-[#777]">visualizações</div></div>
                          <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold">{fmtNumber(topVideo.like_count)}</div><div className="text-[10px] text-[#777]">curtidas</div></div>
                          <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold">{fmtNumber(topVideo.comment_count)}</div><div className="text-[10px] text-[#777]">comentários</div></div>
                        </div>
                        <a href={topVideo.url} target="_blank" rel="noreferrer" className="sf-button sf-button-youtube w-fit">Abrir no YouTube <ArrowIcon className="h-3.5 w-3.5" /></a>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="sf-card p-5">
                <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
                  <div>
                    <div className="text-[11px] font-semibold uppercase leading-4 text-[#ff0000]">Vídeos recentes</div>
                    <h2 className="mt-1 text-xl font-semibold leading-tight text-[#111]">Ranking do canal conectado</h2>
                  </div>
                  <span className="text-xs text-[#777]">{liveMetrics?.recent_videos.length || 0} vídeos analisados</span>
                </div>
                <div className="mt-4 divide-y divide-[#ededed]">
                  {(liveMetrics?.recent_videos || []).slice(0, 6).map((video, index) => (
                    <a key={video.video_id} href={video.url} target="_blank" rel="noreferrer" className="grid gap-3 py-3 sm:grid-cols-[32px_96px_minmax(0,1fr)_auto] sm:items-center">
                      <div className="text-sm font-semibold text-[#999]">#{index + 1}</div>
                      <img src={video.thumbnail_url} alt="" className="h-14 w-24 rounded-md bg-[#111] object-cover" />
                      <div className="min-w-0">
                        <div className="line-clamp-2 text-sm font-semibold text-[#222]">{video.title}</div>
                        <div className="mt-1 text-[11px] text-[#777]">{fmtDate(video.published_at)} · {fmtDuration(video.duration_seconds)}</div>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs leading-5 text-[#666] sm:justify-end sm:text-right">
                        <span>{fmtNumber(video.view_count)} visualizações</span>
                        <span>{fmtNumber(video.like_count)} curtidas</span>
                        <span>{fmtNumber(video.comment_count)} com.</span>
                      </div>
                    </a>
                  ))}
                  {youtubeConnected && !liveLoading && liveMetrics?.recent_videos.length === 0 && <div className="py-8 text-center text-sm text-[#777]">Nenhum vídeo recente retornado pela API do YouTube.</div>}
                  {liveLoading && <div className="py-8 text-center text-sm font-semibold text-[#777]">Carregando métricas ao vivo...</div>}
                </div>
              </div>
            </div>

            <aside className="space-y-5">
              <div className="sf-card p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold uppercase leading-4 text-[#ff0000]">Monetização</div>
                    <h2 className="mt-1 text-lg font-semibold leading-tight text-[#111]">{monetization?.eligible_full_estimate ? "Pronto para o YPP" : monetization?.near_monetization ? "Perto dos marcos" : "Em evolução"}</h2>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-[10px] font-semibold ${monetization?.near_monetization ? "bg-red-50 text-red-700" : "bg-[#f1f1f1] text-[#666]"}`}>{monetization?.eligible_full_estimate ? "Elegível" : monetization?.near_monetization ? "Alerta" : "Monitorando"}</span>
                </div>
                <div className="mt-5 space-y-5">
                  <ProgressBar label="Inscritos" value={liveMetrics?.hidden_subscriber_count ? "Oculto" : fmtExact(liveMetrics?.subscriber_count || 0)} target={fmtExact(monetization?.subscriber_target_full || 1000)} progress={monetization?.subscriber_progress_full || 0} />
                  <ProgressBar label="Horas assistidas" value={fmtExact(monetization?.watch_hours_last_365d || 0)} target={fmtExact(monetization?.watch_hours_target_full || 4000)} progress={monetization?.watch_hours_progress_full || 0} />
                  <ProgressBar label="Visualizações de Shorts em 90 dias" value={fmtNumber(monetization?.shorts_views_90d_estimate || 0)} target={fmtNumber(monetization?.shorts_views_target_full || 10_000_000)} progress={monetization?.shorts_views_progress_full || 0} />
                </div>
                <div className="mt-5 rounded-lg bg-[#f7f7f7] p-3 text-xs leading-5 text-[#666]">
                  {liveMetrics?.analytics_available ? "Horas assistidas carregadas pela API do YouTube Analytics." : "Horas assistidas oficiais dependem do YouTube Analytics/Studio; o painel mantém estimativas com vídeos recentes."}
                </div>
              </div>

              <div className="sf-card p-5">
                <div className="text-[11px] font-semibold uppercase leading-4 text-[#ff0000]">Alertas</div>
                <div className="mt-4 grid gap-3">
                  {(liveMetrics?.alerts || [{ kind: "info", title: "Aguardando YouTube", detail: "Conecte ou atualize o canal para receber alertas ao vivo." }]).map((alert) => <AlertCard key={`${alert.title}-${alert.detail}`} alert={alert} />)}
                </div>
              </div>

              <div className="sf-card p-5">
                <div className="text-[11px] font-semibold uppercase leading-4 text-[#ff0000]">Perfis e limites</div>
                <h2 className="mt-1 text-lg font-semibold leading-tight text-[#111]">Plano {user.plan_code || "starter"}</h2>
                <div className="mt-4">
                  <div className="flex items-center justify-between text-xs"><span className="font-semibold text-[#222]">Uso mensal</span><span className="text-[#666]">{user.unlimited ? `${fmtExact(user.jobs_used)} processamentos` : `${fmtExact(user.jobs_used)} de ${fmtExact(user.monthly_job_limit)}`}</span></div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#ececec]"><div className="h-full rounded-full bg-[#ff0000]" style={{ width: `${usagePercent}%` }} /></div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold text-[#111]">{fmtExact(jobs.length)}</div><div className="text-[#777]">processamentos</div></div>
                  <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold text-[#111]">{fmtExact(readyClips)}</div><div className="text-[#777]">cortes</div></div>
                  <div className="rounded-lg bg-[#f7f7f7] p-3"><div className="text-lg font-semibold text-[#111]">{user.unlimited ? "∞" : fmtExact(user.jobs_remaining ?? 0)}</div><div className="text-[#777]">restantes</div></div>
                </div>
              </div>
            </aside>
          </div>
        </section>
      )}

      {activeSection === "configurar" && (
        <section id="configurar" className="sf-container py-6">
          <div className="mb-5 flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
            <div>
              <div className="sf-kicker">Criar Shorts</div>
              <h2 className="mt-1 text-[28px] font-semibold leading-tight text-[#111]">Pesquisa e corte automático</h2>
              <p className="mt-2 text-sm text-[#666]">Pesquise tendências usando a YouTube Data API e gere cortes verticais.</p>
            </div>
            <button onClick={() => openSection("automacao")} className="sf-button sf-button-outline w-fit">Voltar ao painel</button>
          </div>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_360px]">
            <div className="sf-card overflow-hidden">
              <div className="border-b border-[#e8e8e8] px-5 py-4"><h3 className="text-sm font-semibold text-[#111]">Buscar conteúdo</h3><p className="mt-1 text-xs text-[#666]">Encontre vídeos com potencial para cortes.</p></div>
              <div className="p-5">
                <div className="grid gap-3 md:grid-cols-[1fr_80px_110px_auto]">
                  <input value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} className="sf-input min-w-0 px-3 py-2.5" placeholder="Ex.: marketing digital, imóveis, vendas" />
                  <input value={region} onChange={(e) => setRegion(e.target.value.toUpperCase().slice(0, 2))} className="sf-input px-3 py-2.5 text-center font-medium" />
                  <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="sf-input px-3 py-2.5"><option value={7}>7 dias</option><option value={14}>14 dias</option><option value={30}>30 dias</option><option value={90}>90 dias</option></select>
                  <button onClick={search} disabled={loading} className="sf-button sf-button-primary disabled:opacity-50"><SearchIcon className="h-4 w-4" />{loading ? "Buscando..." : "Buscar"}</button>
                </div>

                <div className="mt-5 max-h-[520px] divide-y divide-[#ededed] overflow-y-auto rounded-lg border border-[#e8e8e8]">
                  {videos.length === 0 && <div className="p-10 text-center text-sm text-[#777]">Faça uma busca para encontrar vídeos.</div>}
                  {videos.map((video) => (
                    <button key={video.video_id} onClick={() => setSelected(video)} className={`flex w-full items-center gap-4 p-3 text-left transition ${selected?.video_id === video.video_id ? "bg-red-50" : "bg-white hover:bg-[#f7f7f7]"}`}>
                      <div className="relative h-16 w-28 flex-none overflow-hidden rounded-md bg-[#111]"><img src={video.thumbnail_url} alt="" className="h-full w-full object-cover" /><span className="absolute inset-0 grid place-items-center bg-black/15"><span className="grid h-8 w-8 place-items-center rounded-full bg-white/95"><PlayIcon className="ml-0.5 h-3.5 w-3.5 text-[#111]" /></span></span></div>
                      <div className="min-w-0 flex-1"><div className="line-clamp-2 text-sm font-semibold leading-5 text-[#222]">{video.title}</div><div className="mt-1 text-[11px] text-[#777]">{video.channel_title} · {fmtNumber(video.view_count)} visualizações · {fmtDuration(video.duration_seconds)}</div></div>
                      {selected?.video_id === video.video_id && <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-[#ff0000] text-white"><CheckIcon className="h-3.5 w-3.5" /></span>}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="sf-card overflow-hidden">
              <div className="border-b border-[#e8e8e8] px-5 py-4"><h3 className="text-sm font-semibold text-[#111]">Configuração</h3><p className="mt-1 text-xs text-[#666]">Defina a quantidade de cortes.</p></div>
              <div className="p-5">
                <label className="text-xs font-medium text-[#222]">Quantidade de Shorts</label>
                <div className="mt-2 grid grid-cols-5 gap-2">{[1, 2, 3, 5, 10].map((n) => <button key={n} onClick={() => setRequestedClips(n)} className={`rounded-lg border py-2.5 text-sm font-semibold ${requestedClips === n ? "border-red-200 bg-red-50 text-red-700" : "border-[#e8e8e8] bg-white text-[#555]"}`}>{n}</button>)}</div>
                <div className="mt-5 divide-y divide-[#ededed] rounded-lg border border-[#e8e8e8] text-xs"><div className="flex justify-between p-3"><span className="text-[#777]">Formato</span><strong className="font-medium text-[#222]">9:16 vertical</strong></div><div className="flex justify-between p-3"><span className="text-[#777]">Duração</span><strong className="font-medium text-[#222]">15-60s</strong></div><div className="flex justify-between p-3"><span className="text-[#777]">Legendas</span><strong className="font-medium text-[#222]">Automáticas</strong></div></div>
                <div className="mt-5"><LanguageSelector /></div>
                <label className="mt-5 flex items-start gap-3 text-xs leading-5 text-[#666]"><input type="checkbox" checked={rightsConfirmed} onChange={(e) => setRightsConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#ff0000]" /><span>Confirmo que possuo direitos ou autorização para reutilizar o conteúdo.</span></label>
                {selected && <div className="mt-4 rounded-lg bg-[#f7f7f7] p-3 text-xs"><div className="text-[#777]">Selecionado</div><div className="mt-1 line-clamp-2 font-medium text-[#222]">{selected.title}</div></div>}
                <button onClick={processSelected} disabled={Boolean(actionId?.startsWith("video-")) || !selected} className="sf-button sf-button-youtube mt-5 w-full disabled:opacity-40">{actionId?.startsWith("video-") ? "Iniciando..." : `Gerar ${requestedClips} Shorts`}</button>
              </div>
            </div>
          </div>
        </section>
      )}

      {activeSection === "processamento" && (
        <section id="processamento" className="sf-container py-6">
          <div className="sf-card overflow-hidden">
            <div className="flex flex-col justify-between gap-3 border-b border-[#e8e8e8] px-5 py-4 md:flex-row md:items-center"><div><div className="sf-kicker">Processamentos</div><h2 className="mt-1 text-xl font-semibold leading-tight text-[#111]">Fila de criação dos Shorts</h2><p className="mt-1 text-xs leading-5 text-[#777]">{activeJobs} processamento(s) ativo(s). Atualização automática a cada 3 segundos.</p></div><button onClick={() => void refresh()} className="sf-button sf-button-outline w-fit"><RefreshIcon className="h-3.5 w-3.5" />Atualizar</button></div>
            {jobs.length === 0 ? <div className="p-10 text-center text-sm text-[#777]">Seus processamentos aparecerão aqui.</div> : <div className="divide-y divide-[#ededed]">{jobs.map((job) => {
              const current = stageIndex[job.status] ?? 0;
              return <article key={job.id} className="p-5">
                <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div className="flex min-w-0 items-center gap-4">{job.source_video.thumbnail_url ? <img src={job.source_video.thumbnail_url} alt="" className="h-14 w-24 rounded-md object-cover" /> : <div className="grid h-14 w-24 place-items-center rounded-md bg-[#111]"><YoutubeIcon className="h-7 w-7 text-red-500" /></div>}<div className="min-w-0"><div className="text-[10px] text-[#777]">Processamento #{job.id}</div><h3 className="line-clamp-2 text-sm font-semibold text-[#222]">{job.source_video.title}</h3><p className="mt-1 text-xs text-[#777]">{job.clips.length}/{job.requested_clips} cortes</p></div></div><div className="flex items-center gap-3"><StatusBadge status={job.status} /><span className="text-xs font-semibold text-[#222]">{job.progress}%</span></div></div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[#ececec]"><div className={`h-full rounded-full transition-all duration-700 ${job.status === "failed" ? "bg-red-500" : "bg-[#ff0000]"}`} style={{ width: `${job.progress}%` }} /></div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{pipeline.map((stage, index) => { const active = job.status !== "failed" && (current >= index || job.status === "ready_for_review"); return <div key={stage} className={`rounded-lg border px-3 py-2 ${active ? "border-red-100 bg-red-50" : "border-[#e8e8e8] bg-white"}`}><div className={`text-[9px] font-medium ${active ? "text-red-700" : "text-[#999]"}`}>{String(index + 1).padStart(2, "0")}</div><div className="mt-0.5 text-[11px] font-medium text-[#555]">{stage}</div></div>; })}</div>
                {job.error && <div className="mt-4 flex flex-col gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-700 sm:flex-row sm:items-center sm:justify-between">
                  <p className="leading-5">{jobErrorMessage(job.error)}</p>
                  {job.status === "failed" && <button onClick={() => retryFailedJob(job.id)} disabled={actionId === `retry-${job.id}`} className="inline-flex w-fit flex-none items-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"><RefreshIcon className="h-3.5 w-3.5" />{actionId === `retry-${job.id}` ? "Recriando..." : "Tentar novamente"}</button>}
                </div>}
              </article>;
            })}</div>}
          </div>
        </section>
      )}

      {activeSection === "cortes" && (
        <section id="cortes" className="sf-container py-6">
          <div className="sf-card overflow-hidden">
            <div className="flex flex-col justify-between gap-3 border-b border-[#e8e8e8] px-5 py-4 md:flex-row md:items-center"><div><div className="sf-kicker">Publicações</div><h2 className="mt-1 text-xl font-semibold leading-tight text-[#111]">Cortes para revisão</h2><p className="mt-1 text-xs leading-5 text-[#777]">Aprove individualmente antes do envio.</p></div><label className="flex w-fit items-center gap-2 text-xs leading-5 text-[#777]">Privacidade<select value={privacy} onChange={(e) => setPrivacy(e.target.value)} className="sf-input px-2.5 py-2 font-medium"><option value="private">Privado</option><option value="unlisted">Não listado</option><option value="public">Público</option></select></label></div>
            {clips.length === 0 ? <div className="p-10 text-center text-sm text-[#777]">Os cortes gerados aparecerão aqui.</div> : <div className="grid gap-4 p-5 xl:grid-cols-2">{clips.map((clip) => {
              const draft = captionDrafts[clip.id] ?? captionDraftFromClip(clip);
              const mediaSrc = clip.media_url ? `${API_URL}${clip.media_url}?v=${encodeURIComponent(clip.updated_at || clip.created_at)}` : "";
              const uploadLocked = ["approved", "upload_queued", "uploading", "uploaded"].includes(clip.status);
              return (
                <article key={clip.id} className="grid items-start gap-4 rounded-xl border border-[#e8e8e8] bg-white p-4 shadow-[0_10px_28px_rgba(17,17,17,0.04)] md:grid-cols-[minmax(210px,240px)_minmax(0,1fr)] 2xl:grid-cols-[minmax(230px,270px)_minmax(0,1fr)]">
                  <ClipPreview clip={clip} mediaSrc={mediaSrc} draft={captionDrafts[clip.id]} />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <StatusBadge status={clip.status} />
                      <span className="text-xs text-[#777]">{(clip.end_seconds - clip.start_seconds).toFixed(1)}s</span>
                    </div>
                    <h3 className="mt-3 line-clamp-3 text-base font-semibold leading-6 text-[#111]">{clip.title}</h3>
                    {clip.hook && <p className="mt-2 text-sm font-medium leading-5 text-[#444]">{clip.hook}</p>}
                    <p className="mt-3 max-h-28 overflow-y-auto pr-1 text-xs leading-5 text-[#666]">{clip.description}</p>
                    <div className="mt-3 flex gap-2 rounded-lg bg-[#f7f7f7] p-3 text-[11px] leading-5 text-[#555]">
                      <CopyIcon className="h-4 w-4 flex-none text-[#ff0000]" />
                      <span className="max-h-20 overflow-y-auto pr-1">{clip.copy}</span>
                    </div>
                    <div className="mt-2 flex gap-2 rounded-lg bg-[#f7f7f7] p-3 text-[11px] leading-5 text-[#555]">
                      <TagsIcon className="h-4 w-4 flex-none text-[#ff0000]" />
                      <span className="max-h-20 overflow-y-auto pr-1">{clip.tags.slice(0, 12).map((tag) => `#${tag}`).join(" ")}</span>
                    </div>
                    <CaptionControls
                      clip={clip}
                      draft={draft}
                      busy={actionId === `caption-${clip.id}`}
                      onChange={(patch) => updateCaptionDraft(clip.id, clip, patch)}
                      onReset={() => resetCaptionSettings(clip)}
                      onSave={() => void applyCaptionSettings(clip)}
                    />
                    {clip.upload_error && <p className="mt-3 rounded-lg bg-red-50 p-3 text-xs font-medium text-red-700">{clip.upload_error}</p>}
                    {clip.youtube_video_id && <a href={`https://www.youtube.com/watch?v=${clip.youtube_video_id}`} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-red-600">Abrir no YouTube <ArrowIcon className="h-3.5 w-3.5" /></a>}
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button onClick={() => void openClipInEditor(clip)} disabled={actionId === `edit-${clip.id}`} className="inline-flex items-center justify-center rounded-lg border border-[#d8d8d8] bg-white px-3.5 py-2 text-xs font-semibold text-[#222] transition hover:border-[#c4c4c4] hover:bg-[#fafafa] disabled:opacity-40">
                        {actionId === `edit-${clip.id}` ? "Abrindo..." : "Editar vídeo"}
                      </button>
                      <button onClick={() => approve(clip.id)} disabled={uploadLocked || actionId === `approve-${clip.id}`} className="rounded-lg bg-[#111] px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-40">{clip.status === "approved" ? "Aprovado" : "Aprovar"}</button>
                      <button onClick={() => upload(clip.id)} disabled={!youtubeConnected || clip.status !== "approved" || actionId === `upload-${clip.id}`} className="flex items-center gap-2 rounded-lg bg-[#ff0000] px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-40"><UploadIcon className="h-3.5 w-3.5" />{clip.status === "uploading" ? "Enviando..." : clip.status === "uploaded" ? "Publicado" : "Enviar ao YouTube"}</button>
                    </div>
                  </div>
                </article>
              );
            })}</div>}
          </div>
        </section>
      )}
    </main>
  );
}
