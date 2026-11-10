"""Validación de instalación sin datos privados ni arranque de servidor."""
from __future__ import annotations

import json
import sys

import pytest

from omr_web import doctor
from omr_web.runtime import PROJECT_ROOT, data_directory


def test_piloto_por_defecto_separa_la_base_de_escritorio(monkeypatch):
    monkeypatch.delenv("OMR_WEB_DATA", raising=False)
    assert data_directory() == (PROJECT_ROOT / "datos" / "omr_web_piloto").resolve()
    assert data_directory() != (PROJECT_ROOT / "datos").resolve()


def test_directorio_configurado_se_resuelve_desde_el_repositorio(monkeypatch, tmp_path):
    monkeypatch.setenv("OMR_WEB_DATA", "datos/copia_pruebas")
    assert data_directory() == (PROJECT_ROOT / "datos" / "copia_pruebas").resolve()
    monkeypatch.setenv("OMR_WEB_DATA", str(tmp_path))
    assert data_directory() == tmp_path.resolve()


def test_doctor_confirma_dependencias_y_no_expone_datos_sensibles(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OMR_WEB_DATA", str(tmp_path))
    monkeypatch.setenv("OMR_WEB_PORT", "0")
    # Para este caso se utiliza un puerto libre conocido como reservado
    # por el SO; valida la respuesta del doctor sin sockets externos.
    output = doctor.main(["--json"])
    report = json.loads(capsys.readouterr().out)
    assert output == 1
    assert report["apto"] is False
    assert any(x["comprobacion"] == "Puerto" and x["estado"] == "error"
               for x in report["resultados"])
    assert "PRIVATE KEY" not in json.dumps(report)
    assert not (tmp_path / "omr" / "sesiones.sqlite3").exists()


def test_doctor_detecta_lan_sin_https(monkeypatch, tmp_path):
    monkeypatch.setenv("OMR_WEB_DATA", str(tmp_path))
    monkeypatch.setenv("OMR_WEB_BIND", "0.0.0.0")
    monkeypatch.delenv("OMR_WEB_CERT", raising=False)
    monkeypatch.delenv("OMR_WEB_KEY", raising=False)
    monkeypatch.setenv("OMR_WEB_PORT", "0")
    report = doctor.diagnose()
    assert any(r["comprobacion"] == "HTTPS LAN" and r["estado"] == "error"
               for r in report)
