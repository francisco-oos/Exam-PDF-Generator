@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Generador seguro de examenes
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Buscando Python 3.13, 3.12 o 3.11...
    py -3.13 --version >nul 2>&1
    if not errorlevel 1 (
        py -3.13 -m venv .venv
    ) else (
        py -3.12 --version >nul 2>&1
        if not errorlevel 1 (
            py -3.12 -m venv .venv
        ) else (
            py -3.11 --version >nul 2>&1
            if not errorlevel 1 (
                py -3.11 -m venv .venv
            ) else (
                echo Se necesita Python 3.13, 3.12 o 3.11.
                echo Ejecuta py -0p para consultar las versiones disponibles.
                pause
                exit /b 1
            )
        )
    )
    if errorlevel 1 (
        echo No se pudo crear el entorno .venv
        pause
        exit /b 1
    )
)
REM Validar tambien PDFium para actualizar un .venv ya creado en versiones previas.
".venv\Scripts\python.exe" -c "import importlib.metadata as m; assert m.version('openpyxl') == '3.1.5'; assert m.version('reportlab') == '5.1.0'; assert m.version('pypdfium2') == '5.15.1'" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Instalando las dependencias solo en este entorno...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo No se pudieron instalar las dependencias.
        pause
        exit /b 1
    )
)
REM Instalar el lector OMR en el mismo entorno: el menu Calificar debe funcionar
REM sin un segundo instalador ni ejecutar otro script por separado.
".venv\Scripts\python.exe" -c "import cv2,numpy,qrcode,pypdf; import omr_evaluaciones.motor" >nul 2>&1
if errorlevel 1 (
    echo Instalando complementos de calificacion OMR...
    ".venv\Scripts\python.exe" -m pip install -r requirements-omr.txt
    if errorlevel 1 (
        echo No se pudieron instalar los complementos OMR.
        echo Revisa la conexion e intenta de nuevo.
        pause
        exit /b 1
    )
)
if not exist "ejemplos\Plantilla_20_preguntas.xlsx" (
    echo Creando plantilla de ejemplo...
    ".venv\Scripts\python.exe" crear_ejemplo.py
    if errorlevel 1 (
        echo No se pudo crear la plantilla.
        pause
        exit /b 1
    )
)
if /I "%~1"=="--verificar" (
    echo [3/3] Verificando generacion de PDF sin abrir la ventana...
    ".venv\Scripts\python.exe" generar.py --entrada "ejemplos\Plantilla_20_preguntas.xlsx" --salida "salidas" --titulo "Prueba de arranque en Windows" --reutilizable --tamano-papel Carta
    if errorlevel 1 (
        echo No se pudo generar el examen de prueba.
        exit /b 1
    )
    echo Verificacion correcta: Python y generacion de PDF listos.
    exit /b 0
)
echo [3/3] Abriendo el generador...
".venv\Scripts\python.exe" iniciar.py
if errorlevel 1 (
    echo Error. Consulta los mensajes anteriores.
    pause
    exit /b 1
)
endlocal
