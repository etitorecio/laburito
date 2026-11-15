import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { Badge, Card, Empty, Msg } from '../ui';

type LinkedAccount = { channel_id: number; youtube_channel_id: string; channel_title: string; workspace_name: string };
type WorkspaceChannel = { id: number; name: string; topic: string; account: LinkedAccount | null };

export default function Accounts() {
  const [channels, setChannels] = useState<WorkspaceChannel[]>([]);
  const [oauthReady, setOauthReady] = useState(false);
  const [oauthConfigLoaded, setOauthConfigLoaded] = useState(false);
  const [missingEnv, setMissingEnv] = useState<string[]>([]);
  const [redirectUri, setRedirectUri] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.get<{ accounts: WorkspaceChannel[]; oauth_ready: boolean; missing_env: string[]; redirect_uri: string }>('/api/youtube/accounts');
      setChannels(result.accounts);
      setOauthReady(result.oauth_ready);
      setOauthConfigLoaded(true);
      setMissingEnv(result.missing_env || []);
      setRedirectUri(result.redirect_uri || '');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function connect(channel: WorkspaceChannel) {
    if (!oauthConfigLoaded) {
      setError("No se pudo comprobar la configuración OAuth del servidor. Actualizá la pantalla e intentá de nuevo.");
      return;
    }
    if (!oauthReady) {
      setError("Faltan las credenciales OAuth de YouTube en el servidor: " + missingEnv.join(", "));
      return;
    }
    setBusyId(channel.id); setError(''); setOk('');
    try {
      const result = await api.post<{ authorization_url: string }>(`/api/youtube/oauth/start?channel_id=${channel.id}`, {});
      window.location.assign(result.authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setBusyId(null);
    }
  }

  async function disconnect(channel: WorkspaceChannel) {
    if (!window.confirm(`¿Desconectar la cuenta de YouTube asignada a «${channel.name}»?`)) return;
    setBusyId(channel.id); setError(''); setOk('');
    try {
      await api.post(`/api/youtube/disconnect?channel_id=${channel.id}`, {});
      setOk(`Cuenta desconectada de ${channel.name}. La otra cuenta no se modifica.`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      {!loading && oauthConfigLoaded && !oauthReady && <Card title="Falta configurar OAuth de YouTube" sub="La conexión no se habilita hasta completar estos datos en el servidor.">
        <p>Configurá estas variables de entorno: <strong>{missingEnv.join(", ")}</strong>.</p>
        <p>Después, en Google Cloud Console, agregá esta URL exacta a las URI de redireccionamiento autorizadas del cliente OAuth:</p>
        <p><code>{redirectUri}</code></p>
        <p className="muted">No pegues el secreto de Google en esta pantalla ni en el chat. Reiniciá la aplicación después de guardar las variables.</p>
      </Card>}
      <Card title="Dos canales, dos cuentas independientes" sub="Cada fábrica conserva su propia autorización de Google. Conectar o desconectar una cuenta no cambia la otra.">
        {loading ? <Empty>Comprobando canales y conexiones…</Empty> : channels.length ? (
          <div className="stack">
            {channels.map((channel) => (
              <section className="card inset" key={channel.id}>
                <div className="row center between">
                  <div>
                    <strong>{channel.name}</strong>
                    <p className="muted" style={{ margin: '4px 0 0' }}>{channel.topic}</p>
                  </div>
                  {channel.account ? <Badge tone="ok">Conectado</Badge> : <Badge tone="warn">Sin conectar</Badge>}
                </div>
                {channel.account ? (
                  <div className="stack">
                    <p><strong>{channel.account.channel_title}</strong><br /><span className="muted">Cuenta de YouTube asignada exclusivamente a {channel.name}.</span></p>
                    <button className="btn ghost" disabled={busyId !== null} onClick={() => void disconnect(channel)}>{busyId === channel.id ? 'Desconectando…' : 'Desconectar esta cuenta'}</button>
                  </div>
                ) : (
                  <button className="btn primary" disabled={busyId !== null || !oauthConfigLoaded || !oauthReady} onClick={() => void connect(channel)}>{busyId === channel.id ? 'Abriendo Google…' : `Conectar cuenta de Google para ${channel.name}`}</button>
                )}
              </section>
            ))}
          </div>
        ) : <Empty>No hay canales internos creados.</Empty>}
        <button className="btn ghost" disabled={busyId !== null || loading} onClick={() => void load()}>Actualizar conexiones</button>
      </Card>
      <Card title="Cómo conectarlas" sub="Hacelo una vez por cada canal.">
        <ol>
          <li>Conectá la cuenta Google que administra el canal de Historias.</li>
          <li>Volvé a esta pantalla y conectá la otra cuenta Google para Frutinovelas.</li>
          <li>En cada fábrica, la publicación se dirige a la cuenta asignada a su canal interno.</li>
        </ol>
        <p className="muted">URI de redirección autorizada en Google Cloud: <code>{redirectUri}</code></p>
        <p className="muted">Los permisos OAuth se guardan por separado en el servidor. Nunca compartas contraseñas ni secretos de Google en el chat.</p>
      </Card>
    </div>
  );
}
