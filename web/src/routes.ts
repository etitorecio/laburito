export type Route =
  | 'landing'
  | 'inicio'
  | 'investigacion'
  | 'canales'
  | 'calendario'
  | 'proyectos'
  | 'editor'
  | 'cola'
  | 'biblioteca'
  | 'analitica'
  | 'autopilot'
  | 'cuentas'
  | 'ajustes';

// Rutas válidas del hash: la landing pública más las secciones del estudio.
export const VALID_ROUTES: Route[] = [
  'landing',
  'inicio',
  'investigacion',
  'canales',
  'calendario',
  'proyectos',
  'editor',
  'cola',
  'biblioteca',
  'analitica',
  'autopilot',
  'cuentas',
  'ajustes',
];

export const ROUTES: { id: Route; label: string; icon: string }[] = [
  { id: 'inicio', label: 'Inicio', icon: '🏠' },
  { id: 'investigacion', label: 'Investigación', icon: '🔎' },
  { id: 'canales', label: 'Canales', icon: '📺' },
  { id: 'calendario', label: 'Calendario', icon: '🗓️' },
  { id: 'proyectos', label: 'Videos', icon: '🎬' },
  { id: 'cola', label: 'Cola', icon: '⚙️' },
  { id: 'biblioteca', label: 'Biblioteca', icon: '🖼️' },
  { id: 'analitica', label: 'Analítica', icon: '📈' },
  { id: 'autopilot', label: 'Autopiloto', icon: '🤖' },
  { id: 'cuentas', label: 'Cuentas', icon: '🔗' },
  { id: 'ajustes', label: 'Ajustes', icon: '⚡' },
];

// En móvil mostramos las cinco secciones principales en la barra inferior.
export const TAB_ROUTES: Route[] = ['inicio', 'investigacion', 'proyectos', 'cola', 'biblioteca'];
