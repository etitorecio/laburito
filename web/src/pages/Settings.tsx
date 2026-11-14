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
  const [youtubeRefreshToken, setYoutubeRefreshToken] = useState("");
  const [youtubeBusy, setYoutubeBusy] = useState(false);
  const [piperBusy, setPiperBusy] = useState(false);

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

  async function saveYoutubeToken() {
    setError(''); setOk(''); setYoutubeBusy(true);
    try {
      const result = await api.post<{ ok: boolean; message: string }>('/api/youtube/token', {
        refresh_token: youtubeRefreshToken.trim(),
      });
      setYoutubeRefreshToken('');
      setOk(result.message);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setYoutubeBusy(false);
    }
  }

  async function installPiperVoice() {
    setError(''); setOk(''); setPiperBusy(true);
    try {
      const result = await api.post<{ installed: boolean; job_id?: number; message: string }>('/api/tts/piper/install');
      setOk(result.job_id ? result.message + ' Tarea #' + result.job_id + ' en la Cola.' : result.message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPiperBusy(false);
    }
  }

  async function testYoutubeConnection() {
    setError(''); setOk(''); setYoutubeBusy(true);
    try {
      const result = await api.get<{ channel_title: string }>('/api/youtube/status');
      setOk('Conectado con el canal: ' + result.channel_title);
      await load();
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

      <Card title="Acceso" sub="Protección del servidor. Para conectar YouTube, APP_TOKEN o AITUBER_TOKEN es obligatorio.">
        <div className="row">
          <Field label="Token de acceso" hint={meta?.auth_required ? 'El servidor exige token: pegalo acá.' : 'Pegalo si configuraste APP_TOKEN o AITUBER_TOKEN en el servidor.'}>
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
        <p className="muted">En Google Cloud habilitá YouTube Data API v3 y creá credenciales OAuth de tipo <b>Aplicación web</b>. Si el consentimiento está en Testing, agregá tu cuenta en Audiencia → Usuarios de prueba. Agregá esta URI autorizada: <code>https://developers.google.com/oauthplayground</code>. En AppJet → variables de entorno, configurá YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET y APP_TOKEN. Guardá los cambios y pegá el APP_TOKEN en la sección Acceso.</p>
        <p className="muted">Abrí el <a href="https://developers.google.com/oauthplayground" target="_blank" rel="noreferrer">OAuth 2.0 Playground oficial de Google</a>. En el engranaje, activá «Use your own OAuth credentials», pegá tu Client ID y Client Secret, elegí Access type «Offline» y Force prompt «Consent Screen».</p>
        <p className="muted">En Step 1 ingresá estos permisos: <code>https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly</code>. Tocá «Authorize APIs» y después «Exchange authorization code for tokens». Copiá el Refresh token que aparece y pegalo acá. Usá tus propias credenciales: el Playground revoca los tokens de prueba a las 24 horas si no las configurás.</p>
        <p className="muted">El refresh token es una contraseña de acceso: pegalo solo acá, nunca en el chat. Laburito lo guarda en el servidor y no vuelve a mostrarlo. Si el consentimiento de Google sigue en Testing, los tokens pueden vencer a los 7 días.</p>
        <Field label="Refresh token de YouTube">
          <input type="password" value={youtubeRefreshToken} onChange={(e) => setYoutubeRefreshToken(e.target.value)} placeholder="Pegá aquí el refresh token de Google" autoComplete="off" />
        </Field>
        <div className="row">
          <button className="btn primary" disabled={youtubeBusy || !meta?.auth_required || youtubeRefreshToken.trim().length < 20} onClick={() => void saveYoutubeToken()}>{youtubeBusy ? 'Guardando…' : 'Guardar conexión de YouTube'}</button>
          <button className="btn ghost" disabled={youtubeBusy || !youtube?.available} onClick={() => void testYoutubeConnection()}>Comprobar conexión real</button>
        </div>
      </Card>

      <Card title="Voz neural española" sub="Mejorá la narración sin pagar APIs ni servicios de voz.">
        <div className="pill-row">
          <Badge tone={diag?.tts.piper_available ? 'ok' : 'warn'}>{diag?.tts.piper_available ? 'Voz neural instalada' : diag?.tts.piper_installed ? 'Motor listo · falta descargar la voz' : 'Motor Piper pendiente de despliegue'}</Badge>
        </div>
        <p className="muted">Piper DaveFX es una voz neural en español de España. La descarga inicial ocupa aproximadamente 63 MB; después funciona localmente, sin conexión ni créditos. El modelo y sus datos son CC0: no requieren atribución. Durante la síntesis consume más RAM que espeak-ng.</p>
        <p className="muted">Cuando termine la instalación, entrá al Autopiloto y elegí «Español neural (Piper DaveFX · España)». Si no la instalás, Laburito sigue usando espeak-ng.</p>
        <button className="btn primary" disabled={piperBusy || !meta?.auth_required || !diag?.tts.piper_installed || !!diag?.tts.piper_available} onClick={() => void installPiperVoice()}>{piperBusy ? 'Encolando…' : diag?.tts.piper_available ? 'Voz neural instalada' : 'Instalar voz neural (63 MB)'}</button>
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
