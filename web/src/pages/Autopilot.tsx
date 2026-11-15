import { useEffect, useState } from 'react';
import { api, type AutopilotRule, type Channel, type Meta, type TemplateOption } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';

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
  destination: 'entrega',
  privacy: 'unlisted',
  auto_publish: false,
  enabled: true,
};

export default function Autopilot() {
  const [data, setData] = useState<Options | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [form, setForm] = useState(INITIAL);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');

  async function load() {
    try {
      const [result, m] = await Promise.all([
        api.get<Options>('/api/autopilot'),
        api.get<Meta>('/api/meta'),
      ]);
      setData(result);
      setMeta(m);
      if (result.templates.length && !result.templates.some((t) => t.id === form.template)) {
        setForm((old) => ({ ...old, template: result.templates[0].id }));
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => { void load(); }, 12000);
    return () => window.clearInterval(interval);
  }, []);

  async function create() {
    setBusy(true); setError(''); setOk('');
    try {
      const payload = {
        ...form,
        channel_id: form.channel_id ? Number(form.channel_id) : null,
        duration_target_sec: Number(form.duration_target_sec),
        cadence_hours: Number(form.cadence_hours),
        videos_per_period: Number(form.videos_per_period),
        period_days: Number(form.period_days),
        schedule_time: form.schedule_time,
        timezone: form.timezone,
        auto_publish: form.auto_publish,
        enabled: form.enabled,
      };
      if (editingId) {
        await api.patch('/api/autopilot/' + editingId, payload);
        setOk('Configuración del Autopiloto actualizada.');
      } else {
        await api.post('/api/autopilot', payload);
        setOk('Autopiloto creado. La producción quedó programada según la cantidad, frecuencia y horario elegidos.');
      }
      setForm(INITIAL);
      setEditingId(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  }

  async function run(id: number) {
    setBusy(true); setError(''); setOk('');
    try {
      const result = await api.post<{ project_id: number; publish_warning?: string | null }>(`/api/autopilot/${id}/run`);
      const started = `Producción iniciada. Proyecto #${result.project_id} agregado a la cola.`;
      setOk(result.publish_warning ? `${started} Atención: ${result.publish_warning}` : started);
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
      voice: rule.voice,
      aspect: rule.aspect,
      caption_style: rule.caption_style,
      transition_default: rule.transition_default,
      resolution: rule.resolution,
      fps: rule.fps,
      music: rule.music,
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
    setError('');
    setOk('Editando «' + (rule.name || rule.niche) + '».');
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(INITIAL);
    setOk('');
  }

  async function toggle(rule: AutopilotRule) {
    setBusy(true); setError('');
    try {
      await api.patch(`/api/autopilot/${rule.id}`, { enabled: !rule.enabled });
      if (editingId === rule.id) setForm((old) => ({ ...old, enabled: !rule.enabled }));
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function remove(id: number) {
    if (!window.confirm('¿Eliminar esta regla de Autopiloto?')) return;
    setBusy(true); setError('');
    try { await api.del(`/api/autopilot/${id}`); if (editingId === id) cancelEdit(); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const templates = (data?.templates ?? meta?.templates ?? []).filter((t) => ["shorts", "listicle", "pov", "quote"].includes(t.id));
  const youtubeReady = data?.destinations?.some((d) => d.id === "youtube" && d.available) ?? false;

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      <Card title="Autopiloto de Shorts" sub="Configurá una vez el canal, el público, la identidad editorial y la producción. Después el piloto descubre temas, crea Shorts verticales y los entrega según tu frecuencia.">
        <h3>1. Canal y estrategia</h3>
        <div className="grid two">
          <Field label="Nombre de la automatización">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Mi canal de Shorts" />
          </Field>
          <Field label="Nicho o temática">
            <input value={form.niche} onChange={(e) => setForm({ ...form, niche: e.target.value })} placeholder="Misterio, ciencia, fútbol, curiosidades, historias, tecnología..." />
          </Field>
          <Field label="Público objetivo"><input value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} placeholder="Ej.: jóvenes de 16 a 30 interesados en misterio" /></Field>
          <Field label="Pilares / subtemas del canal"><input value={form.content_pillars} onChange={(e) => setForm({ ...form, content_pillars: e.target.value })} placeholder="Ej.: casos inexplicables, desapariciones, leyendas urbanas" /></Field>
          <Field label="Temas o enfoques que debe evitar"><input value={form.avoid_topics} onChange={(e) => setForm({ ...form, avoid_topics: e.target.value })} placeholder="Ej.: política partidaria, tragedias recientes" /></Field>
          <Field label="Canal">
            <select value={form.channel_id} onChange={(e) => setForm({ ...form, channel_id: e.target.value })}>
              <option value="">Sin canal asociado</option>
              {(data?.channels ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Formato">
            <select value={form.template} onChange={(e) => {
              const selected = templates.find((t) => t.id === e.target.value);
              setForm({
                ...form,
                template: e.target.value,
                ...(selected ? {
                  aspect: selected.aspect,
                  caption_style: selected.caption_style,
                  duration_target_sec: selected.default_duration,
                } : {}),
              });
            }}>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </Field>
          <Field label="Duración del Short (segundos)">
            <input type="number" min="15" max="90" value={form.duration_target_sec} onChange={(e) => setForm({ ...form, duration_target_sec: Number(e.target.value) })} />
          </Field>
          <Field label="Voz (narración en español)">
            <select value={form.voice} onChange={(e) => setForm({ ...form, voice: e.target.value })}>
              {(meta?.voices ?? []).map((v) => <option key={v.id} value={v.id} disabled={!v.available}>{v.label}{v.available ? '' : ' (no disponible)'}</option>)}
            </select>
          </Field>
          <Field label="Formato de pantalla">
            <select value={form.aspect} onChange={(e) => setForm({ ...form, aspect: e.target.value })}>
              {(meta?.aspects ?? ['9:16', '16:9', '1:1']).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </Field>
          <Field label="Estilo de subtítulos">
            <select value={form.caption_style} onChange={(e) => setForm({ ...form, caption_style: e.target.value })}>
              {(meta?.caption_styles ?? []).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </select>
          </Field>
          <Field label="Transiciones">
            <select value={form.transition_default} onChange={(e) => setForm({ ...form, transition_default: e.target.value })}>
              {(meta?.transitions ?? []).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </select>
          </Field>
          <Field label="Resolución">
            <select value={form.resolution} onChange={(e) => setForm({ ...form, resolution: e.target.value })}>
              {(meta?.resolutions ?? []).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </select>
          </Field>
          <Field label="Fotogramas por segundo">
            <select value={form.fps} onChange={(e) => setForm({ ...form, fps: Number(e.target.value) })}>
              {(meta?.fps_options ?? [25, 30]).map((x) => <option key={x} value={x}>{x} FPS</option>)}
            </select>
          </Field>
          <Field label="Música">
            <select value={form.music} onChange={(e) => setForm({ ...form, music: e.target.value })}>
              <option value="auto">Automática</option>
              {(meta?.music_beds ?? []).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </select>
          </Field>
          <Field label="Volumen de música (0 a 1)">
            <input type="number" min="0" max="1" step="0.01" value={form.music_volume} onChange={(e) => setForm({ ...form, music_volume: Number(e.target.value) })} />
          </Field>
          <Field label="Cantidad de Shorts por período">
            <input type="number" min="1" max="30" value={form.videos_per_period} onChange={(e) => setForm({ ...form, videos_per_period: Math.max(1, Math.min(30, Number(e.target.value))) })} />
          </Field>
          <Field label="Período">
            <select value={form.period_days} onChange={(e) => setForm({ ...form, period_days: Number(e.target.value) })}>
              <option value={1}>Por día</option>
              <option value={7}>Por semana</option>
              <option value={30}>Por mes (30 días)</option>
            </select>
          </Field>
          <Field label="Hora de publicación / producción">
            <input type="time" value={form.schedule_time} onChange={(e) => setForm({ ...form, schedule_time: e.target.value })} />
          </Field>
          <Field label="Zona horaria">
            <select value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })}>
              <option value="America/Argentina/Buenos_Aires">Argentina (Buenos Aires)</option>
              <option value="America/Santiago">Chile</option>
              <option value="America/Montevideo">Uruguay</option>
              <option value="America/Mexico_City">México (CDMX)</option>
              <option value="America/Bogota">Colombia</option>
              <option value="Europe/Madrid">España</option>
              <option value="UTC">UTC</option>
            </select>
          </Field>
          <Field label="Destino">
            <select value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })}>
              <option value="entrega">Guardar para revisar</option>
              <option value="youtube">YouTube (requiere conexión y credenciales)</option>
            </select>
          </Field>
          <Field label="Privacidad en YouTube">
            <select value={form.privacy} onChange={(e) => setForm({ ...form, privacy: e.target.value })}>
              <option value="private">Privado</option><option value="unlisted">Oculto</option><option value="public">Público</option>
            </select>
          </Field>
        </div>
        <h3>2. Identidad del guion</h3>
        <div className="grid two">
          <Field label="Tono narrativo">
            <select value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })}>
              {['Dinámico y cercano','Misterioso y tenso','Documental y riguroso','Humorístico e irónico','Emocional y reflexivo','Enérgico y provocador'].map(x => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="Tipo de gancho inicial">
            <select value={form.hook_style} onChange={(e) => setForm({ ...form, hook_style: e.target.value })}>
              {['Dato sorprendente','Pregunta intrigante','Afirmación polémica verificable','Situación en medio de la acción','Error o mito que desmontar','Misterio sin resolver'].map(x => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="Cierre / llamada a la acción">
            <select value={form.cta} onChange={(e) => setForm({ ...form, cta: e.target.value })}>
              {['Hacé una pregunta concreta al final','Invitá a comentar una opinión','Invitá a compartir el Short','Invitá a seguir el canal','Cerrá con una reflexión, sin pedir interacción'].map(x => <option key={x}>{x}</option>)}
            </select>
          </Field>
        </div>
        <h3>3. Producción del Short</h3>
        <label className="check-row"><input type="checkbox" checked={form.auto_publish} onChange={(e) => setForm({ ...form, auto_publish: e.target.checked })} /> Publicar automáticamente al terminar (YouTube requiere OAuth; si no, guardar la entrega)</label>
        {form.auto_publish && form.destination === "youtube" && !youtubeReady && <p className="muted">Todavía no hay una cuenta de YouTube conectada. Configurala desde <a href="#/ajustes">Ajustes → Conectar YouTube</a>; mientras tanto, los videos se renderizan pero no se publican.</p>}
        {form.destination === 'youtube' && (
          <p className="muted">
            {data?.destinations.find((d) => d.id === 'youtube')?.note || 'YouTube necesita credenciales OAuth configuradas en el servidor.'}
            {(data?.destinations.find((d) => d.id === 'youtube')?.missing_env.length ?? 0) > 0
              ? ` Faltan: ${data?.destinations.find((d) => d.id === 'youtube')?.missing_env.join(', ')}.`
              : ''}
          </p>
        )}
        <label className="check-row"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Activar al crear</label>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn primary" disabled={busy || !form.niche.trim()} onClick={create}>{busy ? 'Procesando…' : editingId ? 'Guardar cambios' : 'Crear Autopiloto'}</button>
          {editingId && <button className="btn ghost" disabled={busy} onClick={cancelEdit}>Cancelar edición</button>}
          <button className="btn ghost" disabled={busy} onClick={() => void load()}>Actualizar</button>
        </div>
        <p className="muted" style={{ marginTop: 12 }}>Configuración recomendada: vertical 9:16, 1080p, 30 FPS y 20–45 segundos. El guion se adapta al público, tono, gancho, pilares y cierre que definiste. El calendario admite cantidades por día, semana o mes, con hora y zona horaria. El descubrimiento usa fuentes gratuitas; la primera fuente es orientativa y no equivale a una verificación periodística completa. Revisá las fuentes antes de habilitar publicación pública automática.</p>
      </Card>

      <Card title="Tus automatizaciones" sub="Podés ejecutarlas ahora, pausarlas o eliminarlas.">
        {!data ? <Empty>Cargando automatizaciones…</Empty> : data.rules.length === 0 ? <Empty>Todavía no configuraste ningún Autopiloto.</Empty> : (
          <div className="list">
            {data.rules.map((rule) => (
              <div className="list-item" key={rule.id}>
                <div className="grow">
                  <h4>{rule.name || rule.niche}</h4>
                  <div className="meta"><span>{rule.niche}</span><span>·</span><span>{rule.cadence_hours} h</span><span>·</span><Badge tone={rule.enabled ? 'ok' : 'warn'}>{rule.enabled ? 'Activo' : 'Pausado'}</Badge></div>
                  <div className="meta"><span>{rule.channel_name || 'Sin canal'}</span><span>·</span><span>{rule.template}</span><span>·</span><span>{rule.destination === 'youtube' ? 'YouTube' : 'Entrega local'}</span></div>
                  <small>{rule.last_project_title ? `Último video: ${rule.last_project_title} · ${rule.last_project_status || "creado"}` : "Todavía no generó proyectos"}{rule.last_job_status ? ` · Render: ${rule.last_job_status}` : ""}{rule.last_job_message && rule.last_job_status === "error" ? ` — ${rule.last_job_message}` : ""}{rule.last_error ? ` · Último error: ${rule.last_error}` : ""}{rule.last_run_at ? ` · Ejecutado: ${new Date(rule.last_run_at).toLocaleString()}` : ""}{rule.next_run_at ? ` · Próximo: ${new Date(rule.next_run_at).toLocaleString()}` : ""}</small>
                </div>
                <div className="row">
                  <button className="btn small ghost" disabled={busy} onClick={() => edit(rule)}>Editar</button>
                  <button className="btn small primary" disabled={busy} onClick={() => void run(rule.id)}>Ejecutar ahora</button>
                  <button className="btn small ghost" disabled={busy} onClick={() => void toggle(rule)}>{rule.enabled ? 'Pausar' : 'Activar'}</button>
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
