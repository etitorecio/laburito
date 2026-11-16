import { useState } from 'react';
import type { Route } from '../routes';

type Go = (route: Route, id?: number) => void;

const NAV_LINKS: { label: string; target: string }[] = [
  { label: 'Funciones', target: 'funciones' },
  { label: 'Plantillas', target: 'plantillas' },
  { label: 'Autopiloto', target: 'autopilot' },
  { label: 'Costo cero', target: 'costo' },
  { label: 'Preguntas', target: 'faq' },
];

const PLATFORMS = ['YouTube', 'TikTok', 'Instagram', 'Reels', 'Shorts', 'Facebook'];

const HERO_CARDS = [
  {
    tag: 'Short · 9:16',
    caption: 'El imperio que cayó en 24 horas',
    grad: 'linear-gradient(160deg,#3b1d6e,#7c3aed 45%,#0f172a)',
    dur: '0:48',
  },
  {
    tag: 'Documental · 16:9',
    caption: 'Historia secreta de la Ruta de la Seda',
    grad: 'linear-gradient(160deg,#0b3b4a,#0e7490 40%,#111827)',
    dur: '12:04',
  },
  {
    tag: 'Short · 9:16',
    caption: '3 inventos que cambiaron el mundo',
    grad: 'linear-gradient(160deg,#4a1d3f,#be185d 45%,#0f172a)',
    dur: '0:52',
  },
];

const TEMPLATES = [
  {
    icon: '📱',
    title: 'Shorts sin rostro',
    desc: 'Vídeos verticales de 30–60 s con gancho, subtítulos quemados y cierre con llamada a la acción.',
    tags: ['9:16', 'Subtítulos', 'Narración'],
    grad: 'linear-gradient(135deg,#312e81,#7c3aed)',
  },
  {
    icon: '🍓',
    title: 'Frutinovelas por episodios',
    desc: 'Historias originales en vertical, con drama, traiciones, giros y finales abiertos para continuar la serie.',
    tags: ['9:16', 'Series', 'Cliffhanger'],
    grad: 'linear-gradient(135deg,#9f1239,#f97316)',
  },
  {
    icon: '🎬',
    title: 'Documental largo',
    desc: 'Episodios de 8 a 20 minutos divididos en escenas, con notas de investigación y fuentes citadas.',
    tags: ['16:9', '8–20 min', 'Fuentes'],
    grad: 'linear-gradient(135deg,#0e7490,#155e75)',
  },
  {
    icon: '🎵',
    title: 'Vídeos con música',
    desc: 'Mezcla pistas libres o propias con la voz y el ritmo de tus escenas. Las licencias se registran; no se puede garantizar que una plataforma nunca reclame un recurso.',
    tags: ['Música', 'Mezcla', 'Libre'],
    grad: 'linear-gradient(135deg,#9d174d,#be185d)',
  },
  {
    icon: '🗣️',
    title: 'Voz en off en español',
    desc: 'Voces locales en español, con alternativas de voz neural que funcionan sin servicios pagos.',
    tags: ['Español', 'Voces locales', 'Sin API'],
    grad: 'linear-gradient(135deg,#4338ca,#0ea5e9)',
  },
  {
    icon: '🖼️',
    title: 'Biblioteca con licencia',
    desc: 'Imágenes y clips de Wikimedia, Openverse e Internet Archive guardando autor y licencia.',
    tags: ['CC', 'Dominio público', 'Créditos'],
    grad: 'linear-gradient(135deg,#065f46,#0d9488)',
  },
  {
    icon: '⚡',
    title: 'Serie en piloto automático',
    desc: 'Define canal, nicho y cadencia: la cola prepara los siguientes episodios sola.',
    tags: ['Cola', 'Calendario', 'Reanudable'],
    grad: 'linear-gradient(135deg,#b45309,#f59e0b)',
  },
  {
    icon: '📦',
    title: 'Exportación completa',
    desc: 'MP4, SRT/VTT, guion, fuentes, miniatura, metadatos e informe de calidad en un ZIP.',
    tags: ['MP4', 'SRT', 'ZIP'],
    grad: 'linear-gradient(135deg,#1e3a8a,#3b82f6)',
  },
];

