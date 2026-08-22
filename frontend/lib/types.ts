export type UserProfile = {
  id: number;
  tenant_id: number;
  email: string;
  display_name: string;
  role: string;
  active: boolean;
  billing_status: string;
  checkout_url: string;
  upgrade_url: string;
  plan_code: string;
  monthly_job_limit: number;
  unlimited: boolean;
  jobs_used: number;
  jobs_remaining?: number | null;
};

export type TeamUser = {
  id: number;
  email: string;
  display_name: string;
  role: string;
  active: boolean;
  youtube_connected: boolean;
  youtube_channel_title?: string | null;
};

export type BillingStatus = {
  plan_code: string;
  billing_status: string;
  monthly_job_limit: number;
  unlimited: boolean;
  jobs_used: number;
  jobs_remaining?: number | null;
  subscription_value_cents: number;
  checkout_url: string;
  upgrade_url: string;
};

export type AdminMetrics = {
  total_users: number;
  active_subscribers: number;
  monthly_revenue_cents: number;
  total_revenue_cents: number;
  jobs_this_month: number;
  unlimited_subscribers: number;
};

export type AdminUser = {
  id: number;
  tenant_id: number;
  workspace: string;
  email: string;
  display_name: string;
  role: string;
  active: boolean;
  plan_code: string;
  billing_status: string;
  monthly_job_limit: number;
  unlimited: boolean;
  jobs_used: number;
  subscription_value_cents: number;
  youtube_connected: boolean;
  youtube_channel_title?: string | null;
  created_at: string;
};

export type ProvisionedCredential = {
  id: number;
  order_id: string;
  email: string;
  display_name: string;
  temporary_password: string;
  created_at: string;
};

export type DownloadAuthStatus = {
  cookie_override: boolean;
  cookie_environment: boolean;
  proxy_override: boolean;
  proxy_environment: boolean;
};

export type KiwifyAdminSettings = {
  webhook_url: string;
  checkout_url: string;
  upgrade_url: string;
  events: string[];
};

export type TrendingVideo = {
  video_id: string;
  title: string;
  channel_title: string;
  thumbnail_url: string;
  url: string;
  published_at?: string | null;
  view_count: number;
  like_count: number;
  comment_count: number;
  duration_seconds: number;
};

export type SourceVideo = {
  id: number;
  youtube_id: string;
  title: string;
  channel_title: string;
  original_url: string;
  thumbnail_url: string;
  rights_confirmed: boolean;
};

export type Clip = {
  id: number;
  job_id: number;
  start_seconds: number;
  end_seconds: number;
  hook: string;
  reason: string;
  title: string;
  description: string;
  copy: string;
  tags: string[];
  media_url: string;
  status: string;
  youtube_video_id?: string | null;
  upload_error?: string | null;
  created_at: string;
};

export type Job = {
  id: number;
  status: string;
  progress: number;
  error?: string | null;
  requested_clips: number;
  created_at: string;
  updated_at: string;
  source_video: SourceVideo;
  clips: Clip[];
};
