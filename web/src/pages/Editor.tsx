import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react';
import { api, fmtDuration, mediaUrl, type MediaResult, type Meta, type Project, type Scene, type TimelineOverlay } from '../api';
import { Badge, Card, Empty, Field, Msg, Progress, statusTone } from '../ui';
import type { Route } from '../routes';
import CaptionStylePicker from '../components/CaptionStylePicker';
import TransitionPicker from '../components/TransitionPicker';
import VisualStylePicker from '../components/VisualStylePicker';
import VideoTypePicker from '../components/VideoTypePicker';
import VoicePicker from '../components/VoicePicker';

interface Props {
  projectId: number;
  go: (route: Route, id?: number) => void;
}

interface PublishDestination {
  id: string;
  label: string;
  available: boolean;
  missing_env: string[];
  note: string;
}

interface YoutubeWorkspaceChannel {
  id: number;
  name: string;
  account: { channel_title: string; youtube_channel_id: string } | null;
}

interface Publication {
  id: number;
  project_id: number;
  destination: string;
  status: string;
  url: string;
  external_id: string;
  message: string;
  created_at: string;
}

interface EditorHistoryEntry {
  target: "scene" | "overlay";
  id: number;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  label: string;
}

const META_MARKER = '[LABURITO_META]';

function captionsEnabledFromNotes(notes: string): boolean {
  if (!notes.includes(META_MARKER)) return true;
  try {
    const metadata = JSON.parse(notes.split(META_MARKER, 2)[1] || '{}');
    return metadata.captions_enabled !== false;
  } catch {
    return true;
  }
}

function notesWithCaptionsSetting(notes: string, enabled: boolean): string {
  const [prefix, rawMetadata] = notes.includes(META_MARKER)
    ? notes.split(META_MARKER, 2)
    : [notes, '{}'];
  let metadata: Record<string, unknown> = {};
  try {
    metadata = JSON.parse(rawMetadata || '{}');
  } catch {
    metadata = {};
  }
  return prefix + META_MARKER + JSON.stringify({ ...metadata, captions_enabled: enabled });
}

function visualStylePromptFromNotes(notes: string): string {
  if (!notes.includes(META_MARKER)) return '';
  try {
    const metadata = JSON.parse(notes.split(META_MARKER, 2)[1] || '{}');
    return typeof metadata.visual_style_prompt === 'string' ? metadata.visual_style_prompt : '';
  } catch {
    return '';
  }
}

function notesWithVisualStylePrompt(notes: string, prompt: string): string {
  const [prefix, rawMetadata] = notes.includes(META_MARKER)
    ? notes.split(META_MARKER, 2)
    : [notes, '{}'];
  let metadata: Record<string, unknown> = {};
  try {
    metadata = JSON.parse(rawMetadata || '{}');
  } catch {
    metadata = {};
  }
  if (prompt.trim()) metadata.visual_style_prompt = prompt.trim().slice(0, 240);
  else delete metadata.visual_style_prompt;
  return prefix + META_MARKER + JSON.stringify(metadata);
}

function thumbnailEnabledFromNotes(notes: string): boolean {
  if (!notes.includes(META_MARKER)) return true;
  try {
    const metadata = JSON.parse(notes.split(META_MARKER, 2)[1] || '{}');
    return metadata.create_thumbnail !== false;
  } catch {
    return true;
  }
}

function notesWithThumbnailSetting(notes: string, enabled: boolean): string {
  const [prefix, rawMetadata] = notes.includes(META_MARKER)
    ? notes.split(META_MARKER, 2)
    : [notes, '{}'];
  let metadata: Record<string, unknown> = {};
  try {
    metadata = JSON.parse(rawMetadata || '{}');
  } catch {
    metadata = {};
  }
  metadata.create_thumbnail = enabled;
  return prefix + META_MARKER + JSON.stringify(metadata);
}

