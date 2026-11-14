import { useEffect, useState } from 'react';
import { api, type AutopilotRule, type CalendarEntry, type Channel, type Project } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';
import type { Route } from '../routes';

type ApMeta = {
  niches: { id: number; name: string }[];
  templates: { id: string; label: string }[];
  resolutions: { id: string; label: string }[];
  caption_styles: { id: string; label: string }[];
  transitions: { id: string; label: string }[];
  fps_options: number[];
  cadences: number[];
};

export default function Calendar({ go }: { go: (route: Route, id?: number) => void }) {
  const [entries, setEntries] = useState<CalendarEntry[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [form, setForm] = useState({
    channel_id: '',
    project_id: '',
    scheduled_for: new Date(Date.now() + 86400000).toISOString().slice(0, 16),
    format: 'documental',
    title: '',
  });

  const [rules, setRules] = useState<AutopilotRule[]>([]);
  const [apMeta, setApMeta] = useState<ApMeta | null>(null);
  const [ruleForm, setRuleForm] = useState({
    name: '',
    niche: '',
    channel_id: '',
    template: 'shorts',
    cadence_hours: 24,
    caption_style: 'short_pop',
    transition_default: 'fundido',
    resolution: '1080p',
    fps: 25,
    auto_publish: false,
    destination: 'entrega',
  });

  async function load() {
    try {
      const [e, c, p, ap] = await Promise.all([
        api.get<CalendarEntry[]>('/api/calendar'),
        api.get<Channel[]>('/api/channels'),
        api.get<Project[]>('/api/projects'),
        api.get<{ rules: AutopilotRule[] } & ApMeta>('/api/autopilot'),
      ]);
      setEntries(e);
      setChannels(c);
      setProjects(p);
      setRules(ap.rules || []);
      setApMeta(ap);
      if (!form.channel_id && c.length) setForm((f) => ({ ...f, channel_id: String(c[0].id) }));
      if (!ruleForm.channel_id && c.length) setRuleForm((f) => ({ ...f, channel_id: String(c[0].id) }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setOk('');
    if (!form.channel_id) return setError('Creá un canal antes de programar publicaciones.');
    try {
      await api.post('/api/calendar', {
        channel_id: Number(form.channel_id),
        project_id: form.project_id ? Number(form.project_id) : null,
        scheduled_for: new Date(form.scheduled_for).toISOString(),
        format: form.format,
        title: form.title || 'Publicación sin título',
      });
      setOk('Publicación programada.');
      setForm((f) => ({ ...f, title: '' }));
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const grouped = entries.reduce<Record<string, CalendarEntry[]>>((acc, entry) => {
    const day = entry.scheduled_for.slice(0, 10);
    (acc[day] = acc[day] || []).push(entry);
    return acc;
  }, {});

  async function createRule(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setOk('');
    try {
      await api.post('/api/autopilot', {
        name: ruleForm.name || ruleForm.niche || 'Piloto automático',
        niche: ruleForm.niche,
        channel_id: ruleForm.channel_id ? Number(ruleForm.channel_id) : null,
        template: ruleForm.template,
        cadence_hours: Number(ruleForm.cadence_hours),
        caption_style: ruleForm.caption_style,
        transition_default: ruleForm.transition_default,
        resolution: ruleForm.resolution,
        fps: Number(ruleForm.fps),
        auto_publish: ruleForm.auto_publish,
        destination: ruleForm.destination,
        enabled: true,
      });
      setOk('Regla de piloto automático creada: la próxima ejecución está agendada.');
      setRuleForm((f) => ({ ...f, name: '', niche: '' }));
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function runRule(id: number) {
    setError('');
    setOk('');
    try {
      const r = await api.post<{ project_id: number; job_id: number }>(`/api/autopilot/${id}/run`, {});
      setOk(`Regla ejecutada: proyecto ${r.project_id} creado y render ${r.job_id} en cola.`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />

      <Card title="Programar publicación" sub="Calendario editorial por canal: documental semanal y Shorts entre medio.">
        <form onSubmit={add}>
          <div className="row">
            <Field label="Canal">
              <select value={form.channel_id} onChange={(e) => setForm({ ...form, channel_id: e.target.value })}>
                <option value="">Elegí un canal</option>
                {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Proyecto (opcional)">
              <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                <option value="">Sin proyecto asociado</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
              </select>
            </Field>
            <Field label="Formato">
              <select value={form.format} onChange={(e) => setForm({ ...form, format: e.target.value })}>
                <option value="documental">Documental</option>
                <option value="short">Short</option>
              </select>
            </Field>
          </div>
          <div className="row">
            <Field label="Fecha y hora">
              <input type="datetime-local" value={form.scheduled_for} onChange={(e) => setForm({ ...form, scheduled_for: e.target.value })} />
            </Field>
            <Field label="Título">
              <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Título de la publicación" />
            </Field>
            <div className="field" style={{ justifyContent: 'flex-end' }}>
              <button className="btn primary" type="submit">Programar</button>
            </div>
          </div>
        </form>
      </Card>

      <Card
        title="Piloto automático"
        sub="Cada regla crea el proyecto con guion escrito, lo renderiza y (opcional) lo sube sola. Sin claves ni servicios pagos."
      >
        <form onSubmit={createRule}>
          <div className="row">
            <Field label="Nombre">
              <input value={ruleForm.name} onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })} placeholder="Serie de misterio" />
            </Field>
            <Field label="Nicho / tema" hint="Se usa como tema del guion y para tomar notas de investigación.">
              <input
                value={ruleForm.niche}
                onChange={(e) => setRuleForm({ ...ruleForm, niche: e.target.value })}
                list="autopilot-niches"
                placeholder="Historia oculta"
              />
              <datalist id="autopilot-niches">
                {(apMeta?.niches ?? []).map((n) => <option key={n.id} value={n.name} />)}
              </datalist>
            </Field>
            <Field label="Canal">
              <select value={ruleForm.channel_id} onChange={(e) => setRuleForm({ ...ruleForm, channel_id: e.target.value })}>
                <option value="">Sin canal</option>
                {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Plantilla">
              <select value={ruleForm.template} onChange={(e) => setRuleForm({ ...ruleForm, template: e.target.value })}>
                {(apMeta?.templates ?? []).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
            </Field>
          </div>
          <div className="row">
            <Field label="Cada">
              <select value={ruleForm.cadence_hours} onChange={(e) => setRuleForm({ ...ruleForm, cadence_hours: Number(e.target.value) })}>
                {(apMeta?.cadences ?? [24]).map((h) => (
                  <option key={h} value={h}>{h < 24 ? `${h} h` : h === 168 ? '7 días' : `${h / 24} día(s)`}</option>
                ))}
              </select>
            </Field>
            <Field label="Resolución">
              <select value={ruleForm.resolution} onChange={(e) => setRuleForm({ ...ruleForm, resolution: e.target.value })}>
                {(apMeta?.resolutions ?? []).map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </Field>
            <Field label="Subtítulos">
              <select value={ruleForm.caption_style} onChange={(e) => setRuleForm({ ...ruleForm, caption_style: e.target.value })}>
                {(apMeta?.caption_styles ?? []).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
            </Field>
            <Field label="FPS">
              <select value={ruleForm.fps} onChange={(e) => setRuleForm({ ...ruleForm, fps: Number(e.target.value) })}>
                {(apMeta?.fps_options ?? [25]).map((f) => <option key={f} value={f}>{f} fps</option>)}
              </select>
            </Field>
          </div>
          <div className="row">
            <Field label="Auto-subida" hint="Se publica al terminar el render.">
              <select
                value={ruleForm.auto_publish ? ruleForm.destination : 'off'}
                onChange={(e) => {
                  const v = e.target.value;
                  setRuleForm({
                    ...ruleForm,
                    auto_publish: v !== 'off',
                    destination: v === 'off' ? ruleForm.destination : v,
                  });
                }}
              >
                <option value="off">No publicar sola</option>
                <option value="entrega">Sí, a la carpeta de entregas</option>
                <option value="youtube">Sí, a YouTube</option>
              </select>
            </Field>
            <div className="field" style={{ justifyContent: 'flex-end' }}>
              <button className="btn primary" type="submit">Crear regla</button>
            </div>
          </div>
        </form>

        {rules.length === 0 ? (
          <Empty>Sin reglas todavía. Creá una y el worker la ejecuta según la cadencia.</Empty>
        ) : (
          <div className="list">
            {rules.map((r) => (
              <div className="list-item" key={r.id}>
                <div className="grow">
                  <h4>{r.name || r.niche}</h4>
                  <div className="meta">
                    <Badge tone={r.enabled ? 'ok' : 'warn'}>{r.enabled ? 'activa' : 'pausada'}</Badge>
                    <span>{r.niche || 'sin nicho'}</span>
                    <span>{r.template}</span>
                    <span>{r.resolution} · {r.fps} fps</span>
                    <span>cada {r.cadence_hours} h</span>
                    {r.auto_publish && <Badge tone="info">auto-subida: {r.destination}</Badge>}
                    {r.next_run_at && <span>próxima: {new Date(r.next_run_at).toLocaleString('es')}</span>}
                  </div>
                </div>
                <div className="row gap-8">
                  {r.last_project_id && (
                    <button className="btn small ghost" onClick={() => go('editor', r.last_project_id!)}>Último proyecto</button>
                  )}
                  <button className="btn small" onClick={() => runRule(r.id)}>Ejecutar ahora</button>
                  <button
                    className="btn small ghost"
                    onClick={async () => { await api.patch(`/api/autopilot/${r.id}`, { enabled: !r.enabled }); await load(); }}
                  >
                    {r.enabled ? 'Pausar' : 'Activar'}
                  </button>
                  <button className="btn small danger" onClick={async () => { await api.del(`/api/autopilot/${r.id}`); await load(); }}>Quitar</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Calendario" sub="Ordenado por día; cada entrada se puede abrir en el editor.">
        {entries.length === 0 ? (
          <Empty>Sin publicaciones programadas.</Empty>
        ) : (
          <div className="stack">
            {Object.entries(grouped).map(([day, list]) => (
              <div key={day}>
                <h4 style={{ margin: '10px 0 6px' }}>{new Date(`${day}T12:00:00`).toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' })}</h4>
                <div className="list">
                  {list.map((entry) => (
                    <div className="list-item" key={entry.id}>
                      <div className="grow">
                        <h4>{entry.title}</h4>
                        <div className="meta">
                          <Badge tone={entry.format === 'short' ? 'info' : 'ok'}>{entry.format}</Badge>
                          <span>{entry.channel_name}</span>
                          <span>{new Date(entry.scheduled_for).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}</span>
                          <Badge>{entry.status}</Badge>
                          {entry.project_title && <span>· {entry.project_title}</span>}
                        </div>
                      </div>
                      <div className="row gap-8">
                        {entry.project_id && <button className="btn small ghost" onClick={() => go('editor', entry.project_id!)}>Abrir</button>}
                        <button className="btn small danger" onClick={async () => { await api.del(`/api/calendar/${entry.id}`); await load(); }}>Quitar</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
