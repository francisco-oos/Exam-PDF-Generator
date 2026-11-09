#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PYTHON=${PYTHON:-python3}
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c "import importlib.metadata as m; assert m.version('openpyxl') == '3.1.5'; assert m.version('reportlab') == '5.1.0'" >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
# El lector OMR se integra en el mismo entorno y menu que el generador.
if ! .venv/bin/python -c "import cv2,numpy,qrcode,pypdf; import omr_evaluaciones.motor" >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements-omr.txt
fi
if [[ ! -f ejemplos/Plantilla_20_preguntas.xlsx ]]; then
  .venv/bin/python crear_ejemplo.py
fi
.venv/bin/python iniciar.py
