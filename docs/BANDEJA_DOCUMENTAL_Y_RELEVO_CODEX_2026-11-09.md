# Bandeja documental OMR — Arquitectura, operación y relevo para Codex

**Fecha:** 2026-11-09  
**Rama de implementación:** `feature/bandeja-documental-omr-evidencias`  
**Base:** `feature/omr-folios-qr-lector` (no reemplazar `main`).  
**Estado:** desarrollo con CI; aceptación física Xerox pendiente.  
**Objetivo:** recibir documentos de escáner de cualquier aplicación, no perder
ni una página, no duplicar resultados, facilitar organizar PDFs y exportar
expedientes verificables conservando los originales.

## 1. Reglas innegociables

1. **Cuestionario ≠ aplicación ≠ folio ≠ ingreso PDF ≠ página escaneada.**
   Cada aplicación conserva una sesión/HMAC y sus folios propios.
2. **El PDF original es inmutable.** Se archiva por SHA-256 una sola vez,
   pero se registra cada recepción y sus páginas. Nunca se sobreescribe.
3. **La identidad se decide por QR/token/HMAC**, no por nombres parecidos,
   OCR de la hoja ni posición dentro del PDF. Sin QR verificable => pendiente.
4. **PDF mixto:** Cabos y Checadores conservan sus páginas en el mismo
   original, pero cada aplicación recibe SOLO las hojas de sus propios folios.
5. **La hoja efectiva sigue siendo única por folio y sesión.** Reimportaciones
   equivalentes no agregan otra calificación; resultados distintos del mismo
   folio exigen decisión humana y no sustituyen la primera nota.
6. **Corregir manualmente** requiere ID y folio impresos cotejados, revisor
   y motivo. La captura de todas las respuestas permanece auditable.
7. **No exportar PDF original mixto dentro del expediente de una sola
   evaluación.** El expediente incluye únicamente las hojas identificadas
   de esa evaluación y el manifiesto de procedencia. La copia original
   global continúa disponible mediante acción explícita del operador.
8. **El PDF organizado es un derivado**, no altera original, QR, evidencia
   OMR, versión del cuestionario ni resultado.

## 2. Implementado y ubicación de código

| Archivo | Responsabilidad |
|---|---|
| `omr_evaluaciones/documentos.py` | `DocumentInbox`, migración SQLite, originales por SHA, ingresos, páginas identificadas y pendientes, bitácora, revisión de identidad, PDF de salida reordenado/girado, miniaturas y reparación opcional |
| `omr_evaluaciones/expedientes.py` | `export_session_bundle`, `participant_receipt`, ZIP interno/oficial, PDF evidencial, bitácora, SHA por entregable, protección de PDFs originales mixtos |
| `omr_evaluaciones/interfaz.py` | «Bandeja PDF» dentro de Calificar y entregar, escaneo con archivo global antes de calificar, vista previa, giro/orden/extracción, resultados y ZIP |
| `omr_evaluaciones/motor.py` | Inspección QR con SHA previo, sesiones firmadas y lectura OMR, evidencias archivadas, QR opcional ZXing solo como fallback |
| `tests/test_bandeja_documental.py` | E2E documental, mezclas, jornadas separadas, reimportaciones, PDF de salida, manifest, identidad y privacidad |
| `tests/test_bandeja_gui.py` | Navegación Tk y archivo de hojas no identificadas |
| `requirements.txt` | Dependencia `pypdf` para copiar/combinar/ordenar/girar/extractar |
| `requirements-pdf-extra.txt` | `zxing-cpp` y `pikepdf` opcionales; no son requisitos para abrir la app |

Las tablas nuevas dentro de `datos/omr/sesiones.sqlite3` son:
`documentos_omr`, `ingresos_documentos_omr`,
`paginas_documentos_omr` y `eventos_documentos_omr`.
No se fusionan ni borran tablas históricas. La base de Biblioteca sigue
separada en `datos/biblioteca.sqlite3`; los UUID de aplicación relacionan
ambas sin copiar preguntas ni volver a generar folios.

Los PDF originales se guardan en
`datos/omr/documentos/originales/<sha256>.pdf`.
Una carpeta de trabajo exportada NO es un nuevo documento recibido.

## 3. Procedimiento del operador

1. En **Diseñar e imprimir**, abrir un cuestionario de Biblioteca, elegir
   Normal/Ecológico y, si corresponde, cargar la lista. Generar PDFs.