export default function Editor({ projectId, go }: Props) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [busy, setBusy] = useState('');
  const [searchFor, setSearchFor] = useState<number | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<number | null>(null);
  const [overlays, setOverlays] = useState<TimelineOverlay[]>([]);
  const [selectedOverlayId, setSelectedOverlayId] = useState<number | null>(null);
  const [draggedOverlayId, setDraggedOverlayId] = useState<number | null>(null);
  const [draggedOverlayOffset, setDraggedOverlayOffset] = useState(0);
  const [visualVariantIndex, setVisualVariantIndex] = useState<Record<number, number>>({});
  const [overlayTextDraft, setOverlayTextDraft] = useState("");
  const [voiceDraft, setVoiceDraft] = useState("");
  const [voiceOverlayVoice, setVoiceOverlayVoice] = useState("");
  const [voiceOverlaySpeed, setVoiceOverlaySpeed] = useState<number | null>(null);
  const [voiceOverlayPitch, setVoiceOverlayPitch] = useState<number | null>(null);
  const [musicBedId, setMusicBedId] = useState("ambiente");
  const [sfxEffectId, setSfxEffectId] = useState("whoosh");
  const [draggedSceneId, setDraggedSceneId] = useState<number | null>(null);
  const [previewPlaying, setPreviewPlaying] = useState(false);
  const [previewElapsed, setPreviewElapsed] = useState(0);
  const [timelineZoom, setTimelineZoom] = useState(1);
  const [splitCursor, setSplitCursor] = useState(0);
  const narrationRef = useRef<HTMLTextAreaElement | null>(null);
  const skipNarrationBlurRef = useRef(false);
  const [results, setResults] = useState<MediaResult[]>([]);
  const [destinations, setDestinations] = useState<PublishDestination[]>([]);
  const [publications, setPublications] = useState<Publication[]>([]);
  const [youtubeChannels, setYoutubeChannels] = useState<YoutubeWorkspaceChannel[]>([]);
  const [publishDest, setPublishDest] = useState('entrega');
  const [historyVersion, setHistoryVersion] = useState(0);
  const historyRef = useRef<EditorHistoryEntry[]>([]);
  const historyCursorRef = useRef(0);
  const historyReplayRef = useRef(false);
  const timer = useRef<number | null>(null);

  useEffect(() => { setSplitCursor(0); }, [selectedSceneId]);

  const load = useCallback(async () => {
    try {
      const nextProject = await api.get<Project>(`/api/projects/${projectId}`);
      const nextOverlays = nextProject.timeline_overlays
        ?? await api.get<TimelineOverlay[]>(`/api/projects/${projectId}/timeline-overlays`);
      setProject(nextProject);
      setOverlays(nextOverlays);
      setSelectedOverlayId((current) => current && nextOverlays.some((clip) => clip.id === current) ? current : null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [projectId]);

  const loadPublish = useCallback(async () => {
    try {
      const [dest, pubs, auto, accounts] = await Promise.all([
        api.get<{ destinations: PublishDestination[] }>('/api/publish/destinations'),
        api.get<{ publications: Publication[] }>(`/api/publications?project_id=${projectId}`),
        api.get<{ enabled: boolean; destination: string }>(`/api/projects/${projectId}/auto-publish`),
        api.get<{ accounts: YoutubeWorkspaceChannel[] }>('/api/youtube/accounts'),
      ]);
      setDestinations(dest.destinations);
      setPublications(pubs.publications);
      setYoutubeChannels(accounts.accounts);
      setPublishDest(auto.destination || 'entrega');
    } catch (e) {
      setError((e as Error).message);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
    void loadPublish();
  }, [load, loadPublish]);

  // Mientras hay un render en curso, refrescamos el proyecto.
  useEffect(() => {
    const active = project?.jobs?.some((j) => ['en_cola', 'ejecutando'].includes(j.status));
    if (!active) return;
    timer.current = window.setInterval(() => void load(), 4000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [project, load]);

  const linkedYoutubeAccount = youtubeChannels.find((channel) => channel.id === project?.channel_id)?.account ?? null;

  // Reproducción de revisión con avance automático entre escenas.
  useEffect(() => {
    if (!previewPlaying) return;
    const tick = window.setInterval(() => {
      setPreviewElapsed((elapsed) => {
        const currentScenes = project?.scenes ?? [];
        const total = currentScenes.reduce((sum, scene) => sum + Math.max(2, Number(scene.audio_sec) || (scene.narration || '').trim().split(/\s+/).filter(Boolean).length / 2.4), 0);
        if (elapsed + 0.25 >= total) {
          setPreviewPlaying(false);
          return total;
        }
        return elapsed + 0.25;
      });
    }, 250);
    return () => window.clearInterval(tick);
  }, [previewPlaying, project?.scenes]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(target.tagName))) return;
      if (event.code === 'Space') {
        event.preventDefault();
        setPreviewPlaying((playing) => !playing);
      } else if (event.code === 'ArrowLeft' || event.code === 'ArrowRight') {
        event.preventDefault();
        const direction = event.code === 'ArrowRight' ? 1 : -1;
        const total = (project?.scenes ?? []).reduce((sum, scene) => sum + Math.max(2, Number(scene.audio_sec) || (scene.narration || '').trim().split(/\s+/).filter(Boolean).length / 2.4), 0);
        setPreviewPlaying(false);
        setPreviewElapsed((elapsed) => Math.max(0, Math.min(total, elapsed + direction)));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [project?.scenes]);

  async function assignChannel(channelId: string) {
    if (!channelId) return;
    setBusy('channel'); setError(''); setOk('');
    try {
      const updated = await api.patch<Project>(`/api/projects/${projectId}`, { channel_id: Number(channelId) });
      setProject(updated);
      setOk('Canal asignado. YouTube usará la cuenta vinculada a ese canal.');
      await loadPublish();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function publishNow() {
    if (publishDest === 'youtube' && !linkedYoutubeAccount) {
      setError('Conectá la cuenta de YouTube correspondiente desde Cuentas antes de publicar este proyecto.');
      return;
    }
    setBusy('publish');
    setError('');
    setOk('');
    try {
      await api.post(`/api/projects/${projectId}/publish`, { destination: publishDest });
      setOk(`Publicación encolada en ${publishDest}.`);
      await Promise.all([load(), loadPublish()]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function generateScript(replace = true) {
    setBusy('script');
    setError('');
    setOk('');
    try {
      const res = await api.post<{ warnings: string[] }>(`/api/projects/${projectId}/script?replace=${replace}`);
      setOk(`Guion generado con ${replace ? 'escenas nuevas' : 'escenas agregadas'}.${res.warnings?.length ? ' Avisos: ' + res.warnings.join(' ') : ''}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  const [voices, setVoices] = useState<Meta['voices']>([]);
  const [meta, setMeta] = useState<Meta | null>(null);

  // Voces y catálogos realmente utilizables en este servidor (espeak-ng/Piper, FFmpeg).
  useEffect(() => {
    api
      .get<Meta>('/api/meta')
      .then((m) => {
        setMeta(m);
        setVoices((m.voices || []).filter((v) => v.available !== false));
      })
      .catch(() => setVoices([]));
  }, []);

  async function patchProject(patch: Record<string, unknown>) {
    try {
      setProject(await api.patch<Project>(`/api/projects/${projectId}`, patch));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function recordHistory(entry: EditorHistoryEntry) {
    if (historyReplayRef.current || !Object.keys(entry.after).length) return;
    const next = historyRef.current.slice(0, historyCursorRef.current);
    next.push(entry);
    historyRef.current = next.slice(-100);
    historyCursorRef.current = historyRef.current.length;
    setHistoryVersion((version) => version + 1);
  }

  async function replayHistory(direction: "undo" | "redo") {
    const index = direction === "undo" ? historyCursorRef.current - 1 : historyCursorRef.current;
    const entry = historyRef.current[index];
    if (!entry) return;
    historyReplayRef.current = true;
    setBusy(direction);
    setError("");
    try {
      const patch = direction === "undo" ? entry.before : entry.after;
      if (entry.target === "scene") {
        const updated = await api.patch<Scene>(`/api/scenes/${entry.id}`, patch);
        setProject((prev) => prev
          ? { ...prev, scenes: (prev.scenes ?? []).map((scene) => scene.id === updated.id ? updated : scene) }
          : prev);
      } else {
        const updated = await api.patch<TimelineOverlay>(`/api/timeline-overlays/${entry.id}`, patch);
        setOverlays((current) => current.map((clip) => clip.id === updated.id ? updated : clip));
      }
      historyCursorRef.current += direction === "undo" ? -1 : 1;
      setHistoryVersion((version) => version + 1);
      setOk(direction === "undo" ? `Deshecho: ${entry.label}` : `Rehecho: ${entry.label}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      historyReplayRef.current = false;
      setBusy("");
    }
  }

  async function undoHistory() {
    await replayHistory("undo");
  }

  async function redoHistory() {
    await replayHistory("redo");
  }

  async function patchScene(scene: Scene, patch: Partial<Scene>) {
    try {
      const updated = await api.patch<Scene>(`/api/scenes/${scene.id}`, patch);
      setProject((prev) =>
        prev ? { ...prev, scenes: (prev.scenes ?? []).map((s) => (s.id === updated.id ? updated : s)) } : prev,
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function addScene() {
    setBusy('scene-add');
    setError('');
    setOk('');
    try {
      const created = await api.post<Scene>(`/api/projects/${projectId}/scenes`, {
        title: `Escena ${(project?.scenes?.length ?? 0) + 1}`,
        narration: '',
        visual_query: project?.topic || project?.title || '',
        transition: project?.transition_default || 'corte',
      });
      setSelectedSceneId(created.id);
      await load();
      setOk('Escena vacía creada. Escribí la narración y elegí su visual antes de renderizar.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function regenerateVisual(scene: Scene) {
    setBusy("visual-" + scene.id);
    setError("");
    setOk("");
    try {
      const variant = visualVariantIndex[scene.id] ?? 0;
      await api.post(`/api/scenes/${scene.id}/regenerate-visual?variant=${variant}`, {});
      setVisualVariantIndex((current) => ({ ...current, [scene.id]: variant + 1 }));
      await load();
      setSelectedSceneId(scene.id);
      setOk("Visual alternativo aplicado. La fuente y su licencia quedaron guardadas.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function duplicateScene(scene: Scene) {
    setBusy(`duplicate-${scene.id}`);
    setError('');
    setOk('');
    try {
      const created = await api.post<Scene>(`/api/scenes/${scene.id}/duplicate`, {});
      await load();
      setSelectedSceneId(created.id);
      setOk('Escena duplicada con su visual, efecto y transición.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function splitSceneAtCursor(scene: Scene, requestedSplitAt?: number) {
    const narration = narrationRef.current?.value ?? scene.narration;
    const splitAt = requestedSplitAt ?? narrationRef.current?.selectionStart ?? splitCursor;
    skipNarrationBlurRef.current = false;
    setBusy("split-" + scene.id);
    setError("");
    setOk("");
    try {
      const splitTime = (timelineStarts[activeSceneIndex] || 0) +
        ((sceneDurations[activeSceneIndex] || 0) * (narration.length ? splitAt / narration.length : 0.5));
      const result = await api.post<{ first: Scene; second: Scene }>(
        "/api/scenes/" + scene.id + "/split",
        { narration, split_at: splitAt },
      );
      await load();
      setSelectedSceneId(result.second.id);
      setPreviewElapsed(splitTime);
      setPreviewPlaying(false);
      setOk("Escena dividida en dos clips independientes.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function regenerate(scene: Scene) {
    setBusy(`regenerate-${scene.id}`);
    setError('');
    setOk('');
    try {
      const result = await api.post<{ note: string }>(`/api/scenes/${scene.id}/regenerate`);
      setOk(result.note || 'Escena regenerada. Revisá el texto antes de renderizar.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function move(scene: Scene, delta: number) {
    if (!project?.scenes) return;
    const ids = project.scenes.map((s) => s.id);
    const from = ids.indexOf(scene.id);
    const to = from + delta;
    if (to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    try {
      await api.post(`/api/projects/${projectId}/scenes/order`, { ids });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function reorderScene(draggedId: number, targetId: number) {
    if (!project?.scenes || draggedId === targetId) return;
    const ids = project.scenes.map((scene) => scene.id);
    const from = ids.indexOf(draggedId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    try {
      await api.post(`/api/projects/${projectId}/scenes/order`, { ids });
      setSelectedSceneId(draggedId);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDraggedSceneId(null);
    }
  }

  async function removeScene(scene: Scene) {
    try {
      await api.del(`/api/scenes/${scene.id}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function searchVisual(scene: Scene) {
    setSearchFor(scene.id);
    setResults([]);
    setError('');
    try {
      const data = await api.post<{ results: MediaResult[]; errors: Record<string, string> }>('/api/research/search', {
        query: scene.visual_query || scene.title,
        provider: 'all',
      });
      setResults(data.results);
      if (!data.results.length) {
        setError('Sin resultados para esa búsqueda. Podés seguir con la tarjeta visual generada localmente.');
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function uploadSceneImage(scene: Scene, file: File) {
    setBusy(`upload-visual-${scene.id}`);
    setError('');
    setOk('');
    try {
      await api.upload(`/api/scenes/${scene.id}/media`, file);
      setOk((file.type.startsWith('video/') ? 'Clip de video' : 'Imagen') + ' asignado a la escena. Se guardó localmente.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  function dropOverlayOnLane(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (draggedOverlayId === null) return;
    const clip = overlays.find((item) => item.id === draggedOverlayId);
    if (!clip) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const seconds = Math.max(0, Math.round(((event.clientX - rect.left - draggedOverlayOffset) / timelineScale) * 10) / 10);
    void patchTimelineOverlay(clip, { start_sec: seconds });
    setDraggedOverlayId(null);
    setDraggedOverlayOffset(0);
  }

  async function createTimelineSfxOverlay() {
    setBusy("create-sfx-overlay");
    setError("");
    setOk("");
    try {
      const clip = await api.post<TimelineOverlay>(`/api/projects/${projectId}/timeline-overlays/sfx`, {
        effect: sfxEffectId,
        start_sec: previewElapsed,
        volume: 0.8,
      });
      await load();
      setSelectedOverlayId(clip.id);
      setOk("Efecto de sonido generado localmente y añadido a la pista.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function createTimelineMusicOverlay() {
    setBusy("create-music-overlay");
    setError("");
    setOk("");
    try {
      const duration = Math.max(5, Math.min(3600, timelineDuration - previewElapsed || 45));
      const clip = await api.post<TimelineOverlay>(`/api/projects/${projectId}/timeline-overlays/music`, {
        bed_id: musicBedId,
        start_sec: previewElapsed,
        duration_sec: duration,
        volume: 0.35,
      });
      await load();
      setSelectedOverlayId(clip.id);
      setOk("Música local generada y añadida a la pista de audio.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function createTimelineVoiceOverlay() {
    const text = voiceDraft.trim();
    if (!text) return;
    setBusy("create-voice-overlay");
    setError("");
    setOk("");
    try {
      const clip = await api.post<TimelineOverlay>(`/api/projects/${projectId}/timeline-overlays/voice`, {
        text,
        start_sec: previewElapsed,
        voice: voiceOverlayVoice || project?.voice || "es",
        speed: voiceOverlaySpeed ?? project?.speed ?? 150,
        pitch: voiceOverlayPitch ?? project?.pitch ?? 45,
        volume: 1,
      });
      setVoiceDraft("");
      await load();
      setSelectedOverlayId(clip.id);
      setOk("Voz en off generada localmente y añadida a la pista de audio.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function createTimelineTextOverlay() {
    const text = overlayTextDraft.trim();
    if (!text) return;
    setBusy("create-text-overlay");
    setError("");
    setOk("");
    try {
      const clip = await api.post<TimelineOverlay>(`/api/projects/${projectId}/timeline-overlays/text`, {
        text,
        start_sec: previewElapsed,
        duration_sec: 4,
      });
      setOverlayTextDraft("");
      await load();
      setSelectedOverlayId(clip.id);
      setOk("Texto agregado como una capa independiente.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function uploadTimelineOverlay(file: File) {
    setBusy("upload-overlay");
    setError("");
    setOk("");
    try {
      const clip = await api.upload<TimelineOverlay>(
        `/api/projects/${projectId}/timeline-overlays/upload?start_sec=${encodeURIComponent(previewElapsed)}`,
        file,
      );
      await load();
      setSelectedOverlayId(clip.id);
      setOk("Capa agregada a la línea de tiempo.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function patchTimelineOverlay(clip: TimelineOverlay, patch: Partial<TimelineOverlay>) {
    try {
      const updated = await api.patch<TimelineOverlay>(`/api/timeline-overlays/${clip.id}`, patch);
      setOverlays((current) => current.map((item) => item.id === clip.id ? updated : item));
      setOk("Capa guardada.");
    } catch (e) {
      setError((e as Error).message);
      await load();
    }
  }

  async function removeTimelineOverlay(clip: TimelineOverlay) {
    try {
      await api.del(`/api/timeline-overlays/${clip.id}`);
      setOverlays((current) => current.filter((item) => item.id !== clip.id));
      setSelectedOverlayId(null);
      setOk("Capa eliminada.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function uploadSceneSound(scene: Scene, file: File) {
    setBusy("upload-sound-" + scene.id);
    setError("");
    setOk("");
    try {
      await api.upload("/api/scenes/" + scene.id + "/sound", file);
      setOk("Efecto de sonido agregado a la escena.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function removeSceneSound(scene: Scene) {
    try {
      await api.del("/api/scenes/" + scene.id + "/sound");
      setOk("Efecto de sonido quitado.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function applyVisual(scene: Scene, item: MediaResult) {
    setBusy(`visual-${scene.id}`);
    try {
      await api.post(`/api/scenes/${scene.id}/visual`, {
        url: item.url,
        license: item.license,
        author: item.author,
        page: item.page,
        title: item.title,
      });
      setOk('Recurso aplicado a la escena y registrado con su licencia.');
      setSearchFor(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function render() {
    setBusy('render');
    setError('');
    setOk('');
    try {
      const res = await api.post<{ job_id: number; reused: boolean }>(`/api/projects/${projectId}/render`);
      setOk(res.reused ? `Ya hay un render en curso (tarea #${res.job_id}).` : `Render encolado (tarea #${res.job_id}).`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  if (!project) {
    return (
      <div className="stack">
        <Msg error={error} />
        {!error && <Card title="Cargando proyecto…"><Progress value={40} /></Card>}
      </div>
    );
  }

  const scenes = project.scenes ?? [];
  const activeScene = scenes.find((scene) => scene.id === selectedSceneId) ?? scenes[0] ?? null;
  const activeSceneIndex = activeScene ? scenes.findIndex((scene) => scene.id === activeScene.id) : -1;
  const activeNarrationLength = activeScene ? (narrationRef.current?.value.length ?? activeScene.narration.length) : 0;
  const canRender = scenes.length > 0 && scenes.every((scene) => Boolean(scene.narration.trim()));
  const words = scenes.reduce((acc, s) => acc + (s.narration || '').trim().split(/\s+/).filter(Boolean).length, 0);
  const quality = project.quality ?? {};
  const captionsEnabled = captionsEnabledFromNotes(project.notes || '');
  const visualStylePrompt = visualStylePromptFromNotes(project.notes || '');
  const thumbnailEnabled = thumbnailEnabledFromNotes(project.notes || '');
  const warnings = Array.isArray(quality.warnings) ? (quality.warnings as string[]) : [];
  const totalChars = scenes.reduce((acc, s) => acc + (s.narration || '').length, 0);
  // La línea de tiempo usa una escala temporal común para todas las pistas.
  const sceneDurations = scenes.map((scene) =>
    Math.max(2, Number(scene.audio_sec) || (scene.narration || '').trim().split(/\s+/).filter(Boolean).length / 2.4),
  );
  const timelineScale = 18 * timelineZoom;
  const timelineStarts = sceneDurations.map((_, index) =>
    sceneDurations.slice(0, index).reduce((sum, duration) => sum + duration, 0),
  );
  const timelineDuration = sceneDurations.reduce((sum, duration) => sum + duration, 0);
  const timelineWidth = Math.max(240, timelineDuration * timelineScale);
  const rawPreviewSceneIndex = timelineStarts.findIndex((start, index) => previewElapsed >= start && previewElapsed < start + sceneDurations[index]);
  const previewSceneIndex = rawPreviewSceneIndex >= 0 ? rawPreviewSceneIndex : Math.max(0, scenes.length - 1);
  const previewScene = scenes[previewSceneIndex] ?? activeScene;
  const previewWords = (previewScene?.narration || '').trim().split(/\s+/).filter(Boolean);
  const previewSceneElapsed = Math.max(0, previewElapsed - (timelineStarts[previewSceneIndex] || 0));
  const previewWordIndex = Math.min(Math.max(0, previewWords.length - 1), Math.floor((previewSceneElapsed / Math.max(0.1, sceneDurations[previewSceneIndex] || 1)) * previewWords.length));
  const previewCaptionStart = Math.max(0, previewWordIndex - 2);
  const previewCaptionWords = previewWords.slice(previewCaptionStart, previewCaptionStart + 5);
  const rulerStep = timelineDuration > 180 ? 30 : timelineDuration > 90 ? 15 : 5;

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      <div className="editor-projectbar">
        <div className="editor-project-title"><h2>{project.title}</h2><span>{project.kind === 'short' ? 'Short vertical' : 'Video largo'} · {project.aspect} · {scenes.length} escenas</span></div>
        <div className="row gap-8">
          <button className="btn small ghost" onClick={() => go('proyectos')}>Volver</button>
          <button className="btn small" onClick={addScene} disabled={!!busy}>{busy === 'scene-add' ? 'Creando…' : 'Nueva escena'}</button>
          <button className="btn small" onClick={() => generateScript(false)} disabled={busy === 'script'}>Generar más escenas</button>
          <button className="btn small primary" onClick={render} disabled={busy === 'render' || !canRender} title={!canRender ? 'Completá la narración de todas las escenas antes de renderizar' : 'Renderizar el video'}>Renderizar</button>
        </div>
      </div>
      <details className="editor-settings">
        <summary><strong>Configuración del video</strong><span>Duración · voz · estilo visual · subtítulos · música</span></summary>
      <Card
        title={project.title}
        sub={`${project.kind === 'short' ? 'Short vertical' : 'Documental'} · ${project.aspect} · ${scenes.length} escenas · ${words} palabras · ~${fmtDuration(totalChars / 14)} de voz`}
      >
        <div className="pill-row" style={{ marginBottom: 12 }}>
          <Badge tone={statusTone(project.status)}>{project.status}</Badge>
          <Badge tone="info">{project.channel_name || 'fábrica sin asignar'}</Badge>
          {quality.resolution ? <Badge>{String(quality.resolution)}</Badge> : null}
          {quality.duration_sec ? <Badge>{fmtDuration(Number(quality.duration_sec))}</Badge> : null}
        </div>

        <div className="row">
          <Field label="Título">
            <input defaultValue={project.title} onBlur={(e) => e.target.value !== project.title && patchProject({ title: e.target.value })} />
          </Field>
          <Field label="Tema">
            <input defaultValue={project.topic} onBlur={(e) => e.target.value !== project.topic && patchProject({ topic: e.target.value })} />
          </Field>
          <Field label="Duración objetivo (s)">
            <input type="number" defaultValue={project.duration_target_sec} onBlur={(e) => patchProject({ duration_target_sec: Number(e.target.value) })} />
          </Field>
        </div>
        <div className="row">
          <Field label="Velocidad de voz">
            <input type="number" defaultValue={project.speed} onBlur={(e) => patchProject({ speed: Number(e.target.value) })} />
          </Field>
          <Field label="Tono de voz">
            <input type="number" defaultValue={project.pitch} onBlur={(e) => patchProject({ pitch: Number(e.target.value) })} />
          </Field>
          <Field label="Aspecto">
            <select defaultValue={project.aspect} onChange={(e) => patchProject({ aspect: e.target.value })}>
              <option value="16:9">16:9 horizontal</option>
              <option value="9:16">9:16 vertical</option>
              <option value="1:1">1:1 cuadrado</option>
              <option value="4:5">4:5 feed vertical</option>
            </select>
          </Field>
          <Field label="Voz en español">
            <VoicePicker
              options={meta?.voices ?? []}
              value={project.voice}
              speed={project.speed}
              pitch={project.pitch}
              onChange={(value) => void patchProject({
                voice: value,
                ...(value === 'es-masculino' ? { pitch: 30 } : value === 'es-agudo' ? { pitch: 65 } : { pitch: 45 }),
              })}
              compact
            />
          </Field>
        </div>
        <div className="row">
          <Field label="Plantilla">
            <select
              value={project.template}
              onChange={(e) => {
                const tpl = (meta?.templates ?? []).find((t) => t.id === e.target.value);
                patchProject(
                  tpl
                    ? { template: tpl.id, aspect: tpl.aspect, caption_style: tpl.caption_style }
                    : { template: e.target.value },
                );
              }}
            >
              {(meta?.templates ?? [{ id: project.template, label: project.template }]).map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </Field>
          <label className="check-row">
            <input
              type="checkbox"
              checked={captionsEnabled}
              onChange={(e) => void patchProject({ notes: notesWithCaptionsSetting(project.notes || '', e.target.checked) })}
            />
            Agregar subtítulos al video
          </label>
          {captionsEnabled ? (
            <Field label="Estilo de subtítulos">
              <CaptionStylePicker
                options={meta?.caption_styles ?? [{ id: project.caption_style, label: project.caption_style }]}
                value={project.caption_style}
                onChange={(value) => void patchProject({ caption_style: value })}
                compact
              />
            </Field>
          ) : <p className="muted">Los subtítulos están desactivados para este proyecto.</p>}
          <Field label="Tipo de video">
            <VideoTypePicker
              options={meta?.video_types ?? []}
              value={project.video_type || 'moving_images'}
              onChange={(value) => void patchProject({ video_type: value })}
              compact
            />
          </Field>
          <Field label="Estilo visual">
            <VisualStylePicker
              options={meta?.visual_styles ?? []}
              value={project.visual_style || 'automatico'}
              onChange={(value) => void patchProject({ visual_style: value })}
              compact
            />
            <Field label="Estilo personalizado (opcional)">
              <textarea
                rows={3}
                maxLength={240}
                value={visualStylePrompt}
                onChange={(e) => void patchProject({ notes: notesWithVisualStylePrompt(project.notes || '', e.target.value) })}
                placeholder="Ej.: iluminación cálida, fotografía analógica, tonos verdes y textura de película…"
              />
            </Field>
            <p className="muted">La descripción guía la búsqueda de imágenes libres y algunos filtros locales; no genera imágenes IA.</p>
            <label className="check-row">
              <input
                type="checkbox"
                checked={thumbnailEnabled}
                onChange={(e) => void patchProject({ notes: notesWithThumbnailSetting(project.notes || '', e.target.checked) })}
              />
              Crear miniatura automáticamente
            </label>
            <Field label="Usar una imagen como referencia (paleta local)">
              <input type="file" accept="image/jpeg,image/png,image/webp" disabled={!!busy} onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setBusy('style-reference'); setError(''); setOk('');
                try {
                  const result = await api.upload<{ visual_style_prompt: string; analysis: string }>('/api/visual-style/analyze', file);
                  await patchProject({ notes: notesWithVisualStylePrompt(project.notes || '', result.visual_style_prompt) });
                  setOk(result.analysis + ' Revisá la descripción antes de renderizar.');
                } catch (error) { setError((error as Error).message); }
                finally { setBusy(''); e.target.value = ''; }
              }} />
            </Field>
          </Field>
          <Field label="Movimiento de las escenas">
            <TransitionPicker
              options={meta?.transitions ?? [{ id: project.transition_default, label: project.transition_default }]}
              value={project.transition_default}
              onChange={(value) => void patchProject({ transition_default: value })}
              compact
            />
          </Field>
          <Field label="Resolución">
            <select value={project.resolution} onChange={(e) => patchProject({ resolution: e.target.value })}>
              {(meta?.resolutions ?? [{ id: project.resolution, label: project.resolution }]).map((r) => (
                <option key={r.id} value={r.id}>{r.label}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className="row">
          <Field label="FPS">
            <select value={project.fps} onChange={(e) => patchProject({ fps: Number(e.target.value) })}>
              {(meta?.fps_options ?? [project.fps]).map((f) => <option key={f} value={f}>{f} fps</option>)}
            </select>
          </Field>
          <Field label="Música">
            <select value={project.music} onChange={(e) => patchProject({ music: e.target.value })}>
              <option value="auto">Automática</option>
              <option value="ninguna">Sin música</option>
              {(meta?.music_beds ?? []).map((m) => (
                <option key={m.id} value={`bed:${m.id}`}>Cama: {m.label}</option>
              ))}
              {(meta?.music_library ?? []).map((f) => (
                <option key={f} value={f}>Biblioteca: {f}</option>
              ))}
              {!['auto', 'ninguna'].includes(project.music) &&
              !(meta?.music_beds ?? []).some((m) => `bed:${m.id}` === project.music) &&
              !(meta?.music_library ?? []).includes(project.music) ? (
                <option value={project.music}>{project.music}</option>
              ) : null}
            </select>
          </Field>
          <Field label="Volumen de música" hint="0 = silencio, 1 = tapa la voz.">
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              defaultValue={project.music_volume ?? 0.12}
              onBlur={(e) => patchProject({ music_volume: Number(e.target.value) })}
            />
          </Field>
        </div>
        <div className="row">
          <button className="btn" onClick={() => generateScript(true)} disabled={busy === 'script'}>
            {busy === 'script' ? 'Generando…' : 'Generar guion completo'}
          </button>
          <a className="btn ghost" href={`/api/projects/${projectId}/download`}>Descargar paquete ZIP</a>
        </div>

        {project.jobs && project.jobs.length > 0 && (
          <div className="list mt-12">
            {project.jobs.map((j) => (
              <div className="list-item" key={j.id}>
                <div className="grow">
                  <div className="meta">
                    <Badge tone={j.status === 'completado' ? 'ok' : j.status === 'error' ? 'bad' : 'warn'}>{j.kind}</Badge>
                    <span>{j.message}</span>
                  </div>
                  {['en_cola', 'ejecutando'].includes(j.status) && <div style={{ marginTop: 6 }}><Progress value={j.progress} /></div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      </details>

      <details className="editor-settings">
        <summary><strong>Publicación</strong><span>YouTube y entrega local</span></summary>
      <Card
        title="Publicación"
        sub="Revisá el render y aprobá manualmente cada entrega o subida a YouTube."
        actions={
          <>
            <select value={publishDest} onChange={(e) => setPublishDest(e.target.value)} style={{ maxWidth: 260 }}>
              {destinations.map((d) => (
                <option key={d.id} value={d.id} disabled={!d.available}>
                  {d.label}
                  {d.available ? '' : ` — falta ${d.missing_env.join(', ')}`}
                </option>
              ))}
            </select>
            <button className="btn small primary" onClick={publishNow} disabled={busy === 'publish' || (publishDest === 'youtube' && !linkedYoutubeAccount)}>
              {busy === 'publish' ? 'Publicando…' : 'Publicar ahora'}
            </button>
          </>
        }
      >
        <div className="stack" style={{ marginBottom: 12 }}>
          <Field label="Fábrica que publicará">
            <select value={project?.channel_id ? String(project.channel_id) : ''} onChange={(e) => void assignChannel(e.target.value)} disabled={busy === 'channel'}>
              <option value="">Elegí una fábrica</option>
              {youtubeChannels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
            </select>
          </Field>
          {!youtubeChannels.length && <button className="btn small ghost" onClick={() => go('cuentas')}>Conectar cuenta de Google en Cuentas</button>}
        </div>
        <p className="muted" style={{ marginBottom: 10 }}>La subida nunca se ejecuta sola. Revisá el video terminado y pulsá Publicar para autorizar cada publicación.</p>
        {publishDest === 'youtube' && (
          linkedYoutubeAccount ? (
            <p className="muted">Este proyecto se publicará en <strong>{linkedYoutubeAccount.channel_title}</strong>, la cuenta vinculada a {youtubeChannels.find((channel) => channel.id === project?.channel_id)?.name || 'su canal interno'}.</p>
          ) : (
            <div className="stack">
              <p className="error-text">{project?.channel_id ? 'Todavía no hay una cuenta de YouTube conectada a este canal.' : 'Este proyecto no está asignado a Historias ni a Frutinovelas.'}</p>
              <button className="btn small ghost" onClick={() => go('cuentas')}>Conectar cuenta de Google</button>
            </div>
          )
        )}
        {destinations.map((d) => (
          <div key={d.id} className="meta" style={{ marginBottom: 6 }}>
            <Badge tone={d.available ? 'ok' : 'warn'}>{d.id}</Badge>
            <span>{d.note}</span>
          </div>
        ))}
        {publications.length > 0 ? (
          <div className="list mt-12">
            {publications.map((p) => (
              <div className="list-item" key={p.id}>
                <div className="grow">
                  <div className="meta">
                    <Badge tone={p.status === 'publicado' ? 'ok' : 'warn'}>{p.destination}</Badge>
                    <span>{p.status}</span>
                    {p.url ? (
                      <a href={p.url} target="_blank" rel="noreferrer">
                        {p.url}
                      </a>
                    ) : null}
                    <span>{p.created_at}</span>
                  </div>
                  <div>{p.message}</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty>Todavía no hay publicaciones de este proyecto.</Empty>
        )}
      </Card>
      </details>


      {scenes.length > 0 && !canRender && <div className="msg">Faltan narraciones en {scenes.filter((scene) => !scene.narration.trim()).length} escena(s). Completá el texto antes de renderizar.</div>}
      <section className="editor-workspace">
        <div className="editor-workspace-main">
          <Card title="Vista previa" sub={activeScene ? "Escena " + (activeSceneIndex + 1) + " de " + scenes.length + " · " + activeScene.title : "Vista previa de escena"}>
            <div className={"editor-preview-stage " + (project.aspect === "9:16" ? "portrait" : project.aspect === "1:1" ? "square" : "")}>
              {previewScene?.visual_path ? (/\.(mp4|mov|webm|mkv)$/i.test(previewScene.visual_path)
                ? <video src={mediaUrl(previewScene.visual_path)} muted playsInline preload="metadata" autoPlay={previewPlaying} loop={!(previewScene.visual_trim_end_sec || previewScene.visual_source_duration_sec)} 
                    onLoadedMetadata={(event) => { const start = previewScene.visual_trim_start_sec ?? 0; const end = previewScene.visual_trim_end_sec ?? 0; const source = previewScene.visual_source_duration_sec ?? 0; const limit = end > start ? end : source > start ? source : 0; event.currentTarget.currentTime = limit > start ? start + (previewSceneElapsed % (limit - start)) : start; if (!previewPlaying) event.currentTarget.pause(); }}
                    onPlay={(event) => { if (!previewPlaying) { event.currentTarget.pause(); return; } const start = previewScene.visual_trim_start_sec ?? 0; const end = previewScene.visual_trim_end_sec ?? 0; const source = previewScene.visual_source_duration_sec ?? 0; const limit = end > start ? end : source > start ? source : 0; const expected = limit > start ? start + (previewSceneElapsed % (limit - start)) : start; if (Math.abs(event.currentTarget.currentTime - expected) > 1) event.currentTarget.currentTime = expected; }}
                    onTimeUpdate={(event) => { if (!previewPlaying) { event.currentTarget.pause(); return; } const start = previewScene.visual_trim_start_sec ?? 0; const end = previewScene.visual_trim_end_sec ?? 0; const source = previewScene.visual_source_duration_sec ?? 0; const limit = end > start ? end : source > start ? source : 0; if (limit > start && event.currentTarget.currentTime >= limit) event.currentTarget.currentTime = start; }} />
                : <img src={mediaUrl(previewScene.visual_path)} alt={previewScene.title} />)
                : <div className="editor-preview-empty"><span>✦</span><strong>Tu escena está lista para ilustrar</strong><small>Buscá un recurso con licencia o subí tu propio material.</small></div>}
              {captionsEnabled && previewCaptionWords.length > 0 && <div className="editor-preview-caption">{previewCaptionWords.map((word, index) => <span key={previewCaptionStart + index} className={previewCaptionStart + index === previewWordIndex ? "current-word" : ""}>{word} </span>)}</div>}
              {overlays.filter((clip) => clip.kind !== "audio" && previewElapsed >= clip.start_sec && previewElapsed < clip.start_sec + clip.duration_sec).map((clip) => {
                const overlayStyle = { left: (clip.x * (1 - clip.width) * 100) + "%", top: (clip.y * 100) + "%", width: (clip.width * 100) + "%", opacity: clip.opacity };
                return clip.kind === "video"
                  ? <video key={clip.id} className="editor-preview-overlay" src={mediaUrl(clip.path)} muted loop autoPlay={previewPlaying} playsInline style={overlayStyle}
                      onLoadedMetadata={(event) => { event.currentTarget.currentTime = Math.max(0, previewElapsed - clip.start_sec); if (!previewPlaying) event.currentTarget.pause(); }}
                      onTimeUpdate={(event) => { if (!previewPlaying) event.currentTarget.pause(); else { const expected = Math.max(0, previewElapsed - clip.start_sec); if (Math.abs(event.currentTarget.currentTime - expected) > 1) event.currentTarget.currentTime = expected; } }} />
                  : <img key={clip.id} className="editor-preview-overlay" src={mediaUrl(clip.path) + (clip.kind === "text" ? "?v=" + encodeURIComponent(clip.updated_at) : "")} alt={clip.title} style={overlayStyle} />;
              })}
              {previewPlaying && overlays.filter((clip) => clip.kind === "audio" && previewElapsed >= clip.start_sec && previewElapsed < clip.start_sec + clip.duration_sec).map((clip) =>
                <audio key={clip.id} hidden autoPlay loop src={mediaUrl(clip.path)}
                  onLoadedMetadata={(event) => { event.currentTarget.volume = Math.max(0, Math.min(1, clip.volume ?? 1)); event.currentTarget.currentTime = Math.max(0, previewElapsed - clip.start_sec); }} />
              )}
              {previewPlaying && previewScene?.audio_path && <audio key={"narration-" + previewScene.id} hidden autoPlay src={mediaUrl(previewScene.audio_path)}
                onLoadedMetadata={(event) => { event.currentTarget.currentTime = previewSceneElapsed; }} />}
              {previewPlaying && previewScene?.sfx_path && previewSceneElapsed >= (previewScene.sfx_start_sec ?? 0) && <audio key={"sfx-" + previewScene.id} hidden autoPlay src={mediaUrl(previewScene.sfx_path)}
                onLoadedMetadata={(event) => { event.currentTarget.volume = Math.max(0, Math.min(1, previewScene.sfx_volume ?? 0.8)); event.currentTarget.currentTime = Math.max(0, previewSceneElapsed - (previewScene.sfx_start_sec ?? 0)); }} />}
              {previewPlaying && project.music && !["none", "ninguna", "sin_musica"].includes(project.music) && <audio key={"music-" + project.id} hidden autoPlay loop src={`/api/projects/${project.id}/music-preview`}
                onLoadedMetadata={(event) => { event.currentTarget.volume = Math.max(0, Math.min(1, project.music_volume ?? 0.3)); event.currentTarget.currentTime = event.currentTarget.duration > 0 ? previewElapsed % event.currentTarget.duration : 0; }} />}
            </div>
            {activeScene && <div className="editor-preview-controls">
              <div className="editor-transport">
                <button className="btn small primary" onClick={() => {
                  if (previewPlaying) setPreviewPlaying(false);
                  else {
                    if (previewElapsed >= timelineDuration || !previewElapsed) setPreviewElapsed(timelineStarts[activeSceneIndex] || 0);
                    setPreviewPlaying(true);
                  }
                }}>{previewPlaying ? "Ⅱ Pausar" : "▶ Reproducir"}</button>
                <input aria-label="Posición de reproducción" type="range" min="0" max={Math.max(1, timelineDuration)} step="0.1" value={Math.min(previewElapsed, timelineDuration)} onChange={(e) => { setPreviewElapsed(Number(e.target.value)); setPreviewPlaying(false); }} />
                <small>{fmtDuration(previewElapsed)} / {fmtDuration(timelineDuration)}</small><span className="editor-shortcuts">Espacio: reproducir · ←/→: avanzar 1 s</span>
              </div>
              <span>{previewScene?.title ?? activeScene.title} · {activeScene.narration.trim().split(/\s+/).filter(Boolean).length} palabras</span>
              <div className="row gap-8">
                <button className="btn small ghost" onClick={() => { if (activeSceneIndex > 0) { setPreviewPlaying(false); setSelectedSceneId(scenes[activeSceneIndex - 1].id); setPreviewElapsed(timelineStarts[activeSceneIndex - 1]); } }} disabled={activeSceneIndex <= 0}>← Anterior</button>
                <button className="btn small ghost" onClick={() => { if (activeSceneIndex < scenes.length - 1) { setPreviewPlaying(false); setSelectedSceneId(scenes[activeSceneIndex + 1].id); setPreviewElapsed(timelineStarts[activeSceneIndex + 1]); } }} disabled={activeSceneIndex >= scenes.length - 1}>Siguiente →</button>
              </div>
            </div>}
          </Card>
          <Card title="Línea de tiempo" sub="Pistas sincronizadas por duración estimada. Arrastrá los clips de video para reordenar; tocá cualquier bloque para editar esa escena.">
            {scenes.length === 0 ? <Empty>Generá un guion o agregá una escena para empezar.</Empty> : <div className="editor-timeline-shell">
              <div className="editor-ruler-row">
                <div className="editor-track-label">TIEMPO</div>
                <div className="editor-ruler" style={{ width: timelineWidth }} onClick={(event) => { const rect = event.currentTarget.getBoundingClientRect(); const second = rect.width ? ((event.clientX - rect.left) / rect.width) * timelineDuration : 0; setPreviewElapsed(Math.max(0, Math.min(timelineDuration, second))); setPreviewPlaying(false); }} title="Tocá para mover el cabezal de reproducción">
                  <span className="editor-ruler-playhead" style={{ left: Math.min(previewElapsed, timelineDuration) * timelineScale }} />
                  {Array.from({ length: Math.floor(timelineDuration / rulerStep) + 1 }, (_, tick) => tick * rulerStep).map((second) => (
                    <span className="editor-ruler-tick" key={second} style={{ left: second * timelineScale }}>
                      <i />{fmtDuration(second)}
                    </span>
                  ))}
                  <span className="editor-ruler-end">{fmtDuration(timelineDuration)}</span>
                </div>
              </div>
              <div className="editor-multitrack">
                {[
                  { id: "visual", label: "VIDEO" },
                  { id: "voice", label: "VOZ" },
                  { id: "captions", label: "SUBTÍTULOS" },
                  { id: "sfx", label: "EFECTOS" },
                ].map((track) => <div className="editor-track" key={track.id}>
                  <div className="editor-track-label">{track.label}</div>
                  <div className="editor-track-lane" style={{ width: timelineWidth }}>
                    {scenes.map((scene, index) => {
                      const seconds = sceneDurations[index];
                      const width = seconds * timelineScale;
                      return <button type="button" key={scene.id}
                        className={"editor-track-clip " + track.id + (previewScene?.id === scene.id ? " active" : "") + (draggedSceneId === scene.id ? " dragging" : "")}
                        style={{ flex: "0 0 " + width + "px", width }}
                        draggable={track.id === "visual"}
                        onDragStart={() => setDraggedSceneId(scene.id)}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => { event.preventDefault(); if (draggedSceneId !== null) void reorderScene(draggedSceneId, scene.id); }}
                        onDragEnd={() => setDraggedSceneId(null)}
                        onClick={() => { setSelectedSceneId(scene.id); setPreviewPlaying(false); setPreviewElapsed(timelineStarts[index]); }}
                        title={scene.title + " · " + fmtDuration(seconds) + " · inicio " + fmtDuration(timelineStarts[index])}>
                        {track.id === "visual" ? <>{scene.visual_path && (/\.(mp4|mov|webm|mkv)$/i.test(scene.visual_path) ? <video src={mediaUrl(scene.visual_path)} muted playsInline preload="metadata" /> : <img src={mediaUrl(scene.visual_path)} alt="" />)}<span>{index + 1}. {scene.title}</span></>
                          : track.id === "voice" ? <span>▰ Voz {index + 1} · {fmtDuration(seconds)}</span>
                          : track.id === "captions" ? <span>{captionsEnabled ? "▤ Texto " + (index + 1) : "Subtítulos desactivados"}</span>
                        : <span>{scene.sfx_path ? "♫ Efecto " + (index + 1) : "Sin efecto"}</span>}
                      </button>;
                    })}
                  </div>
                </div>)}
                <div className="editor-track">
                  <div className="editor-track-label">CAPAS</div>
                  <div className="editor-overlay-lane" style={{ width: timelineWidth }} onDragOver={(event) => event.preventDefault()} onDrop={dropOverlayOnLane}>
                    {overlays.filter((clip) => clip.kind !== "audio").map((clip) => <button type="button" key={clip.id} draggable
                      onDragStart={(event) => { setDraggedOverlayId(clip.id); setDraggedOverlayOffset(event.clientX - event.currentTarget.getBoundingClientRect().left); }} onDragEnd={() => { setDraggedOverlayId(null); setDraggedOverlayOffset(0); }}
                      className={"editor-overlay-clip " + clip.kind + (selectedOverlayId === clip.id ? " active" : "")}
                      style={{ left: clip.start_sec * timelineScale, width: Math.max(34, clip.duration_sec * timelineScale), top: 6 }}
                      onClick={() => { setSelectedOverlayId(clip.id); setPreviewPlaying(false); setPreviewElapsed(clip.start_sec); }}
                      title={clip.title + " · " + fmtDuration(clip.start_sec) + " · " + fmtDuration(clip.duration_sec)}>
                      {clip.kind === "image" ? "▧ " : clip.kind === "text" ? "T " : "▶ "}{clip.title}
                    </button>)}
                    {!overlays.some((clip) => clip.kind !== "audio") && <small className="muted">Imágenes y videos superpuestos de forma independiente.</small>}
                  </div>
                </div>
                <div className="editor-track">
                  <div className="editor-track-label">AUDIO EXTRA</div>
                  <div className="editor-overlay-lane audio-lane" style={{ width: timelineWidth }} onDragOver={(event) => event.preventDefault()} onDrop={dropOverlayOnLane}>
                    {overlays.filter((clip) => clip.kind === "audio").map((clip) => <button type="button" key={clip.id} draggable
                      onDragStart={(event) => { setDraggedOverlayId(clip.id); setDraggedOverlayOffset(event.clientX - event.currentTarget.getBoundingClientRect().left); }} onDragEnd={() => { setDraggedOverlayId(null); setDraggedOverlayOffset(0); }}
                      className={"editor-overlay-clip audio" + (selectedOverlayId === clip.id ? " active" : "")}
                      style={{ left: clip.start_sec * timelineScale, width: Math.max(34, clip.duration_sec * timelineScale), top: 6 }}
                      onClick={() => { setSelectedOverlayId(clip.id); setPreviewPlaying(false); setPreviewElapsed(clip.start_sec); }}
                      title={clip.title + " · " + fmtDuration(clip.start_sec) + " · " + fmtDuration(clip.duration_sec)}>
                      ♫ {clip.title}
                    </button>)}
                    {!overlays.some((clip) => clip.kind === "audio") && <small className="muted">Pistas de audio independientes con volumen propio.</small>}
                  </div>
                </div>
                <div className="editor-track">
                  <div className="editor-track-label">MÚSICA</div>
                  <div className="editor-track-lane" style={{ width: timelineWidth }}>
                    <div className={"editor-music-clip " + (project.music === "ninguna" ? "muted" : "")} style={{ width: timelineWidth, flex: "0 0 " + timelineWidth + "px" }}>
                      <span>♫ {project.music === "ninguna" ? "Sin música" : project.music === "auto" ? "Pista automática" : project.music}</span>
                      <small>{Math.round((project.music_volume ?? 0.12) * 100)}% volumen · {fmtDuration(timelineDuration)}</small>
                    </div>
                  </div>
                </div>
              </div>
            </div>}
            <div className="editor-timeline-footer">
              <span>{scenes.length} clips · {fmtDuration(timelineDuration)} totales estimados</span>
              <span>Escena activa: {activeSceneIndex >= 0 ? activeSceneIndex + 1 : "—"}</span>
              <label className="editor-timeline-zoom">Zoom <input type="range" min="0.5" max="2.5" step="0.1" value={timelineZoom} onChange={(e) => setTimelineZoom(Number(e.target.value))} /></label>
              <button className="btn small" onClick={addScene} disabled={!!busy}>＋ Agregar escena</button>
              <label className="btn small ghost">＋ Añadir capa
                <input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm,video/x-matroska,audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/flac,.mp3,.wav,.ogg,.m4a,.flac" hidden disabled={!!busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void uploadTimelineOverlay(file); e.target.value = ""; }} />
              </label>
            </div>
          </Card>
        </div>
        <aside className="editor-inspector">
          <Card title="Editar escena" sub={activeScene ? "Escena " + (activeSceneIndex + 1) + " · los cambios se guardan al salir del campo" : "Seleccioná una escena"}>
            {!activeScene ? <Empty>Todavía no hay escenas.</Empty> : <div className="editor-inspector-content">
              <div className="scene-head">
                <Badge tone={activeScene.narration.trim() ? "ok" : "warn"}>{activeScene.narration.trim() ? "Texto listo" : "Texto pendiente"}</Badge>
                <div className="row gap-8">
                  <button className="btn small ghost" onClick={() => move(activeScene, -1)} disabled={activeSceneIndex <= 0}>←</button>
                  <button className="btn small ghost" onClick={() => move(activeScene, 1)} disabled={activeSceneIndex >= scenes.length - 1}>→</button>
                  <button className="btn small ghost" onClick={() => duplicateScene(activeScene)} disabled={!!busy}>{busy === "duplicate-" + activeScene.id ? "Duplicando…" : "Duplicar"}</button>
                  <button className="btn small ghost" onClick={() => regenerate(activeScene)} disabled={!!busy}>{busy === "regenerate-" + activeScene.id ? "Reescribiendo…" : "Reescribir texto"}</button>
                  <button className="btn small ghost" onClick={() => void regenerateVisual(activeScene)} disabled={!!busy}>{busy === "visual-" + activeScene.id ? "Buscando visual…" : "Regenerar visual"}</button>
                  <button className="btn small danger" onClick={() => removeScene(activeScene)}>Eliminar</button>
                </div>
              </div>
              <Field label="Nombre de escena"><input defaultValue={activeScene.title} key={"title-" + activeScene.id + "-" + activeScene.updated_at} onBlur={(e) => e.target.value !== activeScene.title && patchScene(activeScene, { title: e.target.value })} /></Field>
              <Field label="Narración"><textarea ref={narrationRef} className="editor-narration-input" defaultValue={activeScene.narration} key={"narration-" + activeScene.id + "-" + activeScene.updated_at} onSelect={(e) => setSplitCursor(e.currentTarget.selectionStart)} onBlur={(e) => { if (skipNarrationBlurRef.current) { skipNarrationBlurRef.current = false; return; } if (e.target.value !== activeScene.narration) void patchScene(activeScene, { narration: e.target.value }); }} /></Field>
              <div className="row gap-8" style={{ flexWrap: "wrap" }}>
                <button className="btn small ghost" onPointerDown={() => { skipNarrationBlurRef.current = true; }} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") skipNarrationBlurRef.current = true; }} onClick={() => void splitSceneAtCursor(activeScene)} disabled={!!busy || splitCursor <= 20 || splitCursor >= activeNarrationLength - 20}>Dividir en el cursor</button>
                <button className="btn small ghost" onPointerDown={() => { skipNarrationBlurRef.current = true; }} onClick={() => { const text = narrationRef.current?.value ?? activeScene.narration; const ratio = Math.max(0, Math.min(1, (previewElapsed - (timelineStarts[activeSceneIndex] || 0)) / Math.max(0.1, sceneDurations[activeSceneIndex] || 1))); const at = Math.round(text.length * ratio); void splitSceneAtCursor(activeScene, at); }} disabled={!!busy || activeScene.narration.length < 42 || previewElapsed <= (timelineStarts[activeSceneIndex] || 0) + 1 || previewElapsed >= (timelineStarts[activeSceneIndex] || 0) + (sceneDurations[activeSceneIndex] || 0) - 1}>Dividir en el cabezal</button>
                <small className="muted">Dividí en el cursor del texto o en la posición actual de reproducción.</small>
              </div>
              {activeScene.narration.trim() && <div className="scene-audio-preview"><span>Previsualizar voz</span><audio controls preload="none" src={"/api/scenes/" + activeScene.id + "/voice-preview?v=" + encodeURIComponent([activeScene.updated_at, project.voice, project.speed, project.pitch].join("-"))} /></div>}
              <Field label="Descripción del visual"><input defaultValue={activeScene.visual_query} key={"visual-" + activeScene.id + "-" + activeScene.updated_at} onBlur={(e) => e.target.value !== activeScene.visual_query && patchScene(activeScene, { visual_query: e.target.value })} /></Field>
              {activeScene.visual_path && /\.(mp4|mov|webm|mkv)$/i.test(activeScene.visual_path) && <div className="scene-trim-controls">
                <strong>Recortar clip de video</strong>
                <small className="muted">Elegí qué fragmento del archivo original se usa en esta escena. Dejá el final en 0 para usar el resto del clip.</small>
                <div className="scene-trim-fields">
                  <Field label={"Entrada (0–" + (activeScene.visual_source_duration_sec ?? 0).toFixed(1) + " s)"}><input type="number" min="0" max={activeScene.visual_source_duration_sec || undefined} step="0.1" defaultValue={activeScene.visual_trim_start_sec ?? 0} key={"trim-in-" + activeScene.id + "-" + activeScene.updated_at} onBlur={(e) => { const value = Math.max(0, Number(e.target.value) || 0); if (value !== (activeScene.visual_trim_start_sec ?? 0)) void patchScene(activeScene, { visual_trim_start_sec: value }); }} /></Field>
                  <Field label={"Salida (0 = final · máx. " + (activeScene.visual_source_duration_sec ?? 0).toFixed(1) + " s)"}><input type="number" min="0" max={activeScene.visual_source_duration_sec || undefined} step="0.1" defaultValue={activeScene.visual_trim_end_sec ?? 0} key={"trim-out-" + activeScene.id + "-" + activeScene.updated_at} onBlur={(e) => { const value = Math.max(0, Number(e.target.value) || 0); if (value !== (activeScene.visual_trim_end_sec ?? 0)) void patchScene(activeScene, { visual_trim_end_sec: value }); }} /></Field>
                </div>
              </div>}
              <Field label="Transición"><TransitionPicker options={meta?.transitions ?? [{ id: activeScene.transition, label: activeScene.transition }]} value={activeScene.transition || project.transition_default} onChange={(value) => void patchScene(activeScene, { transition: value })} compact /></Field>
              <div className="scene-sfx-controls">
                <div className="row gap-8" style={{ justifyContent: "space-between" }}>
                  <strong>Efecto de sonido</strong>
                  {activeScene.sfx_path && <button className="btn small danger" onClick={() => void removeSceneSound(activeScene)}>Quitar</button>}
                </div>
                {activeScene.sfx_path ? <audio controls preload="none" src={mediaUrl(activeScene.sfx_path)} /> : <small className="muted">Sin efecto asignado a esta escena.</small>}
                {activeScene.sfx_path && <>
                  <Field label={"Volumen del efecto: " + Math.round((activeScene.sfx_volume ?? 0.8) * 100) + "%"}>
                    <input type="range" min="0" max="2" step="0.05" value={activeScene.sfx_volume ?? 0.8} onChange={(e) => void patchScene(activeScene, { sfx_volume: Number(e.target.value) })} />
                  </Field>
                  <Field label={"Inicio del efecto: " + (activeScene.sfx_start_sec ?? 0).toFixed(1) + " s"}>
                    <input type="range" min="0" max="20" step="0.1" value={activeScene.sfx_start_sec ?? 0} onChange={(e) => void patchScene(activeScene, { sfx_start_sec: Number(e.target.value) })} />
                  </Field>
                </>}
                <label className="btn small ghost">＋ Subir efecto de sonido
                  <input type="file" accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/flac,.mp3,.wav,.ogg,.m4a,.flac" hidden disabled={!!busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void uploadSceneSound(activeScene, file); e.target.value = ""; }} />
                </label>
              </div>
              <div className="row gap-8">
                <button className="btn small ghost" onClick={() => searchVisual(activeScene)}>Buscar visual con licencia</button>
                <label className="btn small ghost">Subir imagen o video<input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm,video/x-matroska" disabled={!!busy} hidden onChange={(e) => { const file = e.target.files?.[0]; if (file) void uploadSceneImage(activeScene, file); e.target.value = ""; }} /></label>
              </div>
              {activeScene.visual_license && <small className="muted">{activeScene.visual_license} · {activeScene.visual_author || "autor no identificado"}</small>}
              {searchFor === activeScene.id && <div className="thumbs">{results.map((item, index) => <figure key={item.url + "-" + index}>
                {item.thumb ? <img src={item.thumb} alt={item.title} loading="lazy" /> : <div className="shot" />}
                <figcaption>{item.title} · {item.license || "licencia a verificar"}<button className="btn small ghost" onClick={() => applyVisual(activeScene, item)} disabled={busy === "visual-" + activeScene.id}>Usar</button></figcaption>
              </figure>)}{results.length === 0 && <small>Sin resultados todavía.</small>}</div>}
            </div>}
          </Card>
          <Card title="Audio y música" sub="Elegí la pista de fondo y mezclala debajo de la voz.">
            <Field label="Pista musical">
              <select value={project.music || "auto"} onChange={(e) => void patchProject({ music: e.target.value })}>
                <option value="auto">Automática</option>
                <option value="ninguna">Sin música</option>
                {(meta?.music_beds ?? []).map((track) => <option key={track.id} value={"bed:" + track.id}>{track.label}</option>)}
                {(meta?.music_library ?? []).map((track) => <option key={track} value={track}>{track}</option>)}
              </select>
            </Field>
            {project.music !== "ninguna" && <Field label={"Volumen de música: " + Math.round((project.music_volume ?? 0.12) * 100) + "%"}>
              <input type="range" min="0" max="0.5" step="0.01" value={project.music_volume ?? 0.12} onChange={(e) => void patchProject({ music_volume: Number(e.target.value) })} />
            </Field>}
            <label className="btn small ghost">＋ Subir pista de audio
              <input type="file" accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/flac,.mp3,.wav,.ogg,.m4a,.flac" hidden disabled={!!busy} onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setBusy("music-upload"); setError(""); setOk("");
                try {
                  const result = await api.upload<{ filename: string; music_library: string[] }>("/api/music/upload", file);
                  setMeta((previous) => previous ? { ...previous, music_library: result.music_library } : previous);
                  await patchProject({ music: result.filename });
                  setOk("Pista agregada a la biblioteca y asignada a este video.");
                } catch (uploadError) { setError((uploadError as Error).message); }
                finally { setBusy(""); e.target.value = ""; }
              }} />
            </label>
            <small className="muted">Los archivos se guardan localmente. Formatos: MP3, WAV, OGG, M4A y FLAC.</small>
          </Card>
          <Card title="Entrega" sub="Revisá el resultado completo antes de descargarlo.">
            {project.status === "renderizado" ? <div className="stack">
              <video controls preload="metadata" className={project.aspect === "9:16" ? "preview vertical" : "preview"} src={"/api/projects/" + projectId + "/video"} />
              <a className="btn primary" href={"/api/projects/" + projectId + "/video"} download={"video-" + projectId + ".mp4"}>Descargar MP4</a>
            </div> : <Empty>El video final aparecerá después del render.</Empty>}
          </Card>
          <Card title="Capa visual" sub={selectedOverlayId ? "Elemento independiente sobre la pista principal" : "Agregá una imagen o video para superponerlo sin reemplazar la escena."}>
            {(() => {
              const clip = overlays.find((item) => item.id === selectedOverlayId);
              if (!clip) return <>
                <small className="muted">Subí una imagen/video/audio o creá un texto superpuesto. Se insertará en la posición actual del cabezal.</small>
                <Field label="Texto sobre el video"><input value={overlayTextDraft} maxLength={240} onChange={(e) => setOverlayTextDraft(e.target.value)} placeholder="Escribí el texto de la capa…" /></Field>
                <button className="btn small primary" onClick={() => void createTimelineTextOverlay()} disabled={!overlayTextDraft.trim() || !!busy}>＋ Añadir texto</button>
              </>;
              return <div className="editor-inspector-content">
                <Field label="Nombre"><input defaultValue={clip.title} key={"overlay-title-" + clip.id + "-" + clip.updated_at} onBlur={(e) => e.target.value !== clip.title && void patchTimelineOverlay(clip, { title: e.target.value })} /></Field>
                <div className="scene-trim-fields">
                  <Field label="Inicio (s)"><input type="number" min="0" step="0.1" defaultValue={clip.start_sec} key={"overlay-start-" + clip.id + "-" + clip.updated_at} onBlur={(e) => { const value = Math.max(0, Number(e.target.value) || 0); if (value !== clip.start_sec) void patchTimelineOverlay(clip, { start_sec: value }); }} /></Field>
                  <Field label="Duración (s)"><input type="number" min="0.1" max="3600" step="0.1" defaultValue={clip.duration_sec} key={"overlay-duration-" + clip.id + "-" + clip.updated_at} onBlur={(e) => { const value = Math.max(0.1, Number(e.target.value) || 0.1); if (value !== clip.duration_sec) void patchTimelineOverlay(clip, { duration_sec: value }); }} /></Field>
                </div>
                {clip.kind !== "audio" && <>
                  <Field label={"Ancho: " + Math.round(clip.width * 100) + "%"}><input type="range" min="0.05" max="1" step="0.01" value={clip.width} onChange={(e) => void patchTimelineOverlay(clip, { width: Number(e.target.value) })} /></Field>
                  <Field label={"Posición horizontal: " + Math.round(clip.x * 100) + "%"}><input type="range" min="0" max="1" step="0.01" value={clip.x} onChange={(e) => void patchTimelineOverlay(clip, { x: Number(e.target.value) })} /></Field>
                  <Field label={"Posición vertical: " + Math.round(clip.y * 100) + "%"}><input type="range" min="0" max="1" step="0.01" value={clip.y} onChange={(e) => void patchTimelineOverlay(clip, { y: Number(e.target.value) })} /></Field>
                  <Field label={"Opacidad: " + Math.round(clip.opacity * 100) + "%"}><input type="range" min="0" max="1" step="0.05" value={clip.opacity} onChange={(e) => void patchTimelineOverlay(clip, { opacity: Number(e.target.value) })} /></Field>
                </>}
                {clip.kind === "audio" && <>
                  <Field label={"Volumen: " + Math.round((clip.volume ?? 1) * 100) + "%"}><input type="range" min="0" max="2" step="0.05" value={clip.volume ?? 1} onChange={(e) => void patchTimelineOverlay(clip, { volume: Number(e.target.value) })} /></Field>
                  <audio controls preload="metadata" src={mediaUrl(clip.path)} />
                </>}
                <div className="row gap-8">
                  <button className="btn small ghost" onClick={() => { setPreviewElapsed(clip.start_sec); setPreviewPlaying(false); }}>Ir al inicio</button>
                  <button className="btn small ghost" onClick={() => setSelectedOverlayId(null)}>＋ Nueva capa de texto</button>
                  <button className="btn small danger" onClick={() => void removeTimelineOverlay(clip)}>Eliminar capa</button>
                </div>
              </div>;
            })()}
          </Card>
          <Card title="Generar voz en off" sub="Crea una pista de voz independiente con el motor local gratuito. Se inserta en el cabezal actual.">
            <Field label="Texto de la voz"><textarea rows={4} maxLength={12000} value={voiceDraft} onChange={(e) => setVoiceDraft(e.target.value)} placeholder="Escribí lo que querés que diga la voz…" /></Field>
            <Field label="Voz para este clip"><VoicePicker options={voices} value={voiceOverlayVoice || project?.voice || "es"} onChange={setVoiceOverlayVoice} compact speed={voiceOverlaySpeed ?? project?.speed ?? 150} pitch={voiceOverlayPitch ?? project?.pitch ?? 45} /></Field>
            <Field label={"Velocidad: " + (voiceOverlaySpeed ?? project?.speed ?? 150)}><input type="range" min="80" max="220" step="5" value={voiceOverlaySpeed ?? project?.speed ?? 150} onChange={(e) => setVoiceOverlaySpeed(Number(e.target.value))} /></Field>
            <Field label={"Tono: " + (voiceOverlayPitch ?? project?.pitch ?? 45)}><input type="range" min="0" max="99" step="1" value={voiceOverlayPitch ?? project?.pitch ?? 45} onChange={(e) => setVoiceOverlayPitch(Number(e.target.value))} /></Field>
            <button className="btn small primary" onClick={() => void createTimelineVoiceOverlay()} disabled={!voiceDraft.trim() || !!busy}>{busy === "create-voice-overlay" ? "Generando voz…" : "＋ Generar y añadir voz"}</button>
          </Card>
          <Card title="Generar música" sub="Camas musicales locales, sin créditos ni servicios pagos. Se añaden como clips independientes.">
            <Field label="Estilo musical"><select value={musicBedId} onChange={(e) => setMusicBedId(e.target.value)}>
              {(meta?.music_beds ?? []).map((bed) => <option key={bed.id} value={bed.id}>{bed.label}</option>)}
            </select></Field>
            <button className="btn small primary" onClick={() => void createTimelineMusicOverlay()} disabled={!!busy}>{busy === "create-music-overlay" ? "Generando música…" : "＋ Generar y añadir música"}</button>
          </Card>
          <Card title="Efectos de sonido" sub="Generación local por síntesis, sin créditos ni servicios externos.">
            <Field label="Efecto"><select value={sfxEffectId} onChange={(e) => setSfxEffectId(e.target.value)}>
              <option value="whoosh">Barrido</option>
              <option value="impact">Impacto</option>
              <option value="chime">Campanilla</option>
              <option value="click">Clic</option>
              <option value="riser">Subida</option>
            </select></Field>
            <button className="btn small primary" onClick={() => void createTimelineSfxOverlay()} disabled={!!busy}>{busy === "create-sfx-overlay" ? "Generando efecto…" : "＋ Generar y añadir efecto"}</button>
          </Card>
        </aside>
      </section>

        <div className="stack">

          <Card title="Control de calidad" sub="Lo que el render informó realmente.">
            {Object.keys(quality).length === 0 ? (
              <Empty>Sin informe todavía.</Empty>
            ) : (
              <div className="stack">
                <div className="grid stats">
                  <div className="stat"><div className="value">{String(quality.scenes ?? 0)}</div><div className="label">Escenas</div></div>
                  <div className="stat"><div className="value">{fmtDuration(Number(quality.duration_sec ?? 0))}</div><div className="label">Duración</div></div>
                  <div className="stat"><div className="value">{String(quality.subtitles ?? 0)}</div><div className="label">Subtítulos</div></div>
                  <div className="stat"><div className="value">{String(quality.scenes_reused ?? 0)}</div><div className="label">Reutilizadas</div></div>
                </div>
                {warnings.length > 0 ? (
                  <div className="msg">
                    <strong>Avisos del render</strong>
                    <ul style={{ margin: '6px 0 0 18px' }}>
                      {warnings.map((w) => <li key={w}>{w}</li>)}
                    </ul>
                  </div>
                ) : (
                  <div className="msg ok">Sin avisos: todas las escenas tienen voz y material propio.</div>
                )}
              </div>
            )}
          </Card>

          <Card title="Fuentes y créditos" sub="Referencias documentales y atribuciones de los materiales usados en este video.">
            {(project.sources ?? []).length === 0 ? (
              <Empty>Las fuentes y atribuciones aparecerán acá a medida que se incorporen al proyecto.</Empty>
            ) : (
              <div className="list">
                {(project.sources ?? []).map((s) => (
                  <div className="list-item" key={s.id}>
                    <div className="grow">
                      <h4>{s.title || 'Sin título'}</h4>
                      <div className="meta">
                        <span>{s.kind === 'investigacion' ? 'Investigación del tema' : 'Recurso visual'}</span>
                        <span>·</span>
                        <span>{s.author || 'autor desconocido'}</span>
                        <span>·</span>
                        <span>{s.license || 'licencia a verificar'}</span>
                        {s.url && <a href={s.url} target="_blank" rel="noreferrer">ver fuente</a>}
                      </div>
                      {s.notes && <p className="muted">{s.notes}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Miniatura" sub="Subí tu portada o usá la miniatura automática. La imagen personalizada se aplica al próximo render.">
            {project.thumbnail_path ? (
              <img className="shot" alt="Miniatura personalizada" src={mediaUrl(project.thumbnail_path)} />
            ) : project.status === 'renderizado' ? (
              <img className="shot" alt="Miniatura del proyecto" src={mediaUrl(`renders/${projectId}/thumb.jpg`)} onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
            ) : <Empty>La miniatura automática se prepara al renderizar.</Empty>}
            <label className="btn small ghost" style={{ marginTop: 10 }}>
              Subir miniatura personalizada
              <input type="file" accept="image/jpeg,image/png,image/webp" hidden disabled={!!busy} onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setBusy('thumbnail-upload'); setError(''); setOk('');
                try {
                  await api.upload(`/api/projects/${projectId}/thumbnail`, file);
                  await patchProject({ notes: notesWithThumbnailSetting(project.notes || '', true) });
                  await load();
                  setOk('Miniatura guardada. Se usará en el próximo render.');
                } catch (uploadError) { setError((uploadError as Error).message); }
                finally { setBusy(''); e.target.value = ''; }
              }} />
            </label>
          </Card>
        </div>
    </div>
  );
}
