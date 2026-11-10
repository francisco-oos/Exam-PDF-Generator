@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo === INSTALACION OMR WEB - PILOTO AISLADO ===
echo Requiere Python 3.11 a 3.13 de 64 bits y conexion inicial a Internet.
if exist ".venv\Scripts\python.exe" goto instalar
where py >nul 2>&1
if errorlevel 1 goto python_directo
py -3.13 -m venv .venv >nul 2>&1
if not errorlevel 1 goto instalar
py -3.12 -m venv .venv >nul 2>&1
if not errorlevel 1 goto instalar
py -3.11 -m venv .venv >nul 2>&1
if not errorlevel 1 goto instalar
:python_directo
where python >nul 2>&1
if errorlevel 1 goto sin_python
python -c "import sys; assert (3,11) <= sys.version_info[:2] <= (3,13) and sys.maxsize > 2**32" >nul 2>&1
if errorlevel 1 goto sin_python
python -m venv .venv
if errorlevel 1 goto error_venv
:instalar
".venv\Scripts\python.exe" -c "import sys; assert (3,11) <= sys.version_info[:2] <= (3,13) and sys.maxsize > 2**32"
if errorlevel 1 goto sin_python
".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
if errorlevel 1 goto error_dependencias
".venv\Scripts\python.exe" -m omr_web.doctor
if errorlevel 1 goto error_diagnostico
echo.
echo Instalacion aprobada. Para trabajar sin Internet abre Iniciar_OMR_Web_Windows.bat.
exit /b 0
:sin_python
echo ERROR: Instala Python 3.11, 3.12 o 3.13 de 64 bits.
echo Si .venv viene de otra version, respalda y recrea solo esa carpeta.
pause
exit /b 1
:error_venv
echo ERROR: No se pudo crear el entorno virtual.
pause
exit /b 1
:error_dependencias
echo ERROR: Dependencias incompletas. Revisa la conexion y vuelve a ejecutar este instalador.
pause
exit /b 1
:error_diagnostico
echo ERROR: El diagnostico detecto condiciones que impiden operar.
pause
exit /b 1