2. En **Calificar y entregar → Escanear PDF**, cargar cualquier lote.
   Se verifica identidad de las páginas **antes de calificar**. Si se mezclan
   evaluaciones, avisar y pedir confirmación; con «Sí», archivar el PDF completo
   y calificar únicamente las hojas verificadas. Con «No», cancelar sin
   modificar notas.
3. Si ninguna página tiene QR verificable, ofrecer **Archivar sin calificar**.
   Así no se pierde un documento extraviado.
4. Abrir **Bandeja PDF** para ver originales por nombre, SHA, número de
   páginas, ingresos y pendientes. Seleccionar una página para mostrarla.
   **Subir/Bajar/Girar/Extraer/Exportar PDF ordenado** operan sobre una
   copia, sin tocar resultados. También se puede **Añadir página al montaje**,
   abrir otro PDF, añadir páginas y **Exportar PDF combinado**. El montaje
   nunca modifica archivos originales ni reasigna hojas automáticamente.
   **Copiar original** requiere acción expresa.
5. **Vincular pendiente** cuando no se leyó QR: exige seleccionar aplicación,
   ID, folio, revisor y motivo. Crea una hoja **en revisión**, sin nota.
   Después completar manualmente la hoja en **Revisión** con el acetato digital.
6. En **Resultados**, escoger persona para generar **PDF individual**,
   sin claves ni resultados de compañeros.
7. En **Excel de entrega**, exportar ZIP oficial o expediente interno.
   El interno incluye XLSX, Bitácora.pdf, Evidencias_Ordenadas.pdf de hojas
   efectivas, Manifiesto.json y originales SOLO si todas sus páginas
   pertenecen a esa aplicación.
8. Para seguir otro día, **no generar de nuevo los folios**: simplemente
   escanear otras páginas de la misma aplicación. Abrir Historial para
   consultar todo el avance acumulado.

## 4. Actualización e instalación en Windows

**Primero cerrar la app.** Copiar `datos/omr/` completo y
`datos/biblioteca.sqlite3` a un respaldo fuera de la carpeta de desarrollo.
Guardar también `salidas/` si contiene juegos de hojas ya impresos.

Dentro del repositorio:

```powershell
git fetch origin
git switch feature/bandeja-documental-omr-evidencias
git pull --ff-only
.\Iniciar_Windows.bat
```

Si el instalador no instala dependencias nuevas de forma automática:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Opcionales **solo si se desea investigar QR difícil o reparar una copia**:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-pdf-extra.txt
```

**No** instalar dos clones que apunten a la misma BD al mismo tiempo.
**No** subir base SQLite, escaneos originales, nombres o resultados reales
a GitHub, a un issue público ni a una herramienta externa.

### Instalación desde cero para el equipo del compañero

Si ya eliminó el repositorio local, NO usar `git pull` en una carpeta que
no contiene el proyecto. Abrir PowerShell en el directorio donde lo instalará:

```powershell
git clone https://github.com/francisco-oos/Exam-PDF-Generator.git
cd Exam-PDF-Generator
git fetch origin
git switch --track origin/feature/bandeja-documental-omr-evidencias
git status
.\Iniciar_Windows.bat
```

Instalar previamente Git y Python 3.11/3.12/3.13. En un clon limpio,
`Iniciar_Windows.bat` crea `.venv` e instala dependencias y complementos
OMR. Tras el primer arranque, para instalar los tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests/test_bandeja_documental.py tests/test_bandeja_gui.py
.\.venv\Scripts\python.exe -m pytest -q
```

**Para publicar correcciones**, comprobar primero acceso de escritura al
repositorio desde su propia cuenta. No usar ni compartir tokens de GitHub,
Codex u otras cuentas del propietario. Si GitHub rechaza el `push`,
el dueño del repositorio tendrá que autorizar acceso de colaborador o
el compañero deberá usar fork + PR.

En la rama de este trabajo, después de **cada conjunto pequeño de
correcciones y sus pruebas**:

```powershell
git status
git add <archivos_de_codigo_o_tests_modificados>
git commit -m "fix(omr): describe el fallo corregido"
git push origin feature/bandeja-documental-omr-evidencias
```

La sintaxis `<archivos_de_codigo_o_tests_modificados>` es un
marcador: reemplazarla con rutas reales antes de ejecutar. No hacer
`git add .` sin revisar, no agregar `datos/`, `.venv/`,
archivos de escáner, identificadores personales ni secretos.

### Uso eficiente de Codex y límite de tokens

