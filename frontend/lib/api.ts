import type { Clip, Job, TrendingVideo } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {}
    throw new Error(message);
  }
  return response.json();
}

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
export const youtubeStatus = () => api<{ connected: boolean }>("/api/youtube/oauth/status");
export const youtubeStart = () => api<{ authorization_url: string }>("/api/youtube/oauth/start");
