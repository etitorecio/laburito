import { useEffect, useState } from 'react';
import { api, mediaUrl, type Asset } from '../api';
import { Badge, Card, Empty, Msg } from '../ui';

export default function Library() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  async function load() {
    try {
      setAssets(await api.get<Asset[]>('/api/library'));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filtered = assets.filter((a) => !filter || a.kind.includes(filter));
  const images = filtered.filter((a) => ['imagen', 'miniatura', 'thumbnail'].includes(a.kind));
  const files = filtered.filter((a) => !['imagen', 'miniatura', 'thumbnail'].includes(a.kind));

  return (
    <div className="stack">
      <Msg error={error} />
      <Card
        title="Biblioteca"
        sub="Todo lo que la app produjo o descargó: imágenes con licencia, vídeos, subtítulos y paquetes."
        actions={
          <>
            <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 170 }}>
              <option value="">Todo</option>
              <option value="imagen">Imágenes</option>
              <option value="video">Vídeos</option>
              <option value="subtitulos">Subtítulos</option>
              <option value="export_zip">Paquetes ZIP</option>
            </select>
            <button className="btn small ghost" onClick={load}>Actualizar</button>
          </>
        }
      >
        {filtered.length === 0 ? (
          <Empty>Sin archivos todavía. Aparecen al descargar material o renderizar un proyecto.</Empty>
        ) : (
          <>
            {images.length > 0 && (
              <div className="thumbs">
                {images.map((a) => (
                  <figure key={a.id}>
                    <a href={mediaUrl(a.path)} target="_blank" rel="noreferrer">
                      <img src={mediaUrl(a.path)} alt={a.label} loading="lazy" />
                    </a>
                    <figcaption>
                      {a.label}
                      <br />
                      <span className="muted">{a.license || a.kind}</span>
                    </figcaption>
                  </figure>
                ))}
              </div>
            )}

            {files.length > 0 && (
              <div className="list mt-12">
                {files.map((a) => (
                  <div className="list-item" key={a.id}>
                    <div className="grow">
                      <h4>{a.label || a.kind}</h4>
                      <div className="meta">
                        <Badge tone="info">{a.kind}</Badge>
                        <span>{a.project_title || 'sin proyecto'}</span>
                        <span>{Math.round((a.bytes || 0) / 1024)} KB</span>
                        <span>{new Date(a.created_at).toLocaleString('es')}</span>
                      </div>
                    </div>
                    <div className="row gap-8">
                      <a className="btn small ghost" href={mediaUrl(a.path)} download>Descargar</a>
                      <button className="btn small danger" onClick={async () => { await api.del(`/api/library/${a.id}`); await load(); }}>Quitar</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
