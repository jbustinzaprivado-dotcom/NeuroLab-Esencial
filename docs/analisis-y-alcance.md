# Análisis del Documento Maestro y alcance de NeuroLab Esencial

## 1. Los tres niveles de exigencia del documento

El Documento Maestro (v1.0, octubre 2026) mezcla tres niveles. Su §19 lo dice expresamente: *"La arquitectura
enterprise, módulos, entidades, endpoints y criterios de producción incluidos en este documento son una
propuesta de diseño para convertir ese contenido en un sistema real."*

| Nivel | Fuente | Qué exige |
|---|---|---|
| **1. Documento base** (curso PIAD-427, Semana 11) | §3 y §19 | La tarea *"Define la estructura y crea una red neuronal artificial"* con 4 operaciones |
| **2. MVP** | §18 | El flujo mínimo para darlo por demostrable |
| **3. Propuesta enterprise** | §4 a §17 | 10 módulos, 5 roles, PostgreSQL, objetos, cola y workers, auditoría, límites, Docker, monitoreo y checklist de producción |

El archivo `PIAD-427_CONTENIDO.pdf` citado en el §19 no estaba disponible; el nivel 1 se toma de la
transcripción que hace el propio Documento Maestro en su §3.

NeuroLab Esencial cubre **los niveles 1 y 2 completos**, y del nivel 3 conserva las reglas que hacen que el
sistema funcione bien (worker separado, máquina de estados, versiones inmutables, validación en el servidor),
no la infraestructura empresarial.

## 2. Nivel 1: las 4 operaciones de la Semana 11

| Operación | Evidencia que pide el §3 | Dónde se cumple |
|---|---|---|
| Definir la red neuronal y su importancia | Ficha conceptual consultable | **Fundamentos**: concepto, importancia, cómo aprende, glosario |
| Describir su estructura: neuronas, capas, conexiones y activaciones | Diagrama y configuración guardada | **Fundamentos** (neurona interactiva, activaciones) y **Arquitectura** (diagrama, capas y versión guardada) |
| Identificar tipos: Feedforward, RNN, CNN y GAN | Tipo seleccionado y justificación registrada | **Fundamentos** (catálogo con usos y restricciones) y **Proyectos** (tipo y justificación obligatorios) |
| Crear una red con TensorFlow y Keras | Modelo entrenado o error técnico trazable | **Entrenar** y **Seguimiento**: entrenamiento real con Keras; si falla, un mensaje claro y la traza en el servidor |

## 3. Nivel 2: el criterio del MVP (§18)

| Requisito del §18 | Cómo se cumple |
|---|---|
| Un usuario **autenticado** | Inicio de sesión con contraseña cifrada (PBKDF2), token firmado y bloqueo tras 5 intentos |
| **Crea un proyecto** | Pantalla Proyectos |
| Configura una **Feedforward** con capas y activaciones válidas | Diseñador validado en el servidor contra el dataset y el objetivo |
| Selecciona un **dataset de prueba** | Tres datasets demo o un CSV propio validado |
| Inicia un **entrenamiento real en TensorFlow/Keras** | Worker con Keras 3 sobre TensorFlow 2.21 |
| Ve **estado y métricas sin recargar** | Canal SSE con reconexión desde el último evento |
| **Consulta el resultado después** | Historial y ficha de cada entrenamiento, persistidos en la base |
| **Conserva la versión del modelo con trazabilidad** | ZIP inmutable (modelo, preprocesamiento, metadatos) con SHA-256, dataset, parámetros, semilla y versión de código |
| RNN, CNN y GAN como **opciones documentadas** | Catálogo en Fundamentos; un proyecto puede declararlas con su justificación, pero no se diseñan ni entrenan |

## 4. Nivel 3: qué se conservó y qué se dejó fuera

### Se conserva (reglas que dan robustez)

- **Worker separado de la API** (§5, §16): el entrenamiento nunca corre dentro de la petición HTTP.
- **Máquina de estados** (§10): QUEUED → PREPARING → RUNNING → COMPLETED / FAILED / CANCELLED.
- **Cancelación cooperativa** (§10): en cola se cancela al instante; en ejecución, al terminar la época.
- **Versiones que no se sobrescriben** (§10), tanto de arquitecturas como de modelos.
- **Validación en el servidor** (§10): el navegador no decide qué es válido.
- **Validación de archivos** (§10): tipo, tamaño, filas, columnas y contenido.
- **Acceso solo a lo propio** (§11, §12): un proyecto ajeno responde 404.
- **Límites** de épocas, lote, duración, tamaño de carga y trabajos activos (§10, §11).
- **Tiempo real con recuperación** (§12, §16): el estado se guarda en la base y el canal retoma al reconectar.
- **Pruebas** unitarias, de integración y del flujo principal (§12, §15).

### Se deja fuera, y dónde se aparta del Documento Maestro

| Elemento del documento | En NeuroLab Esencial | Por qué |
|---|---|---|
| §5 PostgreSQL | **SQLite**, que se reinicia con el servidor | Un servicio gratuito y una demo única no necesitan otro servidor de base |
| §5 Almacenamiento de objetos | Carpeta local `data/` | Mismo motivo; los archivos son pequeños |
| §11 "Autenticación mediante proveedor seguro" | Login propio, sin Keycloak | Keycloak necesita su propio servidor y memoria que el plan gratuito no tiene |
| §4.2 Cinco roles y miembros por proyecto | Un rol: cada usuario gestiona sus proyectos | El §18 pide un usuario autenticado, no roles |
| M07 comparación y observaciones | Evaluación final (exactitud y matriz de confusión, o R², MAE y RMSE) | El §18 no pide comparar ejecuciones |
| M08 flujo borrador → revisado → aprobado | Versiones inmutables, sin flujo de aprobación | El §18 pide conservar la versión, no aprobarla |
| M09 Reportes, M10 Administración | No incluidos | Fuera del §18 |
| §5 Docker multiservicio, monitoreo, CI/CD, respaldos | Un solo contenedor | Sin producción, no aplica la fase 6 |
| Entrenar RNN, CNN y GAN | Solo documentadas | El §18 las deja para habilitarse progresivamente |

Estas desviaciones son decisiones conscientes para el objetivo de esta versión: **demostrar el sistema en un
hosting gratuito**, no llevarlo a producción. El sistema completo, NeuroLab Enterprise, sí las cumple.

### Una regla que se respetó a propósito

El §5 dice: *"No ejecutar TensorFlow directamente en el navegador para entrenamientos reales"*. Entrenar con
TensorFlow.js en el navegador habría permitido un hosting estático, siempre encendido y más rápido, pero
contradice esa regla. Por eso esta versión entrena en Python, aun con los límites del plan gratuito.

## 5. Por qué cabe en un hosting gratuito

| Necesidad | Sistema completo | NeuroLab Esencial |
|---|---|---|
| Servicios | 6 (web, API, worker, Keycloak, PostgreSQL, almacén) | **1 contenedor** con 2 procesos (API y worker) |
| Memoria medida | Varios GB entre todas las piezas | ~85 MB la API y ~390 MB el worker con TensorFlow |
| Dependencias de Python | pandas, scikit-learn, psutil, boto3, etc. | Solo FastAPI, SQLAlchemy, NumPy y TensorFlow/Keras |
| Base de datos | Servidor PostgreSQL | Un archivo SQLite |

Render Free da 512 MB y 0,1 CPU, y se duerme tras 15 minutos sin visitas. El margen de memoria es justo,
así que se limitan los datasets (≤ 1 MB, ≤ 5000 filas, ≤ 60 columnas) y las capas (≤ 8 capas, ≤ 512 neuronas).
