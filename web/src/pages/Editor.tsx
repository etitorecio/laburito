import { useCallback, useEffect, useRef, useState } from 'react';
import { api, fmtDuration, mediaUrl, type MediaResult, type Project, type Scene } from '../api';
import { Badge, Card, Empty, Field, Msg, Progress, statusTone } from '../ui';
import type { Route } from '../routes';

interface Props {
  projectId: number;
  go: (route: Route, id?: number) => void;
}

export default function Editor({ projectId, go }: Props) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [busy, setBusy] = useState('');
  const [searchFor, setSearchFor] = useState<number | null>(null);
  const [results, setResults] = useState<MediaResult[]>([]);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      setProject(await api.get<Project>(`/api/projects/${projectId}`));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Mientras hay un render en curso, refrescamos el proyecto.
  useEffect(() => {
    const active = project?.jobs?.some((j) => ['en_cola', 'ejecutando'].includes(j.status));
    if (!active) return;
    timer.current = window.setInterval(() => void load(), 4000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [project, load]);

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

  async function regenerate(scene: Scene) {
    try {
      await api.post(`/api/scenes/${scene.id}/regenerate`);
      await load();
    } catch (e) {
      setError((e as Error).message);
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
  const words = scenes.reduce((acc, s) => acc + (s.narration || '').trim().split(/\s+/).filter(Boolean).length, 0);
  const quality = project.quality ?? {};
  const warnings = Array.isArray(quality.warnings) ? (quality.warnings as string[]) : [];
  const totalChars = scenes.reduce((acc, s) => acc + (s.narration || '').length, 0);

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />

      <Card
        title={project.title}
        sub={`${project.kind === 'short' ? 'Short vertical' : 'Documental'} · ${project.aspect} · ${scenes.length} escenas · ${words} palabras · ~${fmtDuration(totalChars / 14)} de voz`}
        actions={
          <>
            <button className="btn small ghost" onClick={() => go('proyectos')}>Volver</button>
            <button className="btn small" onClick={() => generateScript(false)} disabled={busy === 'script'}>+ Escenas</button>
            <button className="btn small primary" onClick={render} disabled={busy === 'render'}>Renderizar</button>
          </>
        }
      >
        <div className="pill-row" style={{ marginBottom: 12 }}>
          <Badge tone={statusTone(project.status)}>{project.status}</Badge>
          <Badge tone="info">{project.channel_name || 'sin canal'}</Badge>
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
            </select>
          </Field>
        </div>
        <div className="row">
          <button className="btn" onClick={() => generateScript(true)} disabled={busy === 'script'}>
            {busy === 'script' ? 'Generando…' : 'Generar guion completo'}
          </button>
          <a className="btn ghost" href={`/api/projects/${projectId}/download`}>Descargar paquete ZIP</a>
          <button className="btn ghost" onClick={async () => { await api.post(`/api/projects/${projectId}/export`); setOk('Exportación encolada. El ZIP estará disponible en unos segundos.'); }}>
            Preparar exportación
          </button>
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

      <div className="grid two">
        <Card title="Escenas" sub="Editá la narración; se guarda al salir del campo. El orden define el montaje.">
          {scenes.length === 0 ? (
            <Empty>Sin escenas. Generá el guion para crear la estructura narrativa.</Empty>
          ) : (
            <div>
              {scenes.map((scene, i) => (
                <div className="scene" key={scene.id}>
                  <div className="scene-head">
                    <div className="row center gap-8">
                      <span className="scene-index">{i + 1}</span>
                      <input
                        defaultValue={scene.title}
                        style={{ minWidth: 160 }}
                        onBlur={(e) => e.target.value !== scene.title && patchScene(scene, { title: e.target.value })}
                      />
                    </div>
                    <div className="row gap-8">
                      <button className="btn small ghost" onClick={() => move(scene, -1)} disabled={i === 0}>↑</button>
                      <button className="btn small ghost" onClick={() => move(scene, 1)} disabled={i === scenes.length - 1}>↓</button>
                      <button className="btn small ghost" onClick={() => regenerate(scene)}>Regenerar</button>
                      <button className="btn small danger" onClick={() => removeScene(scene)}>×</button>
                    </div>
                  </div>
                  <textarea
                    defaultValue={scene.narration}
                    onBlur={(e) => e.target.value !== scene.narration && patchScene(scene, { narration: e.target.value })}
                  />
                  <div className="row" style={{ marginTop: 8 }}>
                    <Field label="Búsqueda visual">
                      <input
                        defaultValue={scene.visual_query}
                        onBlur={(e) => e.target.value !== scene.visual_query && patchScene(scene, { visual_query: e.target.value })}
                      />
                    </Field>
                    <Field label="Transición">
                      <select defaultValue={scene.transition} onChange={(e) => patchScene(scene, { transition: e.target.value })}>
                        <option value="fundido">Fundido</option>
                        <option value="corte">Corte</option>
                        <option value="zoom">Zoom lento</option>
                        <option value="deslizar">Deslizar</option>
                      </select>
                    </Field>
                  </div>
                  <div className="row gap-8">
                    <button className="btn small ghost" onClick={() => searchVisual(scene)}>Buscar imagen con licencia</button>
                    {scene.visual_path ? (
                      <Badge tone="ok">imagen propia: {scene.visual_kind === 'recurso' ? 'recurso externo' : 'tarjeta generada'}</Badge>
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
              <video controls preload="metadata" className={project.aspect === '9:16' ? 'preview vertical' : 'preview'} src={`/api/projects/${projectId}/video`} />
            ) : (
              <Empty>Todavía no hay vídeo. Generá el guion y pulsá Renderizar.</Empty>
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
