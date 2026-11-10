# Mantenimiento y comprobaciones de impresión

## Centro OMR web (rama experimental independiente)

Consultar el [manual OMR web de laptop/tableta](OMR_WEB_TABLETA_PILOTO_Y_PRUEBAS_CLAUDE.md)
para instalación aislada, diagnóstico, roles, concurrencia,
migración de evidencias y pruebas físicas. El Docker del generador
clásico NO ejecuta el servidor OMR. El escritorio Tk descrito abajo
se conserva sin mezclar su base y el nuevo piloto.

## Propósito y seguridad

La aplicación prepara PDF de exámenes reutilizables sin recolectar respuestas de los participantes. La identidad de cada participante **se escribe solo en `Hoja_respuestas.pdf`** cuando se activa el modo ecológico. La hoja de respuestas, el acetato y la clave docente se deben resguardar aparte del cuadernillo.

Se conserva el proyecto original atribuido en `LICENSE` y `README.md`. El renderizador opcional de la vista exacta utiliza **pypdfium2 / PDFium** con licencias permisivas y sus avisos asociados; al distribuir binarios, incluir las licencias del paquete y de PDFium.

## Mapa de módulos y funciones

| Módulo | Función o responsabilidad | Contrato de mantenimiento |
| --- | --- | --- |
| `src/evaluaciones/core.py` | `read_questions()` | Valida XLSX, opciones únicas y archivos de imagen; **no ejecuta fórmulas** |
| `core.py` | `paper_dimensions()` | Tabla única de tamaños: A4, Carta 8.5×11, Oficio 8.5×13 pulgadas |
| `core.py` | `_bubbles()` | **Fuente única de coordenadas** para hoja y acetato; no duplicar geometría en GUI |
| `core.py` | `_exam_pdf()` | Cuadernillo, tipografía, encabezado y marca de agua al fondo de todas las páginas |
| `core.py` | `_answer_sheet()` | Dos modos: hoja para el alumno y acetato; ambos usan mismas coordenadas y tamaño |
| `core.py` | `generate()` | Valida configuración, crea carpeta única, manifiesto con hashes y copia fuentes |
| `preview_pdf.py` | `render_document_preview()` | Genera PDF en `BytesIO`, luego renderiza la página con PDFium; no crea archivos |
| `vista_previa.py` | `render_preview()` | Miniatura **orientativa**: para ver paginación exacta usar vista ampliada |
| `iniciar.py` | `build_ui()`, `open_large_preview()` | Interfaz Tkinter, Zoom, navegación, paletas y controles de formato |
| `biblioteca.py` | `db_connect()`, `save_exam()`, `load_exam()` | Esquema SQLite y migración aditiva; nunca borrar ni reemplazar la BD del usuario |
| `web_app.py` | `_form()`, `Handler.do_POST()` | Formulario local con validación en `generate()`; no subir XLSX por HTTP |
| `crear_ejemplo.py` | `main()` | Ejemplo de cultura general; no incorpora tecnologías, series ni personal empresarial |
| `generar.py` | `main()` | CLI equivalente para scripts y Docker |

## Paginación y modo ecológico

- **A4:** 210 × 297 mm.
- **Carta:** 8.5 × 11 pulgadas.
- **Oficio mexicano:** 8.5 × 13 pulgadas. No confundir con **Legal**, de 8.5 × 14.
- Tipografía de opciones: 8–12 pt en pasos de 0.5; los títulos y preguntas mantienen jerarquía proporcional.
- Activar `reutilizable`: elimina `Nombre`, `Fecha`, `Número/Folio` y `Grupo/Turno` del **cuadernillo**. Añade `NO RAYAR NI MANCHAR` detrás del contenido en cada página. **La hoja de respuestas siempre conserva los campos de identificación.**
- `color_respuestas` cambia tinta del encabezado, campos de identificación, numeración y círculos sobre fondo blanco. No cambia el acetato, que conserva círculos verdes semitransparentes para corregir.
- `Acetato_clave.pdf` no debe mezclarse entre generaciones/versiones. El cambio de tamaño **obliga a imprimir también la hoja** con el mismo ajuste.
- Imprimir al **100 % real**, sin «ajustar a página», sin escalado por controlador, misma orientación. Antes del uso formal, superponer físicamente una hoja con su propio acetato para verificar los centros.

## Persistencia y migración

`datos/biblioteca.sqlite3` es un archivo SQLite local con preguntas, respuestas y recursos originales en BLOB. Es **privado y no cifrado**, así que no lo incluyas en GitHub. Nuevas columnas `tamano_papel`, `letra`, `reutilizable`, `color_respuestas` se agregan con `ALTER TABLE` y valores por defecto compatibles. Para actualizar a un nuevo equipo, **respaldar** `datos/biblioteca.sqlite3` antes de cambiar el ejecutable. Un cuestionario antiguo conserva su modo habitual (sin marca de agua) a menos que lo modifiques.

