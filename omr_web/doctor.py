"""Diagnóstico prearranque del centro OMR web, sin iniciar el servidor.

Uso: python -m omr_web.doctor [--json]
Comprueba Python, arquitectura, dependencias (incluido ZBar nativo),
escritura aislada, integridad básica de SQLite, capacidad y TLS de LAN.
Nunca imprime contraseñas, secretos HMAC ni contenido de evaluaciones.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from .runtime import data_directory, config_file

PACKAGES = (
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("python-multipart", "multipart"),
    ("httpx", "httpx"),
    ("cryptography", "cryptography"),
    ("openpyxl", "openpyxl"),
    ("reportlab", "reportlab"),
    ("Pillow", "PIL"),
    ("pypdfium2", "pypdfium2"),
    ("pypdf", "pypdf"),
    ("numpy", "numpy"),
    ("OpenCV", "cv2"),
    ("qrcode", "qrcode"),
    ("ZBar / pyzbar", "pyzbar.pyzbar"),
)


def diagnose() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        results.append({"comprobacion": name, "estado": status, "detalle": detail})

    compatible = (3, 11) <= sys.version_info[:2] <= (3, 13)
    add("Python", "ok" if compatible else "error",
        f"{sys.version_info.major}.{sys.version_info.minor}; compatible 3.11 a 3.13")
    architecture = sys.maxsize > 2**32
    add("Arquitectura", "ok" if architecture else "error",
        "Python de 64 bits requerido para el motor de imagen")
    for name, module in PACKAGES:
        try:
            importlib.import_module(module)
        except Exception as exc:
            add(f"Dependencia: {name}", "error",
                f"No disponible o sin librería nativa: {type(exc).__name__}")
        else:
            add(f"Dependencia: {name}", "ok", "Importación correcta")

    root = data_directory()
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=root) as file:
            file.write(b"diagnostico")
        add("Almacenamiento", "ok", f"Carpeta del piloto escribible: {root}")
        free = shutil.disk_usage(root).free
        add("Espacio libre", "ok" if free >= 500*1024*1024 else "aviso",
            f"{free // (1024*1024)} MiB libres; recomendado mínimo 500 MiB")
    except OSError as exc:
        add("Almacenamiento", "error", f"No se puede escribir: {type(exc).__name__}")

    for location in (root / "omr" / "sesiones.sqlite3", root / "biblioteca.sqlite3"):
        if not location.exists():
            add(f"SQLite {location.name}", "ok", "Base ausente: primer inicio aislado")
            continue
        try:
            uri = "file:" + quote(str(location.resolve()).replace(os.sep, "/"), safe="/:") + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=3) as db:
                status = db.execute("PRAGMA quick_check").fetchone()[0]
            add(f"SQLite {location.name}", "ok" if status == "ok" else "error",
                "Integridad rápida: " + str(status)[:120])
        except sqlite3.Error as exc:
            add(f"SQLite {location.name}", "error", f"Error SQLite: {type(exc).__name__}")

    host = os.getenv("OMR_WEB_BIND", "127.0.0.1")
    port = os.getenv("OMR_WEB_PORT", "8877")
    try:
        number = int(port)
        if not 1 <= number <= 65535:
            raise ValueError
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", number))
        add("Puerto", "ok", f"{number} disponible para arranque local")
    except (ValueError, OSError):
        add("Puerto", "error", f"Puerto {port!r} inválido u ocupado")
    if host not in ("127.0.0.1", "localhost", "::1"):
        cert = config_file(os.getenv("OMR_WEB_CERT"))
        key = config_file(os.getenv("OMR_WEB_KEY"))
        ready = bool(cert and key and cert.is_file() and key.is_file())
        add("HTTPS LAN", "ok" if ready else "error",
            "Certificado y clave local disponibles" if ready else
            "LAN requiere OMR_WEB_CERT y OMR_WEB_KEY válidos")
    else:
        add("Red", "ok", "Solo localhost por defecto; no expone credenciales por Wi-Fi")
    add("Licencias", "ok" if os.getenv("OMR_WEB_MODE", "pilot") == "pilot" else "error",
        "Piloto aislado; producción bloqueada sin validador central")
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Comprobar piloto OMR antes de iniciar")
    parser.add_argument("--json", action="store_true", help="Salida legible por CI")
    args = parser.parse_args(argv)
    results = diagnose()
    if args.json:
        print(json.dumps({"resultados": results,
                          "apto": not any(r["estado"] == "error" for r in results)},
                         ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"[{item['estado'].upper()}] {item['comprobacion']}: {item['detalle']}")
    return int(any(r["estado"] == "error" for r in results))


if __name__ == "__main__":
    sys.exit(main())
