# NeuroLab Esencial

Versión mínima y funcional de **NeuroLab Enterprise**, pensada para publicarse en un hosting web **gratuito** y
demostrar el sistema en vivo. Cumple la tarea de la Semana 11 (*"Define la estructura y crea una red neuronal
artificial"*) y el criterio de MVP del §18 del Documento Maestro, con un entrenamiento **real** en
TensorFlow/Keras.

> No reemplaza al sistema completo: deja fuera la parte empresarial (roles múltiples, Keycloak, PostgreSQL,
> almacenamiento de objetos, reportes y administración). El detalle de qué se conservó, qué se quitó y por qué
> está en [docs/analisis-y-alcance.md](docs/analisis-y-alcance.md).

## Qué hace

| Pantalla | Qué permite |
|---|---|
| **Inicio** | Resumen de proyectos, entrenamientos y versiones de modelo, y los 4 pasos de la Semana 11 |
| **Fundamentos** | Qué es una red neuronal, una neurona interactiva (z = Σw·x + b), activaciones, cómo aprende, los 4 tipos de red y glosario |
| **Proyectos** | Crear un proyecto con su problema, tipo de red (Feedforward, RNN, CNN o GAN) y la justificación |
| **Datos** | Datasets demo (Iris, fuga de clientes, viviendas) o un CSV propio validado (≤ 1 MB, ≤ 5000 filas) |
| **Arquitectura** | Diseñador de capas Dense/Dropout con validación en el servidor, diagrama de la red, parámetros y versiones |
| **Entrenar** | Épocas, lote, optimizador, tasa de aprendizaje y semilla; el trabajo va a una cola |
| **Seguimiento** | Estado (En cola → Preparando → Ejecutando → Completado), curvas y registro en vivo, cancelación |
| **Historial y modelos** | Cada ejecución con su resultado; cada modelo como versión inmutable con huella SHA-256, descargable |

**Usuarios demo:** `ana.quispe` y `diego.salas`, contraseña `neurolab2026`. Cada uno ve solo sus proyectos.

## Cómo está armado

```
Navegador ── React + TypeScript (web/)
   │  HTTPS
   ▼
API FastAPI (server/app) ──► SQLite (data/neurolab.db)
   │  cola en la base de datos
   ▼
Worker Python (server/worker) ──► TensorFlow/Keras ──► data/models/*.zip
```

- La **API nunca entrena** (§5 y §16): deja el trabajo en cola y responde al instante.
- El **worker** es otro proceso: toma la cola, entrena y publica cada época. El navegador la recibe por **SSE**, y si
  se corta la conexión, retoma desde el último evento.
- `run.py` arranca los dos procesos. Si uno se cae, detiene el otro para que el hosting reinicie todo.

## Ejecutarlo en tu PC (Windows)

Requisitos: Python 3.12 o superior y Node.js 20 o superior.

1. Doble clic en **`iniciar.bat`**. La primera vez crea el entorno, instala TensorFlow y compila la web (varios minutos).
2. Abre **http://localhost:8000**.

A mano, en cualquier sistema:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # en Linux/macOS: .venv/bin/pip
cd web && npm install && npm run build && cd ..
.venv/Scripts/python run.py
```

Si el puerto 8000 está ocupado: `set PORT=8020` (Windows) antes de `run.py`.

## Pruebas

```bash
.venv/Scripts/pip install -r requirements-dev.txt
cd server && ../.venv/Scripts/python -m pytest -q
```

Cubren: login y bloqueo, acceso a proyectos ajenos, validación de arquitecturas y versiones, carga de CSV,
entrenamiento real de clasificación y de regresión, canal en vivo, cancelación y límites.

## Publicarlo gratis en Render

Render construye la imagen desde un repositorio de GitHub.

1. Crea un repositorio nuevo en GitHub y sube el contenido de esta carpeta (sin `data/`, `web/node_modules/` ni
   `web/dist/`: ya están en `.gitignore`).
2. En [render.com](https://render.com), entra con tu cuenta y elige **New → Blueprint**. Conecta el repositorio:
   Render detecta `render.yaml` y crea el servicio **neurolab-esencial** en el plan **Free**. Si Render pidiera un
   método de pago, revisa que el plan elegido sea *Free*: este servicio no usa nada de pago.
   - Alternativa: **New → Web Service**, elige el repositorio, *Language: Docker*, *Instance type: Free*.
3. La primera construcción tarda unos 10 minutos (instala TensorFlow).
4. Abre `https://neurolab-esencial.onrender.com` (o la dirección que te muestre Render) y entra con un usuario demo.

### Qué esperar del plan gratuito

| Límite de Render Free | Efecto |
|---|---|
| 512 MB de memoria y 0,1 CPU | Entrena los datasets demo, pero más lento que en una PC (Iris: ~30–60 s, estimado) |
| Se duerme tras 15 min sin visitas | La primera visita tarda ~1 min; ábrelo unos minutos antes de la demo |
| Disco efímero | Al dormirse o reiniciarse se borra lo creado y vuelven los datos demo |

Medido en local: la API usa ~85 MB y el worker con TensorFlow ~390 MB. Queda poco margen, por eso los límites
de tamaño de los datasets y de las capas.

## Configuración

Variables opcionales (`NEUROLAB_*`): `SECRET_KEY`, `DEMO_PASSWORD`, `DATA_DIR`, `MAX_UPLOAD_KB` (1024),
`MAX_EPOCHS` (100), `MAX_BATCH` (256), `MAX_JOB_MINUTES` (10). Ver `server/app/config.py`.

## Estructura

```
run.py                 arranca API y worker
iniciar.bat            arranque en Windows con doble clic
Dockerfile, render.yaml despliegue en un solo servicio gratuito
server/app/            API: rutas, seguridad, validación de datos y arquitecturas, datos demo
server/worker/         worker: preparación de datos y entrenamiento con TensorFlow/Keras
server/tests/          pruebas automáticas
web/src/               interfaz React + TypeScript
docs/                  análisis del Documento Maestro y alcance de esta versión
```
