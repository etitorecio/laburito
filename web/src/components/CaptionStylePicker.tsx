import type { CSSProperties } from 'react';
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
  aspect?: 'vertical' | 'horizontal';
  compact?: boolean;
}

const SAMPLE = 'ESTA HISTORIA CAMBIÓ TODO';
const BACKDROPS = [
  'linear-gradient(145deg,#172554 0%,#2563eb 48%,#0f172a 100%)',
  'linear-gradient(145deg,#422006 0%,#b45309 48%,#111827 100%)',
  'linear-gradient(145deg,#064e3b 0%,#0f766e 48%,#0f172a 100%)',
];

function previewStyle(option: CaptionStyleOption): CSSProperties {
  const centered = option.y_from_bottom !== undefined && option.y_from_bottom >= 0.45;
  const top = option.y_from_bottom !== undefined && option.y_from_bottom >= 0.75;
  const color = option.fontcolor || 'white';
  const boxColor = option.boxcolor || 'black';
  const alpha = Number.parseFloat(option.box_alpha || '0.55');
  const boxBackground = boxColor === 'yellow' ? `rgba(250,204,21,${alpha})` : boxColor === 'red' ? `rgba(220,38,38,${alpha})` : `rgba(0,0,0,${alpha})`;
  const fontSize = Math.max(10, Math.min(19, 132 * (option.font_ratio || 0.04)));
  const shadow = option.outline
    ? `0 1px 0 #000, 1px 0 0 #000, -1px 0 0 #000, 0 -1px 0 #000, 0 2px 3px #000`
    : '0 2px 5px rgba(0,0,0,.8)';
  return {
    position: 'absolute',
    left: 6,
    right: 6,
    ...(top ? { top: '12%' } : centered ? { top: '50%', transform: 'translateY(-50%)' } : { bottom: option.y_from_bottom !== undefined && option.y_from_bottom < 0.1 ? '7%' : option.y_from_bottom !== undefined && option.y_from_bottom > 0.25 ? '28%' : '15%' }),
    color,
    background: option.box ? boxBackground : 'transparent',
    borderRadius: option.box ? 4 : 0,
    padding: option.box ? '4px 3px' : 0,
    fontFamily: option.id === 'serif_cine' ? 'Georgia, serif' : 'Arial, sans-serif',
    fontWeight: 900,
    fontSize,
    lineHeight: 1.12,
    letterSpacing: option.uppercase ? '.02em' : 0,
    textAlign: 'center',
    textTransform: option.uppercase ? 'uppercase' : 'none',
    textShadow: shadow,
    overflowWrap: 'anywhere',
  };
}

export default function CaptionStylePicker({ options, value, onChange, aspect = 'vertical', compact = false }: Props) {
  return (
    <div className="caption-style-picker" aria-label="Demostraciones de estilos de subtítulos">
      <div className="caption-style-track">
        {options.map((option, index) => {
          const selected = value === option.id;
          const sample = option.uppercase ? SAMPLE : 'Esta historia cambió todo';
          return (
            <button
              key={option.id}
              type="button"
              className={`caption-style-card ${selected ? 'selected' : ''}`}
              aria-pressed={selected}
              onClick={() => onChange(option.id)}
            >
              <span
                className={`caption-style-screen ${aspect === 'horizontal' ? 'landscape' : ''}`}
                style={{ background: BACKDROPS[index % BACKDROPS.length] }}
              >
                <span className="caption-style-scene-label">VISTA PREVIA</span>
                <span className="caption-style-horizon" />
                <span className="caption-style-caption" style={previewStyle(option)}>{sample}</span>
              </span>
              <span className="caption-style-name">{option.label}</span>
              <span className="caption-style-state">{selected ? '✓ Seleccionado' : 'Tocar para elegir'}</span>
            </button>
          );
        })}
      </div>
      {!compact && <p className="muted caption-style-help">Deslizá las tarjetas para ver todos los estilos. La muestra representa el aspecto del subtítulo; el render final usa los parámetros exactos del motor.</p>}
    </div>
  );
}
