"""Configuración por variables de entorno (NEUROLAB_*). Los secretos nunca van en el código."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"NEUROLAB_{name}", default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(ROOT / "data"))))
    # Sin clave fija se genera una al arrancar: las sesiones caducan al reiniciar, lo que basta para una demo.
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", "") or secrets.token_urlsafe(32))
    demo_password: str = field(default_factory=lambda: _env("DEMO_PASSWORD", "neurolab2026"))
    session_hours: int = field(default_factory=lambda: int(_env("SESSION_HOURS", "8")))
    max_upload_kb: int = field(default_factory=lambda: int(_env("MAX_UPLOAD_KB", "1024")))
    min_rows: int = field(default_factory=lambda: int(_env("MIN_ROWS", "20")))
    max_epochs: int = field(default_factory=lambda: int(_env("MAX_EPOCHS", "100")))
    max_batch: int = field(default_factory=lambda: int(_env("MAX_BATCH", "256")))
    max_job_minutes: int = field(default_factory=lambda: int(_env("MAX_JOB_MINUTES", "10")))
    worker_poll_seconds: float = field(default_factory=lambda: float(_env("WORKER_POLL_SECONDS", "1.0")))
    worker_stale_seconds: int = field(default_factory=lambda: int(_env("WORKER_STALE_SECONDS", "90")))
    web_dist: Path = field(default_factory=lambda: Path(_env("WEB_DIST", str(ROOT / "web" / "dist"))))
    code_version: str = "esencial-1.0.0"

    @property
    def database_url(self) -> str:
        return _env("DATABASE_URL", f"sqlite:///{(self.data_dir / 'neurolab.db').as_posix()}")

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"


settings = Settings()
