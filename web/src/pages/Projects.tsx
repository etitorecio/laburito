import { useEffect, useState } from 'react';
import { api, mediaUrl, type Channel, type Diagnostics, type Meta, type Project } from '../api';
import { Badge, Card, Empty, Field, Msg, Progress, statusTone } from '../ui';
import VoicePicker from '../components/VoicePicker';
import MusicPicker from '../components/MusicPicker';
import VisualStylePicker from '../components/VisualStylePicker';
import VideoTypePicker from '../components/VideoTypePicker';
import CaptionStylePicker from '../components/CaptionStylePicker';
import TransitionPicker from '../components/TransitionPicker';
import type { Route } from '../routes';

export default function Projects({ go }: { go: (route: Route, id?: number) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [ollamaAvailable, setOllamaAvailable] = useState<boolean | null>(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [busy, setBusy] = useState(false);
  const [easyMode, setEasyMode] = useState(true);

  const [form, setForm] = useState({
    title: '',
    topic: '',
    input_mode: 'idea' as 'idea' | 'script',
    script_text: '',
    characters: '',
    template: 'shorts',
    channel_id: '' as string,
    duration_target_sec: 60,
    voice: 'es',
    speed: 150,
    pitch: 45,
    aspect: '9:16',
    caption_style: 'short_pop',
    captions_enabled: true,
    visual_style: 'automatico',
    visual_style_prompt: '',
    create_thumbnail: true,
    video_type: 'moving_images',
    music_volume: 0.3,
    transition_default: 'fundido',
    resolution: '720p',
    fps: 25,
    music: 'auto',
  });

  const templates = meta?.templates ?? [];
  const selectedChannel = channels.find((channel) => channel.id === Number(form.channel_id)) ?? null;
  const activeTemplate = templates.find((t) => t.id === form.template) ?? null;
  const voiceOptions = (meta?.voices ?? []).filter((v) => v.language === 'es');

  function applyTemplate(id: string) {
    const tpl = templates.find((t) => t.id === id);
    if (!tpl) {
      setForm({ ...form, template: id });
      return;
    }
    setForm({
      ...form,
      template: tpl.id,
      channel_id: form.channel_id || channels[0]?.id.toString() || '',
      aspect: tpl.aspect,
      caption_style: tpl.caption_style,
      duration_target_sec: tpl.default_duration,
    });
  }

  function templateLabel(id?: string): string {
    return templates.find((t) => t.id === id)?.label ?? id ?? '';
  }

  async function load() {
    try {
      const [p, c, m, diagnostics] = await Promise.all([
        api.get<Project[]>('/api/projects'),
        api.get<Channel[]>('/api/channels'),
        api.get<Meta>('/api/meta'),
        api.get<Diagnostics>('/api/diagnostics'),
      ]);
      setProjects(p);
      setChannels(c);
      setForm((current) => current.channel_id ? current : {
        ...current,
        channel_id: String(c[0]?.id ?? ''),
      });
      setMeta(m);
      setOllamaAvailable(diagnostics.ollama.available);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function create() {
    setError('');
    setOk('');
    const projectTitle = (form.title.trim() || form.topic.trim() || form.script_text.trim().split(/[.!?]/)[0] || 'Nuevo video').slice(0, 120);
    if (form.input_mode === 'idea' && !form.topic.trim()) {
      setError('Escribí la idea o el tema de tu video.');
      return;
    }
    if (form.input_mode === 'script' && !form.script_text.trim()) {
      setError('Pegá el guion completo o cambiá a modo Idea.');
      return;
    }
    if (form.script_text.length > 12000) {
      setError('El guion no puede superar los 12.000 caracteres.');
      return;
    }
    setBusy(true);
    let created: Project | null = null;
    try {
      const { captions_enabled, characters, input_mode, script_text, ...projectForm } = form;
      created = await api.post<Project>('/api/projects', {
        ...projectForm,
        title: projectTitle,
        channel_id: selectedChannel?.id ?? null,
        topic: form.topic || projectTitle,
        notes: (!captions_enabled || form.visual_style_prompt.trim() || !form.create_thumbnail || characters.trim() || (input_mode === 'script' && script_text.trim())) ? '[LABURITO_META]' + JSON.stringify({ captions_enabled, visual_style_prompt: form.visual_style_prompt.trim(), create_thumbnail: form.create_thumbnail, characters: characters.trim(), script_text: input_mode === 'script' ? script_text.trim() : '' }) : '',
      });
      setOk('1/3 · Proyecto creado. Escribiendo el guion y preparando las escenas…');
      const scriptResult = await api.post<{ warnings?: string[] }>('/api/projects/' + created.id + '/script?replace=true');
      const researchFailure = (scriptResult.warnings || []).find((warning) => warning.startsWith('No se pudo completar la investigación automática:'));
      const researchNote = (scriptResult.warnings || []).some((warning) => warning.includes('Investigación integrada'))
        ? ' Investigación del tema incorporada automáticamente.'
        : researchFailure
          ? ' La investigación automática no estuvo disponible; el guion se produjo con la información local disponible.'
          : '';
      setOk('2/3 · Guion listo.' + researchNote + ' Montando voz, imágenes, subtítulos y música…');
      await api.post('/api/projects/' + created.id + '/render');
      setForm({ ...form, title: '', topic: '', script_text: '' });
      setOk('3/3 · Producción enviada al render. Podés seguir el progreso y descargar el MP4 en el editor.' + (researchFailure ? ' Aviso: la investigación automática falló, pero la producción continuó.' : ''));
      await load();
      go('editor', created.id);
    } catch (e) {
      const message = (e as Error).message;
      if (created) {
        setError('El proyecto quedó guardado, pero la producción automática se detuvo: ' + message + '. Abrilo para continuar desde el paso pendiente.');
        await load();
        go('editor', created.id);
      } else {
        setError(message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function createBlank() {
    setError('');
    setOk('');
    const blankTitle = (form.title.trim() || form.topic.trim() || 'Proyecto sin título').slice(0, 120);
    setBusy(true);
    try {
      const { captions_enabled, characters, input_mode, script_text, ...projectForm } = form;
      const created = await api.post<Project>('/api/projects', {
        ...projectForm,
        title: blankTitle,
        channel_id: selectedChannel?.id ?? null,
        topic: form.topic || blankTitle,
        notes: (!captions_enabled || form.visual_style_prompt.trim() || !form.create_thumbnail || characters.trim() || (input_mode === 'script' && script_text.trim()))
          ? '[LABURITO_META]' + JSON.stringify({
              captions_enabled,
              visual_style_prompt: form.visual_style_prompt.trim(),
              create_thumbnail: form.create_thumbnail,
              characters: characters.trim(),
              script_text: input_mode === 'script' ? script_text.trim() : '',
            })
          : '',
      });
      setOk('Proyecto vacío creado. Agregá escenas manualmente o escribí tu guion desde el editor.');
      await load();
      go('editor', created.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(project: Project) {
    if (!confirm(`¿Eliminar «${project.title}» y sus escenas?`)) return;
    try {
      await api.del(`/api/projects/${project.id}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function removeMusic(track: string) {
    if (!confirm('¿Quitar esta pista de la biblioteca local?')) return;
    try {
      await api.del('/api/music/' + encodeURIComponent(track));
      setOk('Pista quitada de la biblioteca.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      {ollamaAvailable === false && <p className="muted">Esta instancia no tiene un modelo generativo conectado: la idea se convierte en un guion estructurado de respaldo. Para generar narraciones originales sin pagar APIs, conectá Ollama local desde Ajustes.</p>}

      <Card title="Crear video" sub="No necesitás configurar nada: elegí el formato, contá de qué trata y AITuber prepara el guion y la producción.">
        <div className="stack" style={{ gap: 14 }}>
          <div className="creation-mode-switch" role="group" aria-label="Nivel de configuración">
            <button type="button" className={easyMode ? 'active' : ''} onClick={() => setEasyMode(true)}>✦ Modo fácil</button>
            <button type="button" className={!easyMode ? 'active' : ''} onClick={() => setEasyMode(false)}>⚙ Ajustes avanzados</button>
          </div>
          {easyMode && <div className="quick-format-grid">
            <button type="button" className={form.aspect === '9:16' ? 'quick-format active' : 'quick-format'} onClick={() => applyTemplate('shorts')}>
              <span className="quick-format-icon">▯</span><strong>Short</strong><small>Vertical · rápido · ideal para Shorts</small>
            </button>
            <button type="button" className={form.aspect === '16:9' ? 'quick-format active' : 'quick-format'} onClick={() => applyTemplate('longform')}>
              <span className="quick-format-icon">▭</span><strong>Documental</strong><small>Horizontal · historias y explicaciones</small>
            </button>
          </div>}
          <Field label="¿De dónde partimos?">
            <select value={form.input_mode} onChange={(e) => setForm({ ...form, input_mode: e.target.value as 'idea' | 'script' })}>
              <option value="idea">Desde una idea: generar el guion</option>
              <option value="script">Desde un guion propio: convertirlo en escenas</option>
            </select>
          </Field>
          {form.input_mode === 'script' && (
            <Field label="Guion completo" hint="Se conserva tu texto y se divide automáticamente en escenas para voz, visuales y render. Máximo 12.000 caracteres.">
              <textarea rows={9} maxLength={12000} value={form.script_text} onChange={(e) => setForm({ ...form, script_text: e.target.value })} placeholder="Pegá acá el guion completo. Separá los cambios de escena con una línea en blanco." />
              <small>{form.script_text.length.toLocaleString('es')} / 12.000 caracteres</small>
            </Field>
          )}
          <Field label={form.input_mode === 'idea' ? '¿De qué querés que trate el video?' : 'Título (opcional)'}>
            <input value={form.input_mode === 'idea' ? form.topic : form.title} onChange={(e) => setForm(form.input_mode === 'idea' ? { ...form, topic: e.target.value, title: e.target.value.slice(0, 120) } : { ...form, title: e.target.value })} placeholder={form.input_mode === 'idea' ? 'Ej.: El misterio de las civilizaciones perdidas' : 'Poné un título para tu video'} />
          </Field>
          {easyMode && <p className="muted">Podés crear el video directamente. Si después querés organizarlo, lo asignás a un canal desde el editor.</p>}
          {!easyMode && <div className="row">
            <Field label="Plantilla de contenido" hint={activeTemplate?.description}>
              <select value={form.template} onChange={(e) => applyTemplate(e.target.value)}>
                {templates.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
            </Field>
            {form.template === 'frutinovela' && <>
              <Field label="Personajes recurrentes">
                <input value={form.characters} onChange={(e) => setForm({ ...form, characters: e.target.value })} placeholder="Manzana (protagonista), Banana (pareja), Pera (rival)..." />
              </Field>
              <p className="muted">Usá siempre los mismos nombres y relaciones. El sistema recupera el final del episodio anterior para continuar la trama.</p>
            </>}
            {form.template === 'reddit_story' && <p className="muted">Historias originales en español con estructura de Reddit: gancho, contexto, escalada, giro y pregunta final. Duración predeterminada: 3 minutos.</p>}
            <Field label="Canal de contenido" hint="Elegí en qué canal interno se guardará este proyecto. Cada canal puede vincularse a una cuenta real de YouTube desde Cuentas.">
              <select value={form.channel_id} onChange={(e) => setForm({ ...form, channel_id: e.target.value })}>
                <option value="">Seleccioná un canal…</option>
                {channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
              </select>
              <div className="row" style={{ gap: 8, marginTop: 6 }}>
                <button type="button" className="btn small ghost" onClick={() => go('cuentas')}>Vincular cuenta de YouTube</button>
                <button type="button" className="btn small ghost" onClick={() => go('canales')}>Crear otro canal</button>
              </div>
            </Field>
            <Field label="Duración objetivo">
              <select value={form.duration_target_sec} onChange={(e) => setForm({ ...form, duration_target_sec: Number(e.target.value) })}>
                {(activeTemplate?.durations ?? [15,30,45,60]).map((duration) => (
                  <option key={duration} value={duration}>{duration < 60 ? duration + ' s' : Math.round(duration / 60) + ' min'}</option>
                ))}
              </select>
            </Field>
          </div>}

          {!easyMode && <>
          <details className="advanced-settings">
            <summary>Voz y narración</summary>
            <Field label="Elegí una voz en español">
              <VoicePicker
                options={voiceOptions}
                value={form.voice}
                speed={form.speed}
                pitch={form.pitch}
                onChange={(value) => setForm({ ...form, voice: value })}
              />
            </Field>
            <div className="row">
              <Field label={'Velocidad: ' + form.speed + ' palabras/minuto'}>
                <input type="range" min="80" max="300" step="5" value={form.speed} onChange={(e) => setForm({ ...form, speed: Number(e.target.value) })} />
              </Field>
              <Field label={'Tono: ' + form.pitch + '/99'}>
                <input type="range" min="0" max="99" value={form.pitch} onChange={(e) => setForm({ ...form, pitch: Number(e.target.value) })} />
              </Field>
            </div>
          </details>

          <details className="advanced-settings">
            <summary>Música de fondo</summary>
            <MusicPicker
              beds={meta?.music_beds ?? []}
              library={meta?.music_library ?? []}
              value={form.music}
              onChange={(value) => setForm({ ...form, music: value })}
            />
            <Field label={'Volumen de música: ' + Math.round(form.music_volume * 100) + '%'}>
              <input type="range" min="0" max="0.5" step="0.01" value={form.music_volume} onChange={(e) => setForm({ ...form, music_volume: Number(e.target.value) })} />
            </Field>
            <Field label="Agregar pistas propias (hasta 5)">
              <input type="file" multiple accept=".mp3,.wav,.ogg,.m4a,.flac,audio/*" disabled={(meta?.music_library.length ?? 0) >= 5} onChange={async (e) => {
                const files = Array.from(e.target.files ?? []);
                const remaining = Math.max(0, 5 - (meta?.music_library.length ?? 0));
                try {
                  for (const file of files.slice(0, remaining)) {
                    if (file.size > 25 * 1024 * 1024) throw new Error(file.name + ' supera 25 MB.');
                    await api.upload('/api/music/upload', file);
                  }
                  setForm((old) => ({ ...old, music: 'auto' }));
                  await load();
                  setOk('Pistas agregadas a la biblioteca local.');
                } catch (error) { setError((error as Error).message); }
                finally { e.target.value = ''; }
              }} />
              <small>{meta?.music_library.length ?? 0}/5 pistas. El modo automático las alterna entre videos.</small>
              {(meta?.music_library ?? []).map((track) => (
                <div className="row center between" key={track}>
                  <small>{track}</small>
                  <button type="button" className="btn small ghost" onClick={() => void removeMusic(track)}>Quitar</button>
                </div>
              ))}
            </Field>
          </details>

          <details className="advanced-settings">
            <summary>Apariencia y tipo de video</summary>
            <h4>Estilo visual</h4>
            <VisualStylePicker options={meta?.visual_styles ?? []} value={form.visual_style} onChange={(value) => setForm({ ...form, visual_style: value })} />
            <Field label="Estilo personalizado (opcional)">
              <textarea rows={3} maxLength={240} value={form.visual_style_prompt} onChange={(e) => setForm({ ...form, visual_style_prompt: e.target.value })} placeholder="Ej.: iluminación cálida, fotografía analógica, tonos verdes y textura de película…" />
            </Field>
            <p className="muted">La descripción guía la búsqueda de imágenes libres y algunos filtros locales; no genera imágenes IA.</p>
            <Field label="Usar una imagen como referencia (paleta local)">
              <input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setBusy(true); setError(''); setOk('');
                try {
                  const result = await api.upload<{ visual_style_prompt: string; analysis: string }>('/api/visual-style/analyze', file);
                  setForm((old) => ({ ...old, visual_style_prompt: result.visual_style_prompt }));
                  setOk(result.analysis + ' Revisá la descripción antes de crear el video.');
                } catch (error) { setError((error as Error).message); }
                finally { setBusy(false); e.target.value = ''; }
              }} />
            </Field>
            <label className="check-row">
              <input type="checkbox" checked={form.create_thumbnail} onChange={(e) => setForm({ ...form, create_thumbnail: e.target.checked })} />
              Crear miniatura automáticamente
            </label>
            <h4>Tipo de video</h4>
            <VideoTypePicker options={meta?.video_types ?? []} value={form.video_type} onChange={(value) => setForm({ ...form, video_type: value })} />
            <div className="row">
              <Field label="Aspecto">
                <select value={form.aspect} onChange={(e) => setForm({ ...form, aspect: e.target.value })}>
                  {(meta?.aspects ?? ['16:9', '9:16', '1:1', '4:5']).map((aspect) => <option key={aspect} value={aspect}>{aspect}</option>)}
                </select>
              </Field>
              <Field label="Resolución">
                <select value={form.resolution} onChange={(e) => setForm({ ...form, resolution: e.target.value })}>
                  {(meta?.resolutions ?? [{ id: '1080p', label: '1080p' }]).map((resolution) => <option key={resolution.id} value={resolution.id}>{resolution.label}</option>)}
                </select>
              </Field>
              <Field label="Cuadros por segundo">
                <select value={form.fps} onChange={(e) => setForm({ ...form, fps: Number(e.target.value) })}>
                  {(meta?.fps_options ?? [25]).map((fps) => <option key={fps} value={fps}>{fps} fps</option>)}
                </select>
              </Field>
            </div>
          </details>

          <details className="advanced-settings">
            <summary>Subtítulos y transiciones</summary>
            <label className="check-row">
              <input type="checkbox" checked={form.captions_enabled} onChange={(e) => setForm({ ...form, captions_enabled: e.target.checked })} />
              Agregar subtítulos al video
            </label>
            {form.captions_enabled ? (
              <Field label="Estilo de subtítulos">
                <CaptionStylePicker options={meta?.caption_styles ?? []} value={form.caption_style} onChange={(value) => setForm({ ...form, caption_style: value })} />
              </Field>
            ) : <p className="muted">El video se renderizará sin subtítulos.</p>}
            <Field label="Movimiento entre escenas">
              <TransitionPicker options={meta?.transitions ?? []} value={form.transition_default} onChange={(value) => setForm({ ...form, transition_default: value })} />
            </Field>
          </details>

          {meta && meta.external_templates.length > 0 && (
            <p className="muted">Los generadores externos de video IA no se incluyen: requerirían servicios con créditos. Los formatos desactivados no se presentan como disponibles.</p>
          )}
          </>}
          <div className="creation-submit">
            <button className="btn primary" onClick={create} disabled={busy || (form.input_mode === 'idea' ? !form.topic.trim() : !form.script_text.trim())}>{busy ? 'Preparando tu video…' : form.input_mode === 'script' ? 'Crear video con mi guion' : '✦ Crear mi video'}</button>
            {!easyMode && <button className="btn ghost" onClick={createBlank} disabled={busy}>Empezar desde cero</button>}
            <small>{easyMode ? 'La configuración recomendada se aplica automáticamente. Podés cambiarla después en el editor.' : 'Podés revisar cada ajuste antes de producir.'}</small>
          </div>
        </div>
      </Card>

      <Card title="Tus videos" sub="Producciones, estado y acceso al editor.">
        {projects.length === 0 ? (
          <Empty>Sin proyectos. Creá el primero y generá el guion.</Empty>
        ) : (
          <div className="list">
            {projects.map((p) => (
              <div className="list-item project-list-item" key={p.id}>
                {p.thumbnail_path ? <img className="project-list-thumb" src={mediaUrl(p.thumbnail_path)} alt="" loading="lazy" /> : p.status === 'renderizado' ? <img className="project-list-thumb" src={`/media/renders/${p.id}/miniatura_${p.kind === 'short' ? 'short' : 'documental'}.jpg`} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; }} /> : <div className="project-list-thumb project-list-thumb-empty">▶</div>}
                <div className="grow">
                  <h4>{p.title}</h4>
                  <div className="meta">
                    <Badge tone={statusTone(p.status)}>{p.status}</Badge>
                    <span>{templateLabel(p.template) || p.aspect}</span>
                    <span>{p.aspect}</span>
                    <span>{p.scenes_count ?? 0} escenas</span>
                    <span>{p.channel_name || 'sin canal'}</span>
                    <span>{new Date(p.updated_at).toLocaleString('es')}</span>
                  </div>
                  {p.job && p.job.status !== 'completado' && (
                    <div style={{ marginTop: 6 }}>
                      <Progress value={p.job.progress} label={p.job.message} />
                    </div>
                  )}
                </div>
                <div className="row gap-8">
                  <button className="btn small primary" onClick={() => go('editor', p.id)}>Abrir editor</button>
                  <button className="btn small danger" onClick={() => remove(p)}>Eliminar</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
