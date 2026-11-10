"""Modelo de datos (§8 del Documento Maestro, reducido) sobre SQLite.

La API y el worker son dos procesos que comparten el mismo archivo: el modo WAL y una
espera ante bloqueos permiten que uno escriba mientras el otro lee.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


settings.data_dir.mkdir(parents=True, exist_ok=True)
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 30})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(connection, _record) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: new_id("PRJ"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    family: Mapped[str] = mapped_column(String(20))
    justification: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: new_id("DS"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    filename: Mapped[str] = mapped_column(String(200))
    rows: Mapped[int] = mapped_column(Integer)
    schema_json: Mapped[list] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    origin: Mapped[str] = mapped_column(String(20))  # demo | carga
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Architecture(Base):
    __tablename__ = "architectures"
    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: new_id("ARC"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TrainingJob(Base):
    __tablename__ = "training_jobs"
    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: new_id("JOB"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    architecture_id: Mapped[str] = mapped_column(ForeignKey("architectures.id"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    target: Mapped[str] = mapped_column(String(120))
    params_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="QUEUED")
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    worker_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)

    architecture: Mapped[Architecture] = relationship()
    dataset: Mapped[Dataset] = relationship()


class JobEvent(Base):
    """Línea de tiempo de un trabajo: estados, métricas por época y logs. Alimenta el canal SSE."""

    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # status | metric | log
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: new_id("MDL"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    job_id: Mapped[str] = mapped_column(ForeignKey("training_jobs.id"))
    version: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(200))
    checksum: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(String(20))
    project_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


def init_db() -> None:
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def emit(db, job_id: str, kind: str, **payload) -> None:
    db.add(JobEvent(job_id=job_id, kind=kind, payload=payload))


def audit(db, actor_id: str, action: str, project_id: str | None = None, **metadata) -> None:
    db.add(AuditEvent(actor_id=actor_id, action=action, project_id=project_id, metadata_json=metadata))
