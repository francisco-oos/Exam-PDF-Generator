"""Humo real del proceso Uvicorn: la interfaz se abre en localhost sin Internet.

No emplea datos del propietario, ni modifica la base del escritorio.
Esta prueba complementa TestClient, que no inicia un socket real.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def test_servidor_piloto_real_arranca_con_base_aislada(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ)
    env.update({
        "OMR_WEB_MODE": "pilot",
        "OMR_WEB_BIND": "127.0.0.1",
        "OMR_WEB_PORT": str(port),
        "OMR_WEB_DATA": str(tmp_path),
    })
    env.pop("OMR_WEB_CERT", None)
    env.pop("OMR_WEB_KEY", None)
    repository = Path(__file__).resolve().parent.parent
    process = subprocess.Popen(
        [sys.executable, "-m", "omr_web.run"],
        cwd=repository, env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("El proceso de servidor se cerró prematuramente.")
            try:
                with urlopen(base + "/api/health", timeout=1) as response:
                    assert response.status == 200
                    assert json.load(response)["modo"] == "piloto-local"
                break
            except (URLError, TimeoutError, ConnectionError):
                time.sleep(0.2)
        else:
            raise AssertionError("Uvicorn no abrió el puerto de localhost.")
        with urlopen(base + "/api/setup/status", timeout=3) as response:
            assert json.load(response)["necesita_configuracion"] is True
        try:
            urlopen(base + "/api/applications", timeout=3)
        except HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError("Las aplicaciones no deben exponerse sin login.")
        with urlopen(base + "/", timeout=3) as response:
            assert response.status == 200
            assert b"OMR" in response.read()
        assert (tmp_path / "omr" / "sesiones.sqlite3").is_file()
        assert not (repository / "datos" / "omr" / "web_usuarios").exists()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
