import { useEffect, useState } from 'react';
import { api, type Diagnostics, type Meta } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';
import CaptionStylePicker from '../components/CaptionStylePicker';
import TransitionPicker from '../components/TransitionPicker';
import VoicePicker from '../components/VoicePicker';

export default function Settings() {
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [youtube, setYoutube] = useState<{ available: boolean; missing_env: string[]; note: string } | null>(null);
  const [youtubeVerified, setYoutubeVerified] = useState(false);
  const [youtubeBusy, setYoutubeBusy] = useState(false);
  const [youtubeOAuthBusy, setYoutubeOAuthBusy] = useState(false);

  async function load() {
    try {
      const [d, m, p] = await Promise.all([
        api.get<Diagnostics>('/api/diagnostics'),
        api.get<Meta>('/api/meta'),
        api.get<{ destinations: { id: string; available: boolean; missing_env: string[]; note: string }[] }>('/api/publish/destinations'),
      ]);
      setDiag(d);
      setMeta(m);
      setValues(m.settings);
      const youtubeDestination = p.destinations.find((x) => x.id === 'youtube') || null;
      setYoutube(youtubeDestination);
      if (youtubeDestination?.available) {
        setYoutubeVerified(false);
        void api.get('/api/youtube/status')
          .then(() => setYoutubeVerified(true))
          .catch(() => setYoutubeVerified(false));
      } else {
        setYoutubeVerified(false);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function save() {
    setError('');
    setOk('');
    try {
      const res = await api.put<Record<string, string>>('/api/settings', { values });
      setValues(res);
      setOk('Configuración guardada.');
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function startYoutubeOAuth() {
    setError(''); setOk(''); setYoutubeOAuthBusy(true);
    try {
      const result = await api.post<{ authorization_url: string; redirect_uri: string }>('/api/youtube/oauth/start', {});
      window.location.assign(result.authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setYoutubeOAuthBusy(false);
    }
  }

  async function testYoutubeConnection() {
    setError(''); setOk(''); setYoutubeBusy(true);
    try {
      const result = await api.get<{ channel_title: string }>('/api/youtube/status');
      setYoutubeVerified(true);
      setOk('Conectado con el canal: ' + result.channel_title);
    } catch (e) {
      setYoutubeVerified(false);
      setError((e as Error).message);
    } finally {
      setYoutubeBusy(false);
    }
  }

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />

      <Card title="Diagnóstico del sistema" sub="Estado real de las herramientas locales." actions={<button className="btn small ghost" onClick={load}>Revisar</button>}>
        {!diag ? (
          <Empty>Consultando…</Empty>
        ) : (
          <div className="stack">
            <div className="pill-row">
              <Badge tone={diag.tts.available ? 'ok' : 'bad'}>TTS: {diag.tts.engine}</Badge>
              <Badge tone={diag.checks.ffmpeg ? 'ok' : 'bad'}>FFmpeg</Badge>
              <Badge tone={diag.font ? 'ok' : 'bad'}>Fuentes</Badge>
              <Badge tone={diag.data_writable ? 'ok' : 'bad'}>Datos escribibles</Badge>
              <Badge tone={diag.worker.worker_alive ? 'ok' : 'warn'}>Worker {diag.worker.worker_alive ? 'activo' : 'detenido'}</Badge>
              <Badge tone={diag.persistence.configured ? 'ok' : 'warn'}>{diag.persistence.configured ? 'Backup externo activo' : 'Sin backup externo'}</Badge>
            </div>
            <div className="table-wrap">
              <table>
                <tbody>
                  <tr><th>Versión</th><td>{diag.version}</td></tr>
                  <tr><th>Python</th><td>{diag.python}</td></tr>
                  <tr><th>Plataforma</th><td>{diag.platform}</td></tr>
                  <tr><th>FFmpeg</th><td>{diag.ffmpeg_version || 'no disponible'}</td></tr>
                  <tr><th>Carpeta de datos</th><td style={{ whiteSpace: 'normal' }}>{diag.data_dir}</td></tr>
                  <tr><th>Espacio libre</th><td>{diag.disk_free_mb} MB</td></tr>
                  <tr><th>Base de datos</th><td>{diag.db_size_kb} KB</td></tr>
                  <tr><th>Persistencia</th><td style={{ whiteSpace: 'normal' }}>{diag.persistence.note}</td></tr>
                  <tr><th>IA local (Qwen)</th><td>{diag.ollama.available ? 'disponible' : 'no detectado'}</td></tr>
                  <tr><th>Cola</th><td>{diag.worker.queued} en cola · {diag.worker.running} en curso · {diag.worker.done} completadas · {diag.worker.failed} con error</td></tr>
                  <tr><th>Voz</th><td style={{ whiteSpace: 'normal' }}>{diag.tts.note}</td></tr>
                </tbody>
              </table>
            </div>
            <small className="muted">{diag.note}</small>
          </div>
        )}
      </Card>

      <Card title="Almacenamiento local" sub="Los proyectos, videos y reglas se guardan en la carpeta de datos de esta instalación.">
        <div className="pill-row">
          <Badge tone={diag?.persistence.local_persistent ? 'ok' : 'warn'}>{diag?.persistence.local_persistent ? 'Disco local persistente activo' : 'Persistencia local por verificar'}</Badge>
        </div>
        <p className="muted">Para no depender de claves de almacenamiento en la nube, ejecutá la aplicación en tu PC con el volumen local ./data. No necesitás Supabase ni otro servicio de almacenamiento. La PC debe permanecer encendida para que el Autopiloto siga trabajando; podés controlarlo desde el celular conectado a la misma red.</p>
      </Card>

      <Card title="Conexión de YouTube" sub="Integración social oficial: vinculá tu canal una sola vez mediante OAuth y Laburito podrá publicar Shorts automáticamente.">
        <div className="pill-row">
          <Badge tone={youtube?.available ? 'ok' : 'warn'}>{youtubeVerified ? 'Canal verificado' : youtube?.available ? 'Credenciales guardadas · falta verificar' : 'Falta configurar la conexión'}</Badge>
          {youtube?.missing_env.map((item) => <Badge key={item} tone="warn">{item}</Badge>)}
        </div>
        <p className="muted">En Google Cloud habilitá YouTube Data API v3 y creá credenciales OAuth de tipo <b>Aplicación web</b>. Agregá como URI de redirección autorizada esta dirección exacta: <code>{window.location.origin}/api/youtube/callback</code>. Si definiste YOUTUBE_REDIRECT_URI en el servidor, usá ese valor en lugar de la dirección calculada. En el archivo .env local configurá YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET. No hace falta ninguna contraseña ni token de IA para usarlo en tu red local.</p>
        <p className="muted">Después de guardar esas variables y reiniciar la app, tocá «Conectar canal con Google». Google te pedirá autorizar el canal una sola vez y Laburito guardará ese permiso en tu carpeta local. Si la pantalla de consentimiento permanece en Testing, Google puede revocar el permiso después de 7 días; para automatización continua revisá el estado de publicación de la app OAuth.</p>
        <p className="muted">La conexión de YouTube sí requiere configurar una vez el Client ID y el Client Secret de tu aplicación OAuth de Google en el archivo .env. Son credenciales de publicación de Google, no claves ni créditos de IA: no intervienen en la escritura, voz ni render. Después solo tocás «Conectar canal» y autorizás tu cuenta; no tenés que copiar ni pegar códigos o refresh tokens. La autorización queda guardada localmente. Si la pantalla de consentimiento permanece en Testing, Google puede revocar el acceso después de 7 días.</p>
        <p className="muted">Importante: hacé la primera conexión desde el navegador de la notebook usando la dirección local «localhost», no desde la IP que abrís en el celular. Google permite redirecciones HTTP locales para localhost, pero puede rechazar una IP privada de la red. Una vez autorizado el canal, podés seguir manejando el Autopiloto desde el teléfono.</p>
        <div className="row">
          <button className="btn primary" disabled={youtubeOAuthBusy || !!youtube?.missing_env.includes('YOUTUBE_CLIENT_ID') || !!youtube?.missing_env.includes('YOUTUBE_CLIENT_SECRET')} onClick={() => void startYoutubeOAuth()}>{youtubeOAuthBusy ? 'Abriendo Google…' : 'Conectar canal con Google'}</button>
          <button className="btn ghost" disabled={youtubeBusy || !youtube?.available} onClick={() => void testYoutubeConnection()}>Comprobar conexión real</button>
        </div>
        
      </Card>

      <Card title="Voz neural española" sub="Mejorá la narración sin pagar APIs ni servicios de voz.">
        <div className="pill-row">
          <Badge tone={diag?.tts.piper_available ? 'ok' : 'warn'}>{diag?.tts.piper_available ? 'Voz neural instalada' : diag?.tts.piper_installed ? 'Motor listo · falta descargar la voz' : 'Motor Piper pendiente de despliegue'}</Badge>
        </div>
        <p className="muted">Piper DaveFX es una voz neural en español de España. La descarga inicial de aproximadamente 63 MB se inicia automáticamente; después funciona localmente, sin conexión ni créditos. El modelo y sus datos son CC0: no requieren atribución. Durante la síntesis consume más RAM que espeak-ng.</p>
        <p className="muted">Cuando termine la descarga, la voz aparece automáticamente en el selector del Autopiloto. Mientras tanto, Laburito sigue usando espeak-ng.</p>
      </Card>

      <Card title="Producción" sub="Parámetros usados por el guionista y el render.">
        <div className="row">
          <Field label="Idioma de producción">
            <p className="muted" style={{ margin: 0 }}>Español (fijo para todos los Shorts y proyectos).</p>
          </Field>
          <Field label="Voz por defecto">
            <VoicePicker
              options={meta?.voices ?? []}
              value={values.default_voice || 'es'}
              onChange={(value) => setValues({ ...values, default_voice: value })}
              compact
            />
          </Field>
          <Field label="Volumen de música (0-1)">
            <input type="number" step="0.01" min="0" max="1" value={values.music_volume || '0.12'} onChange={(e) => setValues({ ...values, music_volume: e.target.value })} />
          </Field>
        </div>
        <div className="row">
          <Field label="Estilo de subtítulos por defecto">
            <CaptionStylePicker
              options={meta?.caption_styles ?? [{ id: 'documental', label: 'Documental' }]}
              value={values.caption_style || 'documental'}
              onChange={(value) => setValues({ ...values, caption_style: value })}
              compact
            />
          </Field>
          <Field label="Plantilla por defecto">
            <select value={values.default_template || 'shorts'} onChange={(e) => setValues({ ...values, default_template: e.target.value })}>
              {(meta?.templates ?? [{ id: 'shorts', label: 'Shorts' }]).map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Resolución por defecto">
            <select value={values.default_resolution || '1080p'} onChange={(e) => setValues({ ...values, default_resolution: e.target.value })}>
              {(meta?.resolutions ?? [{ id: '1080p', label: '1080p' }]).map((r) => (
                <option key={r.id} value={r.id}>{r.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Movimiento por defecto">
            <TransitionPicker
              options={meta?.transitions ?? [{ id: 'fundido', label: 'Fundido' }]}
              value={values.default_transition || 'fundido'}
              onChange={(value) => setValues({ ...values, default_transition: value })}
              compact
            />
          </Field>
        </div>
        <p className="muted">La IA de escritura usa Qwen 2.5 1.5B en tu PC mediante Ollama. Docker lo descarga automáticamente la primera vez (aprox. 1 GB); no necesitás claves, tokens de IA ni créditos.</p>
        <div className="row">
          <Field label="Copia de seguridad automática">
            <select value={values.auto_backup || '1'} onChange={(e) => setValues({ ...values, auto_backup: e.target.value })}>
              <option value="1">Sí, antes de cada render</option>
              <option value="0">No</option>
            </select>
          </Field>
        </div>
        <div className="row">
          <button className="btn primary" onClick={save}>Guardar configuración</button>
          <button className="btn ghost" onClick={async () => { const r = await api.post<{ path: string }>('/api/backup'); setOk(`Copia creada: ${r.path}`); }}>Crear copia de seguridad</button>
        </div>
      </Card>

      <Card title="Música de fondo" sub="Elegí una cama generada localmente, usá tus archivos de data/music/ o desactivá la música en cada proyecto.">
        <p className="muted" style={{ marginTop: 0 }}>
          La app no descarga música: las camas se sintetizan con FFmpeg en el servidor y las pistas propias deben tener licencia
          compatible (por ejemplo Creative Commons), con la atribución guardada en las fuentes del proyecto.
        </p>
        <div className="pill-row">
          {(meta?.music_beds ?? []).map((m) => <Badge key={m.id} tone="info">Cama: {m.label}</Badge>)}
          {(meta?.music_library ?? []).length === 0 ? (
            <Badge tone="warn">data/music/ vacía</Badge>
          ) : (
            (meta?.music_library ?? []).map((f) => <Badge key={f} tone="ok">{f}</Badge>)
          )}
        </div>
      </Card>
    </div>
  );
}
