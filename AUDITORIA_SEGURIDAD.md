# Auditoría de seguridad y adecuación funcional

**Fecha:** 2026-11-08  
**Origen revisado:** [UzielLopez/Exam-PDF-Generator](https://github.com/UzielLopez/Exam-PDF-Generator), rama `master`, commit `409faad51de342f9ed63a46737854df9c7a9af6d` (2020-10-07).  
**Alcance:** lectura estática de `main.py`, `exam.py`, `pdf_in_columns.py`, `README.md`, `LICENSE` y listado de árbol. Verificación pública de dependencias. No se ejecutó el original: el entorno de auditoría carece de acceso de red al clonado Git y el código contenía rutinas destructivas. Se creó una **reimplementación local separada**, no una rama remota del repositorio upstream.

## Resultado

**No recomendado instalar/ejecutar el original en una carpeta con archivos importantes.** No se observan llamadas directas a servidores externos, `subprocess` o ejecución de código arbitrario explícita en los tres Python revisados; esto no garantiza ausencia de vulnerabilidades en librerías o archivos de entrada. Riesgo principal: pérdida local de archivos, entradas poco validadas y claves de corrección desalineadas.

| ID | Gravedad | Hallazgo en origen | Evidencia de código | Mitigación en adaptación |
|---|---|---|---|---|
| SEC-01 | **Alta** | Borrado de TODOS los PNG en el directorio actual al terminar, incluidos archivos no generados por el programa | `exam.py` / `output_exam_files()`: `for f in os.listdir('.')` + `f.endswith('.png')` + `os.remove(...)` | Ya no se eliminan PNG ni se escriben imágenes temporales. En fallo se limpia únicamente una carpeta nueva creada por la ejecución. Prueba automatizada de preservación. |
| SEC-02 | Media | Sobrescritura de resultados con nombres fijos (`Exam.pdf`, etc.) | `exam.py` / `output_exam_files()` | Carpeta nueva única por generación, sin sobrescribir; conserva copia del XLSX original y manifiesto SHA-256. |
| SEC-03 | Media | Ruta de imágenes de un Excel unida sin verificación para `Image.open()` | `exam.py` / `add_question()`: `os.path.join(..., image)` | Se aceptan únicamente imágenes PNG/JPEG locales identificadas por nombre dentro de la carpeta `imagenes` junto al XLSX, con verificación de formato, tamaño, dimensiones y ausencia de symlinks. Las rutas externas/URL se rechazan; el logotipo se selecciona explícitamente. |
| SEC-04 | Media | XLSX y filas sin validación completa antes de acceso a columnas, número de preguntas, fuentes y opciones | `main.py` / `read_excel`, `exam.py` / `add_question` | Cabeceras estrictas, máximo 100 preguntas, límite ZIP decompresión, sin fórmulas ni enlaces externos ni macros, opciones distintas y clave A-D. |
| SEC-05 | Media (integridad) | Orden de opciones aleatorio en cada ejecución, con clave no reproducible entre generaciones | `exam.py` / `shuffle(answers)` | Respuestas en posiciones A-D explícitas y fijas. Sin versiones aleatorias. |
| SEC-06 | Media (corrección) | La imagen de respuesta se coloca con `get_y()+15` y la clave con `get_y()+25`; la superposición sobre acetato no está garantizada | `exam.py` / `output_exam_files()` | Hoja y acetato se generan llamando a la MISMA función de coordenadas; registro gráfico y prueba matemática de posiciones. |
| SEC-07 | Baja/Media | Dependencia original de fuentes Arial de Windows y bibliotecas sin versiones fijadas | `exam.py` / `ImageFont.truetype('arial.ttf')`, `README.md` | Descubrimiento automático de fuentes Arial/DejaVu/Liberation, dependencias fijadas. No se distribuyen fuentes tipográficas. |
| SEC-08 | Media | Ausencia de suites, CI y verificación de PDF | Árbol upstream sin carpeta de tests ni workflow | Suite `pytest` ampliada a 21 casos, prueba de generación con logotipo e imágenes y apertura GUI en escritorio Linux virtual. Workflow CI preparado para Windows/Linux (aún no ejecutado en GitHub). Aún faltan pruebas Windows y con `reportlab 5.1.0`. |

## Dependencias y actualidad

- `openpyxl==3.1.5`. Revisión pública al 08/11/2026: no se detectaron avisos conocidos que afecten directamente a esta versión en el registro consultado. No equivale a auditoría de todo su árbol transitorio.
- `Pillow>=12,<13` agregado para normalizar y comprobar imágenes locales (no se permiten macros ni código embebido).
- `reportlab==5.1.0` seleccionado para instalación: ReportLab publicó correcciones de ejecución de código en `rl_safe_eval` en octubre de 2026. Evitamos alimentar el parser con HTML no escapado y nunca invocamos funciones macro/`rl_safe_eval`. Documentación: https://docs.reportlab.com/releases/notes/whats-new-51/ ; https://pypi.org/project/reportlab/5.1.0/ . La versión 5.1.0 soporta Python 3.11 y 3.12 y distribuye wheel `py3-none-any`.
- **Prueba disponible:** en la máquina Linux se probó con `reportlab 4.4.9` previamente instalado. **No se pudo instalar 5.1.0 dentro del entorno sin acceso a PyPI**, por lo que su combinación final con este código está aún SIN VERIFICAR. Esto debe probarse en Windows o Linux con Internet.
- No hay escaneo `pip-audit` ni verificación de vulnerabilidades de cada dependencia transitiva; son tareas pendientes antes de distribución a múltiples equipos.

## Ajuste funcional acordado

- Un examen de opción múltiple sin variantes aleatorias.
- Banco/editable de preguntas en XLSX, con octava columna opcional `Imagen`.
- Encabezado empresarial (empresa, puesto, título, subtítulo, logotipo e instrucciones).
- Cuadernillo de preguntas + hoja de respuestas separada + acetato de clave con idénticas coordenadas + clave docente.
- PDF A4; imprimir hoja y acetato al 100 %, sin ajuste a página.
- Interfaz simple con diálogo para abrir Excel; archivo de inicio Windows y Linux; CLI y Docker opcional.
- Todas las series del ejemplo son ficticias, no están asociadas al catálogo real.

## Evidencia de pruebas

| Prueba | Resultado |
|---|---|
| Validación de columnas, respuestas y duplicados | Aprobado en Linux |
| Fórmulas, ZIP sobredimensionado y hoja dispersa | Aprobado en Linux |
| Imágenes originales intactas y carpetas de resultado únicas | Aprobado en Linux |
| Escapado de caracteres para PDF | Aprobado en Linux |
| 20 preguntas y visualización del acetato/hoja PDF | Aprobado en Linux; no impreso físicamente |
| Prueba de carga con 100 preguntas, hojas y claves multipágina | Aprobado en Linux |
| Windows 10/11, impresora, superposición física de acetato | Pendiente de validación presencial |
| Dependencias exigidas (`reportlab 5.1.0`) | Pendiente de ejecución real en esta versión |
| Compatibilidad OMR con software de escáner | Fuera de alcance por elección del usuario |

## Estado de ramas

- Upstream original: **solo lectura**, sin permisos para crear ramas ni publicar commits.
- Entrega local: repositorio Git independiente `main` y rama `work/chatgpt/2026-11-08-seguridad-acetato` con la adaptación, empaquetada en un ZIP instalable y un `.bundle` de Git.
- El usuario proporcionó su repositorio propio `francisco-oos/Exam-PDF-Generator`. Se prepara una rama de revisión independiente; no se debe escribir en TRACKING-CORE, Material Sync Node o RepairTracking porque es una herramienta distinta.

## Decisión de instalación

Usar la **adaptación** y mantener el original únicamente como referencia MIT. Instalar en una carpeta de usuario sin permisos administrativos; no ejecutar exámenes descargados de fuentes no confiables sin revisión. La primera instalación requiere Internet para descargar bibliotecas. Tras ello, funciona sin Internet.

## Revisión empresarial posterior (08/11/2026)

- Se agregaron campos de institución, puesto/área, instrucciones y logotipo, además de imágenes por pregunta. La geometría de la hoja/acétato no depende de ninguna de esas variables.
- Se prueban archivos inválidos, rutas `../`, URLs, rutas Windows absolutas, symlinks, falsa extensión e imágenes corruptas.
- Las imágenes se validan antes de producir PDFs y se procesan con Pillow a un formato de píxeles RGB normalizado. Solo se aceptan PNG/JPEG de hasta 4 MB y 12 millones de píxeles.
- La plantilla XLSX admite 7 u 8 columnas y conserva compatibilidad anterior. Se corrigió lectura de dimensiones XLSX desconocidas generadas por algunas bibliotecas.
- La GUI se abrió sin fallos en escritorio Linux virtual; NO equivale a comprobación de Windows real ni impresión en acetato.
- **Evidencia local:** 21 pruebas `pytest` aprobadas con ReportLab 4.4.9 disponible; la versión exigida en el iniciador `5.1.0` sigue pendiente de ejecución y auditoría de dependencias transitivas en una máquina con acceso a PyPI.
- Si se distribuye a terceros, realizar pruebas de seguridad adicionales con archivos hostiles, revisar CVE de dependencias, validar la configuración de seguridad del equipo y obtener autorización del área encargada de los datos.

## Modalidad Docker web (revisión de diseño 08/11/2026)

- La aplicación web usa el servidor estándar de Python y no acepta cargas de archivos por HTTP. Solo muestra los XLSX y los PNG/JPG colocados manualmente en `datos/entradas` o en el ejemplo fijo.
- Puerto del anfitrión publicado únicamente en `127.0.0.1:8765`, no en interfaces externas. Validación de `Host`, token impredecible de formulario para POST y límite de tamaño; datos de salida descargables únicamente desde archivos permitidos dentro de `datos/salidas`.
- Contenedor como usuario sin privilegios, solo lectura salvo `datos` y `/tmp`, con capacidades retiradas y `no-new-privileges`. Docker Desktop sigue siendo un requisito instalado en el anfitrión y el daemon es un componente privilegiado.
- Los datos empresariales permanecen en la carpeta local montada; **no se crea un usuario/autenticación multiusuario**. No exponer el puerto a LAN o Internet. Docker puede resolver/descargar paquetes durante la construcción y tiene conectividad predeterminada; la app no hace solicitudes externas.
- **Pendiente:** ejecutar `docker compose build` y la prueba de inicio/healthcheck en GitHub Actions, porque el entorno local no tiene motor Docker; probar el archivo y la impresión del acetato físicamente.

## Consolidación de ramas y alcance de pruebas (08/11/2026)

La función de interfaz empresarial y la ejecución con Docker se desarrollaron inicialmente en ramas encadenadas; la segunda incluye la primera. Las 23 pruebas de Python aprobaron en el entorno de desarrollo y GitHub Actions confirmó las cuatro combinaciones Python 3.11/3.12 sobre Windows/Ubuntu, además del smoke test de Docker en Ubuntu (ejecuciones 42532803398 y 42532807871). No se ha probado aquí la impresión real ni Docker Desktop en un equipo Windows físico. La distribución recomendada será la rama principal una vez integrada la versión validada; las ramas de funciones anteriores quedan como historial temporal.
