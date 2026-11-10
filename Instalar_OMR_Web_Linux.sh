#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Instalación OMR web (piloto). Se necesita Python 3.11-3.13 de 64 bits."
if [[ ! -x .venv-omr-web/bin/python ]]; then
  python3 -c 'import sys; assert (3,11) <= sys.version_info[:2] <= (3,13) and sys.maxsize > 2**32'
  python3 -m venv .venv-omr-web
fi
.venv-omr-web/bin/python -m pip install -r requirements-web.txt
.venv-omr-web/bin/python -m omr_web.doctor
echo "Instalación completa. Inicia con ./Iniciar_OMR_Web_Linux.sh"