const STEPS = [
  {
    title: 'Elige un nicho',
    desc: 'La investigación propone temas con potencial y ángulos concretos para tu canal.',
  },
  {
    title: 'Genera el guion',
    desc: 'Un guion por escenas con gancho, desarrollo y cierre, más notas de fuentes verificables.',
  },
  {
    title: 'Renderiza y publica',
    desc: 'Voz, visuales, subtítulos y música se montan solos; descargas el MP4 y el ZIP completo.',
  },
];

const FEATURES = [
  {
    icon: '🎙️',
    title: 'Voces locales',
    desc: 'espeak-ng incluido con cinco voces y soporte opcional de Piper para una voz más natural.',
  },
  {
    icon: '🎨',
    title: 'Identidad de canal',
    desc: 'Paleta, tipografía, formato y voz guardados por canal: cada serie mantiene su estilo.',
  },
  {
    icon: '💬',
    title: 'Subtítulos quemados',
    desc: 'SRT y VTT sincronizados y renderizados dentro del vídeo con tipografía y contorno legibles.',
  },
  {
    icon: '✍️',
    title: 'Guiones editables',
    desc: 'Cambia cualquier escena, acorta o alarga, y regenera solo esa parte sin rehacer el vídeo.',
  },
  {
    icon: '🔁',
    title: 'Render reanudable',
    desc: 'Caché por escena: si algo falla, retoma desde donde quedó en lugar de empezar de cero.',
  },
  {
    icon: '🌐',
    title: 'Producción en español',
    desc: 'Guiones, narración, interfaz y subtítulos en español.',
  },
  {
    icon: '🎚️',
    title: 'Calidad controlada',
    desc: '1080x1920 o 1920x1080, bitrate ajustable e informe de calidad con advertencias reales.',
  },
  {
    icon: '🔒',
    title: 'Sin APIs pagas',
    desc: 'Voz, subtítulos y montaje usan herramientas libres en el entorno donde instalás la app; no dependen de créditos comerciales.',
  },
  {
    icon: '📅',
    title: 'Calendario editorial',
    desc: 'Programa episodios por canal y deja que la cola los prepare en el orden previsto.',
  },
];

const AUTOPILOT = [
  { title: 'Conecta tus canales', desc: 'Un canal por nicho, con su voz, formato y cadencia de publicación.' },
  { title: 'Define el tema', desc: 'Investigación, guion y escenas se generan a partir de un solo campo.' },
  { title: 'Deja correr la cola', desc: 'El worker renderiza en segundo plano y te avisa cuando el MP4 está listo.' },
];

const FAQ = [
  {
    q: '¿Qué es AITuber Libre?',
    a: 'Un estudio de vídeo automático que corre en tu propia máquina: investiga un nicho, escribe el guion por escenas, genera la voz, monta los visuales y los subtítulos, y te entrega el MP4 con todo su paquete de publicación.',
  },
  {
    q: '¿Necesito tarjeta de crédito o créditos?',
    a: 'El software no cobra créditos ni suscripciones. Para evitar pagar hosting, ejecutalo en tu propia PC; el render consume sus recursos. Los servicios externos y la publicación en YouTube mantienen sus propias condiciones y cuotas.',
  },
  {
    q: '¿Cuánto tarda en renderizar un vídeo?',
    a: 'Depende de la duración, resolución y potencia de tu PC. El render se procesa escena por escena en segundo plano y la cola continúa aunque cierres la pestaña, mientras la PC siga encendida.',
  },
  {
    q: '¿Qué pasa si el render falla a la mitad?',
    a: 'Cada escena se guarda en caché. Al reintentar se reutilizan las escenas ya terminadas y solo se recalcula lo que falta, en lugar de empezar de cero.',
  },
  {
    q: '¿Puedo usar mi propia voz?',
    a: 'Todavía no permite clonar ni cargar tu propia voz. Usa espeak-ng local y ofrece Piper como voz neural española opcional.',
  },
  {
    q: '¿De dónde salen las imágenes?',
    a: 'De fuentes con licencia clara: Wikimedia Commons, Openverse e Internet Archive. Cada recurso guarda autor, licencia y enlace, y se incluye en el informe del proyecto.',
  },
  {
    q: '¿En qué idioma puedo generar?',
    a: 'La aplicación está limitada intencionalmente al español, tanto en la narración como en los subtítulos y la interfaz.',
  },
  {
    q: '¿Puedo publicar en YouTube, TikTok e Instagram?',
    a: 'La publicación automática disponible es YouTube mediante OAuth y está sujeta a la cuota gratuita de Google. Para TikTok, Instagram y Facebook se exporta el MP4 y se publica manualmente; todavía no hay integración directa.',
  },
  {
    q: '¿Hay una API?',
    a: 'La app expone su propia API HTTP local para proyectos, escenas, cola y exportación, así que puedes automatizar el flujo desde tus propios scripts.',
  },
];

