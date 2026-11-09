# Mantenimiento y comprobaciones de impresión

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
