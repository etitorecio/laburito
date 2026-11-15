import type { OptionItem } from '../api';

export interface CaptionStyleOption extends OptionItem {
  max_words?: number;
  max_chars?: number;
  max_lines?: number;
  font_ratio?: number;
  y_from_bottom?: number;
  box?: boolean;
  box_alpha?: string;
  boxcolor?: string;
  fontcolor?: string;
  outline?: number;
  uppercase?: boolean;
}

interface Props {
  options: CaptionStyleOption[];
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}

export default function CaptionStylePicker({ options, value, onChange, compact = false }: Props) {
  return (
    <div className="caption-style-picker" aria-label="Demostraciones de estilos de subtítulos">
      <div className="caption-style-track">
        {options.map((option) => {
          const selected = value === option.id;
          const previewUrl = `/api/caption-preview/${encodeURIComponent(option.id)}`;
          return (
            <button
              key={option.id}
              type="button"
              className={`caption-style-card ${selected ? 'selected' : ''}`}
              aria-pressed={selected}
              onClick={() => onChange(option.id)}
            >
              <span className="caption-style-screen">
                <img src={previewUrl} alt={`Demostración real del estilo ${option.label}`} loading="lazy" />
              </span>
              <span className="caption-style-name">{option.label}</span>
              <span className="caption-style-state">{selected ? '✓ Seleccionado' : 'Tocar para elegir'}</span>
            </button>
          );
        })}
      </div>
      {!compact && <p className="muted caption-style-help">Deslizá las tarjetas para ver los estilos. Las imágenes se generan con el mismo motor FFmpeg que renderiza tus videos.</p>}
    </div>
  );
}
