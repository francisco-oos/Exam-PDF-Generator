# Relevo a Codex: bandeja PDF, expedientes y pruebas físicas OMR

**Fecha:** 2026-11-09  
**Repositorio:** https://github.com/francisco-oos/Exam-PDF-Generator  
**Rama:** feature/omr-bandeja-expedientes-v1  
**Base:** feature/omr-folios-qr-lector  
**Regla:** NO fusionar a main hasta validar en el equipo físico.

## Arquitectura acordada

Una Evaluación de Biblioteca tiene Aplicaciones; cada Aplicación emite
folios QR únicos. Se pueden recibir PDFs en distintos días. La bandeja
guarda primero el original completo y después clasifica cada página:
QR firmado correcto → aplicación/folio; ilegible → pendiente; QR de otra
evaluación → su aplicación, jamás la clave equivocada.

Solo existen cuadernillos Normal y Ecológico. La lista opcional activa
QR en ambos. El acetato usa geometría universal. Revisiones humanas y
notas anteriores no pueden sobrescribirse por una relectura automática.

## Archivos clave

- omr_evaluaciones/expedientes.py: archivo SHA-256 de PDF originales, índice
  página a página en SQLite, bitácora, asociaciones, operaciones PDF y ZIP.
- omr_evaluaciones/bandeja_ui.py: vista dentro del calificador con miniaturas,
  girar, subir/bajar, extraer, combinar, separar, identificar y reanudar.
- omr_evaluaciones/interfaz.py: archiva ANTES de inspeccionar, confirma mezclas,
  califica por sesión y exporta expediente.
- omr_evaluaciones/motor.py: QR/HMAC, OMR, ZXing-C++ opcional, conserva la clave.
- requirements-omr.txt: pypdf; requirements-omr-opcional.txt: ZXing-C++ y
  pikepdf (no imprescindibles).
- tests/test_expedientes.py: pruebas de identidad, mezcla, recuperación,
  duplicados, rotación, ZIP y privacidad.
- tests/test_integracion_generador_omr.py: controles del escritorio.

**Datos locales:** datos/omr/sesiones.sqlite3 mantiene tablas existentes y
suma documentos_recibidos, documento_paginas y documento_bitacora.
Los nuevos originales están en datos/omr/documentos/SHA256.pdf; los
históricos se conservan en datos/omr/originales/SESION/SHA256.pdf.
Para incorporarlos, pulsar «Incorporar escaneos anteriores» en Bandeja PDF.
No se recalifican durante la migración.

## Instalación / respaldo Windows

1. Cerrar toda instancia del programa.
2. Copiar COMPLETAS las carpetas datos/omr y salidas y el archivo
   datos/biblioteca.sqlite3 a un destino externo. No eliminar fuentes.
3. En PowerShell, dentro del repositorio:

    git fetch origin
    git switch feature/omr-bandeja-expedientes-v1
    git pull --ff-only
    .\Iniciar_Windows.bat

Si faltan dependencias opcionales y el lector QR habitual falla:

    .\.venv\Scripts\python.exe -m pip install -r requirements-omr-opcional.txt

No borrar datos ni reinstalar desde cero en una computadora con sesiones reales.

## Pruebas automatizadas que Codex debe repetir

    .\.venv\Scripts\python.exe -m pytest -q tests/test_expedientes.py
    .\.venv\Scripts\python.exe -m pytest -q tests/test_motor_omr.py
    .\.venv\Scripts\python.exe -m pytest -q tests/test_integracion_generador_omr.py
    .\.venv\Scripts\python.exe -m pytest -q

En Linux usar Xvfb para Tk. CI: Windows/Ubuntu con Python 3.11–3.13;
Docker valida el generador web, no la bandeja Tk.

## Pruebas físicas Xerox VersaLink C7120 (datos ficticios)

Crear exámenes Cabos y Checadores de 20 preguntas, dos o más personas
por examen, respuestas conocidas. Escanear inicialmente PDF multipágina,
300 dpi, escala de grises sin recortar QR ni marcas. Registrar resultados:

| Caso | Operación | Criterio |
|---|---|---|
| A | PDF Cabos–Checadores–Cabos | Cada hoja asociada y calificada en su sesión; aviso con páginas |
| B | QR tapado o hoja genérica | PDF original y página en Bandeja; ninguna nota automática |
| C | Identificar página manualmente por ID + folio | Estado de revisión, sin nota; revisor y motivo auditados |
| D | Escanear 2 participantes hoy y 2 mañana | Una aplicación y 4 folios, sin duplicados |
| E | Subir dos veces el mismo archivo | Un original SHA, una calificación por folio, reimportación auditada |
| F | Segundo escaneo del mismo folio con respuestas distintas | Conflicto, nunca se sobreescribe la primera nota |
| G | Subir/bajar, girar, extraer, combinar | Genera PDFs derivados, el original no cambia |
| H | Exportar expediente interno de PDF mezclado | Excel, evidencias propias, bitácora y manifest SHA; sin páginas ajenas |
| I | Lápiz #2 tenue, fuerte, borrado, dos respuestas | Sin aceptar por error una marca doble; dudas justificadas |
| J | Incorporar escaneos históricos | Se ven las hojas anteriores sin recalificar |
| K | Interrumpir tras archivar y volver a iniciar | Todas las páginas siguen disponibles; reanudar es idempotente |

Verificar también que «No» en la alerta de PDF mezclado cancela la
calificación pero conserva la copia archivada; «Sí» procesa solo QR válidos.

## Métricas de aceptación

- Cero páginas perdidas y cero folios asignados a evaluación incorrecta.
- Cero calificaciones efectivas duplicadas por folio/aplicación.
- Cero correcciones humanas sobreescritas.
- SHA-256 de cada archivo original constante antes/después del organizador.
- ZIP oficial e interno no filtran páginas de otras evaluaciones.
- Tiempos de 2, 10, 50 y 100 páginas, memoria y dudas falsas/reales.
- No extrapolar acierto sintético a escáner físico; medir lápiz con varias
  presiones, 200/300 dpi, rotaciones y correcciones.

## Entregable de Codex y decisión

Codex debe dejar un SOLO reporte en
docs/RESULTADOS_PRUEBAS_FISICAS_OMR_2026-11-09.md: commit, versión Windows,
Python, equipo Xerox, casos A–K, conteos, tiempos, fallos, evidencias de
prueba autorizadas y dictamen APROBADO/BLOQUEADO. No subir listas, exámenes,
bases privadas o escaneos reales de personal a GitHub.

Si algo falla, corregir en ESTA rama, repetir CI + pruebas físicas,
documentar qué se cambió y NO fusionar antes de nuestra revisión.
