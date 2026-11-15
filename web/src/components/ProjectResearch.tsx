import { useEffect, useState } from 'react';
import { api, type MediaResult, type Source } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';

export default function ProjectResearch({ projectId, topic }: { projectId: number; topic: string }) {
  const [query, setQuery] = useState(topic);
  const [provider, setProvider] = useState('all');
  const [results, setResults] = useState<MediaResult[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [disclaimer, setDisclaimer] = useState('');
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState('');
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');

  async function loadSources() {
    try { setSources(await api.get<Source[]>(`/api/sources?project_id=${projectId}`)); }
    catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { void loadSources(); }, [projectId]);

  async function search() {
    if (!query.trim()) { setError('Escribí qué querés investigar.'); return; }
    setBusy(true); setError(''); setOk('');
    try {
      const data = await api.post<{ results: MediaResult[]; errors: Record<string, string>; disclaimer: string }>('/api/research/search', { query, provider });
      setResults(data.results); setErrors(data.errors); setDisclaimer(data.disclaimer);
      if (!data.results.length) setError('No se encontraron materiales. Probá otra búsqueda o proveedor.');
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function save(item: MediaResult) {
    setSaving(item.url); setError(''); setOk('');
    try {
      await api.post('/api/sources', { project_id: projectId, title: item.title, url: item.page || item.url, author: item.author, license: item.license, kind: 'referencia' });
      setOk('Fuente vinculada a este video.'); await loadSources();
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(''); }
  }

  async function remove(id: number) {
    try { await api.del(`/api/sources/${id}`); await loadSources(); }
    catch (e) { setError((e as Error).message); }
  }

  return (
    <Card title="Investigar este video" sub="Buscá referencias y materiales con licencia; las fuentes quedan vinculadas a este proyecto y se incluyen en su paquete.">
      <Msg error={error} ok={ok} />
      <div className="row">
        <Field label="Tema o material para buscar">
          <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void search(); }} placeholder="Palabras clave del tema" />
        </Field>
        <Field label="Fuente">
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="all">Todos</option><option value="openverse">Openverse</option><option value="wikimedia">Wikimedia Commons</option><option value="archive">Internet Archive</option>
          </select>
        </Field>
      </div>
      <button className="btn" onClick={() => void search()} disabled={busy}>{busy ? 'Buscando…' : 'Buscar referencias y material'}</button>
      {disclaimer && <small className="muted">{disclaimer}</small>}
      {Object.keys(errors).length > 0 && <small className="muted">Proveedores sin respuesta: {Object.entries(errors).map(([k,v]) => k + ' (' + v + ')').join(' · ')}</small>}
      {results.length > 0 && <div className="thumbs mt-12">
        {results.map((item, i) => <figure key={item.url + i}>
          {item.thumb ? <img src={item.thumb} alt={item.title} loading="lazy" /> : <div className="shot" />}
          <figcaption><strong>{item.title || 'Sin título'}</strong><br/><small>{item.author || 'Autor no indicado'} · {item.license || 'Licencia a verificar'}</small><br/>
            <a href={item.page || item.url} target="_blank" rel="noreferrer">Ver origen</a><br/>
            <button className="btn small ghost" disabled={saving === item.url} onClick={() => void save(item)}>{saving === item.url ? 'Guardando…' : 'Vincular a este video'}</button>
          </figcaption>
        </figure>)}
      </div>}
      <div className="list mt-12">
        <h4>Fuentes guardadas en este video ({sources.length})</h4>
        {sources.length ? sources.map((source) => <div className="list-item" key={source.id}>
          <div className="grow"><strong>{source.title || 'Fuente sin título'}</strong><div className="meta"><span>{source.author || 'Autor no indicado'}</span><Badge>{source.license || 'Licencia a verificar'}</Badge>{source.url && <a href={source.url} target="_blank" rel="noreferrer">Abrir</a>}</div></div>
          <button className="btn small danger" onClick={() => void remove(source.id)}>Quitar</button>
        </div>) : <Empty>Todavía no vinculaste fuentes a este video.</Empty>}
      </div>
      <p className="muted">Esto organiza fuentes y recursos; no verifica automáticamente afirmaciones históricas ni sustituye la revisión del guion.</p>
    </Card>
  );
}
