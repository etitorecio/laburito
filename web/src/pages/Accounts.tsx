import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { Badge, Card, Empty, Msg } from '../ui';

type LinkedAccount = { channel_id: number; youtube_channel_id: string; channel_title: string; workspace_name: string };
type FactoryAccount = { id: number; name: string; topic: string; account: LinkedAccount | null };

export default function Accounts() {
  const [factories, setFactories] = useState<FactoryAccount[]>([]);
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
    setOauthConfigLoaded(false);
    setError('');
    try {
      const result = await api.get<{ accounts: FactoryAccount[]; oauth_ready: boolean; missing_env: string[]; redirect_uri: string }>('/api/youtube/accounts');
      setFactories(result.accounts);
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

  async function connect(factory: FactoryAccount) {
    if (!oauthConfigLoaded) {
      setError("No se pudo comprobar la configuración OAuth del servidor. Actualizá la pantalla e intentá de nuevo.");
      return;
    }
    if (!oauthReady) {
      setError("Faltan las credenciales OAuth de Google en el servidor: " + missingEnv.join(", "));
      return;
    }
    setBusyId(factory.id); setError(''); setOk('');
    try {
      const result = await api.post<{ authorization_url: string }>(`/api/youtube/oauth/start?channel_id=${factory.id}`, {});
      window.location.assign(result.authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setBusyId(null);
    }
  }

  async function disconnect(factory: FactoryAccount) {
    if (!window.confirm(`¿Desconectar la cuenta real de Google/YouTube vinculada a ${factory.name}?`)) return;
    setBusyId(factory.id); setError(''); setOk('');
    try {
      await api.post(`/api/youtube/disconnect?channel_id=${factory.id}`, {});
      setOk(`Cuenta desconectada de ${factory.name}. La otra fábrica no se modifica.`);
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
      {!loading && oauthConfigLoaded && !oauthReady && <Card title="Falta configurar el acceso de Google" sub="La conexión real se habilita cuando el servidor tiene las credenciales OAuth.">
        <p>Configurá estas variables de entorno en el servidor: <strong>{missingEnv.join(", ")}</strong>.</p>
        <p>En Google Cloud Console, agregá esta URL exacta a las URI de redireccionamiento autorizadas del cliente OAuth:</p>
        <p><code>{redirectUri}</code></p>
        <p className="muted">No pegues el secreto de Google en esta pantalla ni en el chat. Reiniciá la aplicación después de guardar las variables.</p>
      </Card>}
      <Card title="Conectá tus cuentas reales de Google / YouTube" sub="No creamos canales de YouTube. Google te permite elegir la cuenta y la app guarda el canal real que devuelve la autorización.">
        {loading ? <Empty>Comprobando las cuentas vinculadas…</Empty> : factories.length ? (
          <div className="stack">
            {factories.map((factory) => (
              <section className="card inset" key={factory.id}>
                <div className="row center between">
                  <div>
                    <strong>{factory.name}</strong>
                    <p className="muted" style={{ margin: '4px 0 0' }}>{factory.name === 'Historias' ? 'Cuenta Google que publicará tus historias' : 'Cuenta Google que publicará tus frutinovelas'}</p>
                  </div>
                  {factory.account ? <Badge tone="ok">Google conectado</Badge> : <Badge tone="warn">Cuenta sin conectar</Badge>}
                </div>
                {factory.account ? (
                  <div className="stack">
                    <p><strong>{factory.account.channel_title}</strong><br /><span className="muted">Este es el canal real de YouTube devuelto por Google. ID: {factory.account.youtube_channel_id}</span></p>
                    <button className="btn ghost" disabled={busyId !== null} onClick={() => void disconnect(factory)}>{busyId === factory.id ? 'Desconectando…' : 'Desconectar esta cuenta'}</button>
                  </div>
                ) : (
                  <button className="btn primary" disabled={busyId !== null || !oauthConfigLoaded || !oauthReady} onClick={() => void connect(factory)}>{busyId === factory.id ? 'Abriendo Google…' : 'Conectar cuenta de Google'}</button>
                )}
              </section>
            ))}
          </div>
        ) : <Empty>No se encontraron las dos fábricas de contenido.</Empty>}
        <button className="btn ghost" disabled={busyId !== null || loading} onClick={() => void load()}>Actualizar conexiones</button>
      </Card>
      <Card title="Cómo se conecta" sub="La autorización la hacés directamente en Google.">
        <ol>
          <li>En Historias, tocá «Conectar cuenta de Google» y elegí en Google la cuenta que administra tu canal de Historias.</li>
          <li>Volvé a esta pantalla y repetí el proceso en Frutinovelas si querés usar otra cuenta.</li>
          <li>La app consulta a YouTube y muestra el nombre y el ID del canal real autorizado. No inventa ni crea canales de YouTube.</li>
        </ol>
        <p className="muted">URI de redirección autorizada en Google Cloud: <code>{redirectUri}</code></p>
        <p className="muted">Las autorizaciones se guardan por separado para que cada fábrica publique en la cuenta que elegiste. Nunca compartas contraseñas ni secretos de Google en el chat.</p>
      </Card>
    </div>
  );
}
