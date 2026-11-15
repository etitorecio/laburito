import { useEffect, useState } from 'react';
import { api, type Meta } from '../api';

type VideoType = Meta['video_types'][number];
type Clip = { filename: string; size: number; url: string };
type ClipLibraries = Record<string, Clip[]>;

interface Props {
  options: VideoType[];
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}

const ICONS: Record<string, string> = {
  moving_images: '🖼️',
  full_motion_ai: '🎬',
  skeleton: '💀',
  stock_footage: '🎞️',
  minecraft: '⛏️',
  subway: '🏃',
};

const REQUIRED: Record<string, number> = { stock_footage: 5, minecraft: 1, subway: 1 };
const MAX_CLIPS = 5;
const CLIP_SOURCES: Record<string, { label: string; url: string; detail: string }[]> = {
  subway: [
    { label: 'Subway Surfers oficial · vertical 9:16 (SYBO)', url: 'https://www.youtube.com/watch?v=QPW3XwBoQlw', detail: 'La publicación oficial dice FREE TO USE, pero las condiciones generales de SYBO restringen la exhibición pública y el uso comercial salvo autorización. Para monetizar, pedí permiso escrito específico y guardalo.' },
    { label: 'Subway Surfers oficial · horizontal 16:9 (SYBO)', url: 'https://www.youtube.com/watch?v=i0M4ARe9v0Y', detail: 'También marcado FREE TO USE por el canal oficial; habría que recortarlo a vertical. La autorización comercial debe confirmarse frente a las condiciones generales de SYBO.' },
    { label: 'Condiciones oficiales de SYBO', url: 'https://sybogames.com/terms-of-service/', detail: 'SYBO conserva los derechos del juego y limita la publicación o exhibición pública y los usos comerciales no autorizados.' },
  ],
  minecraft: [
    { label: 'Minecraft Parkour · Orbital (creador)', url: 'https://www.youtube.com/watch?v=u7kdVe8q5zs', detail: 'El creador declara permiso para monetizar y pide crédito. Es permiso del autor de la grabación, no una licencia de Mojang.' },
    { label: 'Minecraft Parkour · Addy (Vimeo)', url: 'https://vimeo.com/1005854698', detail: 'El creador declara que permite descargar y reutilizar sus grabaciones y pide crédito; usá solo una opción de descarga habilitada por él. No reemplaza las reglas de Mojang.' },
    { label: 'Reglas oficiales de videos y monetización de Minecraft', url: 'https://www.minecraft.net/en-us/usage-guidelines', detail: 'Mojang permite monetizar videos de gameplay si agregás contenido propio suficiente y respetás sus condiciones.' },
  ],
};

