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

- CI final: cuatro combinaciones Windows/Ubuntu, Python 3.11/3.12, 21 tests aprobados; corregidas rutas portables del manifiesto.
- Capturas de diseño incorporadas en `docs/capturas/` para revisión antes de instalar.
