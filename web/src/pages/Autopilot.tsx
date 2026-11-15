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
  cadence_hours: 24,\n  audience: 'Público general',\n  tone: 'Dinámico y cercano',\n  hook_style: 'Dato sorprendente',\n  cta: 'Hacé una pregunta concreta al final',\n  content_pillars: '',\n  avoid_topics: '',
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
        auto_publish: form.auto_publish,
        enabled: form.enabled,
      };
      if (editingId) {
        await api.patch('/api/autopilot/' + editingId, payload);
        setOk('Configuración del Autopiloto actualizada.');
      } else {
        await api.post('/api/autopilot', payload);
        setOk('Autopiloto creado. La primera ejecución queda programada para ahora.');
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
      duration_target_sec: rule.duration_target_sec ?? 60,
      voice: rule.voice,
      aspect: rule.aspect,
      caption_style: rule.caption_style,
      transition_default: rule.transition_default,
      resolution: rule.resolution,
      fps: rule.fps,
      music: rule.music,
      music_volume: rule.music_volume,
      cadence_hours: rule.cadence_hours,\n      audience: rule.audience || 'Público general',\n      tone: rule.tone || 'Dinámico y cercano',\n      hook_style: rule.hook_style || 'Dato sorprendente',\n      cta: rule.cta || 'Hacé una pregunta concreta al final',\n      content_pillars: rule.content_pillars || '',\n      avoid_topics: rule.avoid_topics || '',
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

  const templates = data?.templates ?? meta?.templates ?? [];
  const youtubeReady = data?.destinations?.some((d) => d.id === "youtube" && d.available) ?? false;

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      <Card title="Autopiloto de Shorts" sub="Configurá una vez el canal, el público, la identidad editorial y la producción. Después el piloto descubre temas, crea Shorts verticales y los entrega según tu frecuencia.">
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
            <input type="number" min="5" max="3600" value={form.duration_target_sec} onChange={(e) => setForm({ ...form, duration_target_sec: Number(e.target.value) })} />
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
          <Field label="Frecuencia">
            <select value={form.cadence_hours} onChange={(e) => setForm({ ...form, cadence_hours: Number(e.target.value) })}>
              {[6, 12, 24, 48, 72, 168].map((h) => <option key={h} value={h}>{h < 24 ? `Cada ${h} horas` : h === 24 ? 'Diariamente' : h === 168 ? 'Semanalmente' : `Cada ${h / 24} días`}</option>)}
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
        <label className="check-row"><input type="checkbox" checked={form.auto_publish} onChange={(e) => setForm({ ...form, auto_publish: e.target.checked })} /> Procesar y entregar automáticamente al terminar (YouTube requiere conexión OAuth)</label>
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
        <p className="muted" style={{ marginTop: 12 }}>Configuración recomendada: vertical 9:16, 1080p, 30 FPS y 20–45 segundos. El guion se adapta al público, tono, gancho, pilares y cierre que definiste. El descubrimiento usa fuentes gratuitas; la primera fuente es orientativa y no equivale a una verificación periodística completa. Revisá las fuentes antes de habilitar publicación pública automática.</p>
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
