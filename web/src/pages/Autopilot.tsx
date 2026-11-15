import { useEffect, useMemo, useState } from 'react';
import { api, type AutopilotRule, type Channel, type Meta, type TemplateOption, type Diagnostics } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';
import CaptionStylePicker from '../components/CaptionStylePicker';
import TransitionPicker from '../components/TransitionPicker';
import VoicePicker from '../components/VoicePicker';

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
  visual_style: 'Movimiento de imágenes con paneo y zoom',
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
  transition_default: 'fundido',
  resolution: '1080p',
  fps: 25,
  music: 'auto',
  music_volume: 0.12,
  destination: 'youtube',
  privacy: 'public',
  auto_publish: true,
  enabled: true,
};

const STEPS = [
  { title: 'Nicho', subtitle: 'Qué contenido va a descubrir y producir' },
  { title: 'Voz', subtitle: 'Elegí una voz en español y su ritmo' },
  { title: 'Música', subtitle: 'Automática, una pista o sin música' },
  { title: 'Apariencia', subtitle: 'Elegí el tipo de video y el estilo visual' },
  { title: 'Subtítulos', subtitle: 'Vista previa del texto y movimiento' },
  { title: 'Publicación', subtitle: 'Dónde se guarda o publica cada Short' },
  { title: 'Calendario', subtitle: 'Duración, frecuencia y horario' },
  { title: 'Confirmación', subtitle: 'Revisá y activá tu Autopiloto' },
];

const PRODUCTION_STAGES = [
  ['1', 'Programación y tema', 'El calendario activa la regla y evita repetir temas.'],
  ['2', 'Investigación y fuentes', 'Busca material documental y registra enlaces y atribuciones.'],
  ['3', 'Guion y gancho', 'Organiza apertura, desarrollo y cierre a partir de la evidencia disponible.'],
  ['4', 'Voz en off', 'Genera la narración en español con el motor TTS configurado.'],
  ['5', 'Selección visual', 'Busca imágenes por escena; los clips de gameplay y los generadores de video aún no están conectados.'],
  ['6', 'Preparación de escenas', 'Prepara cada visual, encuadre, duración y transición con FFmpeg.'],
  ['7', 'Subtítulos', 'Sincroniza y quema subtítulos; también exporta SRT y VTT.'],
  ['8', 'Música y mezcla', 'Mezcla voz y música de fondo según el volumen configurado.'],
  ['9', 'Render vertical', 'Une las escenas y genera el MP4 final en 9:16.'],
  ['10', 'Control de calidad', 'Comprueba que el archivo exista y que ffprobe pueda leer resolución y duración.'],
  ['11', 'Publicación', 'Encola la subida real a YouTube cuando OAuth y la evidencia estén listos.'],
  ['12', 'Registro', 'Guarda el enlace, el ID de YouTube y el resultado de la tarea.'],
];

const VISUAL_OPTIONS = [
  { id: 'moving_images', title: 'Imágenes con movimiento', subtitle: 'En esta versión: imágenes de archivo con paneo y zoom; no se generan con IA', preview: '🖼️', available: true, style: 'Movimiento de imágenes con paneo y zoom', kind: 'stock' },
  { id: 'stock_images', title: 'Videos de archivo', subtitle: 'Fotografías y material de archivo con licencia; el catálogo depende de las fuentes disponibles', preview: '🎞️', available: true, style: 'Fotografía de archivo con licencia', kind: 'stock' },
  { id: 'full_motion_ai', title: 'Video IA de movimiento completo', subtitle: 'Clips de video generados por IA', preview: '🎬', available: false, style: 'Full Motion AI Video', kind: 'ai' },
  { id: 'skeleton', title: 'Video de esqueleto 3D', subtitle: 'Animación 3D de esqueleto: todavía no hay motor de animación conectado', preview: '💀', available: false, style: 'Skeleton Video', kind: 'skeleton' },
  { id: 'minecraft', title: 'Gameplay de Minecraft', subtitle: '5 miniaturas de preview · requiere gameplay propio o licenciado', preview: '⛏️', available: false, style: 'Minecraft gameplay', kind: 'minecraft' },
  { id: 'subway', title: 'Gameplay de Subway Surfers', subtitle: '5 clips de ejemplo · requiere videos con licencia o propios', preview: '🏃', available: false, style: 'Subway Surfers gameplay', kind: 'subway' },
];

