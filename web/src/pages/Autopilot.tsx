import { useEffect, useState } from 'react';
import { api, type AutopilotRule, type Channel, type Meta, type TemplateOption } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';

type Options = {
  rules: AutopilotRule[];
  cadences: number[];
  channels: Channel[];
  templates: TemplateOption[];
};

const INITIAL = {
  name: '',
  niche: '',
  channel_id: '',
  template: 'shorts',
  duration_target_sec: 60,
  voice: 'es',
  cadence_hours: 24,
  destination: 'entrega',
  privacy: 'unlisted',
  auto_publish: false,
  enabled: true,
};

export default function Autopilot() {
  const [data, setData] = useState<Options | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [form, setForm] = useState(INITIAL);
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

  useEffect(() => { void load(); }, []);

  async function create() {
    setBusy(true); setError(''); setOk('');
    try {
      await api.post('/api/autopilot', {
        ...form,
        channel_id: form.channel_id ? Number(form.channel_id) : null,
        duration_target_sec: Number(form.duration_target_sec),
        cadence_hours: Number(form.cadence_hours),
        auto_publish: form.auto_publish,
        enabled: form.enabled,
      });
      setForm(INITIAL);
      setOk('Autopiloto creado. La primera ejecución queda programada para ahora.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  }

  async function run(id: number) {
    setBusy(true); setError(''); setOk('');
    try {
      const result = await api.post<{ project_id: number }>(`/api/autopilot/${id}/run`);
      setOk(`Producción iniciada. Proyecto #${result.project_id} agregado a la cola.`);
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function toggle(rule: AutopilotRule) {
    setBusy(true); setError('');
    try {
      await api.patch(`/api/autopilot/${rule.id}`, { enabled: !rule.enabled });
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function remove(id: number) {
    if (!window.confirm('¿Eliminar esta regla de Autopiloto?')) return;
    setBusy(true); setError('');
    try { await api.del(`/api/autopilot/${id}`); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const templates = data?.templates ?? meta?.templates ?? [];

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      <Card title="Autopiloto" sub="Configurá el nicho y la frecuencia. Laburito busca temas documentados, evita repetir títulos ya usados y crea proyectos automáticamente.">
        <div className="grid two">
          <Field label="Nombre de la automatización">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Mi canal de historias" />
          </Field>
          <Field label="Nicho o temática">
            <input value={form.niche} onChange={(e) => setForm({ ...form, niche: e.target.value })} placeholder="Historias reales, misterio, ciencia..." />
          </Field>
          <Field label="Canal">
            <select value={form.channel_id} onChange={(e) => setForm({ ...form, channel_id: e.target.value })}>
              <option value="">Sin canal asociado</option>
              {(data?.channels ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Formato">
            <select value={form.template} onChange={(e) => setForm({ ...form, template: e.target.value })}>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </Field>
          <Field label="Duración objetivo (segundos)">
            <input type="number" min="5" max="3600" value={form.duration_target_sec} onChange={(e) => setForm({ ...form, duration_target_sec: Number(e.target.value) })} />
          </Field>
          <Field label="Voz">
            <select value={form.voice} onChange={(e) => setForm({ ...form, voice: e.target.value })}>
              {(meta?.voices ?? []).map((v) => <option key={v.id} value={v.id} disabled={!v.available}>{v.label}{v.available ? '' : ' (no disponible)'}</option>)}
            </select>
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
        <label className="check-row"><input type="checkbox" checked={form.auto_publish} onChange={(e) => setForm({ ...form, auto_publish: e.target.checked })} /> Publicar automáticamente al terminar (solo con YouTube configurado)</label>
        <label className="check-row"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Activar al crear</label>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn primary" disabled={busy || !form.niche.trim()} onClick={create}>{busy ? 'Procesando…' : 'Crear Autopiloto'}</button>
          <button className="btn ghost" disabled={busy} onClick={() => void load()}>Actualizar</button>
        </div>
        <p className="muted" style={{ marginTop: 12 }}>El descubrimiento usa Wikipedia en español sin claves ni pagos. La primera fuente es orientativa, no una verificación periodística completa: revisá las fuentes antes de habilitar publicación pública automática.</p>
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
                  <small>{rule.last_project_title ? `Último proyecto: ${rule.last_project_title}` : 'Todavía no generó proyectos'}{rule.next_run_at ? ` · Próxima ejecución: ${new Date(rule.next_run_at).toLocaleString()}` : ''}</small>
                </div>
                <div className="row">
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
