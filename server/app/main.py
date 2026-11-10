"""API de NeuroLab Esencial (FastAPI). Nunca entrena: deja el trabajo en cola y el worker,
otro proceso, lo ejecuta (§5 y §16 del Documento Maestro). También sirve la web compilada."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import architecture as arch_mod
from app import datasets as ds
from app.config import settings
from app.db import (
    Architecture, AuditEvent, Dataset, JobEvent, ModelVersion, Project, SessionLocal, TrainingJob, User, audit,
    emit, init_db,
)
from app.security import CurrentUser, login
from app.seed import DEMO_DATASETS, add_demo_dataset, seed

logger = logging.getLogger("neurolab.api")
API = "/api/v1"
FAMILIES = {"FEEDFORWARD", "RNN", "CNN", "GAN"}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
HEARTBEAT_FILE = settings.data_dir / "worker.heartbeat"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if seed():
        logger.info("Base vacía: se cargaron los datos demo.")
    yield


app = FastAPI(title="NeuroLab Esencial", version=settings.code_version, lifespan=lifespan,
              docs_url=f"{API}/docs", openapi_url=f"{API}/openapi.json")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _not_found(what: str = "Recurso") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} no encontrado.")


def _own_project(db, project_id: str, user: User) -> Project:
    project = db.get(Project, project_id)
    # Un proyecto ajeno responde igual que uno inexistente: no se revela que existe (§11).
    if project is None or project.owner_id != user.id:
        raise _not_found("Proyecto")
    return project


# ------------------------------------------------------------------ serializadores

def project_out(p: Project) -> dict:
    return {"id": p.id, "name": p.name, "description": p.description, "family": p.family,
            "justification": p.justification, "createdAt": _iso(p.created_at)}


def dataset_out(d: Dataset) -> dict:
    return {"id": d.id, "name": d.name, "filename": d.filename, "rows": d.rows, "columns": d.schema_json,
            "checksum": d.checksum, "origin": d.origin, "createdAt": _iso(d.created_at)}


def architecture_out(a: Architecture, schema: list[dict] | None) -> dict:
    summary = None
    if schema is not None:
        summary = arch_mod.validate(arch_mod.ArchitectureIn(name=a.name, **a.config_json), schema)
    return {"id": a.id, "name": a.name, "version": a.version, "config": a.config_json, "summary": summary,
            "createdAt": _iso(a.created_at)}


def job_out(j: TrainingJob) -> dict:
    return {
        "id": j.id, "projectId": j.project_id, "status": j.status, "statusReason": j.status_reason,
        "progress": round(j.progress, 1), "epoch": j.epoch, "params": j.params_json, "target": j.target,
        "architecture": {"id": j.architecture.id, "name": j.architecture.name, "version": j.architecture.version},
        "dataset": {"id": j.dataset.id, "name": j.dataset.name, "checksum": j.dataset.checksum},
        "result": j.result_json, "cancelRequested": j.cancel_requested,
        "createdAt": _iso(j.created_at), "startedAt": _iso(j.started_at), "endedAt": _iso(j.ended_at),
    }


def model_out(m: ModelVersion) -> dict:
    return {"id": m.id, "jobId": m.job_id, "version": m.version, "checksum": m.checksum,
            "metadata": m.metadata_json, "createdAt": _iso(m.created_at)}


# ------------------------------------------------------------------ sesión y estado

class LoginIn(BaseModel):
    username: str
    password: str


@app.post(f"{API}/auth/login")
def do_login(payload: LoginIn):
    user, token = login(payload.username, payload.password)
    with SessionLocal() as db:
        audit(db, user.id, "auth.login")
        db.commit()
    return {"token": token, "user": {"id": user.id, "username": user.username, "displayName": user.display_name}}


@app.get(f"{API}/auth/me")
def me(user: User = CurrentUser):
    return {"id": user.id, "username": user.username, "displayName": user.display_name}


def worker_online() -> bool:
    try:
        return time.time() - HEARTBEAT_FILE.stat().st_mtime < 20
    except FileNotFoundError:
        return False


@app.get(f"{API}/health")
def health():
    with SessionLocal() as db:
        queued = db.query(TrainingJob).filter(TrainingJob.status == "QUEUED").count()
    return {"status": "ok", "workerOnline": worker_online(), "queued": queued, "version": settings.code_version}


@app.get(f"{API}/dashboard")
def dashboard(user: User = CurrentUser):
    with SessionLocal() as db:
        projects = db.query(Project).filter(Project.owner_id == user.id).all()
        ids = [p.id for p in projects]
        jobs = (db.query(TrainingJob).filter(TrainingJob.project_id.in_(ids))
                .order_by(TrainingJob.created_at.desc()).all()) if ids else []
        models = db.query(ModelVersion).filter(ModelVersion.project_id.in_(ids)).count() if ids else 0
        return {
            "projects": len(projects),
            "jobs": len(jobs),
            "active": sum(j.status not in TERMINAL for j in jobs),
            "completed": sum(j.status == "COMPLETED" for j in jobs),
            "models": models,
            "recent": [job_out(j) for j in jobs[:6]],
            "workerOnline": worker_online(),
        }


# ------------------------------------------------------------------ proyectos

class ProjectIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    family: str
    justification: str = Field(min_length=10, max_length=2000)


@app.get(f"{API}/projects")
def list_projects(user: User = CurrentUser):
    with SessionLocal() as db:
        rows = db.query(Project).filter(Project.owner_id == user.id).order_by(Project.created_at.desc()).all()
        return [project_out(p) for p in rows]


@app.post(f"{API}/projects", status_code=201)
def create_project(payload: ProjectIn, user: User = CurrentUser):
    if payload.family not in FAMILIES:
        raise HTTPException(422, "Familia no válida.")
    with SessionLocal() as db:
        project = Project(owner_id=user.id, **payload.model_dump())
        db.add(project)
        db.flush()
        audit(db, user.id, "project.create", project.id, family=payload.family)
        db.commit()
        return project_out(project)


@app.get(f"{API}/projects/{{project_id}}")
def get_project(project_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        return project_out(_own_project(db, project_id, user))


# ------------------------------------------------------------------ datasets

@app.get(f"{API}/demo-datasets")
def demo_datasets(_: User = CurrentUser):
    return [{"key": key, "name": spec["name"], "description": spec["description"], "target": spec["target"]}
            for key, spec in DEMO_DATASETS.items()]


@app.get(f"{API}/projects/{{project_id}}/datasets")
def list_datasets(project_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        rows = db.query(Dataset).filter(Dataset.project_id == project_id).order_by(Dataset.created_at).all()
        return [dataset_out(d) for d in rows]


class DemoDatasetIn(BaseModel):
    key: str


@app.post(f"{API}/projects/{{project_id}}/datasets/demo", status_code=201)
def add_demo(project_id: str, payload: DemoDatasetIn, user: User = CurrentUser):
    if payload.key not in DEMO_DATASETS:
        raise HTTPException(422, "Dataset demo desconocido.")
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        dataset = add_demo_dataset(db, project_id, payload.key)
        audit(db, user.id, "dataset.add_demo", project_id, dataset=dataset.name)
        db.commit()
        return dataset_out(dataset)


@app.post(f"{API}/projects/{{project_id}}/datasets/upload", status_code=201)
async def upload_dataset(project_id: str, name: str = Form(...), file: UploadFile = File(...),
                         user: User = CurrentUser):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, "Solo se aceptan archivos .csv.")
    content = await file.read(settings.max_upload_kb * 1024 + 1)
    try:
        report = ds.inspect_csv(content)
    except ds.DatasetRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    clean = name.strip()[:120] or file.filename
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        dataset = Dataset(project_id=project_id, name=clean, filename=file.filename, rows=report.rows,
                          schema_json=report.schema, checksum=report.checksum, origin="carga")
        db.add(dataset)
        db.flush()
        (settings.datasets_dir / f"{dataset.id}.csv").write_bytes(content)
        audit(db, user.id, "dataset.upload", project_id, dataset=clean, rows=report.rows)
        db.commit()
        return dataset_out(dataset)


@app.get(f"{API}/datasets/{{dataset_id}}/preview")
def preview_dataset(dataset_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        dataset = db.get(Dataset, dataset_id)
        if dataset is None:
            raise _not_found("Dataset")
        _own_project(db, dataset.project_id, user)
    lines = (settings.datasets_dir / f"{dataset_id}.csv").read_text(encoding="utf-8-sig").splitlines()
    return {"header": lines[0].split(","), "rows": [line.split(",") for line in lines[1:9]]}


# ------------------------------------------------------------------ arquitecturas

def _dataset_for(db, payload: arch_mod.ArchitectureIn, project_id: str) -> Dataset:
    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None or dataset.project_id != project_id:
        raise HTTPException(422, "El dataset no pertenece a este proyecto.")
    return dataset


@app.post(f"{API}/projects/{{project_id}}/architectures/validate")
def validate_architecture(project_id: str, payload: arch_mod.ArchitectureIn, user: User = CurrentUser):
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        dataset = _dataset_for(db, payload, project_id)
        return arch_mod.validate(payload, dataset.schema_json)


@app.get(f"{API}/projects/{{project_id}}/architectures")
def list_architectures(project_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        rows = (db.query(Architecture).filter(Architecture.project_id == project_id)
                .order_by(Architecture.name, Architecture.version.desc()).all())
        schemas = {d.id: d.schema_json for d in db.query(Dataset).filter(Dataset.project_id == project_id)}
        return [architecture_out(a, schemas.get(a.config_json.get("dataset_id"))) for a in rows]


@app.post(f"{API}/projects/{{project_id}}/architectures", status_code=201)
def save_architecture(project_id: str, payload: arch_mod.ArchitectureIn, user: User = CurrentUser):
    with SessionLocal() as db:
        project = _own_project(db, project_id, user)
        if project.family != "FEEDFORWARD":
            raise HTTPException(422, f"La familia {project.family} queda documentada; en esta versión solo se "
                                     "diseñan y entrenan redes Feedforward (§18).")
        dataset = _dataset_for(db, payload, project_id)
        summary = arch_mod.validate(payload, dataset.schema_json)
        if not summary["valid"]:
            raise HTTPException(422, " ".join(summary["errors"]))
        last = (db.query(Architecture).filter(Architecture.project_id == project_id,
                                              Architecture.name == payload.name)
                .order_by(Architecture.version.desc()).first())
        # Cada guardado crea una versión nueva; las anteriores no se modifican (§10).
        arch = Architecture(project_id=project_id, name=payload.name, version=(last.version + 1) if last else 1,
                            config_json=payload.model_dump(exclude={"name"}))
        db.add(arch)
        db.flush()
        audit(db, user.id, "architecture.save", project_id, name=arch.name, version=arch.version)
        db.commit()
        return architecture_out(arch, dataset.schema_json)


# ------------------------------------------------------------------ entrenamientos

class TrainingIn(BaseModel):
    architecture_id: str
    epochs: int = Field(default=30, ge=1)
    batch_size: int = Field(default=16, ge=1)
    learning_rate: float = Field(default=0.01, gt=0, le=1)
    optimizer: str = "adam"
    seed: int = Field(default=42, ge=0, le=2**31 - 1)


@app.post(f"{API}/projects/{{project_id}}/training-jobs", status_code=202)
def launch(project_id: str, payload: TrainingIn, user: User = CurrentUser):
    if payload.epochs > settings.max_epochs:
        raise HTTPException(422, f"El máximo de épocas es {settings.max_epochs}.")
    if payload.batch_size > settings.max_batch:
        raise HTTPException(422, f"El tamaño de lote máximo es {settings.max_batch}.")
    if payload.optimizer not in {"adam", "sgd", "rmsprop"}:
        raise HTTPException(422, "Optimizador no válido.")
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        arch = db.get(Architecture, payload.architecture_id)
        if arch is None or arch.project_id != project_id:
            raise HTTPException(422, "La arquitectura no pertenece a este proyecto.")
        dataset = db.get(Dataset, arch.config_json["dataset_id"])
        summary = arch_mod.validate(arch_mod.ArchitectureIn(name=arch.name, **arch.config_json), dataset.schema_json)
        if not summary["valid"]:
            raise HTTPException(422, "La arquitectura ya no es válida: " + " ".join(summary["errors"]))
        active = db.query(TrainingJob).filter(TrainingJob.created_by == user.id,
                                              TrainingJob.status.in_(["QUEUED", "PREPARING", "RUNNING"])).count()
        if active >= 2:
            raise HTTPException(429, "Ya tienes 2 entrenamientos activos; espera a que termine alguno.")
        params = {**payload.model_dump(exclude={"architecture_id"}), "task": summary["task"],
                  "classes": summary["classes"], "split": {"train": 0.7, "validation": 0.15, "test": 0.15},
                  "codeVersion": settings.code_version, "architectureVersion": arch.version}
        job = TrainingJob(project_id=project_id, architecture_id=arch.id, dataset_id=dataset.id,
                          target=arch.config_json["target"], params_json=params, created_by=user.id)
        db.add(job)
        db.flush()
        emit(db, job.id, "status", status="QUEUED", progress=0, epoch=0, reason=None)
        audit(db, user.id, "training.launch", project_id, job=job.id)
        db.commit()
        db.refresh(job)
        return job_out(job)


@app.get(f"{API}/projects/{{project_id}}/training-jobs")
def list_jobs(project_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        rows = (db.query(TrainingJob).filter(TrainingJob.project_id == project_id)
                .order_by(TrainingJob.created_at.desc()).all())
        return [job_out(j) for j in rows]


def _own_job(db, job_id: str, user: User) -> TrainingJob:
    job = db.get(TrainingJob, job_id)
    if job is None:
        raise _not_found("Entrenamiento")
    _own_project(db, job.project_id, user)
    return job


@app.get(f"{API}/training-jobs/{{job_id}}")
def get_job(job_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        return job_out(_own_job(db, job_id, user))


@app.get(f"{API}/training-jobs/{{job_id}}/history")
def job_history(job_id: str, user: User = CurrentUser):
    """Todo lo ocurrido en el trabajo: lo usa la pantalla al abrirse o al reconectar."""
    with SessionLocal() as db:
        _own_job(db, job_id, user)
        events = db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.id).all()
        return [{"id": e.id, "kind": e.kind, "payload": e.payload, "at": _iso(e.created_at)} for e in events]


class CancelIn(BaseModel):
    reason: str = Field(default="Cancelado por el usuario.", max_length=300)


@app.post(f"{API}/training-jobs/{{job_id}}/cancel")
def cancel(job_id: str, payload: CancelIn, user: User = CurrentUser):
    with SessionLocal() as db:
        job = _own_job(db, job_id, user)
        if job.status in TERMINAL:
            raise HTTPException(409, "El trabajo ya terminó.")
        if job.status == "QUEUED":
            # Aún no lo tomó el worker: se cancela de inmediato.
            job.status, job.status_reason = "CANCELLED", payload.reason
            emit(db, job.id, "status", status="CANCELLED", progress=job.progress, epoch=job.epoch,
                 reason=payload.reason)
        else:
            # En ejecución la cancelación es una solicitud: el worker la confirma al cerrar la época (§10).
            job.cancel_requested, job.status_reason = True, payload.reason
            emit(db, job.id, "log", message="Cancelación solicitada; se detendrá al terminar la época en curso.")
        audit(db, user.id, "training.cancel", job.project_id, job=job.id, reason=payload.reason)
        db.commit()
        return job_out(job)


@app.get(f"{API}/training-jobs/{{job_id}}/events")
async def events(job_id: str, request: Request, user: User = CurrentUser):
    """Canal SSE: reenvía cada evento nuevo; con Last-Event-ID retoma donde se cortó (§12)."""

    def check() -> None:
        with SessionLocal() as db:
            _own_job(db, job_id, user)

    await run_in_threadpool(check)
    start = int(request.headers.get("last-event-id") or 0)

    def fetch(after: int) -> tuple[list[JobEvent], str]:
        with SessionLocal() as db:
            rows = (db.query(JobEvent).filter(JobEvent.job_id == job_id, JobEvent.id > after)
                    .order_by(JobEvent.id).limit(200).all())
            return rows, db.get(TrainingJob, job_id).status

    async def stream():
        last, idle = start, 0.0
        while not await request.is_disconnected():
            rows, current = await run_in_threadpool(fetch, last)
            for row in rows:
                last = row.id
                data = json.dumps({"kind": row.kind, "payload": row.payload, "at": _iso(row.created_at)})
                yield f"id: {row.id}\nevent: {row.kind}\ndata: {data}\n\n"
            if current in TERMINAL and not rows:
                yield "event: end\ndata: {}\n\n"
                return
            idle = 0.0 if rows else idle + 0.5
            if idle >= 15:
                idle = 0.0
                yield ": sigue conectado\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ modelos

@app.get(f"{API}/projects/{{project_id}}/models")
def list_models(project_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        rows = (db.query(ModelVersion).filter(ModelVersion.project_id == project_id)
                .order_by(ModelVersion.created_at.desc()).all())
        return [model_out(m) for m in rows]


@app.get(f"{API}/models/{{model_id}}/download")
def download_model(model_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        model = db.get(ModelVersion, model_id)
        if model is None:
            raise _not_found("Modelo")
        _own_project(db, model.project_id, user)
        audit(db, user.id, "model.download", model.project_id, model=model.id)
        db.commit()
    path = settings.models_dir / model.storage_key
    name = f"{model.metadata_json.get('architecture', {}).get('name', 'modelo')}-v{model.version}.zip"
    return FileResponse(path, filename=name, media_type="application/zip")


@app.get(f"{API}/projects/{{project_id}}/audit-events")
def audit_events(project_id: str, user: User = CurrentUser):
    with SessionLocal() as db:
        _own_project(db, project_id, user)
        rows = (db.query(AuditEvent).filter(AuditEvent.project_id == project_id)
                .order_by(AuditEvent.id.desc()).limit(100).all())
        return [{"action": r.action, "actor": r.actor_id, "metadata": r.metadata_json, "at": _iso(r.created_at)}
                for r in rows]


# ------------------------------------------------------------------ web compilada

@app.exception_handler(404)
async def spa_fallback(request: Request, exc):
    """Las rutas de la web (p. ej. /proyectos/PRJ-1) devuelven index.html; las de la API, JSON."""
    index = settings.web_dist / "index.html"
    if not request.url.path.startswith(API) and index.exists():
        return FileResponse(index)
    detail = getattr(exc, "detail", "No encontrado.")
    return JSONResponse({"detail": detail}, status_code=404)


if (settings.web_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    page = settings.web_dist / "index.html"
    if page.exists():
        return FileResponse(page)
    return JSONResponse({"detail": "La web no está compilada. Ejecuta: npm run build en web/."})