- Comenzar leyendo **este manual**, el PR #13 y el conjunto concreto
  de tests de la funcionalidad. No solicitar rediseñar el sistema entero.
- Trabajar de **un escenario F01–F16 a la vez**: reproducir fallo,
  identificar causa, corregir solo archivos implicados, añadir regresión,
  ejecutar prueba focalizada, luego suite relacionada.
- Después de una tanda que pasa, hacer **commit y push**, actualizar
  el PR #13 con caso, causa, corrección y resultados. Evitar dejar cambios
  grandes sin subir cuando se agotará la cuota de Codex.
- Revisar periódicamente el **consumo/cuota de Codex de su propia cuenta**
  en el producto que use; no hay garantía de una cantidad fija de tokens.
  Reservar capacidad para pruebas y documentación final. Evitar lanzar
  agentes paralelos o reenviar íntegramente el repositorio en cada mensaje.
- Si queda poca cuota, **priorizar guardar estado**: commits verificados,
  push y sección de relevo con último SHA, pruebas pasadas/fallidas,
  archivos pendientes, errores y siguiente escenario. No prometer
  continuar en segundo plano.
- No publicar tokens de acceso, claves, contraseñas o valores de entorno
  en archivos, logs, capturas, commits ni comentarios del PR. Nunca
  copiar la base de datos real a cuentas distintas.

## 5. Matriz de pruebas físicas para Codex del compañero

Realizar una copia aislada de `datos/omr` y ejecutar pruebas sobre ella.
Preparar con datos **ficticios** las siguientes evaluaciones, en Carta:

| ID | Escenario | Esperado |
|---|---|---|
| F01 | Lote Cabos con 3 hojas QR correctas | 3 páginas de Cabos vinculadas, 1 sesión |
| F02 | Mezclar 2 Cabos + 1 Checadores | 1 PDF original, hojas repartidas a 2 aplicaciones |
| F03 | Agregar hoja sin QR entre las anteriores | Pendiente visible, no calificada ni descartada |
| F04 | Reimportar exactamente mismo PDF | Misma cantidad de notas, 2 ingresos archivados |
| F05 | Otro PDF con mismo folio y mismas respuestas | Sin calificación repetida |
| F06 | Mismo folio con respuesta diferente | Duplicado conflictivo, sin sustitución de nota |
| F07 | Escanear aplicación en dos jornadas (2+1) | Sesión única y 3 participantes contabilizados |
| F08 | QR borrado y vinculación por ID + folio | Evidencia en revisión, captura manual obligatoria |
| F09 | Acetato digital, marca doble y lápiz n.º 2 | Dudas auténticas pendientes; sin notas inventadas |
| F10 | Reordenar/girar/extraer y combinar páginas de dos PDF | Derivado correcto y SHA de ambos originales intacto |
| F11 | Exportar Cabos de PDF mixto | Sin Checadores en evidencias ni originales adjuntos |
| F12 | Exportar PDF individual | Solo una persona, sin clave de respuestas |
| F13 | ZIP interno y manifiesto | SHA verificados; evidencia, XLSX y bitácora |
| F14 | Cerrar y abrir después de archivar, antes de calificar | Pendientes recuperables y PDF original íntegro |
| F15 | Cancelar alerta de mezcla | Sin nuevas calificaciones ni cambios de notas |
| F16 | Papel girado, bajo contraste y QR parcial | Segundo lector si está instalado; pendiente si no se verifica |

Para cada caso guardar en un **reporte local**: fecha, versión/commit,
Windows, impresora/escáner, DPI, SHA256 del PDF, tiempo de prelectura QR,
tiempo de calificación, páginas totales, verificadas, dudosas, duplicadas,
pendientes, errores, capturas anonimizadas y veredicto **PASA / FALLA**.
No subir archivos privados al repositorio.

La prueba con hoja real de lápiz #2 requiere presiones y borraduras de
distinta intensidad. **Las pruebas sintéticas no certifican un umbral de
calificación físico.** Si aparecen dudas falsas, comparar escaneo fuente
y lectura de contraste, no bajar globalmente el umbral sin análisis.

## 6. Revisión técnica obligatoria antes del merge

- Instalar desde cero Windows 10/11 y Linux sin Internet en ejecución
  (la instalación de pip es aparte), reiniciar y comprobar persistencia.
- Ejecutar `pytest -q`, las pruebas Tk bajo Xvfb (Linux) y pruebas Docker.
- Exportar lote grande de 100 hojas y comprobar tiempos, memoria y archivos.
- Restaurar respaldo anterior para confirmar lectura de SQLite antiguo con
  migración aditiva, sin pérdida de resultados ya revisados.
