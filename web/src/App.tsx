import { createContext, useContext, useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, getToken, setToken, type Health, type User } from './api';
import { LoginPage } from './pages/LoginPage';
import { HomePage } from './pages/HomePage';
import { FundamentalsPage } from './pages/FundamentalsPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ProjectPage } from './pages/ProjectPage';
import { JobPage } from './pages/JobPage';

const SessionContext = createContext<{ user: User; logout: () => void } | null>(null);
export const useSession = () => useContext(SessionContext)!;

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(Boolean(getToken()));
  const queryClient = useQueryClient();

  useEffect(() => {
    if (getToken()) {
      api<User>('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setChecking(false));
    }
    const onLogout = () => { setUser(null); queryClient.clear(); };
    window.addEventListener('neurolab:logout', onLogout);
    return () => window.removeEventListener('neurolab:logout', onLogout);
  }, [queryClient]);

  if (checking) return <div className="center-screen">Cargando…</div>;
  if (!user) return <LoginPage onLogin={setUser} />;

  const logout = () => { setToken(null); setUser(null); queryClient.clear(); };
  return (
    <SessionContext.Provider value={{ user, logout }}>
      <Shell>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/fundamentos" element={<FundamentalsPage />} />
          <Route path="/proyectos" element={<ProjectsPage />} />
          <Route path="/proyectos/:projectId/*" element={<ProjectPage />} />
          <Route path="/entrenamientos/:jobId" element={<JobPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Shell>
    </SessionContext.Provider>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useSession();
  const navigate = useNavigate();
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/health'), refetchInterval: 10_000 });
  const online = health.data?.workerOnline;
  return (
    <div className="shell">
      <aside className="nav" aria-label="Navegación">
        <div className="nav__brand">
          <span className="nav__logo" aria-hidden="true">N</span>
          <span><strong>NeuroLab</strong><small>Esencial</small></span>
        </div>
        <nav>
          <NavLink to="/" end>Inicio</NavLink>
          <NavLink to="/fundamentos">Fundamentos</NavLink>
          <NavLink to="/proyectos">Proyectos</NavLink>
        </nav>
        <div className="nav__status" title="El worker es el proceso que entrena las redes">
          <span className={`dot ${online ? 'dot--ok' : online === false ? 'dot--bad' : ''}`} />
          {online ? 'Motor de entrenamiento listo' : online === false ? 'Motor iniciando…' : 'Comprobando…'}
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span className="topbar__title">Plataforma de redes neuronales artificiales</span>
          <div className="topbar__user">
            <span>{user.displayName}</span>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => { logout(); navigate('/'); }}>Cerrar sesión</button>
          </div>
        </header>
        <main className="canvas">{children}</main>
      </div>
    </div>
  );
}
