import { useEffect, useState } from 'react';
import { api, type Job, type LogRow } from '../api';
import { Badge, Card, Empty, JobBadge, Msg, Progress } from '../ui';
import type { Route } from '../routes';

export default function Queue({ go }: { go: (route: Route, id?: number) => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [error, setError] = useState('');

  async function load() {
    try {
      const [j, l] = await Promise.all([api.get<Job[]>('/api/jobs?limit=30'), api.get<LogRow[]>('/api/logs?limit=40')]);
      setJobs(j);
      setLogs(l);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(id);
  }, []);

  const active = jobs.filter((j) => ['en_cola', 'ejecutando'].includes(j.status));

  return (
    <div className="stack">
      <Msg error={error} />

      <Card
        title="Cola de trabajo"
        sub="Un solo proceso a la vez, persistente: si se reinicia, la tarea se reanuda sin repetir escenas."
        actions={<button className="btn small ghost" onClick={load}>Actualizar</button>}
      >
        <div className="pill-row" style={{ marginBottom: 10 }}>
          <Badge tone={active.length ? 'warn' : 'ok'}>{active.length} activas</Badge>
          <Badge tone="info">{jobs.length} en historial</Badge>
        </div>
        {jobs.length === 0 ? (
          <Empty>Sin tareas. Renderizá un proyecto para ver el progreso acá.</Empty>
        ) : (
          <div className="list">
            {jobs.map((j) => (
              <div className="list-item" key={j.id}>
                <div className="grow">
                  <h4>
                    #{j.id} · {j.kind.replace('_', ' ')} {j.project_title ? `— ${j.project_title}` : ''}
                  </h4>
                  <div className="meta">
                    <JobBadge status={j.status} />
                    <span>{j.message}</span>
                    <span>intentos: {j.attempts}</span>
                  </div>
                  {['en_cola', 'ejecutando'].includes(j.status) && (
                    <div style={{ marginTop: 6 }}><Progress value={j.progress} /></div>
                  )}
                </div>
                <div className="row gap-8">
                  {j.project_id && <button className="btn small ghost" onClick={() => go('editor', j.project_id!)}>Abrir</button>}
                  {['en_cola', 'ejecutando'].includes(j.status) ? (
                    <button className="btn small danger" onClick={async () => { await api.post(`/api/jobs/${j.id}/cancel`); await load(); }}>Cancelar</button>
                  ) : (
                    <button className="btn small ghost" onClick={async () => { await api.post(`/api/jobs/${j.id}/retry`); await load(); }}>Reintentar</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Registro del sistema" sub="Eventos reales de la aplicación, sin métricas inventadas.">
        {logs.length === 0 ? (
          <Empty>Sin eventos.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Hora</th><th>Nivel</th><th>Ámbito</th><th>Mensaje</th></tr>
              </thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td>{new Date(l.created_at).toLocaleTimeString('es')}</td>
                    <td>{l.level}</td>
                    <td>{l.scope}</td>
                    <td style={{ whiteSpace: 'normal' }}>{l.message}</td>
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
