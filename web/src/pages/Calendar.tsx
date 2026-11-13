import { useEffect, useState } from 'react';
import { api, type CalendarEntry, type Channel, type Project } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';
import type { Route } from '../routes';

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

  async function load() {
    try {
      const [e, c, p] = await Promise.all([
        api.get<CalendarEntry[]>('/api/calendar'),
        api.get<Channel[]>('/api/channels'),
        api.get<Project[]>('/api/projects'),
      ]);
      setEntries(e);
      setChannels(c);
      setProjects(p);
      if (!form.channel_id && c.length) setForm((f) => ({ ...f, channel_id: String(c[0].id) }));
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