export default function Landing({ go }: { go: Go }) {
  const [menuOpen, setMenuOpen] = useState(false);


  const scrollTo = (target: string) => {
    setMenuOpen(false);
    const el = document.getElementById(target);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const openStudio = () => go('inicio');

  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-nav-inner">
          <button className="lp-logo" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <span className="lp-logo-mark">A</span>
            AITuber<span className="lp-logo-libre">Libre</span>
          </button>

          <nav className="lp-nav-links">
            {NAV_LINKS.map((l) => (
              <button key={l.target} onClick={() => scrollTo(l.target)}>
                {l.label}
              </button>
            ))}
          </nav>

          <div className="lp-nav-actions">
            <button className="lp-btn lp-btn-ghost lp-hide-sm" onClick={openStudio}>
              Abrir estudio
            </button>
            <button className="lp-btn lp-btn-primary" onClick={openStudio}>
              Comienza gratis
            </button>
            <button
              className="lp-burger"
              aria-label="Menú"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
            >
              ☰
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav className="lp-mobile">
            {NAV_LINKS.map((l) => (
              <button key={l.target} onClick={() => scrollTo(l.target)}>
                {l.label}
              </button>
            ))}
            <button onClick={openStudio}>Abrir estudio</button>
          </nav>
        )}
      </header>

      <section className="lp-hero">
        <span className="lp-badge">
          <span className="lp-dot" /> Software libre · sin créditos de IA ni suscripciones
        </span>
        <h1 className="lp-h1">
          Crea Shorts sin rostro <span className="lp-grad">en piloto automático</span>
        </h1>
        <p className="lp-sub">
          Genera shorts y videos largos en minutos con voces locales, visuales con licencia, subtítulos
          sincronizados y transiciones limpias. Todo el flujo está en español.
        </p>
        <div className="lp-cta-row">
          <button className="lp-btn lp-btn-primary lp-btn-lg" onClick={openStudio}>
            Comienza Gratis →
          </button>
          <button className="lp-btn lp-btn-ghost lp-btn-lg" onClick={() => scrollTo('plantillas')}>
            Ver plantillas
          </button>
        </div>
        <p className="lp-fineprint">Sin tarjeta de crédito · Sin APIs de IA pagas · Herramientas libres</p>

        <div className="lp-platforms">
          <span>Exportar para · publicación manual salvo YouTube</span>
          {PLATFORMS.map((p) => (
            <span className="lp-chip" key={p}>
              {p}
            </span>
          ))}
        </div>

        <div className="lp-phones">
          {HERO_CARDS.map((c) => (
            <div className="lp-phone" key={c.caption} style={{ background: c.grad }}>
              <span className="lp-phone-tag">{c.tag}</span>
              <div className="lp-wave">
                {Array.from({ length: 14 }).map((_, i) => (
                  <i key={i} style={{ height: 5 + ((i * 7) % 17) }} />
                ))}
              </div>
              <p className="lp-phone-cap">{c.caption}</p>
              <span className="lp-phone-dur">{c.dur}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-section lp-center" id="plantillas">
        <p className="lp-eyebrow">Plantillas</p>
        <h2 className="lp-h2">Un estudio completo para Shorts en español.</h2>
        <p className="lp-lead">
          Elige un formato y el estudio se encarga del resto: guion, voz, visuales, subtítulos y montaje.
        </p>
        <div className="lp-tpl-grid">
          {TEMPLATES.map((t) => (
            <article className="lp-tpl" key={t.title}>
              <div className="lp-thumb" style={{ background: t.grad }}>
                <span aria-hidden>{t.icon}</span>
              </div>
              <h3>{t.title}</h3>
              <p>{t.desc}</p>
              <div className="lp-pills">
                {t.tags.map((tag) => (
                  <span className="lp-pill" key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-section lp-center">
        <p className="lp-eyebrow">Cómo funciona</p>
        <h2 className="lp-h2">De idea a video en minutos</h2>
        <p className="lp-lead">Tres pasos. Editor por escenas, render local y exportación lista para revisar.</p>
        <div className="lp-steps">
          {STEPS.map((s, i) => (
            <article className="lp-step" key={s.title}>
              <span className="lp-num">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-section" id="funciones">
        <p className="lp-eyebrow">Funciones</p>
        <h2 className="lp-h2">Todo lo que necesitas en una app</h2>
        <p className="lp-lead">
          Un solo lugar para investigar, escribir, narrar, montar y exportar. Sin saltar entre cinco
          herramientas.
        </p>
        <div className="lp-feat-grid">
          {FEATURES.map((f) => (
            <article className="lp-feat" key={f.title}>
              <span className="lp-ic" aria-hidden>
                {f.icon}
              </span>
              <div>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-section" id="autopilot">
        <div className="lp-split">
          <div>
            <p className="lp-eyebrow">Piloto automático</p>
            <h2 className="lp-h2">Haz crecer tus canales en piloto automático</h2>
            <p className="lp-lead">
              Un canal por nicho, una cadencia clara y una cola que no se detiene. El estudio prepara los
              episodios y tú solo revisas y publicas.
            </p>
            <div className="lp-auto-list">
              {AUTOPILOT.map((a, i) => (
                <div className="lp-auto-item" key={a.title}>
                  <span className="lp-num">{i + 1}</span>
                  <div>
                    <h3>{a.title}</h3>
                    <p>{a.desc}</p>
                  </div>
                </div>
              ))}
            </div>
            <button className="lp-btn lp-btn-primary" onClick={openStudio}>
              Probar el piloto automático
            </button>
          </div>

          <div className="lp-mock" aria-hidden>
            <div className="lp-mock-head">
              <strong>Cola de render</strong>
              <span className="lp-live">EJEMPLO</span>
            </div>
            <div className="lp-mock-row">
              <span className="lp-dotp" style={{ background: '#22d3ee' }} />
              <div>
                <div className="t">Historia · Ep. 12</div>
                <div className="s">Escena 3 de 5 · subtítulos</div>
              </div>
              <span className="lp-st">62%</span>
            </div>
            <div className="lp-bar">
              <span style={{ width: '62%' }} />
            </div>
            <div className="lp-mock-row">
              <span className="lp-dotp" style={{ background: '#8b5cf6' }} />
              <div>
                <div className="t">Shorts · 3 inventos</div>
                <div className="s">Voz generada · pendiente de montaje</div>
              </div>
              <span className="lp-st">en cola</span>
            </div>
            <div className="lp-mock-row">
              <span className="lp-dotp" style={{ background: '#4ade80' }} />
              <div>
                <div className="t">Documental · Ruta de la Seda</div>
                <div className="s">Ejemplo de exportación</div>
              </div>
              <span className="lp-st">listo</span>
            </div>
            <div className="lp-mock-foot">
              <span>Datos de ejemplo</span>
              <span>Estados ilustrativos</span>
              <span>0 créditos externos</span>
            </div>
          </div>
        </div>
      </section>

<section className="lp-section lp-center" id="costo">
        <p className="lp-eyebrow">Gratis de verdad</p>
        <h2 className="lp-h2">Sin tokens, créditos ni suscripciones</h2>
        <p className="lp-lead">
          La producción se ejecuta con herramientas locales y software libre. No hay planes Pro,
          límites de uso de proveedores ni claves de APIs de generación. YouTube requiere únicamente
          autorizar tu propia cuenta para publicar.
        </p>
        <div className="lp-tpl-grid">
          <article className="lp-tpl"><div className="lp-thumb">🖥️</div><h3>Procesamiento local</h3><p>FFmpeg, narración local, subtítulos y montaje en tu equipo.</p></article>
          <article className="lp-tpl"><div className="lp-thumb">🆓</div><h3>Sin créditos</h3><p>No hay saldo, tokens comerciales, planes ni pagos por cada video.</p></article>
          <article className="lp-tpl"><div className="lp-thumb">📱</div><h3>Control desde el celular</h3><p>Configurá, revisá y controlá la producción desde una interfaz adaptable.</p></article>
        </div>
      </section>

      <section className="lp-section" id="faq">
        <div className="lp-center">
          <p className="lp-eyebrow">Preguntas</p>
          <h2 className="lp-h2">Preguntas frecuentes</h2>
          <p className="lp-lead">Todo lo que suele preguntarse antes del primer render.</p>
        </div>
        <div className="lp-faq">
          {FAQ.map((f) => (
            <details key={f.q}>
              <summary>{f.q}</summary>
              <div className="lp-a">{f.a}</div>
            </details>
          ))}
        </div>
      </section>

      <section className="lp-final">
        <div className="lp-final-inner">
          <h2 className="lp-h2">Tu primer video está a un clic</h2>
          <p className="lp-lead lp-center-lead">
            Abre el estudio, elige un nicho y deja que la cola haga el trabajo.
          </p>
          <div className="lp-cta-row">
            <button className="lp-btn lp-btn-primary lp-btn-lg" onClick={openStudio}>
              Comienza Gratis →
            </button>
            <button className="lp-btn lp-btn-ghost lp-btn-lg" onClick={() => scrollTo('costo')}>
              Ver cómo funciona
            </button>
          </div>
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-foot-inner">
          <div>
            <div className="lp-logo">
              <span className="lp-logo-mark">A</span>
              AITuber<span className="lp-logo-libre">Libre</span>
            </div>
            <p className="lp-foot-desc">
              Estudio de vídeo automático con software libre. Investigación, guion, voz, montaje y
              exportación en un solo lugar.
            </p>
            <div className="lp-pills">
              <span className="lp-pill">FFmpeg</span>
              <span className="lp-pill">espeak-ng</span>
              <span className="lp-pill">FastAPI</span>
              <span className="lp-pill">React</span>
            </div>
          </div>
          <div>
            <h4>Producto</h4>
            <ul>
              <li>
                <button onClick={() => scrollTo('funciones')}>Funciones</button>
              </li>
              <li>
                <button onClick={() => scrollTo('plantillas')}>Plantillas</button>
              </li>
              <li>
                <button onClick={() => scrollTo('costo')}>Costo cero</button>
              </li>
              <li>
                <button onClick={() => scrollTo('autopilot')}>Piloto automático</button>
              </li>
            </ul>
          </div>
          <div>
            <h4>Estudio</h4>
            <ul>
              <li>
                <button onClick={() => go('proyectos')}>Proyectos</button>
              </li>
              <li>
                <button onClick={() => go('canales')}>Canales</button>
              </li>
              <li>
                <button onClick={() => go('cola')}>Cola de render</button>
              </li>
              <li>
                <button onClick={() => go('biblioteca')}>Biblioteca</button>
              </li>
            </ul>
          </div>
          <div>
            <h4>Recursos</h4>
            <ul>
              <li>
                <button onClick={() => scrollTo('faq')}>Preguntas frecuentes</button>
              </li>
              <li>
                <button onClick={() => go('ajustes')}>Ajustes y diagnóstico</button>
              </li>
              <li>
                <button onClick={() => go('analitica')}>Analítica</button>
              </li>
            </ul>
          </div>
        </div>
        <div className="lp-foot-bottom">
          <span>© {new Date().getFullYear()} AITuber Libre · Software libre, sin créditos.</span>
          <span>Español · es</span>
        </div>
      </footer>
    </div>
  );
}
