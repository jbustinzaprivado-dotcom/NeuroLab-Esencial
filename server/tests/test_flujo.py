"""Criterio del MVP (§18) de punta a punta, más seguridad y validaciones (§10, §11, §15)."""

import hashlib
import io
import zipfile

from app.config import settings
from worker import main as worker

API = "/api/v1"


def _project(client, headers) -> str:
    """El proyecto demo de Ana (Iris); otras pruebas crean proyectos nuevos."""
    projects = client.get(f"{API}/projects", headers=headers).json()
    return next(p["id"] for p in projects if p["name"] == "Clasificación de especies Iris")


def _run_queue() -> list[str]:
    results = []
    while (job_id := worker.claim()) is not None:
        results.append(worker.run_job(job_id))
    return results


def test_login_rechaza_clave_incorrecta_y_bloquea(client):
    for _ in range(5):
        assert client.post(f"{API}/auth/login", json={"username": "diego.salas", "password": "mala"}).status_code == 401
    blocked = client.post(f"{API}/auth/login", json={"username": "diego.salas", "password": "neurolab2026"})
    assert blocked.status_code == 423
    from app.db import SessionLocal, User
    with SessionLocal() as db:  # se desbloquea para el resto de pruebas
        user = db.query(User).filter(User.username == "diego.salas").one()
        user.locked_until = None
        db.commit()


def test_sin_sesion_no_hay_acceso(client):
    assert client.get(f"{API}/projects").status_code == 401


def test_proyecto_ajeno_responde_404(client, ana, diego):
    ana_project = _project(client, ana)
    assert client.get(f"{API}/projects/{ana_project}", headers=diego).status_code == 404
    assert client.get(f"{API}/projects/{ana_project}/training-jobs", headers=diego).status_code == 404


def test_crear_proyecto_con_familia_y_justificacion(client, ana):
    body = {"name": "Proyecto RNN", "description": "Predecir demanda diaria de energía.", "family": "RNN",
            "justification": "La demanda depende de los días anteriores: hay orden temporal."}
    created = client.post(f"{API}/projects", json=body, headers=ana)
    assert created.status_code == 201 and created.json()["family"] == "RNN"
    project_id = created.json()["id"]
    dataset = client.post(f"{API}/projects/{project_id}/datasets/demo", json={"key": "iris"}, headers=ana).json()
    arch = {"name": "rnn", "dataset_id": dataset["id"], "target": "especie",
            "layers": [{"type": "Dense", "units": 4, "activation": "relu"}], "output": {"units": 3, "activation": "softmax"}}
    rejected = client.post(f"{API}/projects/{project_id}/architectures", json=arch, headers=ana)
    assert rejected.status_code == 422 and "documentada" in rejected.json()["detail"]


def test_validacion_de_arquitectura_y_versiones(client, ana):
    project_id = _project(client, ana)
    dataset = client.get(f"{API}/projects/{project_id}/datasets", headers=ana).json()[0]
    arch = {"name": "prueba", "dataset_id": dataset["id"], "target": "especie",
            "layers": [{"type": "Dense", "units": 6, "activation": "relu"}], "output": {"units": 1, "activation": "sigmoid"}}
    summary = client.post(f"{API}/projects/{project_id}/architectures/validate", json=arch, headers=ana).json()
    assert not summary["valid"] and "3 neuronas con softmax" in summary["errors"][0]
    assert client.post(f"{API}/projects/{project_id}/architectures", json=arch, headers=ana).status_code == 422

    arch["output"] = {"units": 3, "activation": "softmax"}
    first = client.post(f"{API}/projects/{project_id}/architectures", json=arch, headers=ana).json()
    second = client.post(f"{API}/projects/{project_id}/architectures", json=arch, headers=ana).json()
    assert (first["version"], second["version"]) == (1, 2)
    assert first["summary"]["totalParams"] == 4 * 6 + 6 + 6 * 3 + 3  # mismos parámetros que Keras


