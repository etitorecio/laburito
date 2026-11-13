export type Route =
  | 'inicio'
  | 'investigacion'
  | 'canales'
  | 'calendario'
  | 'proyectos'
  | 'editor'
  | 'cola'
  | 'biblioteca'
  | 'analitica'
  | 'ajustes';

export const ROUTES: { id: Route; label: string; icon: string }[] = [
  { id: 'inicio', label: 'Inicio', icon: '🏠' },
  { id: 'investigacion', label: 'Investigación', icon: '🔎' },
  { id: 'canales', label: 'Canales', icon: '📺' },
  { id: 'calendario', label: 'Calendario', icon: '🗓️' },
  { id: 'proyectos', label: 'Proyectos', icon: '🎬' },
  { id: 'cola', label: 'Cola', icon: '⚙️' },
  { id: 'biblioteca', label: 'Biblioteca', icon: '🖼️' },
  { id: 'analitica', label: 'Analítica', icon: '📈' },
  { id: 'ajustes', label: 'Ajustes', icon: '⚡' },
];

// En móvil mostramos las cinco secciones principales en la barra inferior.
export const TAB_ROUTES: Route[] = ['inicio', 'investigacion', 'proyectos', 'cola', 'biblioteca'];
