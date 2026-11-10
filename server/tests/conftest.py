import os
import tempfile

# La base y los archivos de prueba van a una carpeta temporal, antes de importar la app.
os.environ["NEUROLAB_DATA_DIR"] = tempfile.mkdtemp(prefix="neurolab-esencial-test-")
os.environ.setdefault("NEUROLAB_SECRET_KEY", "clave-solo-para-pruebas")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client, username: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "neurolab2026"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture(scope="session")
def ana(client):
    return login(client, "ana.quispe")


@pytest.fixture(scope="session")
def diego(client):
    return login(client, "diego.salas")
