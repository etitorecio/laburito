import { useEffect, useState } from 'react';
import { api, type MediaResult, type Niche, type Note } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';

export default function Research() {
  const [niches, setNiches] = useState<Niche[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');

  const [nicheForm, setNicheForm] = useState({ name: '', demand: 50, competition: 40, trend: 'creciente', difficulty: 40, copyright_risk: 'bajo', monetization: '', series_potential: 60, notes: '' });
  const [noteForm, setNoteForm] = useState({ niche: '', claim: '', evidence_level: 'indicio', source_url: '', methodology: '' });

  const [query, setQuery] = useState('');
  const [provider, setProvider] = useState('all');
  const [results, setResults] = useState<MediaResult[]>([]);
  const [searchErrors, setSearchErrors] = useState<Record<string, string>>({});
  const [searching, setSearching] = useState(false);
  const [disclaimer, setDisclaimer] = useState('');

  async function load() {
    try {
      const [n, no] = await Promise.all([api.get<Niche[]>('/api/research/niches'), api.get<Note[]>('/api/research/notes')]);
      setNiches(n);
      setNotes(no);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function addNiche() {
    setError('');
    setOk('');
    if (!nicheForm.name.trim()) {
      setError('Ponele un nombre al nicho.');
      return;
    }
    try {
      await api.post('/api/research/niches', nicheForm);
      setNicheForm({ ...nicheForm, name: '', monetization: '', notes: '' });
      setOk('Nicho guardado con sus puntajes.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function addNote() {
    setError('');
    setOk('');
    if (!noteForm.claim.trim()) {
      setError('Escribí la afirmación que querés verificar.');
      return;
    }
    try {
      await api.post('/api/research/notes', noteForm);
      setNoteForm({ niche: noteForm.niche, claim: '', evidence_level: 'indicio', source_url: '', methodology: '' });
      setOk('Nota guardada con nivel de evidencia.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function search() {
    setError('');
    setOk('');
    if (!query.trim()) {
      setError('Escribí qué material buscás.');
      return;
    }
    setSearching(true);
    try {
      const data = await api.post<{ results: MediaResult[]; errors: Record<string, string>; disclaimer: string }>('/api/research/search', { query, provider });
      setResults(data.results);
      setSearchErrors(data.errors);
      setDisclaimer(data.disclaimer);
      if (!data.results.length) setError('Sin resultados. Puede que este entorno no tenga salida a internet: la app genera igual tarjetas visuales locales.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSearching(false);
    }
  }

  async function saveSource(item: MediaResult) {
    try {
      await api.post('/api/sources', {
        title: item.title,
        url: item.page || item.url,
        author: item.author,
        license: item.license,
        kind: 'imagen',
      });
      setOk('Fuente guardada en el registro de atribuciones.');
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function removeNiche(id: number) {
    try {
      await api.del(`/api/research/niches/${id}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />

      <Card title="Investigación de nichos" sub="Puntajes que cargás vos a partir de tu propia observación del mercado.">
        <div className="row">
          <Field label="Nicho">
            <input value={nicheForm.name} onChange={(e) => setNicheForm({ ...nicheForm, name: e.target.value })} placeholder="Historia oculta de ciudades" />
          </Field>
          <Field label="Demanda (0-100)">
            <input type="number" min={0} max={100} value={nicheForm.demand} onChange={(e) => setNicheForm({ ...nicheForm, demand: Number(e.target.value) })} />
          </Field>
          <Field label="Competencia (0-100)">
            <input type="number" min={0} max={100} value={nicheForm.competition} onChange={(e) => setNicheForm({ ...nicheForm, competition: Number(e.target.value) })} />
          </Field>
          <Field label="Tendencia">
            <select value={nicheForm.trend} onChange={(e) => setNicheForm({ ...nicheForm, trend: e.target.value })}>
              <option value="creciente">Creciente</option>
              <option value="estable">Estable</option>
              <option value="decreciente">Decreciente</option>
            </select>
          </Field>
        </div>
        <div className="row">
          <Field label="Dificultad de producción">
            <input type="number" min={0} max={100} value={nicheForm.difficulty} onChange={(e) => setNicheForm({ ...nicheForm, difficulty: Number(e.target.value) })} />
          </Field>
          <Field label="Riesgo de copyright">
            <select value={nicheForm.copyright_risk} onChange={(e) => setNicheForm({ ...nicheForm, copyright_risk: e.target.value })}>
              <option value="bajo">Bajo</option>
              <option value="medio">Medio</option>
              <option value="alto">Alto</option>
            </select>
          </Field>
          <Field label="Potencial de serie">
            <input type="number" min={0} max={100} value={nicheForm.series_potential} onChange={(e) => setNicheForm({ ...nicheForm, series_potential: Number(e.target.value) })} />
          </Field>
          <Field label="Monetización">
            <input value={nicheForm.monetization} onChange={(e) => setNicheForm({ ...nicheForm, monetization: e.target.value })} placeholder="AdSense, afiliados…" />
          </Field>
        </div>
        <button className="btn primary" onClick={addNiche}>Guardar nicho</button>

        <div className="table-wrap mt-12">
          {niches.length === 0 ? (
            <Empty>Sin nichos cargados. Empezá por uno con demanda alta y competencia baja.</Empty>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Nicho</th>
                  <th>Oportunidad</th>
                  <th>Demanda</th>
                  <th>Competencia</th>
                  <th>Tendencia</th>
                  <th>Copyright</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {niches.map((n) => (
                  <tr key={n.id}>
                    <td>{n.name}</td>
                    <td><Badge tone={(n.opportunity ?? 0) >= 55 ? 'ok' : (n.opportunity ?? 0) >= 40 ? 'warn' : 'bad'}>{n.opportunity}</Badge></td>
                    <td>{n.demand}</td>
                    <td>{n.competition}</td>
                    <td>{n.trend}</td>
                    <td>{n.copyright_risk}</td>
                    <td><button className="btn small danger" onClick={() => removeNiche(n.id)}>Quitar</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>

      <div className="grid two">
        <Card title="Notas con nivel de evidencia" sub="Cada afirmación del guion debe poder rastrearse hasta una fuente.">
          <Field label="Nicho">
            <input list="niche-list" value={noteForm.niche} onChange={(e) => setNoteForm({ ...noteForm, niche: e.target.value })} placeholder="Nicho al que pertenece" />
          </Field>
          <datalist id="niche-list">
            {niches.map((n) => <option key={n.id} value={n.name} />)}
          </datalist>
          <Field label="Afirmación">
            <textarea value={noteForm.claim} onChange={(e) => setNoteForm({ ...noteForm, claim: e.target.value })} placeholder="Ej: la ciudad tuvo tranvía hasta 1962" />
          </Field>
          <div className="row">
            <Field label="Evidencia">
              <select value={noteForm.evidence_level} onChange={(e) => setNoteForm({ ...noteForm, evidence_level: e.target.value })}>
                <option value="hecho">Hecho documentado</option>
                <option value="indicio">Indicio</option>
                <option value="estimacion">Estimación</option>
              </select>
            </Field>
            <Field label="Fuente (URL)">
              <input value={noteForm.source_url} onChange={(e) => setNoteForm({ ...noteForm, source_url: e.target.value })} placeholder="https://…" />
            </Field>
          </div>
          <Field label="Metodología">
            <input value={noteForm.methodology} onChange={(e) => setNoteForm({ ...noteForm, methodology: e.target.value })} placeholder="Archivo municipal, entrevista, censo…" />
          </Field>
          <button className="btn primary" onClick={addNote}>Agregar nota</button>

          <div className="list mt-12">
            {notes.length === 0 ? (
              <Empty>Sin notas todavía.</Empty>
            ) : (
              notes.slice(0, 12).map((n) => (
                <div className="list-item" key={n.id}>
                  <div className="grow">
                    <h4>{n.claim}</h4>
                    <div className="meta">
                      <Badge tone={n.evidence_level === 'hecho' ? 'ok' : n.evidence_level === 'indicio' ? 'warn' : ''}>{n.evidence_level}</Badge>
                      {n.niche && <span>{n.niche}</span>}
                      {n.source_url && <a href={n.source_url} target="_blank" rel="noreferrer">fuente</a>}
                    </div>
                  </div>
                  <button className="btn small danger" onClick={async () => { await api.del(`/api/research/notes/${n.id}`); await load(); }}>Quitar</button>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card title="Material con licencia" sub="Buscadores libres y sin clave. Verificá siempre la licencia en el origen.">
          <div className="row">
            <Field label="Búsqueda">
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="tranvía buenos aires 1930" />
            </Field>
            <Field label="Proveedor">
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="all">Todos</option>
                <option value="openverse">Openverse</option>
                <option value="wikimedia">Wikimedia Commons</option>
                <option value="archive">Internet Archive</option>
              </select>
            </Field>
          </div>
          <button className="btn" onClick={search} disabled={searching}>{searching ? 'Buscando…' : 'Buscar material'}</button>

          {Object.keys(searchErrors).length > 0 && (
            <div className="msg mt-12">
              Sin respuesta de: {Object.entries(searchErrors).map(([k, v]) => `${k} (${v.slice(0, 60)})`).join(' · ')}
            </div>
          )}
          {disclaimer && <small style={{ display: 'block', marginTop: 8 }}>{disclaimer}</small>}

          <div className="thumbs mt-12">
            {results.map((r, i) => (
              <figure key={`${r.url}-${i}`}>
                {r.thumb ? <img src={r.thumb} alt={r.title} loading="lazy" /> : <div className="shot" />}
                <figcaption>
                  {r.title || 'Sin título'}
                  <br />
                  <span className="muted">{r.license || 'licencia a verificar'}</span>
                  <br />
                  <button className="btn small ghost" onClick={() => saveSource(r)}>Guardar fuente</button>
                  <a className="btn small ghost" href={r.page || r.url} target="_blank" rel="noreferrer">Ver</a>
                </figcaption>
              </figure>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