## Comprobaciones automáticas

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe crear_ejemplo.py
.\.venv\Scripts\python.exe generar.py --entrada ejemplos\Plantilla_20_preguntas.xlsx --tamano-papel Carta --letra 10 --reutilizable
```

La CI de GitHub prueba Windows/Ubuntu con Python 3.11–3.13 y construcción Docker. La impresión física y el diálogo gráfico siguen requiriendo prueba en Windows real. `tests/test_ecologico.py` comprueba geometría, tamaños de PDF, marca de agua, ausencia de datos personales y migración.

## Cambios futuros

1. Modificar los parámetros en `generate()` y sus validaciones **antes** de agregarlos en ventanas o web.
2. Actualizar `_exam_pdf()` y `_answer_sheet()` sin romper el contrato de coordenadas de `_bubbles()`.
3. Actualizar SQLite con migración aditiva; probar biblioteca anterior y una nueva.
4. Modificar `preview_pdf.py` para mantener **vista exacta**, no recrear el diseño con posiciones aproximadas.
5. Agregar tests de los tres tamaños y del modo reutilizable; generar render de PDF y comparar visualmente.
6. Cambiar `README.md` y `CAMBIOS.md` en el mismo PR; no mezclar claves privadas con el repo público.

### Editor de diseño y papelera

- `estudio_diseno.open_design_studio`: crea la ventana de composición con dos paneles. No guarda por cada pulsación, sino que modifica `StringVar`/`BooleanVar` compartidas; el botón Guardar invoca la función de biblioteca de la interfaz principal.
- `render_document_preview` genera PDF con ReportLab y lo renderiza con PDFium en memoria; la vista no es una maqueta distinta. No se editan PDF ya producidos ni se generan temporales en disco por cada cambio de color o letra.
- `biblioteca.db_connect` ejecuta migraciones aditivas para bibliotecas de versiones anteriores; `eliminado_en` permite borrado lógico. `list_exams(trash=True)` muestra papelera. `restore_exam` recupera claves/recursos, y `purge_exam` exige un registro previamente eliminado y lo borra definitivamente en una transacción, aprovechando la clave foránea `ON DELETE CASCADE`.
- La interfaz no expone directamente el borrado irreversible: solicita confirmación de nombre y la palabra `ELIMINAR`, para prevenir errores de ratón. Los PDF exportados son independientes y no se eliminan.
- Tests: `python -m pytest -q tests/test_estudio_y_papelera.py`. Para la interfaz se puede usar `xvfb-run` en Linux o probar manualmente en Windows con datos de ejemplo.


## PR #8 — Arquitectura de renderizado y cierre del editor

El editor `estudio_diseno.open_design_studio()` muestra páginas del PDF real. El objeto `PreviewWorker` de `preview_worker.py` genera y rasteriza los bytes PDF en un **proceso separado** con inicio `spawn`, sin compartir widgets Tkinter. Cada cambio de configuración incrementa una revisión; el proceso devuelve imagen, total de páginas y posible error, y la interfaz solo publica la última revisión válida. Los cambios pendientes se consolidan antes de enviarlos y el PDF puede reutilizarse si la página o el zoom cambian pero no el contenido.

**Cierre correcto:** `WM_DELETE_WINDOW`, botón Volver, tecla Esc y destrucción de la ventana padre deben cancelar `after` pendientes, remover todos los `trace_add`, liberar imágenes y finalizar el proceso hijo. No mover métodos Tk a procesos/hilos trabajadores. La prueba `tests/test_gui.py` realiza 20 aperturas/cierres y cubre el fallo de render, pero la instalación real en Windows y el escalado DPI siguen necesitando comprobación manual.

`export_worker.export_documents()` genera los cuatro PDF en otro proceso, mientras la ventana principal consulta el canal de resultados con `after`. No iniciar exportaciones duplicadas; si falla el proceso, presentar el error al usuario y restaurar los botones. Si se modifica el proceso, añadir pruebas para cierres, excepciones y ausencia de archivos incompletos.

## PR #8 — Acetato RGB y persistencia

La configuración `color_acetato` usa el mismo contrato hexadecimal `#RRGGBB` de las otras paletas. Se aplica en `src/evaluaciones/core.py::_answer_sheet()` al contorno y relleno semitransparente de las posiciones correctas; **nunca alterar el cálculo compartido de `_bubbles()`** por color. El valor por defecto es `#167341` para bibliotecas anteriores.

`biblioteca.db_connect()` agrega `color_acetato` de forma aditiva y crea un respaldo SQLite `.antes-migracion-<id>.bak` cuando corresponde. El registro no debe sobrescribirse ni perder fotos o claves. Para una prueba controlada:
1. Cerrar la aplicación y hacer copia de `datos/biblioteca.sqlite3`, fuera del repositorio.
2. Crear una biblioteca temporal del esquema anterior con preguntas e imagen, abrirla con el código actualizado, comprobar que los recursos siguen intactos y revisar el respaldo.
3. Guardar y reabrir un cuestionario con color distinto, verificar el color en `Acetato_clave.pdf` y en el manifiesto, y comparar posiciones contra `Hoja_respuestas.pdf`.
4. Probar A4, Carta y Oficio con 1, 20 y 100 preguntas; las coordenadas de cada número/opción deben coincidir.

## Pruebas de aceptación manual antes de fusionar PR #8

- En el Windows donde se utiliza: abrir, cambiar colores, papel, zoom, introducir/error en Excel, cambiar Cuadernillo/Respuestas/Acetato y cerrar con X, Volver y Esc; repetir 20 ciclos y probar un cuestionario de 100 reactivos.
- Verificar que la interfaz no queda congelada mientras exporta ni deja procesos Python huérfanos al cerrarse.
- Abrir la biblioteca anterior, revisar la migración, modificar un registro y comprobar que imágenes, respuestas, claves, papelera y revisiones se conservan; restaurar y purgar solo elementos de prueba.
- Imprimir hoja y acetato **del mismo examen y revisión** al 100 % de escala y superponer ambos; no imprimir «ajustar a papel» ni mezclar A4/Carta/Oficio.
- No distribuir exámenes con respuestas, bibliotecas privadas o archivos de producción durante las pruebas. Documentar expresamente cualquier prueba no ejecutada.

### Ejecución automatizada

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\Iniciar_Windows.bat --verificar
```

CI aprobada para el commit `dd3b274` en [GitHub Actions 42548502303](https://github.com/francisco-oos/Exam-PDF-Generator/actions/runs/42548502303). Los tests gráficos se omiten si no existe un escritorio disponible; no confundir éxito de CI con pruebas físicas.

