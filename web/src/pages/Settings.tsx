import { useEffect, useState } from 'react';
import { api, getToken, setToken, type Diagnostics, type Meta } from '../api';
import { Badge, Card, Empty, Field, Msg } from '../ui';

export default function Settings() {
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [token, setTokenValue] = useState(getToken());
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [youtube, setYoutube] = useState<{ available: boolean; missing_env: string[]; note: string } | null>(null);
  const [deviceAuth, setDeviceAuth] = useState<{ user_code: string; verification_url: string; expires_in: number; interval: number } | null>(null);
  const [youtubeBusy, setYoutubeBusy] = useState(false);

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
      setYoutube(p.destinations.find((x) => x.id === 'youtube') || null);
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
      const res = await api.put<{ settings: Record<string, string> }>('/api/settings', values);
      setValues(res.settings);
      setOk('Configuración guardada.');
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function startYoutubeConnection() {
    setError(''); setOk(''); setYoutubeBusy(true);
    try {
      const result = await api.post<{ user_code: string; verification_url: string; expires_in: number; interval: number }>('/api/youtube/device/start');
      setDeviceAuth(result);
      setOk('Código generado. Abrí Google, ingresalo y después volvé para comprobar la autorización.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setYoutubeBusy(false);
    }
  }

  async function checkYoutubeConnection() {
    setError(''); setOk(''); setYoutubeBusy(true);
    try {
      const result = await api.post<{ status: string; message: string; wait_seconds?: number }>('/api/youtube/device/poll');
      if (result.status === 'connected') {
        setDeviceAuth(null);
        setOk(result.message);
        await load();
      } else if (result.status === 'denied' || result.status === 'expired') {
        setDeviceAuth(null);
        setError(result.message);
      } else {
        setOk(result.message);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setYoutubeBusy(false);
    }
  }

  function saveToken() {
    setToken(token.trim());
    setOk(token.trim() ? 'Token guardado en este navegador.' : 'Token eliminado.');
    void load();
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
              <Badge tone={diag.token_configured ? 'ok' : 'info'}>{diag.token_configured ? 'Token activo' : 'Sin token'}</Badge>
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
                  <tr><th>Ollama (opcional)</th><td>{diag.ollama.available ? 'disponible' : 'no detectado'}</td></tr>
                  <tr><th>Cola</th><td>{diag.worker.queued} en cola · {diag.worker.running} en curso · {diag.worker.done} completadas · {diag.worker.failed} con error</td></tr>
                  <tr><th>Voz</th><td style={{ whiteSpace: 'normal' }}>{diag.tts.note}</td></tr>
                </tbody>
              </table>
            </div>
            <small className="muted">{diag.note}</small>
          </div>
        )}
      </Card>

      <Card title="Acceso" sub="Protección opcional con token. Si el servidor define APP_TOKEN o AITUBER_TOKEN, la interfaz lo pide.">
        <div className="row">
          <Field label="Token de acceso" hint={meta?.auth_required ? 'El servidor exige token: pegalo acá.' : 'Opcional: solo si configuraste APP_TOKEN o AITUBER_TOKEN en el servidor.'}>
            <input type="password" value={token} onChange={(e) => setTokenValue(e.target.value)} placeholder="token" />
          </Field>
          <div className="field" style={{ justifyContent: 'flex-end' }}>
            <button className="btn primary" onClick={saveToken}>Guardar token</button>
          </div>
        </div>
      </Card>

      <Card title="Conectar YouTube" sub="Vinculá tu canal una sola vez para que el Autopiloto pueda subir videos automáticamente.">
        <div className="pill-row">
          <Badge tone={youtube?.available ? 'ok' : 'warn'}>{youtube?.available ? 'YouTube conectado' : 'Falta configurar la conexión'}</Badge>
          {youtube?.missing_env.map((item) => <Badge key={item} tone="warn">{item}</Badge>)}
        </div>
        <p className="muted">En Google Cloud habilitá YouTube Data API v3 y creá credenciales OAuth del tipo <b>TVs y dispositivos de entrada limitada</b>. En AppJet → configuración del proyecto → variables de entorno, agregá YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET y APP_TOKEN. Después ingresá el APP_TOKEN en la sección Acceso.</p>
        <p className="muted">Tocá Iniciar conexión. Google mostrará un código y una dirección: abrí esa dirección, ingresá el código exactamente como aparece y autorizá Laburito. Este flujo no necesita dominio propio ni URL de redirección.</p>
        <p className="muted">Google solicita el permiso de administración de YouTube para poder subir videos. No recibe tu contraseña; el token de actualización queda guardado del lado del servidor.</p>
        <p className="muted">Importante: si el consentimiento OAuth queda en modo Testing, los refresh tokens pueden vencer a los 7 días. Para automatización continua, revisá el estado de publicación y la verificación que Google exija.</p>
        <div className="row">
          <button className="btn primary" disabled={youtubeBusy || !meta?.auth_required || !youtube || youtube.missing_env.includes("YOUTUBE_CLIENT_ID") || youtube.missing_env.includes("YOUTUBE_CLIENT_SECRET")} onClick={() => void startYoutubeConnection()}>{youtubeBusy ? 'Procesando…' : 'Iniciar conexión'}</button>
          <button className="btn ghost" onClick={() => void load()}>Comprobar conexión</button>
        </div>
        {deviceAuth && (
          <div className="stack" style={{ marginTop: 12 }}>
            <p><b>Código de Google (respetá mayúsculas y guion):</b></p>
            <title size="2xl" tabularNums>{deviceAuth.user_code}</title>
            <p><a href={deviceAuth.verification_url} target="_blank" rel="noreferrer">{deviceAuth.verification_url}</a></p>
            <p className="muted">Tenés aproximadamente {Math.ceil(deviceAuth.expires_in / 60)} minutos. Después de autorizar, volvé acá y comprobá la conexión.</p>
            <button className="btn primary" disabled={youtubeBusy} onClick={() => void checkYoutubeConnection()}>Ya autoricé, comprobar</button>
          </div>
        )}
      </Card>

      <Card title="Producción" sub="Parámetros usados por el guionista y el render.">
        <div className="row">
          <Field label="Idioma por defecto">
            <select value={values.default_language || 'es'} onChange={(e) => setValues({ ...values, default_language: e.target.value })}>
              <option value="es">Español</option>
              <option value="en">Inglés</option>
              <option value="pt">Portugués</option>
            </select>
          </Field>
          <Field label="Voz por defecto">
            <select value={values.default_voice || 'es'} onChange={(e) => setValues({ ...values, default_voice: e.target.value })}>
              {(meta?.voices ?? []).map((v) => (
                <option key={v.id} value={v.id} disabled={!v.available}>{v.label}{v.available ? '' : ' (no instalada)'}</option>
              ))}
            </select>
          </Field>
          <Field label="Volumen de música (0-1)">
            <input type="number" step="0.01" min="0" max="1" value={values.music_volume || '0.12'} onChange={(e) => setValues({ ...values, music_volume: e.target.value })} />
          </Field>
        </div>
        <div className="row">
          <Field label="Estilo de subtítulos por defecto">
            <select value={values.caption_style || 'documental'} onChange={(e) => setValues({ ...values, caption_style: e.target.value })}>
              {(meta?.caption_styles ?? [{ id: 'documental', label: 'Documental' }]).map((c) => (
                <option key={c.id} value={c.id}>{c.label}</option>
              ))}
            </select>
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
          <Field label="Transición por defecto">
            <select value={values.default_transition || 'fundido'} onChange={(e) => setValues({ ...values, default_transition: e.target.value })}>
              {(meta?.transitions ?? [{ id: 'fundido', label: 'Fundido' }]).map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className="row">
          <Field label="Ollama local (opcional)" hint="URL de Ollama con el modelo llama3.2 instalado. Es opcional, local y sin pagos.">
            <input value={values.ollama_url || ''} onChange={(e) => setValues({ ...values, ollama_url: e.target.value })} placeholder="http://127.0.0.1:11434" />
          </Field>
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
