import { useEffect, useMemo, useState } from 'react';
import { api, type AutopilotRule, type Channel, type Meta, type TemplateOption, type Diagnostics } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';
import CaptionStylePicker from '../components/CaptionStylePicker';
import TransitionPicker from '../components/TransitionPicker';
import VoicePicker from '../components/VoicePicker';
import VideoTypePicker from '../components/VideoTypePicker';
import VisualStylePicker from '../components/VisualStylePicker';
import MusicPicker from '../components/MusicPicker';

type Options = {
  rules: AutopilotRule[];
  cadences: number[];
  channels: Channel[];
  templates: TemplateOption[];
  destinations: { id: string; label: string; available: boolean; missing_env: string[]; note: string }[];
};

const INITIAL = {
  name: '',
  niche: '',
  channel_id: '',
  template: 'shorts',
  duration_target_sec: 30,
  voice: 'es',
  speed: 150,
  pitch: 45,
  visual_style: 'automatico',
  video_type: 'moving_images',
  title_style: 'automatico',
  custom_tags: '',
  cadence_hours: 24,
  videos_per_period: 1,
  period_days: 1,
  schedule_time: '10:00',
  timezone: 'America/Argentina/Buenos_Aires',
  audience: 'Público general',
  tone: 'Dinámico y cercano',
  hook_style: 'Dato sorprendente',
  cta: 'Hacé una pregunta concreta al final',
  content_pillars: '',
  avoid_topics: '',
  aspect: '9:16',
  caption_style: 'short_pop',
  captions_enabled: true,
  transition_default: 'fundido',
  resolution: '1080p',
  fps: 25,
  music: 'auto',
  music_volume: 0.12,
  destination: 'entrega',
  privacy: 'unlisted',
  auto_publish: false,
  enabled: true,
};

const STEPS = [
  { title: 'Nicho', subtitle: 'Elegí el tema y definí qué contenido debe producir' },
  { title: 'Voz', subtitle: 'Escuchá y elegí la voz que narrará tus videos' },
  { title: 'Música', subtitle: 'Automática, pistas propias o sin música' },
  { title: 'Estilo visual', subtitle: 'Elegí el aspecto que tendrán las escenas' },
  { title: 'Subtítulos', subtitle: 'Elegí un estilo y su movimiento con vista previa' },
  { title: 'Canales', subtitle: 'Elegí si guardar los videos o publicarlos en YouTube' },
  { title: 'Calendario', subtitle: 'Definí duración, frecuencia y horario' },
  { title: 'Tipo de video', subtitle: 'Elegí Shorts, documental largo y formato visual' },
  { title: 'Confirmación', subtitle: 'Revisá y activá tu Autopiloto' },
];

