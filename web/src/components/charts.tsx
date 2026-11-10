import type { LayerShape } from '../api';

interface Series { label: string; values: number[]; dashed?: boolean; color: string }

/** Curva por época: entrenamiento (línea continua) y validación (discontinua). */
export function LineChart({ series, title, percent = false }: { series: Series[]; title: string; percent?: boolean }) {
  const width = 460, height = 200, pad = { l: 46, r: 12, t: 12, b: 26 };
  const all = series.flatMap((s) => s.values).filter(Number.isFinite);
  const epochs = Math.max(1, ...series.map((s) => s.values.length));
  if (all.length === 0) {
    return <div className="chart chart--empty"><span>{title}</span><p className="muted small">Las épocas aparecerán aquí en cuanto empiece el entrenamiento.</p></div>;
  }
  let min = Math.min(...all), max = Math.max(...all);
  if (percent) { min = Math.min(min, 0); max = Math.max(max, 1); }
  if (max - min < 1e-9) { max += 1; min -= 1; }
  const x = (i: number) => pad.l + (epochs === 1 ? 0 : (i / (epochs - 1)) * (width - pad.l - pad.r));
  const y = (v: number) => pad.t + (1 - (v - min) / (max - min)) * (height - pad.t - pad.b);
  const ticks = [min, (min + max) / 2, max];
  const fmt = (v: number) => (percent ? `${Math.round(v * 100)} %` : Math.abs(v) >= 1000 ? v.toExponential(1) : v.toFixed(3));
  return (
    <figure className="chart">
      <figcaption>
        <span>{title}</span>
        <span className="chart__legend">
          {series.map((s) => (
            <span key={s.label}><i style={{ borderColor: s.color, borderStyle: s.dashed ? 'dashed' : 'solid' }} />{s.label}</span>
          ))}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} className="chart__grid" />
            <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" className="chart__tick">{fmt(t)}</text>
          </g>
        ))}
        <text x={pad.l} y={height - 6} className="chart__tick">época 1</text>
        <text x={width - pad.r} y={height - 6} textAnchor="end" className="chart__tick">época {epochs}</text>
        {series.map((s) => (
          <polyline key={s.label} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? '5 4' : undefined}
            points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')} />
        ))}
      </svg>
    </figure>
  );
}

/** Dibujo de la red: neuronas por capa (se muestran hasta 8) y sus conexiones. */
export function NetworkDiagram({ layers }: { layers: LayerShape[] }) {
  const visible = layers.filter((l) => !l.name.startsWith('Dropout'));
  if (visible.length < 2) return null;
  const width = 560, height = 230, maxShown = 8;
  const columnX = (i: number) => 40 + (i * (width - 80)) / (visible.length - 1);
  const nodes = visible.map((layer, i) => {
    const shown = Math.min(layer.units, maxShown);
    return Array.from({ length: shown }, (_, j) => ({ x: columnX(i), y: 30 + ((j + 0.5) * (height - 70)) / shown }));
  });
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="diagram" role="img" aria-label="Diagrama de la red neuronal">
      {nodes.slice(0, -1).map((column, i) => column.flatMap((a, ai) => nodes[i + 1].map((b, bi) => (
        <line key={`${i}-${ai}-${bi}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="diagram__edge" />
      ))))}
      {nodes.map((column, i) => column.map((n, j) => (
        <circle key={`${i}-${j}`} cx={n.x} cy={n.y} r={7} className={`diagram__node ${i === 0 ? 'is-input' : i === nodes.length - 1 ? 'is-output' : ''}`} />
      )))}
      {visible.map((layer, i) => (
        <g key={layer.name}>
          <text x={columnX(i)} y={height - 22} textAnchor="middle" className="diagram__label">{layer.name}</text>
          <text x={columnX(i)} y={height - 8} textAnchor="middle" className="diagram__sub">
            {layer.units} neurona{layer.units === 1 ? '' : 's'}{layer.units > maxShown ? ` (se ven ${maxShown})` : ''}
          </text>
        </g>
      ))}
    </svg>
  );
}
