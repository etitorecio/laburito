import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { Badge, Card, Empty, Msg } from '../ui';

type Destination = { available: boolean; missing_env: string[]; note: string };
type AccountStatus = { channel_id: string; channel_title: string };

export default function Accounts() {
  const [destination, setDestination] = useState<Destination | null>(null);
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.get<{ destinations: ({ id: string } & Destination)[] }>('/api/publish/destinations');
      const youtube = result.destinations.find((item) => item.id === 'youtube') as (Destination & { id: string }) | undefined;
      setDestination(youtube ?? null);
      if (youtube?.available) {
        try {
          setAccount(await api.get<AccountStatus>('/api/youtube/status'));
        } catch {
          setAccount(null);
        }
      } else {
        setAccount(null);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function connect() {
    setBusy(true); setError(''); setOk('');
    try {
      const result = await api.post<{ authorization_url: string }>('/api/youtube/oauth/start', {});
      window.location.assign(result.authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm('¿Desconectar esta cuenta de YouTube? Laburito dejará de poder publicar en ella.')) return;
    setBusy(true); setError(''); setOk('');
    try {
      await api.post('/api/youtube/disconnect', {});
      setAccount(null);
      setOk('Cuenta desconectada. Podés vincular otra cuenta cuando quieras.');
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <Msg error={error} ok={ok} />
      <Card title="Cuentas conectadas" sub="Vinculá la cuenta que va a recibir tus publicaciones. La autorización se hace directamente con Google.">
        {loading ? <Empty>Comprobando conexión…</Empty> : account ? (
          <div className="stack">
            <div className="pill-row">
              <Badge tone="ok">YouTube conectado</Badge>
              <Badge tone="ok">Permisos verificados</Badge>
            </div>
            <div className="row center between">
              <div>
                <strong>{account.channel_title}</strong>
                <p className="muted" style={{ margin: '4px 0 0' }}>Canal autorizado para subir videos.</p>
              </div>
              <span aria-hidden>▶️</span>
            </div>
            <div className="row">
              <button className="btn primary" disabled={busy} onClick={() => void connect()}>Conectar otra cuenta</button>
              <button className="btn ghost" disabled={busy} onClick={() => void disconnect()}>{busy ? 'Procesando…' : 'Desconectar'}</button>
              <button className="btn ghost" disabled={busy} onClick={() => void load()}>Actualizar estado</button>
            </div>
          </div>
        ) : (
          <div className="stack">
            <div className="pill-row"><Badge tone="warn">YouTube no conectado</Badge></div>
            <p className="muted">Todavía no hay una cuenta autorizada. Tocá el botón para elegir una cuenta de Google y conceder los permisos de publicación. Podés cambiarla o desconectarla después.</p>
            {destination?.missing_env?.length ? (
              <p className="muted">Falta completar la configuración del servidor: {destination.missing_env.join(', ')}.</p>
            ) : null}
            <button className="btn primary" disabled={busy || !!destination?.missing_env?.some((item) => item.includes('CLIENT'))} onClick={() => void connect()}>{busy ? 'Abriendo Google…' : 'Conectar cuenta de YouTube'}</button>
          </div>
        )}
      </Card>
      <Card title="Cómo funciona" sub="Sin intermediarios ni servicios de publicación pagos.">
        <ul>
          <li>Google te muestra qué cuenta y canal estás autorizando.</li>
          <li>Laburito guarda el permiso en su almacenamiento local para poder publicar.</li>
          <li>En Autopiloto elegís YouTube como destino y definís la privacidad de cada video.</li>
          <li>Desconectar revoca el permiso ante Google cuando es posible y borra el token guardado localmente.</li>
        </ul>
        <p className="muted">La cuenta conectada es independiente de los canales internos que usás para organizar tus proyectos.</p>
      </Card>
    </div>
  );
}
