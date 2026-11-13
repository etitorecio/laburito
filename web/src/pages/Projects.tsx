import { useEffect, useState } from 'react';
import { api, type Channel, type Meta, type Project } from '../api';
import { Badge, Card, Empty, Field, Msg, Progress, statusTone } from '../ui';
import type { Route } from '../routes';

export default function Projects({ go }: { go: (route: Route, id?: number) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [busy, setBusy] = useState(false);

  const [form, setForm] = useState({
    title: '',
    topic: '',
    kind: 'documentary',
    channel_id: '' as string,
    duration_target_sec: 600,
    voice: 'es',
    speed: 150,
    pitch: 45,
    aspect: '16:9',
  });

  async function load() {
    try {
      const [p, c, m] = await Promise.all([
        api.get<Project[]>('/api/projects'),
        api.get<Channel[]>('/api/channels'),
        api.get<Meta>('/api/meta'),
      ]);
      setProjects(p);
      setChannels(c);
      setMeta(m);
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
    if (!form.title.trim()) {
      setError('El proyecto necesita un título.');
      return;
    }
    setBusy(true);
    try {
      const project = await api.post<Project>('/api/projects', {
        ...form,
        channel_id: form.channel_id ? Number(form.channel_id) : null,
        topic: form.topic || form.title,
      });
      setForm({ ...form, title: '', topic: '' });
      setOk('Proyecto creado. Generá el guion para crear las escenas.');
      await load();
      go('editor', project.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function render(project: Project) {
    setError('');
    setOk('');
    try {
      const res = await api.post<{ job_id: number }>(`/api/projects/${project.id}/render`);
      setOk(`Render en cola (tarea #${res.job_id}). Seguí el avance en la sección Cola.`);
      await load();
    } catch (e) {
      setError((e as Error).message);
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

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />

      <Card title="Nuevo proyecto" sub="Documental horizontal (8-20 min) o Short vertical, con voz local.">
        <div className="row">
          <Field label="Título">
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="El último tranvía" />
          </Field>
          <Field label="Tema / pregunta">
            <input value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} placeholder="Qué pasó con el transporte eléctrico" />
          </Field>
        </div>
        <div className="row">
          <Field label="Formato">
            <select
              value={form.kind}
              onChange={(e) => {
                const kind = e.target.value;
                setForm({
                  ...form,
                  kind,
                  aspect: kind === 'short' ? '9:16' : '16:9',
                  duration_target_sec: kind === 'short' ? 45 : 600,
                });
              }}
            >
              {(meta?.kinds ?? [{ id: 'documentary', label: 'Documental', aspect: '16:9' }]).map((k) => (
                <option key={k.id} value={k.id}>{k.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Canal">
            <select value={form.channel_id} onChange={(e) => setForm({ ...form, channel_id: e.target.value })}>
              <option value="">Sin canal</option>
              {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Duración objetivo (s)">
            <input type="number" min={15} max={1800} value={form.duration_target_sec} onChange={(e) => setForm({ ...form, duration_target_sec: Number(e.target.value) })} />
          </Field>
          <Field label="Relación de aspecto">
            <select value={form.aspect} onChange={(e) => setForm({ ...form, aspect: e.target.value })}>
              {(meta?.aspects ?? ['16:9', '9:16']).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </Field>
        </div>
        <div className="row">
          <Field label="Voz">
            <select value={form.voice} onChange={(e) => setForm({ ...form, voice: e.target.value })}>
              {(meta?.voices ?? [{ id: 'es', label: 'Español' }]).map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          </Field>
          <Field label="Velocidad (palabras/min)">
            <input type="number" min={80} max={300} value={form.speed} onChange={(e) => setForm({ ...form, speed: Number(e.target.value) })} />
          </Field>
          <Field label="Tono de voz">
            <input type="number" min={0} max={99} value={form.pitch} onChange={(e) => setForm({ ...form, pitch: Number(e.target.value) })} />
          </Field>
        </div>
        <button className="btn primary" onClick={create} disabled={busy}>{busy ? 'Creando…' : 'Crear proyecto'}</button>
      </Card>

      <Card title="Proyectos" sub="Estado real de cada producción.">
        {projects.length === 0 ? (
          <Empty>Sin proyectos. Creá el primero y generá el guion.</Empty>
        ) : (
          <div className="list">
            {projects.map((p) => (
              <div className="list-item" key={p.id}>
                <div className="grow">
                  <h4>{p.title}</h4>
                  <div className="meta">
                    <Badge tone={statusTone(p.status)}>{p.status}</Badge>
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
                  <button className="btn small" onClick={() => go('editor', p.id)}>Abrir</button>
                  <button className="btn small ghost" onClick={() => render(p)}>Renderizar</button>
                  <a className="btn small ghost" href={`/api/projects/${p.id}/download`}>ZIP</a>
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
