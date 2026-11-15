import { useEffect, useState } from 'react';
import { api, type Diagnostics, type Project } from '../api';
import { Badge, Card, Empty, Progress, Stat, statusTone } from '../ui';
import type { Route } from '../routes';

export default function Home({ go }: { go: (route: Route, id?: number) => void }) {
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.get<Diagnostics>('/api/diagnostics'), api.get<Project[]>('/api/projects')])
      .then(([d, p]) => {
        setDiag(d);
        setProjects(p);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const checks = diag?.checks ?? {};
  const ready = checks.ffmpeg && checks.tts;
  const steps = [
    { done: (diag?.counts.canales ?? 0) > 0, text: 'Crear un canal con identidad y cadencia', route: 'canales' as Route },
    { done: (diag?.counts.proyectos ?? 0) > 0, text: 'Investigar un nicho y guardar notas con fuentes', route: 'investigacion' as Route },
    { done: (diag?.counts.escenas ?? 0) > 0, text: 'Crear un proyecto y generar el guion por escenas', route: 'proyectos' as Route },
    { done: (diag?.counts.tareas ?? 0) > 0, text: 'Renderizar el MP4 y descargar el paquete de publicación', route: 'cola' as Route },
  ];

  return (
    <div className="stack">
      <Card
        title="AITuber Libre"
        sub="Estudio local para investigar nichos y producir documentales y Shorts con software libre."
        actions={<button className="btn primary" onClick={() => go('proyectos')}>Crear video</button>}
      >
        {error && <div className="msg error">{error}</div>}
        <div className="pill-row" style={{ marginBottom: 12 }}>
          <Badge tone={ready ? 'ok' : 'bad'}>{ready ? 'Motor listo' : 'Motor incompleto'}</Badge>
          <Badge tone={checks.ffmpeg ? 'ok' : 'bad'}>FFmpeg</Badge>
          <Badge tone={checks.tts ? 'ok' : 'bad'}>Voz local</Badge>
          <Badge tone={checks.worker ? 'ok' : 'warn'}>Cola</Badge>
          <Badge tone={checks.fuente_subtitulos ? 'ok' : 'warn'}>Subtítulos</Badge>
          <Badge tone="info">Cero costes</Badge>
        </div>
        {!ready && diag && (
          <div className="msg">
            Diagnóstico: {Object.entries(checks).filter(([, ok]) => !ok).map(([name]) => name).join(', ')} sin
            verificar. Revisá Ajustes → Diagnóstico para ver el detalle.
          </div>
        )}
        <div className="grid stats">
          <Stat value={diag?.counts.canales ?? 0} label="Canales" />
          <Stat value={diag?.counts.proyectos ?? 0} label="Videos" />
          <Stat value={diag?.counts.escenas ?? 0} label="Escenas" />
          <Stat value={`${diag?.disk_free_mb ?? 0} MB`} label="Disco libre" />
        </div>
      </Card>

      <div className="grid two">
        <Card title="Ruta de producción" sub="Del nicho al vídeo publicado, sin servicios pagos.">
          <div className="list">
            {steps.map((step, i) => (
              <div className="list-item" key={step.text}>
                <div className="grow">
                  <h4>
                    {step.done ? '✅' : '◻️'} {i + 1}. {step.text}
                  </h4>
                </div>
                <button className="btn small ghost" onClick={() => go(step.route)}>
                  Ir
                </button>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Videos recientes" actions={<button className="btn small ghost" onClick={() => go('proyectos')}>Ver todos</button>}>
          {projects.length === 0 ? (
            <Empty>
              Todavía no hay proyectos. Creá uno, generá el guion y renderizá tu primer documental o Short.
            </Empty>
          ) : (
            <div className="list">
              {projects.slice(0, 5).map((p) => (
                <div className="list-item" key={p.id}>
                  <div className="grow">
                    <h4>{p.title}</h4>
                    <div className="meta">
                      <Badge tone={statusTone(p.status)}>{p.status}</Badge>
                      <span>{p.kind === 'short' ? 'Short 9:16' : 'Documental 16:9'}</span>
                      <span>{p.scenes_count ?? 0} escenas</span>
                    </div>
                    {p.job && p.job.status !== 'completado' && (
                      <div style={{ marginTop: 6 }}>
                        <Progress value={p.job.progress} label={p.job.message} />
                      </div>
                    )}
                  </div>
                  <button className="btn small" onClick={() => go('editor', p.id)}>
                    Abrir
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Cómo trabaja" sub="Reglas del proyecto, para que sepas qué es real y qué no.">
        <div className="grid three">
          <div className="stat">
            <div className="label">Voz</div>
            <p className="mb-0" style={{ marginTop: 6 }}>
              Síntesis local (espeak-ng o Piper si lo instalás). No se envía texto a ningún servicio.
            </p>
          </div>
          <div className="stat">
            <div className="label">Imagen</div>
            <p className="mb-0" style={{ marginTop: 6 }}>
              Tarjetas generadas con FFmpeg + material con licencia descargado de Openverse, Wikimedia o
              Internet Archive.
            </p>
          </div>
          <div className="stat">
            <div className="label">Publicación</div>
            <p className="mb-0" style={{ marginTop: 6 }}>
              La app prepara el paquete (MP4, subtítulos, guion, fuentes, miniatura). Subir a YouTube lo hacés vos.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
