import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  api, getToken, FAMILY_LABEL, type Architecture, type ArchitectureConfig, type Dataset, type DemoDataset,
  type HiddenLayer, type Job, type ModelVersion, type Project, type Summary,
} from '../api';
import { ErrorNote, JobsTable, Panel, formatDate, formatNumber } from '../components/ui';
import { NetworkDiagram } from '../components/charts';

const TABS = [
  ['contexto', 'Contexto'], ['datos', 'Datos'], ['arquitectura', 'Arquitectura'],
  ['entrenar', 'Entrenar'], ['historial', 'Historial'], ['modelos', 'Modelos'],
] as const;

export function ProjectPage() {
  const { projectId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'contexto';
  const project = useQuery({ queryKey: ['project', projectId], queryFn: () => api<Project>(`/projects/${projectId}`) });

  if (project.error) return <ErrorNote error={project.error} />;
  if (!project.data) return <p className="muted">Cargando…</p>;
  const p = project.data;
  return (
    <>
      <div className="page-head">
        <p className="eyebrow"><Link to="/proyectos">Proyectos</Link> / {p.id}</p>
        <h1>{p.name}</h1>
        <span className="chip chip--family">{FAMILY_LABEL[p.family]}</span>
      </div>
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className="tab" onClick={() => setParams({ tab: key })}>{label}</button>
        ))}
      </div>
      {tab === 'contexto' ? <ContextTab project={p} /> : null}
      {tab === 'datos' ? <DataTab project={p} /> : null}
      {tab === 'arquitectura' ? <DesignerTab project={p} /> : null}
      {tab === 'entrenar' ? <TrainTab project={p} /> : null}
      {tab === 'historial' ? <HistoryTab project={p} /> : null}
      {tab === 'modelos' ? <ModelsTab project={p} /> : null}
    </>
  );
}

function ContextTab({ project }: { project: Project }) {
  return (
    <Panel title="Contexto del proyecto">
      <dl className="facts">
        <div><dt>Problema</dt><dd>{project.description}</dd></div>
        <div><dt>Tipo de red</dt><dd>{FAMILY_LABEL[project.family]}</dd></div>
        <div><dt>Justificación del tipo</dt><dd>{project.justification}</dd></div>
        <div><dt>Creado</dt><dd>{formatDate(project.createdAt)}</dd></div>
      </dl>
      {project.family !== 'FEEDFORWARD' ? (
        <p className="alert alert--info">La familia {FAMILY_LABEL[project.family]} queda documentada con su justificación. En esta versión solo se diseñan y entrenan redes Feedforward (§18 del Documento Maestro).</p>
      ) : null}
    </Panel>
  );
}

// ------------------------------------------------------------------ datos

