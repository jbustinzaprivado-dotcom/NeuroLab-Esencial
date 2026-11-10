import { useMemo, useState } from 'react';
import { Panel } from '../components/ui';

type Fn = (z: number) => number;
const ACTIVATIONS: Record<string, { fn: Fn; use: string; range: string }> = {
  relu: { fn: (z) => Math.max(0, z), use: 'Capas ocultas: rápida y evita que el aprendizaje se apague.', range: '[0, ∞)' },
  sigmoid: { fn: (z) => 1 / (1 + Math.exp(-z)), use: 'Salida binaria: da una probabilidad entre 0 y 1.', range: '(0, 1)' },
  tanh: { fn: Math.tanh, use: 'Capas ocultas con datos centrados en cero.', range: '(-1, 1)' },
  linear: { fn: (z) => z, use: 'Salida de regresión: predice un número sin límite.', range: '(-∞, ∞)' },
};

const FAMILIES = [
  {
    name: 'Feedforward (densa)', trainable: true,
    how: 'La información va en una sola dirección: entrada → capas ocultas → salida. Cada neurona se conecta con todas las de la capa siguiente.',
    uses: 'Datos en tabla: riesgo de fuga de clientes, precios de viviendas, clasificación de especies.',
    limits: 'No entiende orden temporal ni la vecindad entre píxeles.',
  },
  {
    name: 'Recurrente (RNN, LSTM, GRU)', trainable: false,
    how: 'Tiene memoria: lee los datos paso a paso y arrastra lo aprendido al siguiente paso.',
    uses: 'Series de tiempo y secuencias: lecturas de sensores, texto, demanda diaria.',
    limits: 'Más lenta de entrenar; las secuencias muy largas pueden "olvidarse" (LSTM y GRU lo mitigan).',
  },
  {
    name: 'Convolucional (CNN)', trainable: false,
    how: 'Recorre la imagen con filtros pequeños que detectan bordes, puntos y formas, y los combina en patrones mayores.',
    uses: 'Imágenes: control de calidad de piezas, dígitos manuscritos, diagnóstico por imagen.',
    limits: 'Necesita datos con estructura espacial y más cómputo; con tablas no aporta.',
  },
  {
    name: 'Generativa adversarial (GAN)', trainable: false,
    how: 'Dos redes compiten: un generador crea ejemplos falsos y un discriminador intenta detectarlos.',
    uses: 'Generar datos sintéticos: imágenes, aumento de datos, equilibrio de clases.',
    limits: 'Entrenamiento inestable y difícil de evaluar; requiere mucho cómputo.',
  },
];

const GLOSSARY: [string, string][] = [
  ['Neurona', 'Unidad que suma sus entradas multiplicadas por pesos, agrega un sesgo y aplica una activación.'],
  ['Peso (w)', 'Importancia de cada entrada; es lo que la red ajusta al aprender.'],
  ['Sesgo (b)', 'Valor que desplaza el resultado de la neurona, como el punto de partida de una balanza.'],
  ['Capa', 'Grupo de neuronas al mismo nivel: entrada, ocultas y salida.'],
  ['Función de activación', 'Decide cuánto "se enciende" la neurona y permite aprender relaciones no lineales.'],
  ['Época', 'Una pasada completa por todos los datos de entrenamiento.'],
  ['Pérdida (loss)', 'Cuánto se equivoca la red; el entrenamiento busca bajarla.'],
  ['Retropropagación', 'Cálculo que reparte el error hacia atrás para corregir cada peso.'],
  ['Sobreajuste', 'La red memoriza el entrenamiento y falla con datos nuevos; se detecta con la validación.'],
  ['Particiones', 'Entrenamiento (aprende), validación (se vigila) y prueba (examen final con datos nunca vistos).'],
];

function ActivationPlot({ name }: { name: string }) {
  const fn = ACTIVATIONS[name].fn;
  const points = useMemo(() => {
    const out: string[] = [];
    for (let i = 0; i <= 80; i += 1) {
      const z = -4 + (8 * i) / 80;
      const y = Math.max(-1.5, Math.min(4, fn(z)));
      out.push(`${(i / 80) * 220},${100 - ((y + 1.5) / 5.5) * 100}`);
    }
    return out.join(' ');
  }, [fn]);
  return (
    <svg viewBox="0 0 220 100" className="plot" role="img" aria-label={`Gráfica de ${name}`}>
      <line x1="0" y1={100 - (1.5 / 5.5) * 100} x2="220" y2={100 - (1.5 / 5.5) * 100} className="plot__axis" />
      <line x1="110" y1="0" x2="110" y2="100" className="plot__axis" />
      <polyline points={points} className="plot__line" />
    </svg>
  );
}