def test_carga_de_csv_validada(client, ana):
    project_id = _project(client, ana)
    upload = lambda content, name="datos.csv": client.post(  # noqa: E731
        f"{API}/projects/{project_id}/datasets/upload", headers=ana,
        data={"name": "mis-datos"}, files={"file": (name, io.BytesIO(content), "text/csv")})
    assert upload(b"\x00\x01binario").status_code == 422
    assert "mínimo" in upload(b"a,b\n1,2\n").json()["detail"]
    assert upload(b"a,a\n" + b"1,2\n" * 30).status_code == 422
    assert upload(b"x,y\n1,2\n", "datos.exe").status_code == 422
    rows = "edad,ingreso,compra\n" + "".join(f"{20 + i % 40},{1000 + i * 7},{'si' if i % 3 else 'no'}\n" for i in range(60))
    accepted = upload(rows.encode())
    assert accepted.status_code == 201 and accepted.json()["rows"] == 60


def test_entrenamiento_real_clasificacion_con_version_trazable(client, ana):
    project_id = _project(client, ana)
    arch = next(a for a in client.get(f"{API}/projects/{project_id}/architectures", headers=ana).json() if a["name"] == "ff-iris")
    job = client.post(f"{API}/projects/{project_id}/training-jobs", headers=ana,
                      json={"architecture_id": arch["id"], "epochs": 25, "batch_size": 16, "learning_rate": 0.02})
    assert job.status_code == 202 and job.json()["status"] == "QUEUED"
    assert _run_queue() == ["COMPLETED"]

    result = client.get(f"{API}/training-jobs/{job.json()['id']}", headers=ana).json()
    assert result["status"] == "COMPLETED" and result["epoch"] == 25
    assert result["result"]["metrics"]["accuracy"] > 0.8
    history = client.get(f"{API}/training-jobs/{result['id']}/history", headers=ana).json()
    statuses = [e["payload"]["status"] for e in history if e["kind"] == "status"]
    assert statuses == ["QUEUED", "PREPARING", "RUNNING", "COMPLETED"]
    assert sum(e["kind"] == "metric" for e in history) == 25

    model = client.get(f"{API}/projects/{project_id}/models", headers=ana).json()[0]
    path = settings.models_dir / f"{result['id']}.zip"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == model["checksum"]
    download = client.get(f"{API}/models/{model['id']}/download", headers=ana)
    with zipfile.ZipFile(io.BytesIO(download.content)) as bundle:
        assert set(bundle.namelist()) == {"model.keras", "preprocess.json", "metadata.json"}


def test_canal_en_vivo_entrega_eventos_y_termina(client, ana):
    project_id = _project(client, ana)
    job_id = client.get(f"{API}/projects/{project_id}/training-jobs", headers=ana).json()[0]["id"]
    with client.stream("GET", f"{API}/training-jobs/{job_id}/events", headers=ana) as stream:
        kinds = [line.split(": ", 1)[1] for line in stream.iter_lines() if line.startswith("event:")]
    assert kinds[0] == "status" and kinds[-1] == "end" and "metric" in kinds
    with client.stream("GET", f"{API}/training-jobs/{job_id}/events", headers={**ana, "Last-Event-ID": "999999"}) as stream:
        assert [line for line in stream.iter_lines() if line.startswith("event:")] == ["event: end"]


def test_regresion_con_columnas_de_texto(client, diego):
    body = {"name": "Precios", "description": "Estimar el precio de una vivienda.", "family": "FEEDFORWARD",
            "justification": "Datos tabulares mixtos por vivienda."}
    project_id = client.post(f"{API}/projects", json=body, headers=diego).json()["id"]
    dataset = client.post(f"{API}/projects/{project_id}/datasets/demo", json={"key": "viviendas"}, headers=diego).json()
    arch = client.post(f"{API}/projects/{project_id}/architectures", headers=diego, json={
        "name": "ff-precios", "dataset_id": dataset["id"], "target": "precio_soles",
        "layers": [{"type": "Dense", "units": 32, "activation": "relu"}, {"type": "Dense", "units": 16, "activation": "relu"}],
        "output": {"units": 1, "activation": "linear"}}).json()
    client.post(f"{API}/projects/{project_id}/training-jobs", headers=diego,
                json={"architecture_id": arch["id"], "epochs": 40, "batch_size": 32, "learning_rate": 0.01})
    assert _run_queue() == ["COMPLETED"]
    job = client.get(f"{API}/projects/{project_id}/training-jobs", headers=diego).json()[0]
    metrics = job["result"]["metrics"]
    assert metrics["r2"] > 0.5 and metrics["mae"] > 1000  # el error se informa en soles, no escalado


