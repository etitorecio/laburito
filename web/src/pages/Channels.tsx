import { useEffect, useState } from 'react';
import { api, type Channel } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';

const EMPTY = {
  name: '',
  topic: '',
  language: 'es',
  audience: '',
  tone: 'documental sobrio',
  visual_identity: '',
  formats: 'documental,short',
  cadence: 'semanal',
};

export default function Channels() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');

  async function load() {
    try {
      setChannels(await api.get<Channel[]>('/api/channels'));
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
    if (!form.name.trim()) {
      setError('El canal necesita un nombre.');
      return;
    }
    try {
      await api.post('/api/channels', form);
      setForm(EMPTY);
      setOk('Canal creado. Ya podés asociarle proyectos y entradas de calendario.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(id: number) {
    try {
      await api.del(`/api/channels/${id}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />

      <Card title="Nuevo canal" sub="Identidad, audiencia y cadencia: la base de una serie sostenible.">
        <div className="row">
          <Field label="Nombre">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Archivo Oculto" />
          </Field>
          <Field label="Tema central">
            <input value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} placeholder="Historia urbana y archivos" />
          </Field>
          <Field label="Audiencia">
            <input value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} placeholder="Adultos curiosos 30-55" />
          </Field>
        </div>
        <div className="row">
          <Field label="Tono">
            <input value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })} />
          </Field>
          <Field label="Identidad visual">
            <input value={form.visual_identity} onChange={(e) => setForm({ ...form, visual_identity: e.target.value })} placeholder="Papel envejecido, tipografía serif" />
          </Field>
          <Field label="Formatos">
            <input value={form.formats} onChange={(e) => setForm({ ...form, formats: e.target.value })} placeholder="documental,short" />
          </Field>
          <Field label="Cadencia">
            <select value={form.cadence} onChange={(e) => setForm({ ...form, cadence: e.target.value })}>
              <option value="diaria">Diaria</option>
              <option value="semanal">Semanal</option>
              <option value="quincenal">Quincenal</option>
              <option value="mensual">Mensual</option>
            </select>
          </Field>
        </div>
        <button className="btn primary" onClick={create}>Crear canal</button>
      </Card>

      <Card title="Canales" sub="Cada canal agrupa proyectos, calendario y analítica.">
        {channels.length === 0 ? (
          <Empty>Todavía no hay canales. Creá el primero arriba.</Empty>
        ) : (
          <div className="list">
            {channels.map((c) => (
              <div className="list-item" key={c.id}>
                <div className="grow">
                  <h4>{c.name}</h4>
                  <div className="meta">
                    <span>{c.topic || 'sin tema definido'}</span>
                    <span>·</span>
                    <span>{c.cadence}</span>
                    <span>·</span>
                    <span>{c.projects ?? 0} proyectos</span>
                    {c.next_entry && <Badge tone="info">próximo: {c.next_entry.scheduled_for.slice(0, 10)}</Badge>}
                  </div>
                  <div className="meta" style={{ marginTop: 4 }}>
                    <span>Audiencia: {c.audience || '—'}</span>
                    <span>·</span>
                    <span>Tono: {c.tone || '—'}</span>
                  </div>
                </div>
                <button className="btn small danger" onClick={() => remove(c.id)}>Eliminar</button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
