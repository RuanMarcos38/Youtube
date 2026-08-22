import type {
  AdminMetrics,
  AdminUser,
  BillingStatus,
  Clip,
  DownloadAuthStatus,
  Job,
  KiwifyAdminSettings,
  ProvisionedCredential,
  TeamUser,
  TrendingVideo,
  UserProfile,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

function apiErrorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const entry = item as { msg?: unknown; loc?: unknown };
        const msg = typeof entry.msg === "string" ? entry.msg : "";
        const loc = Array.isArray(entry.loc) ? entry.loc.filter((part) => part !== "body").map(String).join(".") : "";
        if (!msg) return null;
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter((value): value is string => Boolean(value));
    if (messages.length) return messages.join(" | ");
  }
  try {
    return JSON.stringify(detail ?? body);
  } catch {
    return fallback;
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const fallback = `${response.status} ${response.statusText}`;
    let message = fallback;
    try {
      const body: unknown = await response.json();
      message = apiErrorMessage(body, fallback);
    } catch {}
    throw new Error(`${path}: ${message}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const authMe = () => api<UserProfile>("/api/auth/me");
export const authLogin = (email: string, password: string) =>
  api<UserProfile>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const authRegister = (name: string, email: string, password: string, companyName?: string) =>
  api<UserProfile>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password, company_name: companyName || undefined }),
  });
export const authLogout = () => api<void>("/api/auth/logout", { method: "POST" });
export const listTeam = () => api<TeamUser[]>("/api/auth/team");
export const createTeamUser = (name: string, email: string, password: string, role = "member") =>
  api<TeamUser>("/api/auth/team", { method: "POST", body: JSON.stringify({ name, email, password, role }) });

export const billingMe = () => api<BillingStatus>("/api/billing/me");

export const adminMetrics = () => api<AdminMetrics>("/api/admin/dashboard");
export const adminUsers = () => api<AdminUser[]>("/api/admin/users");
export const adminCredentials = () => api<ProvisionedCredential[]>("/api/admin/provisioned-credentials");
export const adminDownloadAuth = () => api<DownloadAuthStatus>("/api/admin/download-auth");
export const adminKiwifySettings = () => api<KiwifyAdminSettings>("/api/admin/kiwify");
export const adminUpdatePlan = (
  userId: number,
  payload: { plan_code?: string; billing_status?: string; monthly_job_limit?: number; unlimited?: boolean },
) => api<{ ok: boolean }>(`/api/admin/users/${userId}/plan`, { method: "PATCH", body: JSON.stringify(payload) });
export const adminMarkCredentialDelivered = (id: number) =>
  api<{ ok: boolean }>(`/api/admin/provisioned-credentials/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ delivered: true }),
  });
export const adminUpdateDownloadAuth = (payload: {
  cookies_b64?: string;
  proxy_url?: string;
  clear_cookies?: boolean;
  clear_proxy?: boolean;
}) => api<DownloadAuthStatus>("/api/admin/download-auth", { method: "PUT", body: JSON.stringify(payload) });

export async function getTrending(keyword: string, region = "BR", days = 14): Promise<TrendingVideo[]> {
  const params = new URLSearchParams({ keyword, region, days: String(days), max_results: "12" });
  return api(`/api/videos/trending?${params}`);
}

export async function createJob(video: TrendingVideo, requestedClips: number): Promise<Job> {
  return api("/api/jobs", {
    method: "POST",
    body: JSON.stringify({
      video_id: video.video_id,
      title: video.title,
      channel_title: video.channel_title,
      thumbnail_url: video.thumbnail_url,
      url: video.url,
      requested_clips: requestedClips,
      rights_confirmed: true,
    }),
  });
}

export const listJobs = () => api<Job[]>("/api/jobs");
export const listClips = () => api<Clip[]>("/api/clips");
export const approveClip = (id: number) => api<Clip>(`/api/clips/${id}/approve`, { method: "POST" });
export const uploadClip = (id: number, privacyStatus: string) =>
  api<Clip>(`/api/clips/${id}/upload`, { method: "POST", body: JSON.stringify({ privacy_status: privacyStatus }) });
export const youtubeStatus = () => api<{ connected: boolean; channel_title?: string | null }>("/api/youtube/oauth/status");
export const youtubeStart = () => api<{ authorization_url: string }>("/api/youtube/oauth/start");