export default function VideoTypePicker({ options, value, onChange, compact = false }: Props) {
  const [clips, setClips] = useState<ClipLibraries>({});
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  async function loadClips() {
    try {
      setClips(await api.get<ClipLibraries>('/api/background-clips'));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => { void loadClips(); }, []);

  async function upload(category: string, file?: File) {
    if (!file) return;
    if (!rightsConfirmed) {
      setError('Antes de cargar clips, confirmá que tenés derechos o permiso para usarlos.');
      return;
    }
    setBusy(category); setError('');
    try {
      await api.upload(
        `/api/background-clips?category=${encodeURIComponent(category)}&rights_confirmed=true`,
        file,
      );
      await loadClips();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(''); 
    }
  }

  async function remove(category: string, filename: string) {
    setBusy(category); setError('');
    try {
      await api.del(`/api/background-clips/${encodeURIComponent(category)}/${encodeURIComponent(filename)}`);
      await loadClips();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  function ready(option: VideoType) {
    if (option.id === 'moving_images') return true;
    const required = REQUIRED[option.id];
    if (required) return (clips[option.id]?.length || 0) >= required;
    return option.available;
  }

  return (
    <div className="video-type-picker">
      <label className="clip-rights-confirm">
        <input type="checkbox" checked={rightsConfirmed} onChange={(e) => setRightsConfirmed(e.target.checked)} />
        Confirmo que los clips que cargue son míos o tengo permiso para utilizarlos y publicarlos
      </label>
      <div className="video-type-track">
        {options.map((option) => {
          const selected = value === option.id;
          const required = REQUIRED[option.id] || 0;
          const categoryClips = clips[option.id] || [];
          const isReady = ready(option);
          return (
            <article key={option.id} className={`video-type-card ${selected ? 'selected' : ''} ${isReady ? '' : 'unavailable'}`}>
              <div className="video-type-heading">
                <span className="video-type-icon">{ICONS[option.id] || '🎥'}</span>
                <div>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </div>
              </div>

              {required > 0 ? (
                <>
                  <div className={`video-type-preview ${option.id}`}>
                    <span>{ICONS[option.id] || '🎥'}</span>
                    <small>Referencia visual · requiere clips propios o autorizados</small>
                  </div>
                  <details className="background-clip-manager">
                    <summary>Administrar clips · {categoryClips.length} cargados · mínimo {required}, máximo {MAX_CLIPS}</summary>
                    <div className="clip-source-list">
                      <strong>Fuentes y permisos revisados</strong>
                      {(CLIP_SOURCES[option.id] || []).map((source) => (
                        <div key={source.url}>
                          <a href={source.url} target="_blank" rel="noreferrer">{source.label}</a>
                          <small>{source.detail}</small>
                        </div>
                      ))}
                      <small>Subí solo material con permiso comercial explícito del titular. Grabar tu propia partida no elimina los derechos sobre el juego. No uses páginas para extraer videos de YouTube.</small>
                    </div>
                    <div className="background-clip-slots">
                  {Array.from({ length: MAX_CLIPS }, (_, index) => {
                    const clip = categoryClips[index];
                    const src = clip ? `${clip.url}` : '';
                    return (
                      <div className="background-clip-slot" key={index}>
                        {clip ? (
                          <>
                            <video src={src} controls muted playsInline preload="none" />
                            <span>Clip {index + 1} · {clip.filename}</span>
                            <button type="button" className="clip-remove" disabled={busy === option.id} onClick={() => void remove(option.id, clip.filename)}>Quitar</button>
                          </>
                        ) : (
                          <label className="clip-upload-slot">
                            <span>＋</span>
                            <small>Agregar clip {index + 1} (hasta {MAX_CLIPS})</small>
                            <input
                              type="file"
                              accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
                              disabled={busy === option.id || !rightsConfirmed}
                              onChange={(e) => {
                                const file = e.target.files?.[0];
                                void upload(option.id, file);
                                e.target.value = '';
                              }}
                            />
                          </label>
                        )}
                      </div>
                    );
                  })}
                    </div>
                  </details>
                </>
              ) : option.id === 'full_motion_ai' ? (
                <div className="video-type-preview full_motion_ai">
                  <span>🎬</span>
                  <small>No disponible sin un motor local viable o servicio con créditos</small>
                </div>
              ) : (
                <div className="video-type-placeholder">
                  {option.id === 'skeleton' ? (
                    <video src="/api/skeleton-preview/walk" controls muted loop playsInline preload="none" />
                  ) : option.id === 'moving_images' ? (
                    <video src="/api/transition-preview/kenburns" controls muted loop playsInline preload="none" />
                  ) : (
                    <>
                      <span>{ICONS[option.id] || '🎥'}</span>
                      <small>No hay un motor local conectado</small>
                    </>
                  )}
                </div>
              )}

              <div className="video-type-footer">
                {required > 0 && <small>{categoryClips.length} de {MAX_CLIPS} clips · mínimo {required}</small>}
                <button
                  type="button"
                  className="btn small"
                  disabled={!isReady || busy === option.id}
                  onClick={() => onChange(option.id)}
                >
                  {selected ? '✓ Seleccionado' : isReady ? 'Elegir este formato' : required ? 'Faltan clips' : 'Todavía no disponible'}
                </button>
              </div>
              {busy === option.id && <small className="muted">Procesando video…</small>}
            </article>
          );
        })}
      </div>
      {error && <p className="error-text">{error}</p>}
      {!compact && <p className="muted caption-style-help">Minecraft y Subway Surfers necesitan al menos un clip propio o autorizado; podés cargar hasta cinco para alternarlos. Los archivos se guardan en el almacenamiento de esta instalación y no se envían a servicios de terceros.</p>}
    </div>
  );
}
