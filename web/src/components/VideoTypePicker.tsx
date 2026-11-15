import { useEffect, useState } from 'react';
import { api, getToken, type Meta } from '../api';

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

const REQUIRED: Record<string, number> = { stock_footage: 5, minecraft: 5, subway: 5 };

export default function VideoTypePicker({ options, value, onChange, compact = false }: Props) {
  const [clips, setClips] = useState<ClipLibraries>({});
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const token = getToken();

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
                <div className="background-clip-slots">
                  {Array.from({ length: required }, (_, index) => {
                    const clip = categoryClips[index];
                    const src = clip ? `${clip.url}${token ? `?token=${encodeURIComponent(token)}` : ''}` : '';
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
                            <small>Agregar clip {index + 1} de {required}</small>
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
              ) : (
                <div className="video-type-placeholder">
                  {option.id === 'skeleton' ? (
                    <video
                      src={`/api/skeleton-preview/walk${token ? `?token=${encodeURIComponent(token)}` : ''}`}
                      controls muted loop playsInline preload="none"
                    />
                  ) : (
                    <>
                      <span>{ICONS[option.id] || '🎥'}</span>
                      <small>{option.id === 'moving_images' ? 'Fotos de archivo con paneo y zoom' : 'No hay un modelo local conectado'}</small>
                    </>
                  )}
                </div>
              )}

              <div className="video-type-footer">
                {required > 0 && <small>{categoryClips.length}/{required} clips cargados</small>}
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
      {!compact && <p className="muted caption-style-help">Minecraft y Subway Surfers usan cinco clips propios o autorizados que se alternan automáticamente. Los archivos se guardan en tu PC y no se envían a servicios externos.</p>}
    </div>
  );
}
