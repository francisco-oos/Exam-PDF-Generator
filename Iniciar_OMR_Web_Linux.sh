#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Ejecuta primero: bash Instalar_OMR_Web_Linux.sh (requiere Internet inicial)." >&2
  exit 1
fi
.venv/bin/python -m omr_web.doctor
exec .venv/bin/python -m omr_web.run
