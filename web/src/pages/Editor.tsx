import { useCallback, useEffect, useRef, useState } from 'react';
import { api, fmtDuration, mediaUrl, type MediaResult, type Meta, type Project, type Scene } from '../api';
import { Badge, Card, Empty, Field, Msg, Progress, statusTone } from '../ui';
import type { Route } from '../routes';
import CaptionStylePicker from '../components/CaptionStylePicker';
import TransitionPicker from '../components/TransitionPicker';
import VisualStylePicker from '../components/VisualStylePicker';
import VideoTypePicker from '../components/VideoTypePicker';
import VoicePicker from '../components/VoicePicker';
import ProjectResearch from '../components/ProjectResearch';

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
  const [draggedSceneId, setDraggedSceneId] = useState<number | null>(null);
  const [results, setResults] = useState<MediaResult[]>([]);
  const [destinations, setDestinations] = useState<PublishDestination[]>([]);
  const [publications, setPublications] = useState<Publication[]>([]);
  const [youtubeChannels, setYoutubeChannels] = useState<YoutubeWorkspaceChannel[]>([]);
  const [publishDest, setPublishDest] = useState('entrega');
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      setProject(await api.get<Project>(`/api/projects/${projectId}`));
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

  const [voices, setVoices] = useState<{ id: string; label: string; available?: boolean }[]>([]);
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
      await api.upload(`/api/scenes/${scene.id}/image`, file);
      setOk('Imagen asignada a la escena. Se guardó como recurso local.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
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
  const canRender = scenes.length > 0 && scenes.every((scene) => Boolean(scene.narration.trim()));
  const words = scenes.reduce((acc, s) => acc + (s.narration || '').trim().split(/\s+/).filter(Boolean).length, 0);
  const quality = project.quality ?? {};
  const captionsEnabled = captionsEnabledFromNotes(project.notes || '');
  const visualStylePrompt = visualStylePromptFromNotes(project.notes || '');
  const thumbnailEnabled = thumbnailEnabledFromNotes(project.notes || '');
  const warnings = Array.isArray(quality.warnings) ? (quality.warnings as string[]) : [];
  const totalChars = scenes.reduce((acc, s) => acc + (s.narration || '').length, 0);

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      {!['frutinovela', 'reddit_story'].includes(project.template) && (
        <details className="editor-settings">
          <summary><strong>Investigación y fuentes</strong><span>Consultar evidencia y recursos del tema</span></summary>
          <ProjectResearch projectId={projectId} topic={project.topic || project.title} />
        </details>
      )}


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

      {scenes.length > 0 && !canRender && (
        <div className="msg">
          Faltan narraciones en {scenes.filter((scene) => !scene.narration.trim()).length} escena(s). Completá el texto antes de renderizar.
        </div>
      )}
      <div className="grid two">
        <Card title="Línea de tiempo" sub="Cada bloque representa una escena. La duración es estimada a partir de la narración; elegí un bloque para editarlo.">
          {scenes.length === 0 ? <Empty>La línea de tiempo aparece cuando generás el guion.</Empty> : (
            <div className="editor-timeline" aria-label="Línea de tiempo de escenas">
              {scenes.map((scene, index) => {
                const sceneWords = (scene.narration || '').trim().split(/\s+/).filter(Boolean).length;
                const estimatedSeconds = Math.max(2, sceneWords / 2.4);
                const totalEstimated = scenes.reduce((sum, item) => sum + Math.max(2, (item.narration || '').trim().split(/\s+/).filter(Boolean).length / 2.4), 0);
                const width = Math.max(9, (estimatedSeconds / Math.max(1, totalEstimated)) * 100);
                return (
                  <button
                    type="button"
                    key={scene.id}
                    className={`editor-timeline-item ${selectedSceneId === scene.id || (!selectedSceneId && index === 0) ? 'active' : ''} ${draggedSceneId === scene.id ? 'dragging' : ''}`}
                    style={{ flexBasis: width + '%' }}
                    draggable
                    onDragStart={() => setDraggedSceneId(scene.id)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => { event.preventDefault(); if (draggedSceneId !== null) void reorderScene(draggedSceneId, scene.id); }}
                    onDragEnd={() => setDraggedSceneId(null)}
                    onClick={() => {
                      setSelectedSceneId(scene.id);
                      document.getElementById('scene-' + scene.id)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }}
                    title={scene.title + ' · ~' + Math.round(estimatedSeconds) + ' s'}
                  >
                    {scene.visual_path && (/\\.(mp4|mov|webm|mkv)$/i.test(scene.visual_path)
                      ? <video className="editor-timeline-thumb" src={mediaUrl(scene.visual_path)} muted playsInline preload="metadata" />
                      : <img className="editor-timeline-thumb" src={mediaUrl(scene.visual_path)} alt="" loading="lazy" />)}
                    <strong>{index + 1}. {scene.title}</strong>
                    <small>~{Math.round(estimatedSeconds)} s</small>
                  </button>
                );
              })}
            </div>
          )}
        </Card>

        <Card title="Escenas" sub="Editá la narración; se guarda al salir del campo. El orden define el montaje.">
          {scenes.length === 0 ? (
            <Empty>Sin escenas. Generá el guion para crear la estructura narrativa.</Empty>
          ) : (
            <div>
              {scenes.map((scene, i) => (
                <div id={`scene-${scene.id}`} className={`scene ${selectedSceneId === scene.id ? 'selected' : ''}`} key={scene.id}>
                  <div className="scene-head">
                    <div className="row center gap-8">
                      <span className="scene-index">{i + 1}</span>
                      <input
                        defaultValue={scene.title}
                        key={`title-${scene.id}-${scene.updated_at}`}
                        style={{ minWidth: 160 }}
                        onBlur={(e) => e.target.value !== scene.title && patchScene(scene, { title: e.target.value })}
                      />
                      <Badge tone={scene.narration.trim() ? 'ok' : 'warn'}>{scene.narration.trim() ? 'Texto listo' : 'Texto pendiente'}</Badge>
                    </div>
                    <div className="row gap-8">
                      <button className="btn small ghost" onClick={() => move(scene, -1)} disabled={i === 0}>↑</button>
                      <button className="btn small ghost" onClick={() => move(scene, 1)} disabled={i === scenes.length - 1}>↓</button>
                      <button className="btn small ghost" onClick={() => regenerate(scene)} disabled={busy === `regenerate-${scene.id}`}>{busy === `regenerate-${scene.id}` ? 'Regenerando…' : 'Regenerar'}</button>
                      <button className="btn small danger" onClick={() => removeScene(scene)}>×</button>
                    </div>
                  </div>
                  {scene.visual_path && (/\\.(mp4|mov|webm|mkv)$/i.test(scene.visual_path)
                    ? <video className="scene-visual-preview" src={mediaUrl(scene.visual_path)} controls muted playsInline preload="metadata" />
                    : <img className="scene-visual-preview" src={mediaUrl(scene.visual_path)} alt={`Visual de ${scene.title}`} loading="lazy" />)}
                  <textarea
                    defaultValue={scene.narration}
                    key={`narration-${scene.id}-${scene.updated_at}`}
                    onBlur={(e) => e.target.value !== scene.narration && patchScene(scene, { narration: e.target.value })}
                  />
                  {scene.narration.trim() && (
                    <div className="scene-audio-preview">
                      <span>Escuchar esta narración</span>
                      <audio controls preload="none" src={`/api/scenes/${scene.id}/voice-preview?v=${encodeURIComponent([scene.updated_at, project.voice, project.speed, project.pitch].join('-'))}`} />
                    </div>
                  )}
                  <div className="row" style={{ marginTop: 8 }}>
                    <Field label="Búsqueda visual">
                      <input
                        defaultValue={scene.visual_query}
                        key={`visual-${scene.id}-${scene.updated_at}`}
                        onBlur={(e) => e.target.value !== scene.visual_query && patchScene(scene, { visual_query: e.target.value })}
                      />
                    </Field>
                    <Field label="Movimiento de esta escena">
                      <TransitionPicker
                        options={meta?.transitions ?? [{ id: scene.transition, label: scene.transition }]}
                        value={scene.transition || project.transition_default}
                        onChange={(value) => void patchScene(scene, { transition: value })}
                        compact
                      />
                    </Field>
                  </div>
                  <div className="row gap-8">
                    <button className="btn small ghost" onClick={() => searchVisual(scene)}>Buscar imagen con licencia</button>
                    <Field label="Subir imagen propia o autorizada">
                      <input type="file" accept="image/jpeg,image/png,image/webp" disabled={!!busy} onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void uploadSceneImage(scene, file);
                        e.target.value = '';
                      }} />
                    </Field>
                    {scene.visual_path ? (
                      <Badge tone="ok">{scene.visual_url === 'archivo local subido' ? 'imagen propia' : scene.visual_kind === 'recurso' ? 'recurso externo' : 'tarjeta generada'}</Badge>
                    ) : (
                      <Badge tone="warn">tarjeta visual automática</Badge>
                    )}
                    {scene.visual_license && <small>{scene.visual_license}</small>}
                  </div>
                  {searchFor === scene.id && (
                    <div className="mt-12">
                      <div className="thumbs">
                        {results.map((r, idx) => (
                          <figure key={`${r.url}-${idx}`}>
                            {r.thumb ? <img src={r.thumb} alt={r.title} loading="lazy" /> : <div className="shot" />}
                            <figcaption>
                              {r.license || 'licencia a verificar'}
                              <br />
                              <button className="btn small ghost" onClick={() => applyVisual(scene, r)} disabled={busy === `visual-${scene.id}`}>
                                Usar
                              </button>
                            </figcaption>
                          </figure>
                        ))}
                      </div>
                      {results.length === 0 && <small>Sin resultados todavía.</small>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="stack">
          <Card title="Vídeo renderizado" sub="Vista previa del último render completado.">
            {project.status === 'renderizado' ? (
              <>
                <video controls preload="metadata" className={project.aspect === '9:16' ? 'preview vertical' : 'preview'} src={`/api/projects/${projectId}/video`} />
                <a className="btn primary" href={`/api/projects/${projectId}/video`} download={`video-${projectId}.mp4`}>
                  Descargar MP4 para subir manualmente
                </a>
              </>
            ) : (
              <Empty>Todavía no hay vídeo terminado. La producción automática va a generar el guion y renderizarlo; seguí el progreso en las tareas de arriba.</Empty>
            )}
          </Card>

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

          <Card title="Fuentes y atribuciones" sub="Registro exportable junto al vídeo.">
            {(project.sources ?? []).length === 0 ? (
              <Empty>Sin fuentes registradas. Guardá material desde Investigación o el editor.</Empty>
            ) : (
              <div className="list">
                {(project.sources ?? []).map((s) => (
                  <div className="list-item" key={s.id}>
                    <div className="grow">
                      <h4>{s.title || 'Sin título'}</h4>
                      <div className="meta">
                        <span>{s.author || 'autor desconocido'}</span>
                        <span>·</span>
                        <span>{s.license || 'licencia a verificar'}</span>
                        {s.url && <a href={s.url} target="_blank" rel="noreferrer">ver</a>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Miniatura" sub="Se genera en el render; podés descargarla del ZIP.">
            {project.status === 'renderizado' ? (
              <img className="shot" alt="Miniatura del proyecto" src={mediaUrl(`renders/${projectId}/thumb.jpg`)} onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
            ) : (
              <Empty>La miniatura aparece después del primer render.</Empty>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
