// Cliente HTTP de AITuber Libre. Todo es local: misma origen, sin servicios externos.

const TOKEN_KEY = 'aituber_token';

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setToken(value: string): void {
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* almacenamiento no disponible */
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const token = getToken();
  if (token) headers['X-App-Token'] = token;
  const response = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string> | undefined) } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* sin cuerpo JSON */
    }
    if (response.status === 401) throw new Error('Token de acceso requerido. Configuralo en Ajustes.');
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
  caption_style: string;
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

export interface Meta {
  voices: { id: string; label: string; available: boolean; gender?: string; language?: string }[];
  aspects: string[];
  kinds: { id: string; label: string; aspect: string }[];
  templates: TemplateOption[];
  external_templates: TemplateOption[];
  resolutions: OptionItem[];
  fps_options: number[];
  caption_styles: OptionItem[];
  transitions: OptionItem[];
  music_beds: OptionItem[];
  music_library: string[];
  script_templates: OptionItem[];
  evidence_levels: string[];
  settings: Record<string, string>;
  auth_required: boolean;
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
  tts: { available: boolean; engine: string; voices: { id: string; label: string; available: boolean }[]; note: string };
  font: string | null;
  ffmpeg_version: string;
  ollama: { url: string; available: boolean; optional: boolean };
  counts: Record<string, number>;
  worker: { worker_alive: boolean; queued: number; running: number; done: number; failed: number; engine?: string };
  token_configured: boolean;
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
