@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if /I "%~1"=="--verificar" goto verificar
if not exist ".venv-omr-web\Scripts\python.exe" goto falta_instalar
".venv-omr-web\Scripts\python.exe" -m omr_web.doctor
if errorlevel 1 goto fallo
echo.
echo OMR WEB PILOTO: http://127.0.0.1:8877 (solo en esta PC por defecto)
echo Los datos del piloto se guardan en datos\omr_web_piloto.
".venv-omr-web\Scripts\python.exe" -m omr_web.run
if errorlevel 1 goto fallo
exit /b 0
:verificar
if exist ".venv-omr-web\Scripts\python.exe" (
  ".venv-omr-web\Scripts\python.exe" -m omr_web.doctor --json
) else (
  python -m omr_web.doctor --json
)
exit /b %errorlevel%
:falta_instalar
echo Falta instalar el piloto. Ejecuta una vez Instalar_OMR_Web_Windows.bat con Internet.
pause
exit /b 1
:fallo
echo OMR WEB no pudo iniciar. Consulta el diagnostico anterior.
pause
exit /b 1