- Verificar recuperación si se cierra la app tras archivar y antes de calificar.
- Comparar el número de hojas validado por sesión ANTES y DESPUÉS de cambios.
- Confirmar no exposición de datos de otras evaluaciones en el ZIP oficial
  ni en el expediente interno. El original mixto se copia explícitamente.
- Si una prueba falla, dejar evidencia y **no** hacer merge.

## 7. Riesgos y descartes

- **No se instala Paperless-ngx** ni otro servidor: la bandeja es ligera,
  SQLite local e integrada en el mismo menú; no requiere Docker en Windows.
- **No se usó código copiado de otros repositorios** ni se arrastraron sus
  dependencias/licencias completas; pypdf ofrece la manipulación necesaria.
- ZXing-C++ y pikepdf permanecen opcionales por compatibilidad de ruedas
  binarias Windows/Linux y por consumo de recursos.
- **No se modifica automáticamente la identidad de una hoja con QR inválido**.
  Vincular manualmente exige evidencia de ID y folio y revisión integral.
- Los documentos históricos previos siguen en `datos/omr/originales` y
  sus hojas PNG en `datos/omr/escaneos`. La bandeja indexa **ingresos nuevos**;
  la migración automática retroactiva de cientos de PDFs antiguos no se
  ejecuta sin un respaldo y una simulación de recuperación.
- Un PDF que incluya datos de varios exámenes no debe copiarse completo en
  un ZIP de una sola evaluación. Si se necesita auditoría del lote original,
  usar la copia global controlada con permisos internos.

## 8. Criterio de entrega

El PR se mantiene **en borrador**, sin fusionar con la rama base ni con
`main`, hasta que Codex del compañero registre pruebas físicas F01–F16
y se resuelvan los problemas encontrados. Documentar cambios en este
mismo archivo, sin crear múltiples documentos paralelos de relevo.

## 9. Seguimiento Windows — 2026-11-09

### Tanda 1: instalación limpia y actualización del iniciador

- Clon limpio en Windows, Python 3.13, base `7947347`, rama de este PR.
- `Iniciar_Windows.bat --verificar`: crea el entorno, instala dependencias
  básicas/OMR y genera documentos correctamente.
- Suite inicial: **154 aprobadas, 3 omitidas**, 54.78 s.
- Fallo reproducido retirando solamente `pypdf` del entorno de prueba:
  el BAT anunciaba verificación correcta, pero importar la interfaz OMR
  fallaba con `ModuleNotFoundError`. La comprobación antigua solo validaba
  openpyxl, reportlab y PDFium, omitiendo la nueva bandeja.
- Corrección mínima: comprobar también la importación de `pypdf` antes
  de decidir si instalar requirements.txt. Regresión ejecutada en rojo/verde.
- Verificación posterior: el BAT reinstala pypdf automáticamente, genera
  PDFs e importa la interfaz OMR. Suite iniciador + bandeja + Tk:
  **16 aprobadas**, 14.78 s.
- Datos exclusivamente ficticios; salidas y logs locales ignorados por Git.
- CI del commit base: Windows/Linux Python 3.11/3.12/3.13 y Docker aprobados
  (Actions run 42712304947). Docker local no tiene el motor en ejecución.
- Aceptación física F01–F16 y Xerox todavía pendiente; los resultados
  anteriores son automáticos/sintéticos, no certifican papel ni lápiz real.

### Tanda 2: protección de evidencias en PDF individual

- Reproducción con tres regresiones fallidas: exportar resultado individual
  sobre un PDF de la bandeja, de originales históricos o de escaneos
  sobrescribía la evidencia. El organizador ya protegía esas rutas, pero
  participant_receipt no invocaba esa validación.
- Corrección: reutilizar DocumentInbox.validate_output antes de escribir.
  Se conservan la interfaz pública y el formato del PDF individual.
- Suite bandeja documental + Tk: **18 aprobadas**, 24.11 s. Los tres casos
  nuevos comprueban rechazo y conservación exacta de bytes/SHA original.
- Apertura visual desde Iniciar_Windows.bat, vista previa del cuadernillo,
  navegación a Calificar y entregar y Bandeja PDF comprobadas en Windows.
- Omisiones iniciales: dos tests de enlaces simbólicos sin permisos y
  un inicio Tk intermitente; el test Tk pasó en ambas tandas focalizadas.
