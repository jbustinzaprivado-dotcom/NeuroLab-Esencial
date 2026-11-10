"""Usuarios y proyectos demo. La base es SQLite y se reinicia con el servidor: al arrancar
vacía, se vuelve a cargar todo esto."""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.datasets import inspect_csv
from app.db import Architecture, Dataset, Project, SessionLocal, User
from app.security import hash_password

DEMO_DIR = Path(__file__).parent / "demo_data"

DEMO_DATASETS = {
    "iris": {
        "name": "iris",
        "file": "iris.csv",
        "description": "150 flores con medidas de sépalo y pétalo; objetivo «especie» (3 clases).",
        "target": "especie",
    },
    "fuga_clientes": {
        "name": "fuga-clientes",
        "file": "fuga_clientes.csv",
        "description": "1200 clientes empresariales; objetivo «fuga» (sí/no a 90 días). Incluye columnas de texto.",
        "target": "fuga",
    },
    "viviendas": {
        "name": "viviendas",
        "file": "viviendas.csv",
        "description": "900 viviendas de Lima; objetivo «precio_soles» (regresión).",
        "target": "precio_soles",
    },
}

USERS = [
    ("USR-01", "ana.quispe", "Ana Quispe"),
    ("USR-02", "diego.salas", "Diego Salas"),
]


def demo_bytes(key: str) -> bytes:
    return (DEMO_DIR / DEMO_DATASETS[key]["file"]).read_bytes()


def add_demo_dataset(db, project_id: str, key: str) -> Dataset:
    spec = DEMO_DATASETS[key]
    content = demo_bytes(key)
    report = inspect_csv(content)
    dataset = Dataset(project_id=project_id, name=spec["name"], filename=spec["file"], rows=report.rows,
                      schema_json=report.schema, checksum=report.checksum, origin="demo")
    db.add(dataset)
    db.flush()
    (settings.datasets_dir / f"{dataset.id}.csv").write_bytes(content)
    return dataset


def seed() -> bool:
    with SessionLocal() as db:
        if db.query(User).first():
            return False
        password = hash_password(settings.demo_password)
        for user_id, username, name in USERS:
            db.add(User(id=user_id, username=username, display_name=name, password_hash=password))
        db.flush()

        iris = Project(owner_id="USR-01", name="Clasificación de especies Iris", family="FEEDFORWARD",
                       description="Identificar la especie de una flor a partir de cuatro medidas, como ejemplo "
                                   "de clasificación con una red densa.",
                       justification="Datos tabulares con pocas columnas numéricas: una red Feedforward basta y "
                                     "no hay orden temporal ni estructura de imagen.")
        fuga = Project(owner_id="USR-02", name="Riesgo de fuga de clientes", family="FEEDFORWARD",
                       description="Anticipar qué clientes dejarán el servicio en 90 días para enfocar campañas "
                                   "de retención.",
                       justification="Variables tabulares mixtas (numéricas y categóricas) por cliente: "
                                     "Feedforward con one-hot para las categorías.")
        db.add_all([iris, fuga])
        db.flush()
        iris_ds = add_demo_dataset(db, iris.id, "iris")
        fuga_ds = add_demo_dataset(db, fuga.id, "fuga_clientes")
        db.add(Architecture(project_id=iris.id, name="ff-iris", version=1, config_json={
            "dataset_id": iris_ds.id, "target": "especie",
            "layers": [{"type": "Dense", "units": 16, "activation": "relu"},
                       {"type": "Dense", "units": 8, "activation": "relu"}],
            "output": {"units": 3, "activation": "softmax"},
        }))
        db.add(Architecture(project_id=fuga.id, name="ff-fuga", version=1, config_json={
            "dataset_id": fuga_ds.id, "target": "fuga",
            "layers": [{"type": "Dense", "units": 32, "activation": "relu"},
                       {"type": "Dropout", "rate": 0.2},
                       {"type": "Dense", "units": 16, "activation": "relu"}],
            "output": {"units": 1, "activation": "sigmoid"},
        }))
        db.commit()
        return True
