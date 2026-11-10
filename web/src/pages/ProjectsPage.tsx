import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, FAMILY_LABEL, type Family, type Project } from '../api';
import { ErrorNote, Panel, formatDate } from '../components/ui';

const HINTS: Record<Family, string> = {
  FEEDFORWARD: 'Para datos en tabla (columnas numéricas o categorías). Es la familia que se entrena en esta versión.',
  RNN: 'Para secuencias en el tiempo. Quedará documentada: en esta versión no se diseña ni se entrena.',
  CNN: 'Para imágenes. Quedará documentada: en esta versión no se diseña ni se entrena.',
  GAN: 'Para generar datos sintéticos. Quedará documentada: en esta versión no se diseña ni se entrena.',
};

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/projects') });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', family: 'FEEDFORWARD' as Family, justification: '' });

  const create = useMutation({
    mutationFn: () => api<Project>('/projects', { method: 'POST', json: form }),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      navigate(`/proyectos/${project.id}`);
    },
  });

  return (
    <>
      <div className="page-head page-head--row">
        <div>
          <p className="eyebrow">Proyectos de IA</p>
          <h1>Tus proyectos</h1>
          <p className="muted">Cada proyecto describe un problema, el tipo de red elegido y por qué.</p>
        </div>
        <button className="btn btn--primary" onClick={() => setOpen(!open)}>{open ? 'Cerrar' : 'Nuevo proyecto'}</button>
      </div>

      {open ? (
        <Panel title="Nuevo proyecto" subtitle="La justificación del tipo de red queda registrada (operación «identificar tipos de redes»).">
          <form className="form" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <label className="field"><span>Nombre</span>
              <input className="input" required minLength={3} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="field"><span>Problema que se quiere resolver</span>
              <textarea className="input" required minLength={10} rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            <label className="field"><span>Tipo de red</span>
              <select className="input" value={form.family} onChange={(e) => setForm({ ...form, family: e.target.value as Family })}>
                {(Object.keys(FAMILY_LABEL) as Family[]).map((f) => <option key={f} value={f}>{FAMILY_LABEL[f]}</option>)}
              </select>
              <small className="muted">{HINTS[form.family]}</small>
            </label>
            <label className="field"><span>¿Por qué este tipo de red?</span>
              <textarea className="input" required minLength={10} rows={3} value={form.justification} onChange={(e) => setForm({ ...form, justification: e.target.value })} />
            </label>
            <ErrorNote error={create.error} />
            <div><button className="btn btn--primary" disabled={create.isPending}>{create.isPending ? 'Creando…' : 'Crear proyecto'}</button></div>
          </form>
        </Panel>
      ) : null}

      <ErrorNote error={projects.error} />
      <div className="cards">
        {(projects.data ?? []).map((project) => (
          <Link key={project.id} to={`/proyectos/${project.id}`} className="card">
            <span className="chip chip--family">{FAMILY_LABEL[project.family]}</span>
            <h3>{project.name}</h3>
            <p className="muted small">{project.description}</p>
            <span className="small muted">{project.id} · {formatDate(project.createdAt)}</span>
          </Link>
        ))}
        {projects.data?.length === 0 ? <p className="muted">Aún no tienes proyectos. Crea el primero.</p> : null}
      </div>
    </>
  );
}
