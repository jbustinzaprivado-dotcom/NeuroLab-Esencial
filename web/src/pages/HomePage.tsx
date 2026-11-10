import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, type Dashboard } from '../api';
import { useSession } from '../App';
import { ErrorNote, JobsTable, Panel } from '../components/ui';

const STEPS = [
  { title: '1. Entender la red', text: 'Qué es una red neuronal y por qué importa en IA.', to: '/fundamentos' },
  { title: '2. Elegir el tipo', text: 'Feedforward, RNN, CNN o GAN, con su justificación.', to: '/proyectos' },
  { title: '3. Describir la estructura', text: 'Capas, neuronas y activaciones en el diseñador.', to: '/proyectos' },
  { title: '4. Crear la red con Keras', text: 'Entrenamiento real en TensorFlow con métricas en vivo.', to: '/proyectos' },
];

export function HomePage() {
  const { user } = useSession();
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dashboard>('/dashboard'), refetchInterval: 5_000 });
  const d = dashboard.data;
  return (
    <>
      <div className="page-head">
        <p className="eyebrow">Inicio</p>
        <h1>Hola, {user.displayName.split(' ')[0]}</h1>
        <p className="muted">Define la estructura y crea una red neuronal artificial: el recorrido de la Semana 11, de la teoría al modelo entrenado.</p>
      </div>
      <ErrorNote error={dashboard.error} />
      <div className="kpis">
        <div className="kpi"><span>Proyectos</span><strong>{d?.projects ?? '—'}</strong></div>
        <div className="kpi"><span>Entrenamientos activos</span><strong>{d?.active ?? '—'}</strong></div>
        <div className="kpi"><span>Completados</span><strong>{d?.completed ?? '—'}</strong></div>
        <div className="kpi"><span>Versiones de modelo</span><strong>{d?.models ?? '—'}</strong></div>
      </div>
      <div className="steps">
        {STEPS.map((step) => (
          <Link key={step.title} to={step.to} className="step">
            <strong>{step.title}</strong>
            <span>{step.text}</span>
          </Link>
        ))}
      </div>
      <Panel title="Entrenamientos recientes" subtitle="Se actualiza solo; el entrenamiento sigue en el servidor aunque cierres la pantalla.">
        <JobsTable jobs={d?.recent ?? []} showProject />
      </Panel>
    </>
  );
}
