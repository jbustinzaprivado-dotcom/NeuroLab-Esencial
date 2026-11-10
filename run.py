"""Arranca NeuroLab Esencial: la API (con la web compilada) y el worker, como dos procesos.

    python run.py

En Render este es el comando de inicio. Si uno de los dos procesos se cae, se detiene
el otro y el servicio se reinicia completo, así nunca queda la API sin worker.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "server"


def main() -> int:
    port = os.environ.get("PORT", "8000")
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    env = {**os.environ, "PYTHONPATH": str(SERVER), "PYTHONUNBUFFERED": "1"}
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", port,
         "--no-access-log", "--proxy-headers", "--forwarded-allow-ips=*"],
        cwd=SERVER, env=env,
    )
    # La API crea la base y los datos demo; el worker arranca un instante después.
    time.sleep(2)
    worker = subprocess.Popen([sys.executable, "-m", "worker.main"], cwd=SERVER, env=env)
    processes = {"API": api, "worker": worker}
    print(f"NeuroLab Esencial en http://{'localhost' if host == '127.0.0.1' else host}:{port}", flush=True)

    def stop(*_):
        for proc in processes.values():
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while True:
            for name, proc in processes.items():
                code = proc.poll()
                if code is not None:
                    print(f"El proceso {name} terminó (código {code}); se detiene todo.", flush=True)
                    stop()
                    for other in processes.values():
                        try:
                            other.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            other.kill()
                    return code or 1
            time.sleep(1)
    except KeyboardInterrupt:
        stop()
        return 0


if __name__ == "__main__":
    sys.exit(main())
