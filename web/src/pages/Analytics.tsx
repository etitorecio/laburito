import { useEffect, useRef, useState } from 'react';
import { api, type AnalyticsRow, type AnalyticsSummary } from '../api';
import { Badge, Card, Empty, Msg, Stat } from '../ui';

export default function Analytics() {
  const [rows, setRows] = useState<AnalyticsRow[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const [r, s] = await Promise.all([
        api.get<AnalyticsRow[]>('/api/analytics'),
        api.get<AnalyticsSummary>('/api/analytics/summary'),
      ]);
      setRows(r);
      setSummary(s);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError('');
    setOk('');
    try {
      const res = await api.upload<{ imported: number; skipped: number; errors: string[] }>('/api/analytics/import', file);
      setOk(`Importadas ${res.imported} filas reales${res.skipped ? `, ${res.skipped} descartadas` : ''}.`);
      if (res.errors?.length) setError(res.errors.slice(0, 5).join(' · '));
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  const s = summary?.summary;

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />

      <Card
        title="Analítica"
        sub="Importá el CSV real de YouTube Studio. La app no inventa métricas: si no hay datos, lo dice."
        actions={
          <>
            <input ref={fileRef} type="file" accept=".csv,text/csv" onChange={upload} style={{ display: 'none' }} />
            <button className="btn small primary" onClick={() => fileRef.current?.click()}>Importar CSV</button>
          </>
        }
      >
        <p className="muted" style={{ marginTop: 0 }}>
          Columnas reconocidas: título, formato, impresiones, vistas, CTR, retención, duración media, interacciones,
          suscriptores y fecha. Se aceptan los encabezados en español o inglés.
        </p>

        {!s || s.views === 0 ? (
          <Empty>Sin datos importados todavía. El resumen aparecerá con métricas reales del canal.</Empty>
        ) : (
          <>
            <div className="grid stats">
              <Stat value={s.views.toLocaleString('es')} label="Vistas" />
              <Stat value={`${s.ctr}%`} label="CTR medio" />
              <Stat value={`${s.retention}%`} label="Retención media" />
              <Stat value={s.subscribers.toLocaleString('es')} label="Suscriptores" />
            </div>

            <div className="table-wrap mt-12">
              <table>
                <thead>
                  <tr><th>Formato</th><th>Vídeos</th><th>Vistas</th><th>Retención</th></tr>
                </thead>
                <tbody>
                  {s.formats.map((f) => (
                    <tr key={f.format}>
                      <td>{f.format}</td>
                      <td>{f.videos}</td>
                      <td>{f.views.toLocaleString('es')}</td>
                      <td>{f.retention}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {s.best && (
              <p className="muted">
                Mejor rendimiento: <strong>{s.best.title}</strong> — {s.best.views.toLocaleString('es')} vistas, {s.best.retention}% de retención.
              </p>
            )}
          </>
        )}
      </Card>

      {summary?.hypotheses && summary.hypotheses.length > 0 && (
        <Card title="Hipótesis de mejora" sub="Derivadas de los datos importados; son sugerencias a probar, no hechos.">
          <ul className="clean">
            {summary.hypotheses.map((h) => <li key={h}>{h}</li>)}
          </ul>
        </Card>
      )}

      <Card title="Vídeos registrados" sub={`${rows.length} filas con métricas reales importadas.`}>
        {rows.length === 0 ? (
          <Empty>Sin vídeos registrados.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Título</th><th>Formato</th><th>Vistas</th><th>CTR</th><th>Retención</th><th>Publicado</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td style={{ whiteSpace: 'normal' }}>{r.title}</td>
                    <td><Badge tone={r.format === 'short' ? 'info' : 'ok'}>{r.format}</Badge></td>
                    <td>{r.views.toLocaleString('es')}</td>
                    <td>{r.ctr}%</td>
                    <td>{r.retention}%</td>
                    <td>{r.published_at ? new Date(r.published_at).toLocaleDateString('es') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
