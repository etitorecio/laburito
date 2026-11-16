import { useEffect, useState } from 'react';
import { api, mediaUrl, type Project } from '../api';
import { Badge, Card, Empty, Msg, statusTone } from '../ui';

type Aspect = '9:16' | '1:1' | '16:9';

export default function EditorHub({ go }: { go: (route: 'editor' | 'proyectos', id?: number) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    try { setProjects(await api.get<Project[]>('/api/projects')); }
    catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { void load(); }, []);

  async function start(aspect: Aspect) {
    setBusy(true); setError('');
    try {
      const project = await api.post<Project>('/api/projects', {
        title: 'Proyecto nuevo',
        topic: '',
        kind: aspect === '9:16' ? 'short' : 'documentary',
        aspect,
        template: aspect === '9:16' ? 'shorts' : 'longform',
        duration_target_sec: aspect === '9:16' ? 60 : 600,
        voice: 'es',
        music: 'auto',
      });
      go('editor', project.id);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const recent = projects.slice(0, 8);
  return <div className="stack editor-hub">
    <Msg error={error} />
    <Card title="Abrir un video" sub="Continuá editando una producción o retomá un proyecto guardado.">
      {recent.length ? <div className="editor-hub-projects">{recent.map((project) => (
        <button className="editor-hub-project" key={project.id} onClick={() => go('editor', project.id)}>
          <span className={'editor-hub-thumb ' + (project.aspect === '9:16' ? 'portrait' : '')}>{project.thumbnail_path ? <img src={mediaUrl(project.thumbnail_path)} alt="" /> : project.status === "renderizado" ? <img src={mediaUrl("renders/" + project.id + "/miniatura_" + (project.kind === "short" ? "short" : "documental") + ".jpg")} alt="" /> : "▶"}</span>
          <span className="editor-hub-project-info"><strong>{project.title}</strong><small>{project.kind === 'short' ? 'Short vertical' : 'Video largo'} · {project.aspect} · {project.scenes_count ?? 0} escenas</small></span>
          <Badge tone={statusTone(project.status)}>{project.status}</Badge>
          <span aria-hidden>›</span>
        </button>
      ))}</div> : <Empty>Todavía no hay videos. Empezá con un proyecto vacío o creá uno desde Videos.</Empty>}
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="btn ghost" onClick={() => go('proyectos')}>Ver todos los videos</button>
      </div>
    </Card>
    <Card title="Empezar desde cero" sub="Elegí el formato del lienzo. Podés agregar escenas, imágenes, clips y música después.">
      <div className="editor-hub-formats">
        <button className="editor-hub-format tall" onClick={() => void start('9:16')} disabled={busy}><span>▯</span><strong>Vertical</strong><small>9:16 · Shorts, TikTok y Reels</small></button>
        <button className="editor-hub-format square" onClick={() => void start('1:1')} disabled={busy}><span>□</span><strong>Cuadrado</strong><small>1:1 · Feed social</small></button>
        <button className="editor-hub-format wide" onClick={() => void start('16:9')} disabled={busy}><span>▭</span><strong>Horizontal</strong><small>16:9 · YouTube</small></button>
      </div>
      {busy && <p className="muted">Preparando el espacio de edición…</p>}
    </Card>
  </div>;
}
