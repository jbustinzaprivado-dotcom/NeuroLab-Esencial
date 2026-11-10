"""Worker de entrenamiento: proceso aparte de la API (§5 y §16 del Documento Maestro).

Toma los trabajos en cola uno por uno, sigue la máquina de estados del §10
(QUEUED → PREPARING → RUNNING → COMPLETED / FAILED / CANCELLED), publica cada época y
guarda el modelo como versión inmutable con su huella SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import socket
import threading
import time
import traceback
import zipfile
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
# Un solo hilo: el plan gratuito da 0,1 CPU y más hilos solo suman memoria y cambios de contexto.
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import Dataset, ModelVersion, SessionLocal, TrainingJob, emit, init_db, utcnow  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker: %(message)s")
logger = logging.getLogger("neurolab.worker")
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"
HEARTBEAT_FILE = settings.data_dir / "worker.heartbeat"
_stop = threading.Event()


class ControlledError(Exception):
    """Error esperado cuyo mensaje se muestra tal cual al usuario."""


def beat() -> None:
    HEARTBEAT_FILE.touch()


def _heartbeat_loop() -> None:
    # Señal de vida cada 5 s, también durante una época larga: la API la usa para "worker en línea".
    while not _stop.wait(5):
        beat()


def _transition(db, job: TrainingJob, status: str, reason: str | None = None) -> None:
    job.status, job.status_reason = status, reason if reason is not None else job.status_reason
    if status in {"COMPLETED", "FAILED", "CANCELLED"}:
        job.ended_at = utcnow()
    emit(db, job.id, "status", status=status, progress=job.progress, epoch=job.epoch, reason=reason)
    if status == "FAILED" and reason:
        emit(db, job.id, "log", message=reason, level="error")


def recover_interrupted() -> None:
    """Hay un solo worker: lo que quedó a medias al reiniciar no va a terminar solo."""
    with SessionLocal() as db:
        for job in db.query(TrainingJob).filter(TrainingJob.status.in_(["PREPARING", "RUNNING"])):
            _transition(db, job, "FAILED", "El servidor se reinició durante el entrenamiento; reinténtalo.")
        db.commit()


def reap_stale() -> None:
    cutoff = utcnow() - timedelta(seconds=settings.worker_stale_seconds)
    with SessionLocal() as db:
        stale = db.query(TrainingJob).filter(TrainingJob.status.in_(["PREPARING", "RUNNING"]),
                                             TrainingJob.heartbeat_at < cutoff).all()
        for job in stale:
            _transition(db, job, "FAILED", "El worker dejó de responder; reintenta el trabajo.")
        db.commit()


def claim() -> str | None:
    """Toma el trabajo más antiguo en cola con un UPDATE condicional: nunca dos veces el mismo."""
    with SessionLocal() as db:
        row = db.execute(text("SELECT id FROM training_jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1")).first()
        if row is None:
            return None
        now = utcnow()
        taken = db.execute(
            text("UPDATE training_jobs SET status='PREPARING', worker_id=:w, heartbeat_at=:n, started_at=:n "
                 "WHERE id=:id AND status='QUEUED'"),
            {"w": WORKER_ID, "n": now, "id": row.id},
        ).rowcount
        if not taken:
            db.rollback()
            return None
        emit(db, row.id, "status", status="PREPARING", progress=0, epoch=0, reason=None)
        db.commit()
        return row.id


def _log(job_id: str, message: str, level: str = "info") -> None:
    with SessionLocal() as db:
        emit(db, job_id, "log", message=message, level=level)
        db.commit()


def run_job(job_id: str) -> str:
    import keras

    from worker.training import build_model, evaluate, prepare

    started = time.monotonic()
    try:
        with SessionLocal() as db:
            job = db.get(TrainingJob, job_id)
            params, config = dict(job.params_json), dict(job.architecture.config_json)
            dataset: Dataset = job.dataset
            schema, dataset_name, target = dataset.schema_json, dataset.name, job.target
            arch_name, arch_version = job.architecture.name, job.architecture.version
        _log(job_id, f"Preparando «{dataset_name}» (objetivo «{target}»).")

        content = (settings.datasets_dir / f"{dataset.id}.csv").read_bytes()
        try:
            data = prepare(content, schema, target, params["task"], params["split"], params["seed"])
        except ValueError as exc:
            raise ControlledError(f"Preprocesamiento: {exc}") from exc

        keras.utils.set_random_seed(params["seed"])
        model = build_model(config, data.x_train.shape[1], params["task"], params["optimizer"],
                            params["learning_rate"])
        _log(job_id, f"Particiones: {len(data.y_train)} entrenamiento · {len(data.y_val)} validación · "
                     f"{len(data.y_test)} prueba. Entrada de {data.x_train.shape[1]} neuronas; "
                     f"{model.count_params():,} parámetros.")

        with SessionLocal() as db:
            job = db.get(TrainingJob, job_id)
            if job.cancel_requested:
                _transition(db, job, "CANCELLED", job.status_reason or "Cancelado por el usuario.")
                db.commit()
                return "CANCELLED"
            _transition(db, job, "RUNNING")
            db.commit()

        epochs = params["epochs"]
        limit = settings.max_job_minutes * 60
        outcome = {"stop": None}

        class Progress(keras.callbacks.Callback):
            def on_epoch_end(self, epoch, logs=None):
                logs = {k: float(v) for k, v in (logs or {}).items()}
                with SessionLocal() as db:
                    job = db.get(TrainingJob, job_id)
                    job.epoch, job.progress, job.heartbeat_at = epoch + 1, (epoch + 1) / epochs * 100, utcnow()
                    emit(db, job_id, "metric", epoch=epoch + 1, **logs)
                    if job.cancel_requested:
                        outcome["stop"] = "cancelled"
                    elif time.monotonic() - started > limit:
                        outcome["stop"] = "timeout"
                    elif _stop.is_set():
                        outcome["stop"] = "shutdown"
                    db.commit()
                if outcome["stop"]:
                    self.model.stop_training = True

        model.fit(data.x_train, data.y_train, validation_data=(data.x_val, data.y_val), epochs=epochs,
                  batch_size=params["batch_size"], callbacks=[Progress()], verbose=0)

        if outcome["stop"]:
            reason = {"cancelled": None, "timeout": f"Superó el límite de {settings.max_job_minutes} min.",
                      "shutdown": "El servidor se detuvo durante el entrenamiento; reinténtalo."}[outcome["stop"]]
            with SessionLocal() as db:
                job = db.get(TrainingJob, job_id)
                status = "CANCELLED" if outcome["stop"] == "cancelled" else "FAILED"
                _transition(db, job, status, reason or job.status_reason or "Cancelado por el usuario.")
                db.commit()
            return status

        metrics = evaluate(model, data, params["task"])
        _register(job_id, model, data, metrics, arch_name, arch_version, dataset, params)
        return "COMPLETED"

    except ControlledError as exc:
        _finish_failed(job_id, str(exc))
    except Exception:  # noqa: BLE001 — cualquier fallo cierra el trabajo con un estado conocido
        logger.error("Fallo en %s:\n%s", job_id, traceback.format_exc())
        _finish_failed(job_id, "Error interno del motor de entrenamiento. La traza quedó en el registro del servidor.")
    return "FAILED"


def _finish_failed(job_id: str, reason: str) -> None:
    with SessionLocal() as db:
        job = db.get(TrainingJob, job_id)
        if job.status not in {"COMPLETED", "FAILED", "CANCELLED"}:
            _transition(db, job, "FAILED", reason)
            db.commit()


def _register(job_id, model, data, metrics, arch_name, arch_version, dataset, params) -> None:
    """Guarda modelo, preprocesamiento y metadatos en un ZIP inmutable con su huella SHA-256."""
    with SessionLocal() as db:
        job = db.get(TrainingJob, job_id)
        last = (db.query(ModelVersion).filter(ModelVersion.project_id == job.project_id)
                .order_by(ModelVersion.version.desc()).first())
        version = (last.version + 1) if last else 1
        metadata = {
            "jobId": job_id, "projectId": job.project_id, "version": version,
            "architecture": {"name": arch_name, "version": arch_version},
            "dataset": {"id": dataset.id, "name": dataset.name, "checksum": dataset.checksum},
            "target": job.target, "params": params, "metrics": metrics, "features": data.feature_names,
            "codeVersion": settings.code_version, "trainedBy": job.created_by, "createdAt": utcnow().isoformat(),
        }
        key = f"{job_id}.zip"
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            model.save(folder / "model.keras")
            (folder / "preprocess.json").write_text(json.dumps(data.preprocess, ensure_ascii=False, indent=2))
            (folder / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
            with zipfile.ZipFile(settings.models_dir / key, "w", zipfile.ZIP_DEFLATED) as bundle:
                for name in ("model.keras", "preprocess.json", "metadata.json"):
                    bundle.write(folder / name, name)
        checksum = hashlib.sha256((settings.models_dir / key).read_bytes()).hexdigest()
        db.add(ModelVersion(project_id=job.project_id, job_id=job_id, version=version, storage_key=key,
                            checksum=checksum, metadata_json=metadata))
        job.result_json = {"metrics": metrics, "modelVersion": version, "checksum": checksum}
        job.progress = 100.0
        emit(db, job_id, "log", message=f"Modelo registrado como versión {version} (SHA-256 {checksum[:12]}…).")
        _transition(db, job, "COMPLETED")
        db.commit()


def _free_memory() -> None:
    """Suelta el grafo de Keras del trabajo anterior: en el hosting gratuito hay 512 MB en total."""
    import gc

    import keras

    keras.backend.clear_session()
    gc.collect()


def main() -> None:
    init_db()
    beat()
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: _stop.set())
    recover_interrupted()
    logger.info("Cargando TensorFlow…")
    import keras  # noqa: F401 — se carga al arrancar para que el primer entrenamiento empiece antes
    logger.info("Worker %s listo; esperando trabajos.", WORKER_ID)
    while not _stop.is_set():
        reap_stale()
        job_id = claim()
        if job_id is None:
            _stop.wait(settings.worker_poll_seconds)
            continue
        logger.info("Trabajo %s: %s", job_id, run_job(job_id))
        _free_memory()
    logger.info("Worker detenido.")


if __name__ == "__main__":
    main()
