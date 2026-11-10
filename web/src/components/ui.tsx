import { Link } from 'react-router-dom';
import { STATUS_LABEL, type Job, type JobStatus } from '../api';

export function StatusChip({ status }: { status: JobStatus }) {
  return <span className={`chip chip--${status.toLowerCase()}`}>{STATUS_LABEL[status]}</span>;
}

export function Panel({ title, subtitle, actions, children }: { title: string; subtitle?: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <header className="panel__head">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p className="muted small">{subtitle}</p> : null}
        </div>
        {actions}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="alert alert--error" role="alert">{(error as Error).message}</p>;
}

export function mainMetric(job: Job): string {
  const m = job.result.metrics as Record<string, number> | undefined;
  if (!m) return '—';
  if ('accuracy' in m) return `Exactitud ${(m.accuracy * 100).toFixed(1)} %`;
  if ('r2' in m) return `R² ${m.r2.toFixed(3)}`;
  return '—';
}

export function JobsTable({ jobs, showProject = false }: { jobs: Job[]; showProject?: boolean }) {
  if (jobs.length === 0) return <p className="muted">Aún no hay entrenamientos.</p>;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Trabajo</th>{showProject ? <th>Proyecto</th> : null}<th>Arquitectura</th><th>Estado</th>
            <th>Épocas</th><th>Resultado (prueba)</th><th>Fecha</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td><Link to={`/entrenamientos/${job.id}`}>{job.id}</Link></td>
              {showProject ? <td>{job.projectId}</td> : null}
              <td>{job.architecture.name} v{job.architecture.version}</td>
              <td><StatusChip status={job.status} /></td>
              <td>{job.epoch}/{job.params.epochs}</td>
              <td>{mainMetric(job)}</td>
              <td>{formatDate(job.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-PE', { dateStyle: 'short', timeStyle: 'short' });
}

export function formatNumber(value: number, decimals = 0): string {
  return value.toLocaleString('es-PE', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