function DataTab({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const datasets = useQuery({ queryKey: ['datasets', project.id], queryFn: () => api<Dataset[]>(`/projects/${project.id}/datasets`) });
  const demos = useQuery({ queryKey: ['demo-datasets'], queryFn: () => api<DemoDataset[]>('/demo-datasets') });
  const [demoKey, setDemoKey] = useState('iris');
  const [name, setName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['datasets', project.id] });

  const addDemo = useMutation({ mutationFn: () => api(`/projects/${project.id}/datasets/demo`, { method: 'POST', json: { key: demoKey } }), onSuccess: refresh });
  const upload = useMutation({
    mutationFn: () => {
      const body = new FormData();
      body.append('name', name || file!.name.replace(/\.csv$/i, ''));
      body.append('file', file!);
      return api(`/projects/${project.id}/datasets/upload`, { method: 'POST', body });
    },
    onSuccess: () => { setFile(null); setName(''); void refresh(); },
  });

  return (
    <div className="grid-2">
      <Panel title="Datasets del proyecto" subtitle="Se reparten 70 % entrenamiento, 15 % validación y 15 % prueba.">
        <ErrorNote error={datasets.error} />
        {(datasets.data ?? []).length === 0 ? <p className="muted">Agrega un dataset demo o sube un CSV.</p> : null}
        {(datasets.data ?? []).map((d) => (
          <details key={d.id} className="dataset">
            <summary><strong>{d.name}</strong> <span className="muted small">{formatNumber(d.rows)} filas · {d.columns.length} columnas · {d.origin}</span></summary>
            <table className="table table--compact">
              <thead><tr><th>Columna</th><th>Tipo</th><th>Valores distintos</th><th>Vacíos</th></tr></thead>
              <tbody>{d.columns.map((c) => <tr key={c.name}><td>{c.name}</td><td>{c.kind}</td><td>{c.unique}</td><td>{c.nulls}</td></tr>)}</tbody>
            </table>
            <p className="small muted">SHA-256 {d.checksum.slice(0, 16)}…</p>
          </details>
        ))}
      </Panel>
      <div className="stack">
        <Panel title="Agregar dataset demo">
          <select className="input" value={demoKey} onChange={(e) => setDemoKey(e.target.value)}>
            {(demos.data ?? []).map((d) => <option key={d.key} value={d.key}>{d.name}</option>)}
          </select>
          <p className="small muted">{demos.data?.find((d) => d.key === demoKey)?.description}</p>
          <ErrorNote error={addDemo.error} />
          <button className="btn" disabled={addDemo.isPending} onClick={() => addDemo.mutate()}>Agregar</button>
        </Panel>
        <Panel title="Subir CSV propio" subtitle="UTF-8 con encabezados; hasta 1 MB y 5000 filas. Se valida antes de aceptarlo.">
          <form className="form" onSubmit={(e) => { e.preventDefault(); if (file) upload.mutate(); }}>
            <input className="input" placeholder="Nombre (opcional)" value={name} onChange={(e) => setName(e.target.value)} />
            <input className="input" type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <ErrorNote error={upload.error} />
            <div><button className="btn" disabled={!file || upload.isPending}>{upload.isPending ? 'Validando…' : 'Subir y validar'}</button></div>
          </form>
        </Panel>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ diseñador

const HIDDEN_ACTS = ['relu', 'tanh', 'sigmoid', 'elu', 'selu', 'linear'];
const OUTPUT_ACTS = ['softmax', 'sigmoid', 'linear'];

function suggestedOutput(summary: Summary | null): { units: number; activation: string } | null {
  if (!summary?.task) return null;
  if (summary.task === 'regression') return { units: 1, activation: 'linear' };
  return summary.classes === 2 ? { units: 1, activation: 'sigmoid' } : { units: summary.classes ?? 2, activation: 'softmax' };
}

function DesignerTab({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const datasets = useQuery({ queryKey: ['datasets', project.id], queryFn: () => api<Dataset[]>(`/projects/${project.id}/datasets`) });
  const archs = useQuery({ queryKey: ['architectures', project.id], queryFn: () => api<Architecture[]>(`/projects/${project.id}/architectures`) });
  const [name, setName] = useState('mi-red');
  const [config, setConfig] = useState<ArchitectureConfig>({
    dataset_id: '', target: '', layers: [{ type: 'Dense', units: 16, activation: 'relu' }, { type: 'Dense', units: 8, activation: 'relu' }],
    output: { units: 1, activation: 'sigmoid' },
  });
  const [summary, setSummary] = useState<Summary | null>(null);
  // La salida sigue la sugerida para el objetivo hasta que el usuario la edita a mano.
  const [autoOutput, setAutoOutput] = useState(true);
  const dataset = datasets.data?.find((d) => d.id === config.dataset_id);

  useEffect(() => {
    if (!config.dataset_id && datasets.data?.length) setConfig((c) => ({ ...c, dataset_id: datasets.data[0].id, target: datasets.data[0].columns[datasets.data[0].columns.length - 1].name }));
  }, [datasets.data, config.dataset_id]);

  // Validación en el backend mientras se edita (el frontend no decide qué es válido).
  useEffect(() => {
    if (!config.dataset_id || !config.target || project.family !== 'FEEDFORWARD') return;
    const timer = setTimeout(() => {
      api<Summary>(`/projects/${project.id}/architectures/validate`, { method: 'POST', json: { name, ...config } })
        .then(setSummary).catch((err) => setSummary({ valid: false, errors: [err.message], warnings: [], layers: [], totalParams: 0 }));
    }, 300);
    return () => clearTimeout(timer);
  }, [config, name, project.id, project.family]);

  useEffect(() => {
    const next = suggestedOutput(summary);
    if (autoOutput && next && (next.units !== config.output.units || next.activation !== config.output.activation)) {
      setConfig((c) => ({ ...c, output: next }));
    }
  }, [summary, autoOutput, config.output.units, config.output.activation]);

  const save = useMutation({
    mutationFn: () => api<Architecture>(`/projects/${project.id}/architectures`, { method: 'POST', json: { name, ...config } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['architectures', project.id] }),
  });

  const setLayer = (index: number, layer: HiddenLayer) => setConfig({ ...config, layers: config.layers.map((l, i) => (i === index ? layer : l)) });
  const move = (index: number, delta: number) => {
    const layers = [...config.layers];
    const [item] = layers.splice(index, 1);
    layers.splice(index + delta, 0, item);
    setConfig({ ...config, layers });
  };
  const suggestion = suggestedOutput(summary);

  if (project.family !== 'FEEDFORWARD') {
    return <p className="alert alert--info">Este proyecto es de tipo {FAMILY_LABEL[project.family]}: queda documentado. El diseñador de esta versión trabaja con redes Feedforward.</p>;
  }
  if (datasets.data && datasets.data.length === 0) {
    return <p className="alert alert--info">Primero agrega un dataset en la pestaña <strong>Datos</strong>: la red se diseña según sus columnas.</p>;
  }

  return (
    <div className="designer">
      <Panel title="Capas" subtitle="Define entradas, capas ocultas, neuronas, activaciones y salida.">
        <div className="form">
          <label className="field"><span>Nombre</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="field"><span>Dataset</span>
            <select className="input" value={config.dataset_id} onChange={(e) => {
              const d = datasets.data?.find((x) => x.id === e.target.value);
              setAutoOutput(true);
              setConfig({ ...config, dataset_id: e.target.value, target: d?.columns[d.columns.length - 1].name ?? '' });
            }}>
              {(datasets.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Columna objetivo (lo que la red predice)</span>
            <select className="input" value={config.target} onChange={(e) => { setAutoOutput(true); setConfig({ ...config, target: e.target.value }); }}>
              {(dataset?.columns ?? []).map((c) => <option key={c.name} value={c.name}>{c.name} · {c.kind}</option>)}
            </select>
          </label>
          <div className="layer layer--fixed">Entrada · {summary?.inputWidth ?? '—'} neuronas (una por columna numérica y por categoría)</div>
          {config.layers.map((layer, i) => (
            <div key={i} className="layer">
              <strong>{i + 1}. {layer.type}</strong>
              {layer.type === 'Dense' ? (
                <>
                  <label>neuronas <input className="input input--sm" type="number" min={1} max={512} value={layer.units} onChange={(e) => setLayer(i, { ...layer, units: Number(e.target.value) })} /></label>
                  <label>activación <select className="input input--sm" value={layer.activation} onChange={(e) => setLayer(i, { ...layer, activation: e.target.value })}>{HIDDEN_ACTS.map((a) => <option key={a}>{a}</option>)}</select></label>
                </>
              ) : (
                <label>descarte <input className="input input--sm" type="number" min={0} max={0.8} step={0.05} value={layer.rate} onChange={(e) => setLayer(i, { ...layer, rate: Number(e.target.value) })} /></label>
              )}
              <span className="layer__actions">
                <button type="button" className="btn btn--ghost btn--sm" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Subir">↑</button>
                <button type="button" className="btn btn--ghost btn--sm" disabled={i === config.layers.length - 1} onClick={() => move(i, 1)} aria-label="Bajar">↓</button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfig({ ...config, layers: config.layers.filter((_, j) => j !== i) })} aria-label="Quitar">✕</button>
              </span>
            </div>
          ))}
          <div className="row">
            <button type="button" className="btn btn--sm" disabled={config.layers.length >= 8} onClick={() => setConfig({ ...config, layers: [...config.layers, { type: 'Dense', units: 8, activation: 'relu' }] })}>+ Dense</button>
            <button type="button" className="btn btn--sm" disabled={config.layers.length >= 8} onClick={() => setConfig({ ...config, layers: [...config.layers, { type: 'Dropout', rate: 0.2 }] })}>+ Dropout</button>
          </div>
          <div className="layer layer--fixed">
            <strong>Salida</strong>
            <label>neuronas <input className="input input--sm" type="number" min={1} max={64} value={config.output.units} onChange={(e) => { setAutoOutput(false); setConfig({ ...config, output: { ...config.output, units: Number(e.target.value) } }); }} /></label>
            <label>activación <select className="input input--sm" value={config.output.activation} onChange={(e) => { setAutoOutput(false); setConfig({ ...config, output: { ...config.output, activation: e.target.value } }); }}>{OUTPUT_ACTS.map((a) => <option key={a}>{a}</option>)}</select></label>
            {suggestion && (suggestion.units !== config.output.units || suggestion.activation !== config.output.activation) ? (
              <button type="button" className="btn btn--sm" onClick={() => { setAutoOutput(true); setConfig({ ...config, output: suggestion }); }}>Usar la sugerida</button>
            ) : null}
          </div>
        </div>
      </Panel>

      <div className="stack">
        <Panel title="Vista previa y validación" subtitle={summary?.task ? `Tarea: ${summary.task === 'regression' ? 'regresión' : `clasificación de ${summary.classes} clases`} · salida esperada: ${summary.expectedOutput}` : undefined}>
          {summary ? <NetworkDiagram layers={summary.layers} /> : null}
          {summary?.errors.map((e) => <p key={e} className="alert alert--error">{e}</p>)}
          {summary?.warnings.map((w) => <p key={w} className="alert alert--warn">{w}</p>)}
          {summary?.layers.length ? (
            <table className="table table--compact">
              <thead><tr><th>Capa</th><th>Neuronas</th><th>Activación</th><th>Parámetros</th></tr></thead>
              <tbody>
                {summary.layers.map((l) => <tr key={l.name}><td>{l.name}</td><td>{l.units}</td><td>{l.activation ?? (l.rate !== undefined ? `descarte ${l.rate}` : '—')}</td><td>{formatNumber(l.params)}</td></tr>)}
                <tr><td colSpan={3}><strong>Total de parámetros (pesos y sesgos)</strong></td><td><strong>{formatNumber(summary.totalParams)}</strong></td></tr>
              </tbody>
            </table>
          ) : null}
          <ErrorNote error={save.error} />
          {save.data ? <p className="alert alert--ok">Guardada como {save.data.name} v{save.data.version}.</p> : null}
          <button className="btn btn--primary" disabled={!summary?.valid || save.isPending} onClick={() => save.mutate()}>Guardar versión</button>
        </Panel>
        <Panel title="Versiones guardadas" subtitle="Cada guardado crea una versión nueva; las anteriores no cambian.">
          {(archs.data ?? []).length === 0 ? <p className="muted">Aún no hay arquitecturas.</p> : (
            <table className="table table--compact">
              <thead><tr><th>Nombre</th><th>Capas</th><th>Parámetros</th><th>Guardada</th></tr></thead>
              <tbody>{(archs.data ?? []).map((a) => <tr key={a.id}><td>{a.name} v{a.version}</td><td>{a.config.layers.length + 1}</td><td>{a.summary ? formatNumber(a.summary.totalParams) : '—'}</td><td>{formatDate(a.createdAt)}</td></tr>)}</tbody>
            </table>
          )}
        </Panel>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ entrenar

function TrainTab({ project }: { project: Project }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const archs = useQuery({ queryKey: ['architectures', project.id], queryFn: () => api<Architecture[]>(`/projects/${project.id}/architectures`) });
  const valid = useMemo(() => (archs.data ?? []).filter((a) => a.summary?.valid), [archs.data]);
  const [form, setForm] = useState({
    architecture_id: '', epochs: 30, batch_size: 16, learning_rate: 0.01, optimizer: 'adam', seed: 42,
    class_weight: 'none' as 'none' | 'balanced', threshold: 0.5,
  });
  const chosen = form.architecture_id || valid[0]?.id || '';
  const summary = valid.find((a) => a.id === chosen)?.summary;
  const classification = summary?.task === 'classification';
  const binary = classification && summary?.classes === 2;

  const launch = useMutation({
    mutationFn: () => api<Job>(`/projects/${project.id}/training-jobs`, { method: 'POST', json: { ...form, architecture_id: chosen } }),
    onSuccess: (job) => { void queryClient.invalidateQueries({ queryKey: ['jobs', project.id] }); navigate(`/entrenamientos/${job.id}`); },
  });
  const num = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: Number(e.target.value) });

  if (archs.data && valid.length === 0) return <p className="alert alert--info">Primero guarda una arquitectura válida en la pestaña <strong>Arquitectura</strong>.</p>;
  return (
    <Panel title="Configurar y encolar entrenamiento" subtitle="El servidor entrena con TensorFlow/Keras en un proceso aparte; puedes salir de la pantalla y volver.">
      <form className="form form--grid" onSubmit={(e) => { e.preventDefault(); launch.mutate(); }}>
        <label className="field field--wide"><span>Arquitectura</span>
          <select className="input" value={chosen} onChange={(e) => setForm({ ...form, architecture_id: e.target.value })}>
            {valid.map((a) => <option key={a.id} value={a.id}>{a.name} v{a.version} · {a.config.target} · {formatNumber(a.summary!.totalParams)} parámetros</option>)}
          </select>
        </label>
        <label className="field"><span>Épocas (1–100)</span><input className="input" type="number" min={1} max={100} value={form.epochs} onChange={num('epochs')} /></label>
        <label className="field"><span>Tamaño de lote</span><input className="input" type="number" min={1} max={256} value={form.batch_size} onChange={num('batch_size')} /></label>
        <label className="field"><span>Tasa de aprendizaje</span><input className="input" type="number" min={0.0001} max={1} step={0.0001} value={form.learning_rate} onChange={num('learning_rate')} /></label>
        <label className="field"><span>Optimizador</span>
          <select className="input" value={form.optimizer} onChange={(e) => setForm({ ...form, optimizer: e.target.value })}>
            <option value="adam">Adam</option><option value="rmsprop">RMSprop</option><option value="sgd">SGD</option>
          </select>
        </label>
        <label className="field"><span>Semilla (misma semilla, mismo resultado)</span><input className="input" type="number" min={0} value={form.seed} onChange={num('seed')} /></label>
        {classification ? (
          <label className="field"><span>Peso de las clases</span>
            <select className="input" value={form.class_weight} onChange={(e) => setForm({ ...form, class_weight: e.target.value as 'none' | 'balanced' })}>
              <option value="none">Igual para todas</option>
              <option value="balanced">Balanceado: más peso a la clase menos frecuente</option>
            </select>
            <small className="muted">Útil cuando una respuesta es rara (pocos «sí»): la red deja de ignorarla, a cambio de más falsas alarmas.</small>
          </label>
        ) : null}
        {binary ? (
          <label className="field"><span>Umbral de alerta: {Math.round(form.threshold * 100)} %</span>
            <input type="range" min={0.05} max={0.95} step={0.05} value={form.threshold} onChange={num('threshold')} />
            <small className="muted">Desde qué probabilidad se avisa la clase positiva. Más bajo detecta más casos y da más falsas alarmas. Se puede explorar después sin reentrenar.</small>
          </label>
        ) : null}
        <div className="field--wide"><ErrorNote error={launch.error} /></div>
        <div className="field--wide"><button className="btn btn--primary" disabled={!chosen || launch.isPending}>{launch.isPending ? 'Encolando…' : 'Entrenar'}</button></div>
      </form>
    </Panel>
  );
}

// ------------------------------------------------------------------ historial y modelos

function HistoryTab({ project }: { project: Project }) {
  const jobs = useQuery({ queryKey: ['jobs', project.id], queryFn: () => api<Job[]>(`/projects/${project.id}/training-jobs`), refetchInterval: 5_000 });
  return (
    <Panel title="Historial de entrenamientos" subtitle="Cada ejecución queda guardada con sus parámetros, su dataset y su resultado.">
      <ErrorNote error={jobs.error} />
      <JobsTable jobs={jobs.data ?? []} />
    </Panel>
  );
}

async function downloadModel(model: ModelVersion) {
  const response = await fetch(`/api/v1/models/${model.id}/download`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!response.ok) { alert('No se pudo descargar el modelo.'); return; }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `${model.metadata.architecture?.name ?? 'modelo'}-v${model.version}.zip`;
  link.click();
  URL.revokeObjectURL(url);
}

function ModelsTab({ project }: { project: Project }) {
  const models = useQuery({ queryKey: ['models', project.id], queryFn: () => api<ModelVersion[]>(`/projects/${project.id}/models`) });
  return (
    <Panel title="Versiones del modelo" subtitle="Cada entrenamiento completado guarda una versión que no se sobrescribe: pesos (model.keras), preprocesamiento y metadatos, con su huella SHA-256.">
      <ErrorNote error={models.error} />
      {(models.data ?? []).length === 0 ? <p className="muted">Aún no hay versiones: completa un entrenamiento.</p> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Versión</th><th>Arquitectura</th><th>Dataset</th><th>Resultado (prueba)</th><th>Huella SHA-256</th><th>Entrenamiento</th><th></th></tr></thead>
            <tbody>
              {(models.data ?? []).map((m) => {
                const metrics = m.metadata.metrics ?? {};
                return (
                  <tr key={m.id}>
                    <td><strong>v{m.version}</strong></td>
                    <td>{m.metadata.architecture?.name} v{m.metadata.architecture?.version}</td>
                    <td>{m.metadata.dataset?.name}</td>
                    <td>{'accuracy' in metrics ? `Exactitud ${(metrics.accuracy * 100).toFixed(1)} %` : `R² ${Number(metrics.r2).toFixed(3)}`}</td>
                    <td><code>{m.checksum.slice(0, 12)}…</code></td>
                    <td><Link to={`/entrenamientos/${m.jobId}`}>{m.jobId}</Link></td>
                    <td><button className="btn btn--sm" onClick={() => void downloadModel(m)}>Descargar</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