export function FundamentalsPage() {
  const [x, setX] = useState([0.8, 0.3, 0.5]);
  const [w, setW] = useState([0.9, -0.6, 0.4]);
  const [b, setB] = useState(0.1);
  const [activation, setActivation] = useState('relu');
  const z = x.reduce((sum, xi, i) => sum + xi * w[i], b);
  const out = ACTIVATIONS[activation].fn(z);

  const slider = (label: string, value: number, set: (v: number) => void, min = -1, max = 1) => (
    <label className="slider">
      <span>{label} = <strong>{value.toFixed(2)}</strong></span>
      <input type="range" min={min} max={max} step={0.05} value={value} onChange={(e) => set(Number(e.target.value))} />
    </label>
  );

  return (
    <>
      <div className="page-head">
        <p className="eyebrow">Fundamentos neuronales</p>
        <h1>Qué es una red neuronal y por qué importa</h1>
        <p className="muted">
          Una red neuronal artificial es un modelo que <strong>aprende patrones a partir de ejemplos</strong> en lugar de seguir reglas escritas a mano.
          Está formada por neuronas organizadas en capas y conectadas por pesos que se ajustan durante el entrenamiento.
          Es la base del aprendizaje profundo: reconoce imágenes, entiende texto y anticipa fallas o fraudes.
        </p>
      </div>

      <Panel title="Una neurona, paso a paso" subtitle="Mueve los valores y observa cómo cambia la salida: z = Σ wᵢ·xᵢ + b, y luego la activación.">
        <div className="neuron">
          <div className="neuron__controls">
            {x.map((xi, i) => (
              <div key={i} className="neuron__pair">
                {slider(`x${i + 1}`, xi, (v) => setX(x.map((old, j) => (j === i ? v : old))), 0, 1)}
                {slider(`w${i + 1}`, w[i], (v) => setW(w.map((old, j) => (j === i ? v : old))))}
              </div>
            ))}
            {slider('sesgo b', b, setB)}
            <label className="field">
              <span>Activación</span>
              <select className="input" value={activation} onChange={(e) => setActivation(e.target.value)}>
                {Object.keys(ACTIVATIONS).map((name) => <option key={name}>{name}</option>)}
              </select>
            </label>
          </div>
          <div className="neuron__result">
            <p className="formula">z = {x.map((xi, i) => `${xi.toFixed(2)}·${w[i].toFixed(2)}`).join(' + ')} + {b.toFixed(2)} = <strong>{z.toFixed(3)}</strong></p>
            <p className="formula">salida = {activation}(z) = <strong>{out.toFixed(3)}</strong></p>
            <ActivationPlot name={activation} />
            <p className="small muted">{ACTIVATIONS[activation].use} Rango: {ACTIVATIONS[activation].range}.</p>
          </div>
        </div>
      </Panel>

      <Panel title="Cómo aprende" subtitle="El ciclo que TensorFlow/Keras repite en cada lote de datos.">
        <ol className="cycle">
          <li><strong>Propagación hacia adelante:</strong> los datos atraviesan las capas y la red da una predicción.</li>
          <li><strong>Pérdida:</strong> se mide cuánto se equivocó comparando con la respuesta real.</li>
          <li><strong>Retropropagación:</strong> se calcula cuánto contribuyó cada peso al error.</li>
          <li><strong>Optimizador:</strong> Adam, SGD o RMSprop ajustan los pesos un poco en la dirección que reduce el error.</li>
        </ol>
      </Panel>

      <Panel title="Tipos de redes neuronales" subtitle="En esta versión se entrena Feedforward; las demás familias se documentan para identificarlas y justificar la elección (§18).">
        <div className="families">
          {FAMILIES.map((family) => (
            <article key={family.name} className="family">
              <header>
                <h3>{family.name}</h3>
                <span className={`chip ${family.trainable ? 'chip--completed' : 'chip--queued'}`}>{family.trainable ? 'Se entrena aquí' : 'Documentada'}</span>
              </header>
              <p><strong>Cómo funciona:</strong> {family.how}</p>
              <p><strong>Casos de uso:</strong> {family.uses}</p>
              <p><strong>Restricciones:</strong> {family.limits}</p>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Glosario">
        <dl className="glossary">
          {GLOSSARY.map(([term, text]) => (
            <div key={term}><dt>{term}</dt><dd>{text}</dd></div>
          ))}
        </dl>
      </Panel>
    </>
  );
}