const THUMB_IMAGES: Record<string, string[]> = {
  stock: ['/previews/stock-01.svg', '/previews/stock-02.svg', '/previews/stock-03.svg', '/previews/stock-04.svg', '/previews/stock-05.svg'],
  minecraft: ['/previews/voxel-01.svg', '/previews/voxel-02.svg', '/previews/voxel-03.svg', '/previews/voxel-04.svg', '/previews/voxel-05.svg'],
  subway: ['/previews/runner-01.svg', '/previews/runner-02.svg', '/previews/runner-03.svg', '/previews/runner-04.svg', '/previews/runner-05.svg'],
};

const THUMB_BACKGROUNDS: Record<string, string[]> = {
  stock: [
    'linear-gradient(135deg,#1e3a5f,#78a6c8)',
    'linear-gradient(135deg,#4b3621,#c69b63)',
    'linear-gradient(135deg,#253b32,#8ba88d)',
    'linear-gradient(135deg,#3f315d,#b19acb)',
    'linear-gradient(135deg,#293747,#9aa7b6)',
  ],
  minecraft: [
    'linear-gradient(180deg,#8bc6ec 0 45%,#4d8b43 45% 70%,#79553a 70%)',
    'linear-gradient(180deg,#b7d7e8 0 40%,#315d39 40% 68%,#72513a 68%)',
    'linear-gradient(180deg,#6b778d 0 42%,#555b42 42% 70%,#41352c 70%)',
    'linear-gradient(180deg,#f0c77b 0 38%,#56884a 38% 68%,#8b6240 68%)',
    'linear-gradient(180deg,#7db3d1 0 40%,#426b42 40% 70%,#594632 70%)',
  ],
  subway: [
    'linear-gradient(180deg,#54b8e8 0 40%,#f2c34b 40% 50%,#326b9e 50% 100%)',
    'linear-gradient(180deg,#9bd7f0 0 38%,#f08a37 38% 52%,#275c88 52% 100%)',
    'linear-gradient(180deg,#4c9cc8 0 40%,#e6bb44 40% 50%,#334d75 50% 100%)',
    'linear-gradient(180deg,#8bd0e9 0 36%,#e36c45 36% 50%,#1d5a83 50% 100%)',
    'linear-gradient(180deg,#63b9d9 0 40%,#e9c85a 40% 50%,#244f78 50% 100%)',
  ],
  ai: ['linear-gradient(135deg,#172554,#7c3aed)'],
  skeleton: ['linear-gradient(135deg,#171717,#737373)'],
};


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
    () => (data?.templates ?? meta?.templates ?? []).filter((t) => ['shorts', 'listicle', 'pov', 'quote'].includes(t.id)),
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
      visual_style: rule.visual_style || 'Movimiento de imágenes con paneo y zoom',
      title_style: rule.title_style || 'automatico',
      custom_tags: rule.custom_tags || '',
      aspect: rule.aspect,
      caption_style: rule.caption_style,
      transition_default: rule.transition_default,
      resolution: rule.resolution,
      fps: rule.fps,
      music: (rule.music || 'auto').replace(/^bed:/, ''),
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
            <Field label="Pista / ambiente musical">
              <select value={form.music} onChange={(e) => update('music', e.target.value)}>
                <option value="auto">Automática según el contenido</option>
                <option value="ninguna">Sin música</option>
                {(meta?.music_beds ?? []).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
                {(meta?.music_library ?? []).map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
            </Field>
            <Field label="Subir una pista propia (máximo 25 MB)">
              <input type="file" accept=".mp3,.wav,.ogg,.m4a,.flac,audio/*" onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setBusy(true); setError(''); setOk('');
                try {
                  const result = await api.upload<{ filename: string }>('/api/music/upload', file);
                  update('music', result.filename);
                  setOk('Pista agregada: ' + result.filename);
                  await load();
                } catch (err) { setError((err as Error).message); }
                finally { setBusy(false); e.target.value = ''; }
              }} />
            </Field>
            <Field label={'Volumen de música: ' + Math.round(form.music_volume * 100) + '%'}>
              <input type="range" min="0" max="0.5" step="0.01" value={form.music_volume} onChange={(e) => update('music_volume', Number(e.target.value))} />
            </Field>
            <p className="muted">La música integrada se genera localmente. La carga de pistas propias y la rotación de varias canciones todavía no están conectadas al autopiloto.</p>
          </>}

          {step === 3 && <>
<h3>Tipo de Short y aspecto visual</h3>
            <p className="muted">Este autopiloto solo crea Shorts verticales 9:16. No genera documentales ni videos horizontales.</p>
            <Field label="Formato narrativo">
              <select value={form.template} onChange={(e) => chooseTemplate(e.target.value)}>
                {templates.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
            </Field>
            {selectedTemplate && <p className="muted">{selectedTemplate.description}</p>}
            <h4>Formato visual y catálogo de clips</h4>
            <p className="muted">Cada tarjeta muestra miniaturas rectangulares como referencia. Las miniaturas de Minecraft y Subway son ilustrativas: no incluyen ni descargan gameplay real. Solo se pueden activar formatos que el motor actual puede producir.</p>
            <div className="visual-style-track">
              {VISUAL_OPTIONS.map((item) => {
                const selected = form.visual_style === item.style;
                const imageThumbs = THUMB_IMAGES[item.kind];
                const thumbs = imageThumbs ?? THUMB_BACKGROUNDS[item.kind] ?? THUMB_BACKGROUNDS.stock;
                const count = item.kind === 'minecraft' || item.kind === 'subway' ? 5 : Math.min(3, thumbs.length);
                return <button key={item.id} type="button" disabled={!item.available}
                  onClick={() => update('visual_style', item.style)}
                  aria-pressed={selected}
                  style={{ flex: '0 0 250px', minWidth: 250, textAlign: 'left', padding: 0, overflow: 'hidden', borderRadius: 12, scrollSnapAlign: 'start',
                    border: selected ? '2px solid #dc2626' : '1px solid var(--border, #d1d5db)',
                    background: 'var(--card, #fff)', opacity: item.available ? 1 : 0.76,
                    cursor: item.available ? 'pointer' : 'not-allowed' }}>
                  <div aria-label={`Previews de ${item.title}`} style={{ height: 96, display: 'flex', gap: 6, padding: 6, background: '#111827',
                    overflowX: 'auto', overflowY: 'hidden', scrollSnapType: 'x mandatory', WebkitOverflowScrolling: 'touch' }}>
                    {Array.from({ length: count }, (_, index) => (
                      <div key={index} style={{ flex: '0 0 88px', minWidth: 88, borderRadius: 5,
                        position: 'relative', overflow: 'hidden', scrollSnapAlign: 'start',
                        background: imageThumbs ? `center / cover no-repeat url("${thumbs[index % thumbs.length]}")` : thumbs[index % thumbs.length] }}>
                        <span style={{ position: 'absolute', left: 3, bottom: 3, color: '#fff',
                          fontSize: 9, fontWeight: 800, textShadow: '0 1px 3px #000' }}>
                          {count > 1 ? '0' + (index + 1) : item.preview}
                        </span>
                        {item.kind === 'minecraft' && <span style={{ position: 'absolute', right: 2, top: 4, fontSize: 16 }}>⛏️</span>}
                        {item.kind === 'subway' && <span style={{ position: 'absolute', right: 2, top: 4, fontSize: 16 }}>🏃</span>}
                        {item.kind === 'skeleton' && <span style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', fontSize: 30 }}>💀</span>}
                        {item.kind === 'ai' && <span style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', fontSize: 30 }}>🎬</span>}
                        {item.kind === 'stock' && <span style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', fontSize: 25 }}>▧</span>}
                      </div>
                    ))}
                  </div>
                  <div style={{ padding: 10 }}>
                    <strong style={{ display: 'block', fontSize: 14 }}>{item.title}</strong>
                    <small className="muted">{item.subtitle}</small>
                    <small style={{ display: 'block', marginTop: 5, color: item.available ? '#15803d' : '#b45309' }}>
                      {item.available ? (selected ? '✓ Seleccionado' : 'Disponible') : 'No implementado todavía'}
                    </small>
                  </div>
                </button>;
              })}
            </div>
            <p className="muted">La selección de formato se conserva por separado de los ajustes de guion. La personalización libre del estilo visual se habilitará cuando tenga un campo propio y no pueda sobrescribir el formato elegido.</p>
            <Field label="Proporción de pantalla">
              <select value={form.aspect} onChange={(e) => update('aspect', e.target.value)}>
                {(meta?.aspects ?? ['9:16','16:9','1:1']).map((a) => <option key={a} value={a}>{a}{a === '9:16' ? ' · vertical recomendado' : ''}</option>)}
              </select>
            </Field>


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
            <p className="muted">El estilo orienta la búsqueda de imágenes de archivo y las consultas visuales de cada escena. No convierte una imagen en otra ni genera imágenes IA; los clips IA, avatares y personajes 3D todavía no están implementados.</p>
          </>}

          {step === 4 && <>
            <h3>Subtítulos y movimiento</h3>
            <p className="muted">Elegí cómo se muestran los textos y cómo se mueve cada escena. Podés ver una muestra antes de seleccionar.</p>
            <Field label="Estilo de subtítulos">
              <CaptionStylePicker
                options={meta?.caption_styles ?? []}
                value={form.caption_style}
                onChange={(value) => update('caption_style', value)}
              />
            </Field>
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
<h3>Publicación automática en YouTube Shorts</h3>
            <p className="muted">La publicación automática queda activada por defecto. Cada Short se renderiza, se valida como vertical de hasta 3 minutos y se sube a tu canal cuando termina. Para que funcione, la conexión OAuth de YouTube debe estar verificada en Ajustes.</p>
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
            <Field label="Destino de cada Short">
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
            <label className="check-row">
              <input type="checkbox" checked={form.auto_publish} onChange={(e) => update('auto_publish', e.target.checked)} />
              Publicar automáticamente en YouTube al terminar el render
            </label>
            {form.destination === 'youtube' && !youtubeReady && <p className="muted">YouTube todavía no está listo. Conectalo en <a href="#/ajustes">Ajustes → YouTube</a>. Hasta entonces, no se puede publicar.</p>}
            {form.destination === 'youtube' && destinationInfo && <p className="muted">{destinationInfo.note}{destinationInfo.missing_env.length ? ' Faltan: ' + destinationInfo.missing_env.join(', ') + '.' : ''}</p>}

          </>}

          {step === 6 && <>
<h3>Duración y calendario automático</h3>
            <Field label="Duración objetivo">
              <select value={form.duration_target_sec} onChange={(e) => update('duration_target_sec', Number(e.target.value))}>
                {[15,20,30,45,60,90,120,180].map((x) => <option key={x} value={x}>{x} segundos</option>)}
              </select>
            </Field>
            <Field label="Cantidad de Shorts">
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
            <h3>Revisá tu Autopiloto</h3>
            <div className="card" style={{ marginTop: 12 }}>
              <strong>{form.name || 'Nuevo Autopiloto'} · {form.niche || 'Sin nicho'}</strong>
              <p>{form.videos_per_period} Short(s) cada {form.period_days === 1 ? 'día' : form.period_days === 7 ? 'semana' : '30 días'}, a las {form.schedule_time} ({form.timezone}).</p>
              <p>{form.duration_target_sec}s · 9:16 · {form.resolution} · {form.destination === 'youtube' && form.auto_publish ? 'Publicación automática en YouTube Shorts' : 'Guardar en Laburito'}.</p>
              <p>Voz: {voiceOptions.find((v) => v.id === form.voice)?.label || form.voice} · Música: {form.music === 'auto' ? 'Automática' : form.music === 'ninguna' ? 'Sin música' : form.music}</p>
              <p>Visual: {VISUAL_OPTIONS.find((v) => v.style === form.visual_style)?.title || form.visual_style} · Subtítulos: {meta?.caption_styles.find((x) => x.id === form.caption_style)?.label || form.caption_style}</p>
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
              : <button className="btn primary" disabled={busy || !form.niche.trim()} onClick={() => void save()}>{busy ? 'Guardando…' : editingId ? 'Guardar cambios' : 'Crear autopiloto'}</button>}
            {editingId && <button className="btn ghost" disabled={busy} onClick={reset}>Cancelar</button>}
          </div>
        </div>
      </Card>

      <Card title="Flujo de producción de cada Short" sub="Orden real del trabajo: desde la regla programada hasta el registro de la publicación.">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8 }}>
          {PRODUCTION_STAGES.map(([number, title, detail]) => (
            <div key={number} style={{ display: 'flex', gap: 10, padding: 10, border: '1px solid var(--border, #d1d5db)', borderRadius: 10 }}>
              <span style={{ flex: '0 0 26px', height: 26, display: 'grid', placeItems: 'center', borderRadius: 99, background: 'var(--surface, #e5e7eb)', fontWeight: 800 }}>{number}</span>
              <div><strong style={{ fontSize: 13 }}>{title}</strong><small className="muted" style={{ display: 'block', marginTop: 3 }}>{detail}</small></div>
            </div>
          ))}
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
