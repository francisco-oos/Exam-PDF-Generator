@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py >nul 2>&1
if exist ".venv\Scripts\python.exe" goto ejecutar
if not errorlevel 1 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 (
  echo No se pudo crear el entorno virtual de Python 3.11-3.13.
  pause
  exit /b 1
)
:ejecutar
".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
if errorlevel 1 (
  echo No se pudieron instalar las dependencias de la web OMR.
  pause
  exit /b 1
)
echo IMPORTANTE: PILOTO LOCAL. La licencia central todavia no esta activa.
".venv\Scripts\python.exe" -m omr_web.run
if errorlevel 1 pause
endlocal
