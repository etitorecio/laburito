import { useState } from 'react';
import { getToken, type OptionItem } from '../api';

interface Props {
  beds: OptionItem[];
  library: string[];
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}

export default function MusicPicker({ beds, library, value, onChange, compact = false }: Props) {
  const [preview, setPreview] = useState<string | null>(null);
  const token = getToken();
  const previewUrl = preview
    ? `${preview.startsWith('bed:') ? `/api/music-preview/${encodeURIComponent(preview.slice(4))}` : `/api/music-file/${encodeURIComponent(preview)}`}${token ? `?token=${encodeURIComponent(token)}` : ''}`
    : '';
  const choices = [
    { id: 'auto', label: 'Automática', detail: 'Alterna las pistas cargadas o las camas locales.', icon: '🔀' },
    { id: 'ninguna', label: 'Sin música', detail: 'Solo narración y sonido original del clip (si corresponde).', icon: '🔇' },
    ...beds.map((bed) => ({ id: `bed:${bed.id}`, label: bed.label, detail: 'Pista generada localmente.', icon: '🎹' })),
    ...library.map((file) => ({ id: file, label: file, detail: 'Pista cargada en tu biblioteca local.', icon: '🎵' })),
  ];
  return (
    <div className="music-picker">
      <div className="music-track">
        {choices.map((choice) => {
          const selected = value === choice.id;
          return (
            <article key={choice.id} className={`music-card ${selected ? 'selected' : ''}`}>
              <button type="button" className="music-select" aria-pressed={selected} onClick={() => onChange(choice.id)}>
                <span className="music-icon">{choice.icon}</span>
                <strong>{choice.label}</strong>
                <small>{choice.detail}</small>
                <span className="music-state">{selected ? '✓ Seleccionada' : 'Tocar para elegir'}</span>
              </button>
              {choice.id !== 'auto' && choice.id !== 'ninguna' && (
                <button type="button" className="music-listen" onClick={() => setPreview(choice.id)}>▶ Escuchar</button>
              )}
            </article>
          );
        })}
      </div>
      {preview && (
        <div className="music-preview-player">
          <span>Muestra: {choices.find((x) => x.id === preview)?.label || preview}</span>
          <audio key={preview} controls autoPlay preload="auto" src={previewUrl} />
        </div>
      )}
      {!compact && <p className="muted caption-style-help">El modo automático rota las pistas locales entre los Shorts. No se conecta a catálogos pagos.</p>}
    </div>
  );
}
