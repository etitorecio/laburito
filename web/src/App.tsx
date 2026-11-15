import { useCallback, useEffect, useState } from 'react';
import { api, type Diagnostics, type Meta } from './api';
import { ROUTES, VALID_ROUTES, type Route } from './routes';
import Home from './pages/Home';
import Research from './pages/Research';
import Channels from './pages/Channels';
import Calendar from './pages/Calendar';
import Projects from './pages/Projects';
import Editor from './pages/Editor';
import Queue from './pages/Queue';
import Library from './pages/Library';
import Analytics from './pages/Analytics';
import Autopilot from './pages/Autopilot';
import Settings from './pages/Settings';
import Landing from './pages/Landing';

function parseHash(): { route: Route; id?: number } {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [name, id] = raw.split('/');
  const valid = VALID_ROUTES.includes(name as Route);
  const route = (valid ? name : 'inicio') as Route;
  const parsed = id ? Number(id) : undefined;
  return { route, id: parsed && Number.isFinite(parsed) ? parsed : undefined };
}

export default function App() {
  const [route, setRoute] = useState<Route>(parseHash().route);
  const [projectId, setProjectId] = useState<number | undefined>(parseHash().id);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [authError, setAuthError] = useState('');

  const go = useCallback((next: Route, id?: number) => {
    setRoute(next);
    setProjectId(id);
    window.location.hash = id ? `#/${next}/${id}` : `#/${next}`;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    const onHash = () => {
      const parsed = parseHash();
      setRoute(parsed.route);
      setProjectId(parsed.id);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const m = await api.get<Meta>('/api/meta');
        setMeta(m);
        setDiag(await api.get<Diagnostics>('/api/diagnostics'));
        setAuthError('');
      } catch (e) {
        setAuthError((e as Error).message);
      }
    })();
  }, [route]);

  // La portada pública se muestra sin la barra lateral del estudio.
  if (route === 'landing') {
    return <Landing go={go} />;
  }

  const current = ROUTES.find((r) => r.id === route);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="dot" />
          <div>
            <strong>AITuber Libre</strong>
            <small>estudio local · sin costes</small>
          </div>
        </div>
        <nav>
          {ROUTES.map((r) => (
            <button key={r.id} className={`nav-item ${route === r.id ? 'active' : ''}`} onClick={() => go(r.id)}>
              <span className="ico" aria-hidden>{r.icon}</span>
              {r.label}
            </button>
          ))}
        </nav>
        <div className="side-foot">
          <button className="nav-item" onClick={() => go('landing')}>
            <span className="ico" aria-hidden>
              🌐
            </span>
            Ver sitio
          </button>
          {diag && (
            <div className="mini">
              <span className={`led ${diag.tts.available ? 'on' : 'off'}`} />
              voz {diag.tts.available ? diag.tts.engine : 'no disponible'}
            </div>
          )}
          {diag && <div className="mini"><span className={`led ${diag.worker.worker_alive ? 'on' : 'off'}`} /> cola {diag.worker.queued + diag.worker.running} activa</div>}
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <h1>{current?.label ?? 'Inicio'}</h1>
          <div className="top-actions">
            {diag && !diag.tts.available && <span className="badge bad">sin voz</span>}
            <button className="btn small primary" onClick={() => go('proyectos')}>Nuevo proyecto</button>
          </div>
        </header>

        {authError && (
          <div className="msg error" style={{ marginBottom: 12 }}>
            {authError} <button className="btn small ghost" onClick={() => go('ajustes')}>Configurar</button>
          </div>
        )}

        {route === 'inicio' && <Home go={go} />}
        {route === 'investigacion' && <Research />}
        {route === 'canales' && <Channels />}
        {route === 'calendario' && <Calendar go={go} />}
        {route === 'proyectos' && <Projects go={go} />}
        {route === 'editor' && (projectId ? <Editor projectId={projectId} go={go} /> : <Projects go={go} />)}
        {route === 'cola' && <Queue go={go} />}
        {route === 'biblioteca' && <Library />}
        {route === 'analitica' && <Analytics />}
        {route === 'autopilot' && <Autopilot />}
        {route === 'ajustes' && <Settings />}

        <footer className="foot">
          <span>{meta ? `${meta.kinds.length} formatos · ${meta.voices.filter((v) => v.available).length} voces instaladas` : 'cargando…'}</span>
          <span>Software libre: FFmpeg · espeak-ng · FastAPI · React</span>
        </footer>
      </main>

      <nav className="tabbar">
        {ROUTES.filter((r) => ['inicio', 'investigacion', 'proyectos', 'autopilot', 'cola'].includes(r.id)).map((r) => (
          <button key={r.id} className={`tab ${route === r.id ? 'active' : ''}`} onClick={() => go(r.id)}>
            <span aria-hidden>{r.icon}</span>
            <small>{r.label}</small>
          </button>
        ))}
      </nav>
    </div>
  );
}