def test_cancelar_trabajo_en_cola(client, ana):
    project_id = _project(client, ana)
    arch = client.get(f"{API}/projects/{project_id}/architectures", headers=ana).json()[0]
    job = client.post(f"{API}/projects/{project_id}/training-jobs", headers=ana,
                      json={"architecture_id": arch["id"], "epochs": 5}).json()
    cancelled = client.post(f"{API}/training-jobs/{job['id']}/cancel", headers=ana, json={"reason": "Prueba"})
    assert cancelled.json()["status"] == "CANCELLED"
    assert worker.claim() is None  # el worker ya no lo toma
    assert client.post(f"{API}/training-jobs/{job['id']}/cancel", headers=ana, json={}).status_code == 409


def test_limites_de_parametros(client, ana):
    project_id = _project(client, ana)
    arch = client.get(f"{API}/projects/{project_id}/architectures", headers=ana).json()[0]
    too_many = client.post(f"{API}/projects/{project_id}/training-jobs", headers=ana,
                           json={"architecture_id": arch["id"], "epochs": 1000})
    assert too_many.status_code == 422 and "máximo de épocas" in too_many.json()["detail"]


def test_peso_balanceado_y_umbral_en_clasificacion_binaria(client, diego):
    """Peso a la clase minoritaria y umbral de alerta (caso de fuga de clientes)."""
    project_id = next(p["id"] for p in client.get(f"{API}/projects", headers=diego).json()
                      if p["name"] == "Riesgo de fuga de clientes")
    arch = client.get(f"{API}/projects/{project_id}/architectures", headers=diego).json()[0]
    base = {"architecture_id": arch["id"], "epochs": 30, "batch_size": 32, "learning_rate": 0.005}
    ids = []
    for extra in ({}, {"class_weight": "balanced"}, {"threshold": 0.3}):
        # Uno a la vez: el límite es de 2 entrenamientos activos por usuario.
        ids.append(client.post(f"{API}/projects/{project_id}/training-jobs", headers=diego, json={**base, **extra}).json()["id"])
        assert _run_queue() == ["COMPLETED"]
    plain, balanced, low = (client.get(f"{API}/training-jobs/{i}", headers=diego).json() for i in ids)

    def detected(job):
        (_, _), (fn, tp) = job["result"]["metrics"]["confusion"]
        return tp

    # Dar más peso a los «si», o bajar el umbral, detecta más clientes que se van.
    assert detected(balanced) > detected(plain)
    assert detected(low) >= detected(plain)
    assert balanced["params"]["class_weight"] == "balanced" and low["params"]["threshold"] == 0.3

    metrics = low["result"]["metrics"]
    assert metrics["positiveClass"] == "si" and metrics["threshold"] == 0.3
    # La matriz guardada coincide con recalcularla desde los puntajes con el mismo umbral.
    matrix = [[0, 0], [0, 0]]
    for real, score in metrics["scores"]:
        matrix[real][int(score >= 0.3)] += 1
    assert matrix == metrics["confusion"]
    logs = [e["payload"].get("message", "") for e in client.get(f"{API}/training-jobs/{ids[1]}/history", headers=diego).json()]
    assert any(line.startswith("Peso de clases balanceado") for line in logs)


def test_umbral_no_aplica_en_regresion_ni_multiclase(client, ana):
    project_id = _project(client, ana)
    arch = next(a for a in client.get(f"{API}/projects/{project_id}/architectures", headers=ana).json() if a["name"] == "ff-iris")
    job = client.post(f"{API}/projects/{project_id}/training-jobs", headers=ana,
                      json={"architecture_id": arch["id"], "epochs": 5, "threshold": 0.3}).json()
    assert job["params"]["threshold"] is None  # Iris tiene 3 clases: no hay una clase positiva
    client.post(f"{API}/training-jobs/{job['id']}/cancel", headers=ana, json={})
    assert client.post(f"{API}/projects/{project_id}/training-jobs", headers=ana,
                       json={"architecture_id": arch["id"], "threshold": 0.99}).status_code == 422
