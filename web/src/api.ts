/* Cliente de la API: tipos, peticiones con token y lectura del canal de eventos (SSE). */

export type Family = 'FEEDFORWARD' | 'RNN' | 'CNN' | 'GAN';
export type JobStatus = 'QUEUED' | 'PREPARING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface User { id: string; username: string; displayName: string }
export interface Project { id: string; name: string; description: string; family: Family; justification: string; createdAt: string }
export interface Column { name: string; kind: 'integer' | 'float' | 'categorical' | 'empty'; nulls: number; unique: number }
export interface Dataset { id: string; name: string; filename: string; rows: number; columns: Column[]; checksum: string; origin: string; createdAt: string }
export interface DemoDataset { key: string; name: string; description: string; target: string }
export type HiddenLayer = { type: 'Dense'; units: number; activation: string } | { type: 'Dropout'; rate: number };
export interface ArchitectureConfig { dataset_id: string; target: string; layers: HiddenLayer[]; output: { units: number; activation: string } }
export interface LayerShape { name: string; units: number; activation?: string; rate?: number; params: number }
export interface Summary {
  valid: boolean; errors: string[]; warnings: string[]; task?: 'classification' | 'regression'; classes?: number;
  inputWidth?: number; layers: LayerShape[]; totalParams: number; expectedOutput?: string;
}
export interface Architecture { id: string; name: string; version: number; config: ArchitectureConfig; summary: Summary | null; createdAt: string }
export interface ClassMetrics { accuracy: number; testRows: number; classes: string[]; confusion: number[][] }
export interface RegressionMetrics { r2: number; mae: number; rmse: number; testRows: number }
export interface Job {
  id: string; projectId: string; status: JobStatus; statusReason: string | null; progress: number; epoch: number;
  params: { epochs: number; batch_size: number; learning_rate: number; optimizer: string; seed: number; task: string; classes: number; codeVersion: string; architectureVersion: number };
  target: string; architecture: { id: string; name: string; version: number }; dataset: { id: string; name: string; checksum: string };
  result: { metrics?: ClassMetrics | RegressionMetrics; modelVersion?: number; checksum?: string };
  cancelRequested: boolean; createdAt: string; startedAt: string | null; endedAt: string | null;
}
export interface JobEvent { id?: number; kind: 'status' | 'metric' | 'log'; payload: Record<string, unknown>; at: string }
export interface ModelVersion { id: string; jobId: string; version: number; checksum: string; metadata: Record<string, any>; createdAt: string }
export interface Dashboard { projects: number; jobs: number; active: number; completed: number; models: number; recent: Job[]; workerOnline: boolean }
export interface Health { status: string; workerOnline: boolean; queued: number; version: string }

const TOKEN_KEY = 'neurolab.token';

export function getToken(): string | null {
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token: string | null) {
  try { token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* sin almacenamiento */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

function detailOf(body: any, fallback: string): string {
  if (typeof body?.detail === 'string') return body.detail;
  if (Array.isArray(body?.detail)) return body.detail.map((d: any) => `${(d.loc ?? []).slice(-1)[0] ?? ''}: ${d.msg}`).join(' · ');
  return fallback;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) { headers.set('Content-Type', 'application/json'); body = JSON.stringify(init.json); }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...init, headers, body, signal: controller.signal });
  } catch {
    throw new ApiError(0, 'No hay conexión con el servidor. Si estaba dormido, espera un minuto y reintenta.');
  } finally {
    clearTimeout(timer);
  }
  if (response.status === 401 && path !== '/auth/login') {
    setToken(null);
    window.dispatchEvent(new Event('neurolab:logout'));
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, detailOf(data, `Error ${response.status}`));
  return data as T;
}

/** Lee el canal SSE con fetch (permite enviar el token por cabecera) y reconecta desde el último evento. */
export function followEvents(jobId: string, onEvent: (event: JobEvent & { id: number }) => void, onEnd: () => void, startAfter = 0): () => void {
  let lastId = startAfter;
  let stopped = false;
  let controller = new AbortController();

  const connect = async () => {
    while (!stopped) {
      controller = new AbortController();
      try {
        const headers: Record<string, string> = { Accept: 'text/event-stream' };
        const token = getToken();
        if (token) headers.Authorization = `Bearer ${token}`;
        if (lastId) headers['Last-Event-ID'] = String(lastId);
        const response = await fetch(`/api/v1/training-jobs/${jobId}/events`, { headers, signal: controller.signal });
        if (!response.ok || !response.body) throw new Error(String(response.status));
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let cut: number;
          while ((cut = buffer.indexOf('\n\n')) >= 0) {
            const block = buffer.slice(0, cut);
            buffer = buffer.slice(cut + 2);
            let id = 0, event = '', data = '';
            for (const line of block.split('\n')) {
              if (line.startsWith('id: ')) id = Number(line.slice(4));
              else if (line.startsWith('event: ')) event = line.slice(7);
              else if (line.startsWith('data: ')) data += line.slice(6);
            }
            if (event === 'end') { stopped = true; onEnd(); return; }
            if (!event || !data) continue;
            lastId = id || lastId;
            onEvent({ ...(JSON.parse(data) as JobEvent), id });
          }
        }
      } catch {
        if (stopped) return;
      }
      // Se cortó la conexión: espera un poco y retoma desde el último evento recibido.
      if (!stopped) await new Promise((r) => setTimeout(r, 1500));
    }
  };
  void connect();
  return () => { stopped = true; controller.abort(); };
}

export const STATUS_LABEL: Record<JobStatus, string> = {
  QUEUED: 'En cola', PREPARING: 'Preparando', RUNNING: 'Ejecutando', COMPLETED: 'Completado', FAILED: 'Fallido', CANCELLED: 'Cancelado',
};
export const FAMILY_LABEL: Record<Family, string> = { FEEDFORWARD: 'Feedforward', RNN: 'Recurrente (RNN)', CNN: 'Convolucional (CNN)', GAN: 'Generativa (GAN)' };
export const TERMINAL: JobStatus[] = ['COMPLETED', 'FAILED', 'CANCELLED'];
