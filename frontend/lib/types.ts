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
