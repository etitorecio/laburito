// Cliente HTTP de AITuber Libre. Todo es local: misma origen, sin servicios externos.

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string> | undefined) } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* sin cuerpo JSON */
    }
    if (response.status === 401) throw new Error('La solicitud no fue autorizada.');
    throw new Error(detail);
  }
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return (await response.json()) as T;
  return (await response.text()) as unknown as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T,>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  put: <T,>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  del: <T,>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T,>(path: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<T>(path, { method: 'POST', body: form });
  },
};

export interface Scene {
  id: number;
  project_id: number;
  idx: number;
  title: string;
  narration: string;
  visual_query: string;
  transition: string;
  status: string;
  visual_path: string | null;
  visual_kind: string | null;
  visual_license: string | null;
  visual_author: string | null;
  visual_url: string | null;
  sfx_path?: string;
  sfx_volume?: number;
  sfx_start_sec?: number;
  updated_at: string;
}

export interface Source {
  id: number;
  project_id: number | null;
  scene_id: number | null;
  title: string;
  url: string;
  author: string;
  license: string;
  accessed_at: string;
  attribution: string;
  kind: string;
  notes?: string;
}

export interface Job {
  id: number;
  project_id: number | null;
  kind: string;
  status: string;
  progress: number;
  message: string;
  attempts: number;
  created_at: string;
  updated_at: string;
  project_title?: string | null;
}

export interface Project {
  id: number;
  channel_id: number | null;
  title: string;
  topic: string;
  kind: string;
  aspect: string;
  status: string;
  duration_target_sec: number;
  voice: string;
  speed: number;
  pitch: number;
  notes: string;
  template: string;
  visual_style: string;
  visual_style_prompt?: string;
  create_thumbnail?: boolean;
  thumbnail_path?: string;
  video_type: string;
  caption_style: string;
  captions_enabled?: boolean;
  transition_default: string;
  resolution: string;
  fps: number;
  music: string;
  music_volume: number | null;
  quality_json: string | null;
  quality?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  channel_name?: string | null;
  scenes_count?: number;
  scenes?: Scene[];
  sources?: Source[];
  jobs?: Job[];
  job?: Pick<Job, 'id' | 'status' | 'progress' | 'message'> | null;
}

export interface Channel {
  id: number;
  name: string;
  topic: string;
  language: string;
  audience: string;
  tone: string;
  visual_identity: string;
  formats: string;
  cadence: string;
  projects?: number;
  next_entry?: CalendarEntry | null;
}

export interface CalendarEntry {
  id: number;
  channel_id: number;
  project_id: number | null;
  scheduled_for: string;
  format: string;
  title: string;
  status: string;
  channel_name?: string;
  project_title?: string | null;
}

export interface Niche {
  id: number;
  name: string;
  demand: number;
  competition: number;
  trend: string;
  difficulty: number;
  copyright_risk: string;
  monetization: string;
  series_potential: number;
  notes: string;
  opportunity?: number;
}

export interface Note {
  id: number;
  niche: string;
  claim: string;
  evidence_level: string;
  source_url: string;
  accessed_at: string;
  methodology: string;
}

export interface Asset {
  id: number;
  project_id: number | null;
  scene_id: number | null;
  kind: string;
  path: string;
  label: string;
  license: string;
  author: string;
  url: string;
  bytes: number;
  created_at: string;
  project_title?: string | null;
}

export interface MediaResult {
  title: string;
  url: string;
  page: string;
  author: string;
  license: string;
  provider: string;
  thumb?: string;
  width?: number;
  height?: number;
}

export interface AnalyticsRow {
  id: number;
  title: string;
  format: string;
  impressions: number;
  views: number;
  ctr: number;
  retention: number;
  avg_duration_sec: number;
  interactions: number;
  subscribers: number;
  published_at: string;
  origin: string;
}

export interface AnalyticsSummary {
  count: number;
  summary: {
    views: number;
    impressions: number;
    ctr: number;
    retention: number;
    subscribers: number;
    formats: { format: string; videos: number; views: number; retention: number }[];
    best: { title: string; views: number; retention: number };
  } | null;
  hypotheses?: string[];
  note?: string;
}

export interface TemplateOption {
  id: string;
  label: string;
  description?: string;
  kind: string;
  aspect: string;
  script: string;
  caption_style: string;
  durations: number[];
  default_duration: number;
  available: boolean;
  requires?: string;
}

export interface OptionItem {
  id: string;
  label: string;
  note?: string;
}

export interface AutopilotRule {
  id: number;
  name: string;
  niche: string;
  channel_id: number | null;
  channel_name?: string | null;
  template: string;
  duration_target_sec: number | null;
  voice: string;
  speed: number;
  pitch: number;
  visual_style: string;
  visual_style_prompt?: string;
  create_thumbnail?: boolean;
  video_type: string;
  title_style: string;
  custom_tags: string;
  aspect: string;
  caption_style: string;
  captions_enabled?: boolean;
  transition_default: string;
  resolution: string;
  fps: number;
  music: string;
  music_volume: number;
  audience: string;
  tone: string;
  hook_style: string;
  cta: string;
  content_pillars: string;
  avoid_topics: string;
  cadence_hours: number;
  videos_per_period: number;
  period_days: number;
  schedule_time: string;
  timezone: string;
  enabled: boolean;
  destination: string;
  privacy: string;
  auto_publish: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_project_id: number | null;
  last_project_title?: string | null;
  last_project_status?: string | null;
  last_job_status?: string | null;
  last_job_message?: string | null;
  last_job_progress?: number | null;
  last_job_kind?: string | null;
  last_error?: string | null;
}

export interface Meta {
  voices: { id: string; label: string; available: boolean; gender?: string; language?: string }[];
  video_types: (OptionItem & { description: string; available: boolean })[];
  visual_styles: (OptionItem & { description: string })[];
  aspects: string[];
  kinds: { id: string; label: string; aspect: string }[];
  templates: TemplateOption[];
  external_templates: TemplateOption[];
  resolutions: OptionItem[];
  fps_options: number[];
  caption_styles: (OptionItem & {
    max_words?: number; max_chars?: number; max_lines?: number; font_ratio?: number;
    y_from_bottom?: number; box?: boolean; box_alpha?: string; boxcolor?: string;
    fontcolor?: string; outline?: number; uppercase?: boolean;
  })[];
  transitions: OptionItem[];
  music_beds: OptionItem[];
  music_library: string[];
  script_templates: OptionItem[];
  evidence_levels: string[];
  settings: Record<string, string>;
}

export interface Diagnostics {
  version: string;
  python: string;
  platform: string;
  data_dir: string;
  data_writable: boolean;
  disk_free_mb: number;
  db_size_kb: number;
  checks: Record<string, boolean>;
  tts: { available: boolean; engine: string; piper_installed?: boolean; piper_available?: boolean; piper_model?: string | null; voices: { id: string; label: string; available: boolean }[]; note: string };
  font: string | null;
  ffmpeg_version: string;
  ollama: { url: string; available: boolean; optional: boolean };
  counts: Record<string, number>;
  worker: { worker_alive: boolean; queued: number; running: number; done: number; failed: number; engine?: string };
  persistence: { configured: boolean; local_persistent?: boolean; provider: string | null; bucket: string | null; private: boolean | null; note: string };
  note: string;
}

export interface LogRow {
  id: number;
  level: string;
  scope: string;
  message: string;
  data: string | null;
  created_at: string;
}

export function mediaUrl(path: string): string {
  const clean = path.replace(/^.*\/data\//, '').replace(/^\/+/, '');
  return `/media/${clean}`;
}

export function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds || 0));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}
