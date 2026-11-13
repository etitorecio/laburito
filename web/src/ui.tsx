import type { ReactNode } from 'react';

export function Card({ title, sub, actions, children }: { title?: string; sub?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <p className="sub">{sub}</p>}
          </div>
          {actions && <div className="row gap-8">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="stat">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}

export function Badge({ children, tone = '' }: { children: ReactNode; tone?: '' | 'ok' | 'warn' | 'bad' | 'info' }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Progress({ value, label }: { value: number; label?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value || 0)));
  return (
    <div>
      <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${pct}%` }} />
      </div>
      {label && <small>{label}</small>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Msg({ error, ok }: { error?: string; ok?: string }) {
  if (error) return <div className="msg error">{error}</div>;
  if (ok) return <div className="msg ok">{ok}</div>;
  return null;
}

const JOB_TONES: Record<string, '' | 'ok' | 'warn' | 'bad' | 'info'> = {
  completado: 'ok',
  ejecutando: 'info',
  en_cola: 'warn',
  error: 'bad',
  cancelado: '',
};

export function JobBadge({ status }: { status: string }) {
  return <Badge tone={JOB_TONES[status] ?? ''}>{status.replace('_', ' ')}</Badge>;
}

export function statusTone(status: string): '' | 'ok' | 'warn' | 'bad' | 'info' {
  if (['completado', 'publicado', 'renderizado', 'listo'].includes(status)) return 'ok';
  if (['en_render', 'en_cola', 'ejecutando', 'revision'].includes(status)) return 'warn';
  if (['error', 'bloqueado'].includes(status)) return 'bad';
  return 'info';
}
