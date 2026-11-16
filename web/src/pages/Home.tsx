import { useEffect, useRef, useState } from 'react';
import { api, mediaUrl, type Diagnostics, type Project, type Channel } from '../api';
import { Badge, Empty, Progress, statusTone } from '../ui';
import type { Route } from '../routes';

const QUICK = [
  { icon: '✦', title: 'Crear un video', desc: 'Idea, guion, voz y montaje', route: 'proyectos' as Route, tone: 'violet' },
  { icon: '◉', title: 'Mis canales', desc: 'Identidad y cuentas conectadas', route: 'canales' as Route, tone: 'cyan' },
  { icon: '⌁', title: 'Autopiloto', desc: 'Programá tu producción', route: 'autopilot' as Route, tone: 'pink' },
  { icon: '▤', title: 'Biblioteca', desc: 'Recursos y material visual', route: 'biblioteca' as Route, tone: 'blue' },
];

export default function Home({ go }: { go: (route: Route, id?: number) => void }) {
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState('');
  const [prompt, setPrompt] = useState('');
  const [creating, setCreating] = useState(false);
  const [channelId, setChannelId] = useState('');
  const promptRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    Promise.all([
      api.get<Diagnostics>('/api/diagnostics'),
      api.get<Project[]>('/api/projects'),
      api.get<Channel[]>('/api/channels'),
    ]).then(([d, p, c]) => {
      setDiag(d); setProjects(p); setChannels(c);
    }).catch((e: Error) => setError(e.message));
  }, []);

  const checks = diag?.checks ?? {};
  const ready = Boolean(checks.ffmpeg && checks.tts);

  return (
    <div className="studio-home">
      {error && <div className="msg error">{error}</div>}
      {diag && !diag.persistence.configured && !diag.persistence.local_persistent && (
        <div className="msg">
          <strong>Almacenamiento no persistente.</strong> Esta instancia puede perder proyectos y archivos si el servidor se reinicia o reemplaza. Para conservar todo sin pagar hosting, ejecutá la versión local con Docker y su carpeta de datos persistente.
        </div>
      )}
      <section className="studio-hero">
        <div className="studio-hero-copy">
          <span className="studio-eyebrow"><i /> TU ESTUDIO DE CREACIÓN</span>
          <h2>De una idea a tu próximo <span>video.</span></h2>
          <p>Creá Shorts y videos largos, organizá todos tus canales y producí contenido desde un solo lugar.</p>
          <div className="studio-hero-actions">
            <button className="studio-primary" onClick={() => promptRef.current?.focus()}>＋ Crear video</button>
            <button className="studio-secondary" onClick={() => go('autopilot')}>Configurar autopiloto ↗</button>
          </div>
          <div className="studio-trust"><span>✓ Sin créditos pagos</span><span>✓ Herramientas libres</span><span>✓ Tus canales, tu control</span></div>
        </div>
        <div className="studio-showcase" aria-label="Vistas ilustrativas de formatos de video">
          <div className="showcase-card showcase-short"><small>SHORT · 9:16</small><span className="showcase-symbol">✦</span><strong>Historias que atrapan</strong><em>00:58</em></div>
          <div className="showcase-card showcase-doc"><small>DOCUMENTAL · 16:9</small><span className="showcase-symbol">◈</span><strong>Secretos de la historia</strong><em>12:40</em></div>
          <div className="showcase-card showcase-series"><small>SERIE · EPISODIOS</small><span className="showcase-symbol">♡</span><strong>Frutinovela</strong><em>EP. 04</em></div>
        </div>
      </section>

      <section className="studio-section" aria-label="Crear video con una instrucción">
        <div className="studio-section-head"><div><span className="studio-eyebrow">DECILO Y SE HACE</span><h3>¿Qué video querés que haga?</h3><p>Escribí una orden simple. Laburito prepara el guion y deja el render trabajando en segundo plano.</p></div></div>
        <div className="studio-prompt-presets" aria-label="Elegir un tipo de video">
          <button type="button" onClick={() => { setPrompt('Haceme un short sobre '); promptRef.current?.focus(); }}>▯ <span>Short</span></button>
          <button type="button" onClick={() => { setPrompt('Haceme una historia de terror'); promptRef.current?.focus(); }}>◉ <span>Historia</span></button>
          <button type="button" onClick={() => { setPrompt('Haceme una frutinovela'); promptRef.current?.focus(); }}>♡ <span>Frutinovela</span></button>
          <button type="button" onClick={() => { setPrompt('Haceme un documental sobre '); promptRef.current?.focus(); }}>▭ <span>Documental</span></button>
        </div>
        <form className="studio-prompt-form" onSubmit={async (event) => {
          event.preventDefault();
          if (!prompt.trim() || creating) return;
          setCreating(true); setError('');
          try {
            const result = await api.post<{ project_id: number; job_id: number; status: string }>('/api/create-from-prompt', {
              prompt: prompt.trim(),
              channel_id: channelId ? Number(channelId) : null,
            });
            setPrompt('');
            go('editor', result.project_id);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setCreating(false);
          }
        }}>
          <textarea
            ref={promptRef}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={2}
            maxLength={1000}
            placeholder="Ej.: Haceme un short sobre la historia de Nirvana…"
            aria-label="Describí el video que querés crear"
            style={{ width: '100%', minHeight: 76, resize: 'vertical' }}
          />
          <div className="studio-prompt-controls">
            <label>
              <span>Canal</span>
              <select value={channelId} onChange={(event) => setChannelId(event.target.value)}>
                <option value="">Automático según el formato</option>
                {channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
              </select>
            </label>
            <button className="studio-primary" type="submit" disabled={creating || !prompt.trim()}>{creating ? 'Preparando tu video…' : 'Crear video →'}</button>
          </div>
          <small className="muted">No tenés que elegir voz, imágenes ni edición: Laburito usa la configuración del canal y prepara la producción automáticamente.</small>
        </form>
      </section>

      <section className="studio-stats">
        <div><span>Canales</span><strong>{diag?.counts.canales ?? channels.length}</strong><small>Según tu almacenamiento</small></div>
        <div><span>Videos</span><strong>{diag?.counts.proyectos ?? projects.length}</strong><small>Proyectos creados</small></div>
        <div><span>Escenas</span><strong>{diag?.counts.escenas ?? 0}</strong><small>En tu biblioteca</small></div>
        <div><span>Motor local</span><strong className={ready ? 'stat-ready' : 'stat-warn'}>{ready ? 'Listo' : 'Revisar'}</strong><small>{ready ? 'FFmpeg y voz disponibles' : 'Ver diagnóstico del sistema'}</small></div>
      </section>

      <section className="studio-section">
        <div className="studio-section-head"><div><span className="studio-eyebrow">EMPEZÁ A PRODUCIR</span><h3>¿Qué querés hacer hoy?</h3></div></div>
        <div className="studio-quick-grid">
          {QUICK.map((item) => <button className={'studio-quick '+item.tone} key={item.title} onClick={() => go(item.route)}><span className="quick-icon">{item.icon}</span><span><strong>{item.title}</strong><small>{item.desc}</small></span><b>↗</b></button>)}
        </div>
      </section>

      <section className="studio-section">
        <div className="studio-section-head"><div><span className="studio-eyebrow">TU ESPACIO</span><h3>Canales</h3><p>Administrá todos tus proyectos desde cada identidad.</p></div><button className="studio-link" onClick={() => go('canales')}>Ver todos →</button></div>
        {channels.length ? <div className="studio-channel-grid">{channels.slice(0,4).map((c,i)=><button className="studio-channel" key={c.id} onClick={() => go('canales')}><span className={'channel-avatar c'+(i%4)}>{c.name.slice(0,1).toUpperCase()}</span><span><strong>{c.name}</strong><small>{c.topic || 'Tema por definir'}</small></span><b>{c.projects ?? 0} videos</b></button>)}</div> : <div className="studio-empty"><span>◎</span><strong>Todavía no creaste canales</strong><p>Creá Historias, Frutinovela y todos los canales que quieras.</p><button className="studio-secondary" onClick={() => go('canales')}>Crear mi primer canal</button></div>}
      </section>

      <section className="studio-section">
        <div className="studio-section-head"><div><span className="studio-eyebrow">ACTIVIDAD RECIENTE</span><h3>Tus últimos videos</h3></div><button className="studio-link" onClick={() => go('proyectos')}>Ver proyectos →</button></div>
        {projects.length ? <div className="studio-project-list">{projects.slice(0,5).map(p=><div className="studio-project" key={p.id}><span className="project-thumb">{p.thumbnail_path ? <img src={mediaUrl(p.thumbnail_path)} alt="" loading="lazy" /> : p.status === 'renderizado' ? <img src={`/media/renders/${p.id}/miniatura_${p.kind === 'short' ? 'short' : 'documental'}.jpg`} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; e.currentTarget.parentElement!.textContent = '▶'; }} /> : '▶'}</span><div className="project-info"><strong>{p.title}</strong><small>{p.kind === 'short' ? 'Short vertical' : 'Video horizontal'} · {p.scenes_count ?? 0} escenas</small>{p.job && p.job.status !== 'completado' && <Progress value={p.job.progress} label={p.job.message}/>}</div><Badge tone={statusTone(p.status)}>{p.status}</Badge><button className="studio-open" onClick={() => go('editor',p.id)}>Abrir</button></div>)}</div> : <Empty>Todavía no hay videos. Creá tu primer proyecto para empezar.</Empty>}
      </section>
      <div className="studio-bottom-note"><span>✦</span> AITuber Libre · Producción local, sin créditos ni suscripciones obligatorias.</div>
    </div>
  );
}
