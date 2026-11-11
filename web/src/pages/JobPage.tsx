import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  api, followEvents, TERMINAL, type ClassMetrics, type Job, type JobEvent, type JobStatus, type RegressionMetrics,
} from '../api';
import { ErrorNote, Panel, StatusChip, formatDate, formatNumber } from '../components/ui';
import { LineChart } from '../components/charts';

const STEPS: JobStatus[] = ['QUEUED', 'PREPARING', 'RUNNING', 'COMPLETED'];

export function JobPage() {
  const { jobId = '' } = useParams();
  const queryClient = useQueryClient();
  const job = useQuery({ queryKey: ['job', jobId], queryFn: () => api<Job>(`/training-jobs/${jobId}`) });
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [live, setLive] = useState(false);

  // Primero se carga todo lo ocurrido (sirve también al reconectar) y luego se sigue el canal en vivo.
  useEffect(() => {
    let stop = () => {};
    let cancelled = false;
    api<(JobEvent & { id: number })[]>(`/training-jobs/${jobId}/history`).then((history) => {
      if (cancelled) return;
      setEvents(history);
      const last = history.length ? history[history.length - 1].id : 0;
      setLive(true);
      stop = followEvents(jobId, (event) => {
        setEvents((prev) => [...prev, event]);
        if (event.kind === 'status') void queryClient.invalidateQueries({ queryKey: ['job', jobId] });
      }, () => { setLive(false); void queryClient.invalidateQueries({ queryKey: ['job', jobId] }); }, last);
    }).catch(() => undefined);
    return () => { cancelled = true; stop(); };
  }, [jobId, queryClient]);

  const cancel = useMutation({
    mutationFn: () => api<Job>(`/training-jobs/${jobId}/cancel`, { method: 'POST', json: { reason: 'Cancelado desde la pantalla de seguimiento.' } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['job', jobId] }),
  });

  const metrics = useMemo(() => events.filter((e) => e.kind === 'metric').map((e) => e.payload as Record<string, number>), [events]);
  const logs = events.filter((e) => e.kind === 'log');
  const lastStatus = [...events].reverse().find((e) => e.kind === 'status')?.payload as { status?: JobStatus; reason?: string } | undefined;

  if (job.error) return <ErrorNote error={job.error} />;
  const j = job.data;
  if (!j) return <p className="muted">Cargando…</p>;
  const status: JobStatus = (lastStatus?.status as JobStatus) ?? j.status;
  const regression = j.params.task === 'regression';
  const epochsDone = metrics.length ? metrics[metrics.length - 1].epoch : j.epoch;
  const progress = TERMINAL.includes(status) && status === 'COMPLETED' ? 100 : (epochsDone / j.params.epochs) * 100;
  const series = (key: string) => metrics.map((m) => m[key]);

  return (
    <>
      <div className="page-head page-head--row">
        <div>
          <p className="eyebrow"><Link to={`/proyectos/${j.projectId}?tab=historial`}>{j.projectId}</Link> / {j.id}</p>
          <h1>{j.architecture.name} v{j.architecture.version} · objetivo «{j.target}»</h1>
          <p className="muted small">{live ? '● Conectado en vivo' : 'Sin conexión en vivo (el trabajo terminó o se está reconectando)'}</p>
        </div>
        {!TERMINAL.includes(status) ? (
          <button className="btn btn--danger" disabled={cancel.isPending || j.cancelRequested} onClick={() => cancel.mutate()}>
            {j.cancelRequested ? 'Cancelación solicitada' : 'Cancelar'}
          </button>
        ) : null}
      </div>
      <ErrorNote error={cancel.error} />

      <Panel title="Estado" actions={<StatusChip status={status} />}>
        <ol className="states">
          {STEPS.map((step) => {
            const reached = events.some((e) => e.kind === 'status' && (e.payload as { status: string }).status === step);
            return <li key={step} className={reached ? 'is-done' : ''}><StatusChip status={step} /></li>;
          })}
        </ol>
        <div className="progress" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${Math.min(100, progress)}%` }} />
        </div>
        <p className="small muted">Época {epochsDone} de {j.params.epochs} · {Math.round(progress)} %</p>
        {status === 'FAILED' || status === 'CANCELLED' ? (
          <p className={`alert ${status === 'FAILED' ? 'alert--error' : 'alert--warn'}`}>{lastStatus?.reason ?? j.statusReason}</p>
        ) : null}
        {status === 'QUEUED' || status === 'PREPARING' ? (
          <p className="small muted">El servidor gratuito usa poca CPU: preparar TensorFlow puede tardar unos segundos.</p>
        ) : null}
      </Panel>

      <div className="grid-2">
        <LineChart title="Pérdida por época" series={[
          { label: 'entrenamiento', values: series('loss'), color: '#4338ca' },
          { label: 'validación', values: series('val_loss'), color: '#0ea5e9', dashed: true },
        ]} />
        {regression ? (
          <LineChart title="Error absoluto medio (escalado)" series={[
            { label: 'entrenamiento', values: series('mae'), color: '#4338ca' },
            { label: 'validación', values: series('val_mae'), color: '#0ea5e9', dashed: true },
          ]} />
        ) : (
          <LineChart title="Exactitud por época" percent series={[
            { label: 'entrenamiento', values: series('accuracy'), color: '#4338ca' },
            { label: 'validación', values: series('val_accuracy'), color: '#0ea5e9', dashed: true },
          ]} />
        )}
      </div>

      {status === 'COMPLETED' && j.result.metrics ? <Results job={j} /> : null}

      <div className="grid-2">
        <Panel title="Registro del worker">
          <ul className="logs">
            {logs.map((e, i) => <li key={i} className={(e.payload.level as string) === 'error' ? 'is-error' : ''}><time>{formatDate(e.at)}</time> {String(e.payload.message)}</li>)}
            {logs.length === 0 ? <li className="muted">Sin mensajes todavía.</li> : null}
          </ul>
        </Panel>
        <Panel title="Trazabilidad" subtitle="Todo lo necesario para repetir este entrenamiento.">
          <dl className="facts facts--compact">
            <div><dt>Dataset</dt><dd>{j.dataset.name} · SHA-256 {j.dataset.checksum.slice(0, 12)}…</dd></div>
            <div><dt>Arquitectura</dt><dd>{j.architecture.name} v{j.architecture.version}</dd></div>
            <div><dt>Parámetros</dt><dd>{j.params.epochs} épocas · lote {j.params.batch_size} · {j.params.optimizer} · tasa {j.params.learning_rate} · semilla {j.params.seed}</dd></div>
            {j.params.task === 'classification' ? (
              <div><dt>Peso de clases / umbral</dt><dd>{j.params.class_weight === 'balanced' ? 'balanceado' : 'igual para todas'}{j.params.threshold != null ? ` · umbral ${Math.round(j.params.threshold * 100)} %` : ''}</dd></div>
            ) : null}
            <div><dt>Particiones</dt><dd>70 % entrenamiento · 15 % validación · 15 % prueba</dd></div>
            <div><dt>Versión de código</dt><dd>{j.params.codeVersion}</dd></div>
            <div><dt>Encolado / fin</dt><dd>{formatDate(j.createdAt)} → {formatDate(j.endedAt)}</dd></div>
            {j.result.modelVersion ? <div><dt>Modelo</dt><dd>versión {j.result.modelVersion} · SHA-256 {j.result.checksum?.slice(0, 12)}… (<Link to={`/proyectos/${j.projectId}?tab=modelos`}>ver</Link>)</dd></div> : null}
          </dl>
        </Panel>
      </div>
    </>
  );
}

function Results({ job }: { job: Job }) {
  const m = job.result.metrics!;
  if ('r2' in m) {
    const r = m as RegressionMetrics;
    return (
      <Panel title="Evaluación final con datos de prueba" subtitle={`${r.testRows} filas que la red nunca vio durante el entrenamiento.`}>
        <div className="kpis">
          <div className="kpi"><span>R²</span><strong>{r.r2.toFixed(3)}</strong><small>1 = predicción perfecta</small></div>
          <div className="kpi"><span>Error absoluto medio</span><strong>{formatNumber(r.mae, 1)}</strong><small>en las unidades de «{job.target}»</small></div>
          <div className="kpi"><span>RMSE</span><strong>{formatNumber(r.rmse, 1)}</strong><small>castiga más los errores grandes</small></div>
        </div>
      </Panel>
    );
  }
  const c = m as ClassMetrics;
  if (c.scores && c.positiveClass) return <BinaryResults metrics={c} />;
  return (
    <Panel title="Evaluación final con datos de prueba" subtitle={`${c.testRows} filas que la red nunca vio · exactitud ${(c.accuracy * 100).toFixed(1)} %`}>
      <Matrix classes={c.classes} confusion={c.confusion} />
    </Panel>
  );
}

function Matrix({ classes, confusion }: { classes: string[]; confusion: number[][] }) {
  return (
    <>
      <p className="small muted">Matriz de confusión: filas = clase real, columnas = lo que predijo la red. La diagonal son los aciertos.</p>
      <div className="table-wrap">
        <table className="table table--matrix">
          <thead><tr><th>Real \ Predicha</th>{classes.map((label) => <th key={label}>{label}</th>)}</tr></thead>
          <tbody>
            {confusion.map((row, i) => (
              <tr key={classes[i]}>
                <th>{classes[i]}</th>
                {row.map((value, k) => <td key={k} className={i === k ? 'is-hit' : value ? 'is-miss' : ''}>{value}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Binaria: indicadores de negocio y un control para probar otro umbral sobre las mismas predicciones. */
function BinaryResults({ metrics }: { metrics: ClassMetrics }) {
  const trained = metrics.threshold ?? 0.5;
  const [cut, setCut] = useState(trained);
  const scores = metrics.scores!;
  const positive = metrics.positiveClass!;
  const negative = metrics.classes[0];
  const matrix = useMemo(() => {
    const m = [[0, 0], [0, 0]];
    for (const [real, score] of scores) m[real][score >= cut ? 1 : 0] += 1;
    return m;
  }, [scores, cut]);
  const [[tn, fp], [fn, tp]] = matrix;
  const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)} %` : '—');
  return (
    <Panel title="Evaluación final con datos de prueba" subtitle={`${scores.length} filas que la red nunca vio · entrenado con umbral ${Math.round(trained * 100)} %`}>
      <div className="kpis">
        <div className="kpi"><span>Detecta «{positive}»</span><strong>{tp} de {tp + fn}</strong><small>{pct(tp, tp + fn)} de los casos reales (recall)</small></div>
        <div className="kpi"><span>Falsas alarmas</span><strong>{fp}</strong><small>de {tn + fp} casos «{negative}»</small></div>
        <div className="kpi"><span>Cuando avisa, acierta</span><strong>{pct(tp, tp + fp)}</strong><small>precisión de las alertas</small></div>
        <div className="kpi"><span>Exactitud</span><strong>{pct(tp + tn, scores.length)}</strong><small>aciertos totales</small></div>
      </div>
      <label className="threshold">
        <span>Probar otro umbral: avisar «{positive}» desde <strong>{Math.round(cut * 100)} %</strong> de probabilidad</span>
        <input type="range" min={0.05} max={0.95} step={0.05} value={cut} onChange={(e) => setCut(Number(e.target.value))} />
        <small className="muted">
          Recalcula con las mismas predicciones, sin reentrenar.
          {Math.abs(cut - trained) > 1e-9 ? <> <button type="button" className="btn btn--ghost btn--sm" onClick={() => setCut(trained)}>Volver a {Math.round(trained * 100)} %</button></> : null}
        </small>
      </label>
      <Matrix classes={metrics.classes} confusion={matrix} />
    </Panel>
  );
}
