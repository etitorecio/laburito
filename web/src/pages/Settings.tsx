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

  async function load() {
    try {
      const [d, m] = await Promise.all([api.get<Diagnostics>('/api/diagnostics'), api.get<Meta>('/api/meta')]);
      setDiag(d);
      setMeta(m);
      setValues(m.settings);
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

  function saveToken() {
    setToken(token.trim());
    setOk(token.trim() ? 'Token guardado en este navegador.' : 'Token eliminado.');
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

      <Card title="Acceso" sub="Protección opcional con token. Si el servidor define AITUBER_TOKEN, la interfaz lo pide.">
        <div className="row">
          <Field label="Token de acceso" hint={meta?.auth_required ? 'El servidor exige token: pegalo acá.' : 'Opcional: solo si configuraste AITUBER_TOKEN en el servidor.'}>
            <input type="password" value={token} onChange={(e) => setTokenValue(e.target.value)} placeholder="token" />
          </Field>
          <div className="field" style={{ justifyContent: 'flex-end' }}>
            <button className="btn primary" onClick={saveToken}>Guardar token</button>
          </div>
        </div>
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
          <Field label="Estilo de subtítulos">
            <select value={values.caption_style || 'documental'} onChange={(e) => setValues({ ...values, caption_style: e.target.value })}>
              <option value="documental">Documental (bloques cortos)</option>
              <option value="short">Short (frases grandes)</option>
              <option value="minimo">Mínimo (solo lo esencial)</option>
            </select>
          </Field>
          <Field label="Ollama local (opcional)" hint="URL de un Ollama propio, p. ej. http://127.0.0.1:11434. Nunca se usa un servicio pago.">
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

      <Card title="Música de fondo" sub="Colocá archivos libres en la carpeta data/music/ del servidor; se mezclan automáticamente con volumen bajo.">
        <p className="muted" style={{ marginTop: 0 }}>
          La app no descarga música: usá pistas con licencia compatible (por ejemplo Creative Commons) y guardá la atribución en las fuentes del proyecto.
        </p>
      </Card>
    </div>
  );
}