export default function Autopilot() {
  const [data, setData] = useState<Options | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [persistenceConfigured, setPersistenceConfigured] = useState<boolean | null>(null);
  const [persistenceNote, setPersistenceNote] = useState('');
  const [form, setForm] = useState(INITIAL);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');

  async function load() {
    try {
      const [result, m, diagnostics] = await Promise.all([
        api.get<Options>('/api/autopilot'),
        api.get<Meta>('/api/meta'),
        api.get<Diagnostics>('/api/diagnostics'),
      ]);
      setData(result);
      setMeta(m);
      setPersistenceConfigured(diagnostics.persistence.configured || !!diagnostics.persistence.local_persistent);
      setPersistenceNote(diagnostics.persistence.note);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => { void load(); }, 12000);
    return () => window.clearInterval(interval);
  }, []);

  const templates = useMemo(
    () => (data?.templates ?? meta?.templates ?? []).filter((t) => ['shorts', 'listicle', 'pov', 'quote', 'longform', 'explainer', 'cuadrado', 'vertical_45'].includes(t.id)),
    [data, meta],
  );
  const youtubeReady = data?.destinations?.some((d) => d.id === 'youtube' && d.available) ?? false;
  const selectedTemplate = templates.find((t) => t.id === form.template);

  function update<K extends keyof typeof INITIAL>(key: K, value: (typeof INITIAL)[K]) {
    setForm((old) => ({ ...old, [key]: value }));
  }

  async function save() {
    if (form.auto_publish && form.destination === 'youtube' && !youtubeReady) {
      setError('Antes de activar la publicación automática, conectá y verificá tu canal de YouTube en Ajustes.');
      return;
    }
    if (form.auto_publish && form.destination === 'youtube' && persistenceConfigured === false) {
      setError('Para autopublicar sin perder el Short ante un reinicio, ejecutá Laburito en tu PC con un volumen local persistente.');
      return;
    }
    setBusy(true); setError(''); setOk('');
    try {
      const payload = {
        ...form,
        channel_id: form.channel_id ? Number(form.channel_id) : null,
        duration_target_sec: Number(form.duration_target_sec),
        cadence_hours: Number(form.cadence_hours),
        videos_per_period: Number(form.videos_per_period),
        period_days: Number(form.period_days),
        music_volume: Number(form.music_volume),
        fps: Number(form.fps),
      };
      if (editingId) {
        await api.patch('/api/autopilot/' + editingId, payload);
        setOk('Configuración actualizada.');
      } else {
        await api.post('/api/autopilot', payload);
        setOk('Autopiloto creado. Quedó programado con todas las opciones elegidas.');
      }
      setForm(INITIAL);
      setEditingId(null);
      setStep(0);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  }

  async function run(id: number) {
    setBusy(true); setError(''); setOk('');
    try {
      const result = await api.post<{ project_id: number; publish_warning?: string | null }>('/api/autopilot/' + id + '/run');
      const started = 'Producción iniciada. Proyecto #' + result.project_id + ' agregado a la cola.';
      setOk(result.publish_warning ? started + ' Atención: ' + result.publish_warning : started);
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  function edit(rule: AutopilotRule) {
    setForm({
      name: rule.name,
      niche: rule.niche,
      channel_id: rule.channel_id ? String(rule.channel_id) : '',
      template: rule.template,
      duration_target_sec: rule.duration_target_sec ?? 30,
      voice: rule.voice?.startsWith('es') ? rule.voice : 'es',
      speed: rule.speed ?? 150,
      pitch: rule.pitch ?? 45,
      visual_style: rule.visual_style || 'automatico',
      video_type: rule.video_type || 'moving_images',
      title_style: rule.title_style || 'automatico',
      custom_tags: rule.custom_tags || '',
      aspect: rule.aspect,
      caption_style: rule.caption_style,
      captions_enabled: rule.captions_enabled !== false,
      transition_default: rule.transition_default,
      resolution: rule.resolution,
      fps: rule.fps,
      music: rule.music || 'auto',
      music_volume: rule.music_volume,
      cadence_hours: rule.cadence_hours,
      videos_per_period: rule.videos_per_period || 1,
      period_days: rule.period_days || 1,
      schedule_time: rule.schedule_time || '10:00',
      timezone: rule.timezone || 'America/Argentina/Buenos_Aires',
      audience: rule.audience || 'Público general',
      tone: rule.tone || 'Dinámico y cercano',
      hook_style: rule.hook_style || 'Dato sorprendente',
      cta: rule.cta || 'Hacé una pregunta concreta al final',
      content_pillars: rule.content_pillars || '',
      avoid_topics: rule.avoid_topics || '',
      destination: rule.destination,
      privacy: rule.privacy,
      auto_publish: rule.auto_publish,
      enabled: rule.enabled,
    });
    setEditingId(rule.id);
    setStep(0);
    setError('');
    setOk('Editando «' + (rule.name || rule.niche) + '».');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function reset() {
    setEditingId(null);
    setForm(INITIAL);
    setStep(0);
    setOk('');
    setError('');
  }

  async function toggle(rule: AutopilotRule) {
    setBusy(true); setError('');
    try {
      await api.patch('/api/autopilot/' + rule.id, { enabled: !rule.enabled });
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function remove(id: number) {
    if (!window.confirm('¿Eliminar esta automatización?')) return;
    setBusy(true); setError('');
    try {
      await api.del('/api/autopilot/' + id);
      if (editingId === id) reset();
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  function chooseTemplate(id: string) {
    const selected = templates.find((t) => t.id === id);
    setForm((old) => ({
      ...old,
      template: id,
      ...(selected ? {
        aspect: selected.aspect,
        caption_style: selected.caption_style,
        duration_target_sec: selected.default_duration,
      } : {}),
    }));
  }

  const voiceOptions = (meta?.voices ?? []).filter((v) => v.language === 'es');
  const destinationInfo = data?.destinations.find((d) => d.id === 'youtube');

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      {persistenceConfigured === false && <p className="muted" style={{ padding: 12, border: '1px solid var(--border, #d1d5db)', borderRadius: 10 }}>
        <strong>Falta almacenamiento persistente.</strong> Para conservar la programación y el historial, ejecutá Laburito en tu PC con la carpeta local ./data.
      </p>}
      {persistenceConfigured === true && <p className="muted">{persistenceNote}</p>}
      <Card title={editingId ? 'Editar autopiloto' : 'Crear autopiloto'} sub="Configurá una vez todo lo que querés producir. Después el sistema usa estas reglas en cada Short programado.">
        <div className="stack" style={{ gap: 12 }}>
          <div className="autopilot-progress">
            <div className="autopilot-progress-top">
              <span>PASO {step + 1} DE {STEPS.length}</span>
              <strong>{STEPS[step].title}</strong>
            </div>
            <div className="autopilot-progress-bar"><span style={{ width: ((step + 1) / STEPS.length * 100) + '%' }} /></div>
            <p className="muted">{STEPS[step].subtitle}</p>
          </div>

          {step === 0 && <>
<h3>Definí el contenido del canal</h3>
            <Field label="Nicho principal">
              <input value={form.niche} onChange={(e) => update('niche', e.target.value)} placeholder="Misterio, ciencia, fútbol, historias, tecnología..." />
            </Field>
            <p className="muted">El descubrimiento automático combina temas documentados en Wikipedia y resúmenes académicos de OpenAlex con señales del RSS público de Google Trends Argentina cuando coinciden con el nicho. Las tendencias son señales de búsqueda, no garantía de viralidad ni de ingresos.</p>
            <Field label="Público al que le hablamos">
              <input value={form.audience} onChange={(e) => update('audience', e.target.value)} placeholder="Ej.: jóvenes interesados en historias reales" />
            </Field>
            <Field label="Subtemas que sí debe cubrir">
              <textarea value={form.content_pillars} onChange={(e) => update('content_pillars', e.target.value)} rows={3} placeholder="Separalos por coma. Ej.: casos extraños, leyendas, desapariciones..." />
            </Field>
            <Field label="Temas que debe evitar">
              <textarea value={form.avoid_topics} onChange={(e) => update('avoid_topics', e.target.value)} rows={2} placeholder="Ej.: tragedias recientes, política partidaria..." />
            </Field>

          <details className="advanced-settings">
            <summary>Personalizar guiones (opcional)</summary>
<h3>Personalidad de los guiones</h3>
            <Field label="Tono narrativo">
              <select value={form.tone} onChange={(e) => update('tone', e.target.value)}>
                {['Dinámico y cercano','Misterioso y tenso','Documental y riguroso','Humorístico e irónico','Emocional y reflexivo','Enérgico y provocador'].map((x) => <option key={x}>{x}</option>)}
              </select>
            </Field>
            <Field label="Cómo empieza cada Short (gancho)">
              <select value={form.hook_style} onChange={(e) => update('hook_style', e.target.value)}>
                {['Dato sorprendente','Pregunta intrigante','Afirmación polémica verificable','Situación en medio de la acción','Error o mito que desmontar','Misterio sin resolver'].map((x) => <option key={x}>{x}</option>)}
              </select>
            </Field>
            <Field label="Cómo termina">
              <select value={form.cta} onChange={(e) => update('cta', e.target.value)}>
                {['Hacé una pregunta concreta al final','Invitá a comentar una opinión','Invitá a compartir el Short','Invitá a seguir el canal','Cerrá con una reflexión, sin pedir interacción'].map((x) => <option key={x}>{x}</option>)}
              </select>
            </Field>
          </details>

<h3>Organizá los Shorts en un canal de contenido</h3>
            <Field label="Nombre de esta automatización">
              <input value={form.name} onChange={(e) => update('name', e.target.value)} placeholder="Ej.: Curiosidades diarias" />
            </Field>
            <Field label="Canal interno de Laburito">
              <select value={form.channel_id} onChange={(e) => update('channel_id', e.target.value)}>
                <option value="">Sin canal asociado todavía</option>
                {(data?.channels ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <p className="muted">Este canal organiza los proyectos y evita repetir temas. No selecciona la cuenta de YouTube: la cuenta real de publicación se conecta una sola vez en Ajustes.</p>
          </>}

          {step === 1 && <>
<h3>Voz española</h3>
            <p className="muted">Todos los Shorts se escriben y narran en español. Elegí únicamente la voz y el ritmo de narración.</p>
            <Field label="Elegí una voz en español">
              <VoicePicker
                options={voiceOptions}
                value={form.voice}
                speed={form.speed}
                pitch={form.pitch}
                onChange={(value) => {
                  update('voice', value);
                  if (value === 'es-masculino') update('pitch', 30);
                  else if (value === 'es-agudo') update('pitch', 65);
                  else update('pitch', 45);
                }}
                compact
              />
            </Field>
            <Field label={'Velocidad de narración: ' + form.speed + ' palabras/minuto'}>
              <input type="range" min="80" max="300" step="5" value={form.speed} onChange={(e) => update('speed', Number(e.target.value))} />
            </Field>
            <Field label={'Tono de voz (pitch): ' + form.pitch + '/99'}>
              <input type="range" min="0" max="99" step="1" value={form.pitch} onChange={(e) => update('pitch', Number(e.target.value))} />
            </Field>
            <div className="muted">La velocidad y el tono se aplican al motor espeak-ng. Piper usa el ritmo y tono propios del modelo neural.</div>
          </>}

          {step === 2 && <>
<h3>Música de fondo y mezcla</h3>
            <Field label="Elegí la música de fondo">
              <MusicPicker
                beds={meta?.music_beds ?? []}
                library={meta?.music_library ?? []}
                value={form.music}
                onChange={(value) => update('music', value)}
                compact
              />
            </Field>
            <Field label="Subir pistas propias (hasta 5 pistas de 25 MB cada una)">
              <input type="file" multiple accept=".mp3,.wav,.ogg,.m4a,.flac,audio/*" disabled={busy || (meta?.music_library.length ?? 0) >= 5} onChange={async (e) => {
                const files = Array.from(e.target.files ?? []);
                if (!files.length) return;
                const existing = meta?.music_library.length ?? 0;
                const selected = files.slice(0, Math.max(0, 5 - existing));
                if (!selected.length) { setError('Ya hay cinco pistas guardadas.'); e.target.value = ''; return; }
                setBusy(true); setError(''); setOk('');
                try {
                  const added: string[] = [];
                  for (const file of selected) {
                    if (file.size > 25 * 1024 * 1024) throw new Error(file.name + ' supera el límite de 25 MB.');
                    const result = await api.upload<{ filename: string }>('/api/music/upload', file);
                    added.push(result.filename);
                  }
                  update('music', 'auto');
                  setOk(added.length + ' pista(s) agregada(s). El modo automático las alternará en los próximos videos.');
                  await load();
                } catch (err) { setError((err as Error).message); }
                finally { setBusy(false); e.target.value = ''; }
              }} />
              <small>{meta?.music_library.length ?? 0}/5 pistas guardadas. En modo Automática se alternan en cada video.</small>
            </Field>
            <Field label={'Volumen de música: ' + Math.round(form.music_volume * 100) + '%'}>
              <input type="range" min="0" max="0.5" step="0.01" value={form.music_volume} onChange={(e) => update('music_volume', Number(e.target.value))} />
            </Field>
            <p className="muted">Las camas musicales se generan localmente. El modo automático alterna las pistas que cargaste y, si no hay ninguna, rota las camas integradas.</p>
          </>}

          {step === 3 && <>
            <h3>Elegí el aspecto de tus escenas</h3>
            <p className="muted">Cada tarjeta muestra una vista previa del tratamiento visual local. El estilo se aplicará a las imágenes de cada escena.</p>
            <VisualStylePicker
              options={meta?.visual_styles ?? []}
              value={form.visual_style}
              onChange={(value) => update('visual_style', value)}
              compact
            />
            <p className="muted">Los estilos disponibles aplican filtros de color, contraste y textura. No se presentan como generadores de imágenes IA.</p>
          </>}

          {step === 4 && <>
            <h3>Subtítulos y movimiento</h3>
            <p className="muted">Elegí cómo se muestran los textos y cómo se mueve cada escena. Podés ver una muestra antes de seleccionar.</p>
            <label className="check-row">
              <input type="checkbox" checked={form.captions_enabled} onChange={(e) => update('captions_enabled', e.target.checked)} />
              Agregar subtítulos al video
            </label>
            {form.captions_enabled ? (
              <Field label="Elegí el estilo de subtítulos">
                <CaptionStylePicker
                  options={meta?.caption_styles ?? []}
                  value={form.caption_style}
                  onChange={(value) => update('caption_style', value)}
                />
              </Field>
            ) : <p className="muted">El video se renderizará sin texto superpuesto ni archivos de subtítulos.</p>}
            <Field label="Movimiento de las escenas">
              <TransitionPicker
                options={meta?.transitions ?? []}
                value={form.transition_default}
                onChange={(value) => update('transition_default', value)}
                compact
              />
            </Field>
          </>}

          {step === 5 && <>
<h3>Elegí dónde guardar o publicar tus videos</h3>
            <p className="muted">Podés guardar cada video en tu biblioteca local sin conectar ninguna cuenta, o autorizar YouTube para publicarlo automáticamente cuando termine. La conexión se configura una sola vez en Ajustes.</p>
            <Field label="Estilo de título automático">
              <select value={form.title_style} onChange={(e) => update('title_style', e.target.value)}>
                <option value="automatico">Mantener el título del tema</option>
                <option value="pregunta">Abrir con una pregunta</option>
                <option value="curiosidad">Curiosidad / dato que despierta interés</option>
                <option value="directo">Título directo y descriptivo</option>
                <option value="misterio">Misterio / intriga</option>
              </select>
            </Field>
            <Field label="Etiquetas adicionales (separadas por coma)">
              <input value={form.custom_tags} onChange={(e) => update('custom_tags', e.target.value)} placeholder="Ej.: curiosidades, historia, datos interesantes" />
            </Field>
            <Field label="Destino de cada video">
              <select value={form.destination} onChange={(e) => update('destination', e.target.value)}>
                <option value="entrega">Guardar en Laburito para revisar</option>
                <option value="youtube">Publicar en YouTube</option>
              </select>
            </Field>
            <Field label="Privacidad en YouTube">
              <select value={form.privacy} onChange={(e) => update('privacy', e.target.value)}>
                <option value="private">Privado</option>
                <option value="unlisted">Oculto (solo con enlace)</option>
                <option value="public">Público</option>
              </select>
            </Field>
            {form.destination === 'youtube' && <label className="check-row">
              <input type="checkbox" checked={form.auto_publish} onChange={(e) => update('auto_publish', e.target.checked)} />
              Publicar automáticamente en YouTube al terminar el render
            </label>}
            {form.destination === 'entrega' && <p className="muted">Los videos se guardarán en tu biblioteca para que puedas revisarlos y publicarlos manualmente. No requiere cuenta externa ni credenciales.</p>}
            {form.destination === 'youtube' && !youtubeReady && <p className="muted">YouTube todavía no está listo. Conectalo en <a href="#/ajustes">Ajustes → YouTube</a>. Hasta entonces, no se puede publicar.</p>}
            {form.destination === 'youtube' && destinationInfo && <p className="muted">{destinationInfo.note}{destinationInfo.missing_env.length ? ' Faltan: ' + destinationInfo.missing_env.join(', ') + '.' : ''}</p>}

          </>}

          {step === 6 && <>
<h3>Duración y calendario automático</h3>
            <Field label="Duración objetivo">
              <select value={form.duration_target_sec} onChange={(e) => update('duration_target_sec', Number(e.target.value))}>
                {Array.from(new Set([...(selectedTemplate?.durations ?? [15,20,30,45,60,90,120,180]), ...(form.video_type === 'skeleton' ? [420] : [])])).filter((x) => form.video_type !== 'skeleton' || x <= 420).sort((a, b) => a - b).map((x) => <option key={x} value={x}>{x >= 60 ? Math.floor(x / 60) + ' minuto(s)' : x + ' segundos'}</option>)}
              </select>
            </Field>
            <Field label="Cantidad de videos">
              <input type="number" min="1" max="30" value={form.videos_per_period} onChange={(e) => update('videos_per_period', Math.max(1, Math.min(30, Number(e.target.value))))} />
            </Field>
            <Field label="Por período">
              <select value={form.period_days} onChange={(e) => update('period_days', Number(e.target.value))}>
                <option value={1}>Cada día</option>
                <option value={7}>Cada semana</option>
                <option value={30}>Cada 30 días</option>
              </select>
            </Field>
            <Field label="Hora de producción/publicación">
              <input type="time" value={form.schedule_time} onChange={(e) => update('schedule_time', e.target.value)} />
            </Field>
            <Field label="Zona horaria">
              <select value={form.timezone} onChange={(e) => update('timezone', e.target.value)}>
                <option value="America/Argentina/Buenos_Aires">Argentina</option>
                <option value="America/Santiago">Chile</option>
                <option value="America/Montevideo">Uruguay</option>
                <option value="America/Mexico_City">México</option>
                <option value="America/Bogota">Colombia</option>
                <option value="Europe/Madrid">España</option>
                <option value="UTC">UTC</option>
              </select>
            </Field>
            <p className="muted">Ejemplo: 1 Short por día, a las 10:00 de Argentina. El horario configura cuándo se inicia la producción programada; la publicación ocurre al terminar si activás la publicación automática.</p>
          </>}

          {step === 7 && <>
            <h3>Elegí el tipo y formato de video</h3>
            <Field label="Plantilla de contenido">
              <select value={form.template} onChange={(e) => chooseTemplate(e.target.value)}>
                {templates.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
            </Field>
            {selectedTemplate && <p className="muted">{selectedTemplate.description}</p>}
            <p className="muted">Los documentales largos usan formato horizontal. Los Shorts y Reels usan formato vertical. Minecraft, Subway y stock requieren que cargues clips propios o con permiso.</p>
            <VideoTypePicker
              options={meta?.video_types ?? []}
              value={form.video_type}
              onChange={(value) => update('video_type', value)}
              compact
            />
            <div className="row">
              <Field label="Calidad de exportación">
                <select value={form.resolution} onChange={(e) => update('resolution', e.target.value)}>
                  {(meta?.resolutions ?? []).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
                </select>
              </Field>
              <Field label="Fluidez">
                <select value={form.fps} onChange={(e) => update('fps', Number(e.target.value))}>
                  {(meta?.fps_options ?? [25,30]).map((x) => <option key={x} value={x}>{x} FPS</option>)}
                </select>
              </Field>
            </div>
            {form.video_type === 'skeleton' && form.duration_target_sec > 420 && <p className="muted">Skeleton admite hasta 7 minutos. Reducí la duración en el paso anterior para usar este formato.</p>}
          </>}
          {step === 8 && <>
            <h3>Revisá tu Autopiloto</h3>
            <div className="card" style={{ marginTop: 12 }}>
              <strong>{form.name || 'Nuevo Autopiloto'} · {form.niche || 'Sin nicho'}</strong>
              <p>{form.videos_per_period} video(s) cada {form.period_days === 1 ? 'día' : form.period_days === 7 ? 'semana' : '30 días'}, a las {form.schedule_time} ({form.timezone}).</p>
              <p>{form.duration_target_sec >= 60 ? Math.floor(form.duration_target_sec / 60) + ' min' : form.duration_target_sec + ' s'} · {form.aspect} · {form.resolution} · {form.destination === 'youtube' && form.auto_publish ? 'Publicación automática en YouTube' : 'Guardar en Laburito'}.</p>
              <p>Voz: {voiceOptions.find((v) => v.id === form.voice)?.label || form.voice} · Música: {form.music === 'auto' ? 'Automática' : form.music === 'ninguna' ? 'Sin música' : form.music}</p>
              <p>Tipo: {meta?.video_types.find((v) => v.id === form.video_type)?.label || form.video_type} · Estilo: {meta?.visual_styles.find((v) => v.id === form.visual_style)?.label || form.visual_style} · Subtítulos: {meta?.caption_styles.find((x) => x.id === form.caption_style)?.label || form.caption_style}</p>
            </div>
            <label className="check-row">
              <input type="checkbox" checked={form.enabled} onChange={(e) => update('enabled', e.target.checked)} />
              Activar el Autopiloto al guardar
            </label>
          </>}

          <div className="row" style={{ justifyContent: 'space-between', marginTop: 16 }}>
            <button className="btn ghost" disabled={step === 0 || busy} onClick={() => setStep((s) => Math.max(0, s - 1))}>Atrás</button>
            {step < STEPS.length - 1
              ? <button className="btn primary" disabled={busy || (step === 0 && !form.niche.trim())} onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}>Continuar</button>
              : <button className="btn primary" disabled={busy || !form.niche.trim() || (form.video_type === 'skeleton' && form.duration_target_sec > 420)} onClick={() => void save()}>{busy ? 'Guardando…' : editingId ? 'Guardar cambios' : 'Crear autopiloto'}</button>}
            {editingId && <button className="btn ghost" disabled={busy} onClick={reset}>Cancelar</button>}
          </div>
        </div>
      </Card>

      <Card title="Tus autopilotos" sub="Controlá cada automatización sin perder su configuración.">
        {!data ? <Empty>Cargando automatizaciones…</Empty> : data.rules.length === 0 ? <Empty>Todavía no configuraste ningún autopiloto.</Empty> : (
          <div className="list">
            {data.rules.map((rule) => (
              <div className="list-item" key={rule.id}>
                <div className="grow">
                  <h4>{rule.name || rule.niche}</h4>
                  <div className="meta"><span>{rule.niche}</span><span>·</span><span>{rule.videos_per_period || 1} cada {rule.period_days || 1} día(s)</span><span>·</span><Badge tone={rule.enabled ? 'ok' : 'warn'}>{rule.enabled ? 'Activo' : 'Pausado'}</Badge></div>
                  <div className="meta"><span>{rule.channel_name || 'Sin canal'}</span><span>·</span><span>{rule.template}</span><span>·</span><span>{rule.destination === 'youtube' ? 'YouTube' : 'Entrega local'}</span></div>
                  <small>{rule.last_project_title ? 'Último Short: ' + rule.last_project_title + ' · ' + (rule.last_project_status || 'creado') : 'Todavía no generó proyectos'}{rule.last_job_status ? ' · ' + (rule.last_job_kind === 'publish_project' ? 'Publicación' : 'Producción') + ': ' + rule.last_job_status : ''}{rule.last_job_message ? ' — ' + rule.last_job_message : ''}{rule.last_error ? ' · Último error: ' + rule.last_error : ''}{rule.last_run_at ? ' · Ejecutado: ' + new Date(rule.last_run_at).toLocaleString() : ''}{rule.next_run_at ? ' · Próximo: ' + new Date(rule.next_run_at).toLocaleString() : ''}</small>
                  {rule.last_job_status && ['en_cola', 'ejecutando'].includes(rule.last_job_status) && <div style={{ marginTop: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}><span>{rule.last_job_kind === 'publish_project' ? 'Publicando Short' : 'Produciendo Short'}</span><strong>{Math.max(0, Math.min(100, rule.last_job_progress || 0))}%</strong></div>
                    <div style={{ height: 6, borderRadius: 99, overflow: 'hidden', background: 'var(--border, #d1d5db)', marginTop: 4 }}><div style={{ width: Math.max(0, Math.min(100, rule.last_job_progress || 0)) + '%', height: '100%', background: 'var(--accent, #2563eb)', transition: 'width .3s ease' }} /></div>
                  </div>}
                </div>
                <div className="row">
                  <button className="btn small ghost" disabled={busy} onClick={() => edit(rule)}>Editar configuración</button>
                  <button className="btn small primary" disabled={busy} onClick={() => void run(rule.id)}>Crear ahora</button>
                  <button className="btn small ghost" disabled={busy} onClick={() => void toggle(rule)}>{rule.enabled ? 'Pausar' : 'Reanudar'}</button>
                  <button className="btn small danger" disabled={busy} onClick={() => void remove(rule.id)}>Eliminar</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
