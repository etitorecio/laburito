import type { OptionItem } from '../api';
import { getToken } from '../api';

interface VisualStyleOption extends OptionItem {
  description: string;
}

interface Props {
  options: VisualStyleOption[];
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}

export default function VisualStylePicker({ options, value, onChange, compact = false }: Props) {
  const token = getToken();
  return (
    <div className="visual-style-picker">
      <div className="visual-style-picker-track">
        {options.map((style) => {
          const selected = value === style.id;
          const src = `/api/visual-style-preview/${encodeURIComponent(style.id)}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
          return (
            <button
              key={style.id}
              type="button"
              className={`visual-style-card ${selected ? 'selected' : ''}`}
              aria-pressed={selected}
              onClick={() => onChange(style.id)}
            >
              <span className="visual-style-preview">
                <img src={src} alt={`Muestra del estilo ${style.label}`} loading="lazy" />
              </span>
              <strong>{style.label}</strong>
              <small>{style.description}</small>
              <span className="visual-style-selected">{selected ? '✓ Seleccionado' : 'Tocar para elegir'}</span>
            </button>
          );
        })}
      </div>
      {!compact && <p className="muted caption-style-help">Estas muestras se procesan con los filtros locales que se aplican al video final. No usan créditos ni generan imágenes externas.</p>}
    </div>
  );
}
