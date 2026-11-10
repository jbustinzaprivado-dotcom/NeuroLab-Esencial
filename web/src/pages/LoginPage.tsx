import { useState } from 'react';
import { api, setToken, type User } from '../api';

export function LoginPage({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ token: string; user: User }>('/auth/login', { method: 'POST', json: { username, password } });
      setToken(result.token);
      onLogin(result.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <form className="login__card" onSubmit={submit}>
        <span className="nav__logo nav__logo--lg" aria-hidden="true">N</span>
        <h1>NeuroLab Esencial</h1>
        <p className="muted">Define la estructura y crea una red neuronal artificial con TensorFlow y Keras.</p>
        <label htmlFor="user">Usuario</label>
        <input id="user" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <label htmlFor="pass">Contraseña</label>
        <input id="pass" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error ? <p className="alert alert--error" role="alert">{error}</p> : null}
        <button className="btn btn--primary" disabled={busy}>{busy ? 'Entrando…' : 'Iniciar sesión'}</button>
        <p className="small muted">Demo: <code>ana.quispe</code> o <code>diego.salas</code> · contraseña <code>neurolab2026</code>. La primera visita puede tardar ~1 min si el servidor estaba dormido.</p>
      </form>
    </div>
  );
}
