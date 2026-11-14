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
    template: 'shorts',
    channel_id: '' as string,
    duration_target_sec: 30,
    voice: 'es',
    speed: 150,
    pitch: 45,
    aspect: '9:16',
    caption_style: 'short_pop',
    transition_default: 'fundido',
    resolution: '1080p',
    fps: 25,
    music: 'auto',
  });

  const templates = meta?.templates ?? [];
  const activeTemplate = templates.find((t) => t.id === form.template) ?? null;

  function applyTemplate(id: string) {
    const tpl = templates.find((t) => t.id === id);
    if (!tpl) {
      setForm({ ...form, template: id });
      return;
    }
    setForm({
      ...form,
      template: tpl.id,
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

      <Card title="Nuevo proyecto" sub="Elegí plantilla, formato, resolución, voz, subtítulos, transición y música. Todo se renderiza local con FFmpeg.">
        <div className="row">
          <Field label="Título">
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="El último tranvía" />
          </Field>
          <Field label="Tema / pregunta">
            <input value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} placeholder="Qué pasó con el transporte eléctrico" />
          </Field>
        </div>
        <div className="row">
          <Field label="Plantilla" hint={activeTemplate?.description}>
            <select value={form.template} onChange={(e) => applyTemplate(e.target.value)}>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Canal">
            <select value={form.channel_id} onChange={(e) => setForm({ ...form, channel_id: e.target.value })}>
              <option value="">Sin canal</option>
              {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Duración objetivo">
            <select value={form.duration_target_sec} onChange={(e) => setForm({ ...form, duration_target_sec: Number(e.target.value) })}>
              {(activeTemplate?.durations ?? [15, 30, 45, 60]).map((d) => (
                <option key={d} value={d}>{d < 60 ? `${d} s` : `${Math.round(d / 60)} min`}</option>
              ))}
              {!(activeTemplate?.durations ?? []).includes(form.duration_target_sec) ? (
                <option value={form.duration_target_sec}>{form.duration_target_sec} s</option>
              ) : null}
            </select>
          </Field>
          <Field label="Aspecto">
            <select value={form.aspect} onChange={(e) => setForm({ ...form, aspect: e.target.value })}>
              {(meta?.aspects ?? ['16:9', '9:16']).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </Field>
          <Field label="Resolución">
            <select value={form.resolution} onChange={(e) => setForm({ ...form, resolution: e.target.value })}>
              {(meta?.resolutions ?? [{ id: '1080p', label: '1080p' }]).map((r) => (
                <option key={r.id} value={r.id}>{r.label}</option>
              ))}
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
        <div className="row">
          <Field label="Estilo de subtítulos">
            <select value={form.caption_style} onChange={(e) => setForm({ ...form, caption_style: e.target.value })}>
              {(meta?.caption_styles ?? [{ id: 'documental', label: 'Documental' }]).map((c) => (
                <option key={c.id} value={c.id}>{c.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Transición por defecto">
            <select value={form.transition_default} onChange={(e) => setForm({ ...form, transition_default: e.target.value })}>
              {(meta?.transitions ?? [{ id: 'fundido', label: 'Fundido' }]).map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Cuadros por segundo">
            <select value={form.fps} onChange={(e) => setForm({ ...form, fps: Number(e.target.value) })}>
              {(meta?.fps_options ?? [25]).map((f) => <option key={f} value={f}>{f} fps</option>)}
            </select>
          </Field>
          <Field label="Música de fondo" hint="Las camas se generan localmente con FFmpeg, sin descargas.">
            <select value={form.music} onChange={(e) => setForm({ ...form, music: e.target.value })}>
              <option value="auto">Automática (biblioteca o cama)</option>
              <option value="ninguna">Sin música</option>
              {(meta?.music_beds ?? []).map((m) => (
                <option key={m.id} value={`bed:${m.id}`}>Cama: {m.label}</option>
              ))}
              {(meta?.music_library ?? []).map((f) => (
                <option key={f} value={f}>Biblioteca: {f}</option>
              ))}
            </select>
          </Field>
        </div>
        {meta && meta.external_templates.length > 0 && (
          <p className="muted" style={{ marginTop: 0 }}>
            Plantillas que dependen de un proveedor externo de IA de vídeo (no incluidas):{' '}
            {meta.external_templates.map((t) => t.label).join(' · ')}.
          </p>
        )}
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
