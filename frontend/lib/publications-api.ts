import { API_URL } from "./api";
import type { Clip } from "./types";

export type YouTubeAvailability = {
  blocked: boolean;
  blocked_at?: string | null;
  blocked_until?: string | null;
  seconds_remaining: number;
  message: string;
};

export type TikTokPublicationClip = Clip & {
  tiktok_status: string;
  tiktok_error?: string | null;
  tiktok_publish_id?: string | null;
};

export type TikTokMetricSnapshot = {
  captured_at: string;
  followers: number;
  following: number;
  likes_total: number;
  video_count: number;
  views_period: number;
  likes_period: number;
  comments_period: number;
  shares_period: number;
};

export type TikTokDashboardAlert = {
  kind: "success" | "warning" | "danger" | "info" | string;
  title: string;
  detail: string;
};

export type TikTokMetrics = {
  available: boolean;
  metrics_authorized: boolean;
  reason?: string;
  refreshed_at?: string;
  period_days?: number;
  profile?: {
    display_name: string;
    avatar_url: string;
    followers: number;
    following: number;
    likes_total: number;
    video_count: number;
  } | null;
  period?: {
    videos: number;
    views: number;
    likes: number;
    comments: number;
    shares: number;
    engagement_total: number;
    engagement_rate: number;
    avg_views_per_video: number;
  } | null;
  growth?: {
    followers_delta: number;
    likes_total_delta: number;
    video_count_delta: number;
    views_period_delta: number;
  };
  top_videos?: Array<{
    id: string;
    title: string;
    create_time: number;
    duration: number;
    cover_image_url: string;
    share_url: string;
    view_count: number;
    like_count: number;
    comment_count: number;
    share_count: number;
  }>;
  monetization?: {
    official_revenue_available: boolean;
    official_revenue: number | null;
    currency: string;
    creator_rewards_min_duration_sec: number;
    duration_eligible_videos: number;
    duration_ineligible_videos: number;
    note: string;
  };
  alerts?: TikTokDashboardAlert[];
  history: TikTokMetricSnapshot[];
  local_publications: {
    total_attempts: number;
    published_confirmed: number;
    processing: number;
    failed: number;
    paused_limit: number;
    queued: number;
  };
};

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { credentials: "include", cache: "no-store" });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {}
    throw new Error(message);
  }
  return response.json();
}

export const youtubePublicationClips = () =>
  request<{ platform: "youtube"; availability: YouTubeAvailability; clips: Clip[] }>("/api/publications/youtube");

export const tiktokPublicationClips = () =>
  request<{ platform: "tiktok"; clips: TikTokPublicationClip[] }>("/api/publications/tiktok");

export const tiktokMetrics = (days = 30) => request<TikTokMetrics>(`/api/tiktok/metrics?days=${days}`);
