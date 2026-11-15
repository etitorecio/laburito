import { useState } from 'react';
import { getToken, type Meta } from '../api';

type VoiceOption = Meta['voices'][number];

interface Props {
  options: VoiceOption[];
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}

export default function VoicePicker({ options, value, onChange, compact = false }: Props) {
  const [previewVoice, setPreviewVoice] = useState<string | null>(null);
  const token = getToken();
  const previewUrl = previewVoice
    ? `/api/voice-preview/${encodeURIComponent(previewVoice)}${token ? `?token=${encodeURIComponent(token)}` : ''}`
    : '';
  return (
    <div className="voice-picker">
      <div className="voice-track">
        {options.map((voice) => {
          const selected = value === voice.id;
          return (
            <div key={voice.id} className={`voice-card ${selected ? 'selected' : ''} ${voice.available ? '' : 'unavailable'}`}>
              <button
                type="button"
                className="voice-select"
                disabled={!voice.available}
                aria-pressed={selected}
                onClick={() => onChange(voice.id)}
              >
                <span className="voice-avatar">{voice.gender === 'femenino' ? '♀' : voice.gender === 'masculino' ? '♂' : '◉'}</span>
                <strong>{voice.label}</strong>
                <small>{voice.available ? (selected ? '✓ Seleccionada' : 'Seleccionar voz') : 'No disponible'}</small>
              </button>
              <button
                type="button"
                className="voice-preview-button"
                disabled={!voice.available}
                onClick={() => setPreviewVoice(voice.id)}
              >
                ▶ Escuchar
              </button>
            </div>
          );
        })}
      </div>
      {previewVoice && (
        <div className="voice-preview-player">
          <span>Muestra: {options.find((v) => v.id === previewVoice)?.label}</span>
          <audio key={previewVoice} controls autoPlay preload="auto" src={previewUrl} />
        </div>
      )}
      {!compact && <p className="muted caption-style-help">Las muestras se generan en tu instalación, sin enviar texto a servicios externos.</p>}
    </div>
  );
}
