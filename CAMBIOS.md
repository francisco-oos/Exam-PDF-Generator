# Historial de cambios

## 2026-11-08 · Interfaz empresarial (rama de revisión)

- Publicación propuesta en `francisco-oos/Exam-PDF-Generator`, rama `work/chatgpt/2026-11-08-interfaz-profesional`.
- Interfaz en español, con panel de diseño, empresa, puesto, título, subtítulo, logotipo e instrucciones.
- PDF del cuadernillo con estilo corporativo, bloques de preguntas que no se cortan, tablas de identificación, pie de página y figuras opcionales por pregunta.
- XLSX admite columna `Imagen` opcional, con recursos PNG/JPEG validados dentro de `imagenes/`.
- Archivos de origen y de imagen se copian a la carpeta de resultados para facilitar trazabilidad y reutilización.
- Hoja de respuestas y acetato conservan coordenadas idénticas y corrección manual por superposición.
- Pruebas nuevas: recorrido de rutas, formatos falsos, imágenes externas y marcas de clave; apertura GUI en un escritorio Linux virtual.
- `main` queda para revisión; sin instalación en los equipos del personal ni distribución automática.

## Base de seguridad previa

- Reimplementación segura inspirada en el proyecto de UzielLopez (MIT): evita borrado de PNG, salidas sobreescritas, orden aleatorio de respuestas y Excel sin validación.
- Iniciadores independientes para Windows/Linux, CLI y CI.

## Docker e interfaz web local

- Dockerfile de Python 3.12 con fuentes DejaVu, usuario no privilegiado y ejemplo incluido.
- `compose.yaml` con red solo en `127.0.0.1:8765`, datos persistentes, sistema de archivos de solo lectura, límites y healthcheck.
- `web_app.py`: interfaz desde navegador, sin subida HTTP, con token CSRF y descargas acotadas.
- Manual `DOCKER_Y_GIT.md` con instalación y comandos Git paso a paso.
- Pruebas de selección y generación web incorporadas a pytest; la CI incluye construcción y smoke test Docker en Ubuntu.

## 2026-11-08 · Generador reutilizable y vista previa

- Eliminada la lista fija de puestos en la ventana de Windows/Linux: ahora se escribe libremente el área, grupo o público.
- Añadido panel lateral con miniaturas de cuadernillo, hoja y acetato; actualiza título, empresa, grupo, instrucciones y primera pregunta sin modificar archivos.
- Reutilizado `core._bubbles` para que las marcas de hoja y acetato de la vista previa coincidan con la geometría del motor de impresión.
- La vista del cuadernillo es orientativa, no una rasterización del PDF final; para imprimir se usa el archivo generado.
- Etiquetas de documento actualizadas a «Área / grupo»; preservado el argumento `puesto` en API por compatibilidad.
- Los bancos de 4 funciones (80 preguntas) se preparan fuera de GitHub; contienen claves y no se publican en código.

## Biblioteca y personalización de documentos (2026-11-08)
- Plantilla descargable `plantillas/Plantilla_Cuestionario.xlsx`, generada con guía y ejemplos, con validación de una letra A/B/C/D.
- Biblioteca de cuestionarios local SQLite con persistencia de encabezados, 1–100 preguntas, respuestas, fotografías y logotipos, y revisión incremental.
- Editor de preguntas A/B/C/D en ventana local y catálogo de cuestionarios para reabrir/editar/regenerar.
- Paletas RGB independientes de título y subtítulo (PDF, vista previa y manifest).
- Acetato con relleno semitransparente (26 %) y contorno visible, manteniendo centros geométricos exactos.
- Web local Docker: descargar plantilla y escoger colores; biblioteca SQLite solo disponible en escritorio nativo por ahora.
- Nuevas pruebas de biblioteca, exportación, integridad de recursos, validación RGB, color PDF y opacidad del acetato.

## 2026-11-08 · Impresión ecológica y formatos adicionales

- Modo opcional de cuadernillo **reutilizable**: omitir identificación personal y poner marca de agua «NO RAYAR NI MANCHAR» detrás de todas las páginas.
- Tamaños A4/Carta/Oficio (8.5 × 13), con geometría única para hoja/acetato, pruebas de MediaBox y paginación.
- Escala de letra configurable de 8 a 12 puntos y vista ampliada en PDF real (PDFium) con zoom y navegación.
- Paleta RGB independiente para tinta de la hoja de respuestas (manteniendo fondo blanco y acetato verde).
- Migración SQLite sin pérdida de datos: guarda tamaño, letra, modo reutilizable y color de respuestas.
- Ejemplo de 20 preguntas de cultura general sin referencias a empresas, series o personal; plantilla XLSX descargable con ejemplos neutrales.
- Documentación y docstrings de mantenimiento. Ver `docs/MANTENIMIENTO_Y_PRUEBAS.md`.

## Editor de diseño y papelera recuperable

- La vista grande se convirtió en **Editar diseño · PDF real**. El acceso está en la barra principal y junto a la vista previa. El panel de propiedades modifica título, subtítulo, empresa, grupo, papel, letra, reutilización y los tres colores RGB, mientras el documento se redibuja con la misma librería que los PDF finales.
- `estudio_diseno.py` centraliza la ventana de edición: renderizado en memoria con PDFium, navegación entre hojas, zoom, actualización de variables compartidas y acciones de editar preguntas, guardar y generar. No se implementa edición libre por arrastre de objetos PDF externos.
- La biblioteca SQLite incorpora **eliminado_en** mediante migración aditiva, con papelera, restauración y borrado definitivo. `delete_exam` oculta y conserva preguntas/recursos; `purge_exam` requiere que ya esté en papelera y elimina recursos en cascada. La interfaz exige confirmación y, para el borrado permanente, escribir `ELIMINAR`.
- El editor mantiene los cambios de diseño sincronizados con la ventana principal y no altera PDF existentes hasta generar un nuevo juego. Los PDF previamente exportados no se eliminan al limpiar la biblioteca.
- Se añadieron tests de regresión para papelera, restauración, recursos BLOB, IDs inválidos y vista PDF real.
