"""Rutas y configuración comunes del piloto OMR.

El piloto NO escribe en el almacén Tk (datos/omr) de manera implícita.
Una copia previamente respaldada puede indicarse con OMR_WEB_DATA.
Rutas relativas en esa variable siempre se resuelven desde el repositorio,
no desde el directorio de trabajo del proceso ni el programador de tareas.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def data_directory() -> Path:
    configured = os.environ.get("OMR_WEB_DATA", "").strip()
    if not configured:
        return (PROJECT_ROOT / "datos" / "omr_web_piloto").resolve()
    location = Path(configured).expanduser()
    if not location.is_absolute():
        location = PROJECT_ROOT / location
    return location.resolve()

def config_file(path: str | None) -> Path | None:
    """Los certificados de servicios se resuelven desde el repositorio."""
    if not path:
        return None
    file = Path(path).expanduser()
    return (file if file.is_absolute() else PROJECT_ROOT / file).resolve()
