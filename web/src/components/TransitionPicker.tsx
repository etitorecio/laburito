import type { OptionItem } from '../api';
import { getToken } from '../api';

interface Props {
  options: OptionItem[];
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}

export default function TransitionPicker({ options, value, onChange, compact = false }: Props) {
  const token = getToken();
  return (
    <div className="transition-picker" aria-label="Demostraciones de movimiento de escena">
      <div className="transition-track">
        {options.map((option) => {
          const selected = value === option.id;
          const src = `/api/transition-preview/${encodeURIComponent(option.id)}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
          return (
            <div key={option.id} className={`transition-card ${selected ? 'selected' : ''}`}>
              <span className="transition-screen">
                <video src={src} controls muted loop playsInline preload="metadata" autoPlay={selected} />
              </span>
              <button
                type="button"
                className="transition-select"
                aria-pressed={selected}
                onClick={() => onChange(option.id)}
              >
                <span className="transition-name">{option.label}</span>
                <span className="transition-state">{selected ? '✓ Seleccionado' : 'Tocar para elegir'}</span>
              </button>
            </div>
          );
        })}
      </div>
      {!compact && <p className="muted caption-style-help">Cada muestra es un clip generado por FFmpeg con el mismo efecto que se aplica al render.</p>}
    </div>
  );
}
