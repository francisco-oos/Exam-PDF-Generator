# Manual único — diseño, folios, lectura OMR y entrega

**Alcance:** este repositorio contiene un solo diseñador de exámenes y un
apartado de calificación. El OMR de folios es una modalidad de la misma
evaluación, **no otro generador ni otra base de preguntas**. La lectura real usa
OpenCV, QR firmado con HMAC y revisión humana. Las pruebas sintéticas no
certifican todavía precisión en la Xerox VersaLink C7120.

## Procedimiento para el personal (Windows 10/11 o Linux)

1. Abrir `Iniciar_Windows.bat` (Windows) o `Iniciar_Linux.sh` (Linux). Se abre
   directamente **Diseñar e imprimir** con el PDF real a la derecha.
2. Importar un XLSX de preguntas o abrir un cuestionario desde la biblioteca.
   Configurar título, institución, grupo, papel y colores.
3. Si se aplicará a personas identificadas, descargar la **plantilla de
   participantes**, rellenar SOLO la hoja **Participantes** y pulsar
   **Cargar lista**. Los campos son `ID_personal` (texto único, obligatorio),
   `Nombre` (obligatorio), `Area_adscripcion`, `Grupo` y `Turno`. El ejemplo
   está en otra pestaña y no se importa. Puedes **Quitar lista** para
   volver a exámenes anónimos.
4. Escoger la modalidad:
   - **Tradicional:** cuadernillo y hoja. Con lista se generan
     `Por_participante/` y `Paquetes_individuales.zip` para entregar a cada
     persona su cuadernillo y hoja, además de la hoja agrupada.
   - **Ecológica:** solo un cuadernillo reutilizable; con lista se generan
     hojas de respuestas identificadas para todos. Sin lista, hoja genérica.
   - **Folio + QR:** con lista se generan hojas individuales con nombre,
     ID, folio y QR firmado. Usa un solo cuadernillo reutilizable; además
     el acetato se adapta a la geometría de las burbujas del lector OMR.
     **Sin lista, NO se generan QR ni folios**.
5. En el diseñador seleccionar **Cuadernillo / Respuestas / Acetato**
   y verificar la vista exacta, incluidas las marcas cuadradas de la hoja QR.
   El QR de la vista es deliberadamente una MUESTRA SIN SESIÓN VÁLIDA.
6. Pulsar **Generar PDF de examen**. Se crea una carpeta nueva con
   `Cuadernillo.pdf`, `Hoja_respuestas.pdf`, `Acetato_clave.pdf`,
   `Clave_docente.pdf`, `manifest.json`, `LEEME_IMPRESION.txt` y,
   cuando corresponde, los paquetes por persona y `Sesion_OMR.txt`.
   La lista y el examen originales no se sobrescriben.
7. Imprimir al **100 %**, sin «ajustar a página». Las hojas QR requieren que
   estén presentes las **cuatro marcas cuadradas, el QR completo y todas
   las burbujas**. No mezclar acetatos de modalidades diferentes.
8. Para corregir por escáner, pulsar **Calificar y entregar** desde el menú.
   La ventana maximizada SOLO permite **Historial, Escanear PDF, Revisión,
   Resultados y Excel de entrega**. Elegir en Historial la sesión que figura
   en `Sesion_OMR.txt` de la carpeta impresa.
9. Escanear el lote en PDF multipágina. Perfil inicial propuesto para
   validar físicamente: **Xerox VersaLink C7120**, 300 dpi en escala de grises,
   sin recortar bordes. Cargarlo en **Escanear PDF**. Se conserva el PDF
   original y sus hashes; QR/HMAC identifica al participante, las cuatro
   marcas permiten rectificar y el lector evalúa los círculos.
10. En **Revisión** resolver cualquier marca ambigua, duplicada o sin QR
    viendo la evidencia. La identificación manual requiere ID + folio y
    una revisión íntegra. En **Resultados** consultar aciertos y temas.
    En **Excel de entrega** exportar la versión oficial sin claves o la
    interna con incidencias. Una sesión con incidencias se indica
    **PROVISIONAL**. Salir con **Volver al diseño** para retomar el mismo
    cuestionario sin abrir otra copia.

## Reglas que no se deben romper

- Un solo XLSX de preguntas y una sola lista opcional para todas las modalidades.
- El cuadernillo y la hoja convencional comparten coordenadas con el acetato
  convencional; la hoja QR comparte `bubble_positions` con el lector OMR y
  con su propio acetato generado para esa sesión.
- Al editar preguntas después de imprimir NO cambian las claves de sesiones
  antiguas: siempre generar un lote nuevo si varía el cuestionario.
- La sesión y los QR usan identificadores opacos: el QR no contiene nombre
  ni ID personal. Las evidencias y la lista quedan locales y no cifradas;
  controlar el acceso, respaldar y no subir a Git.
- Sin lista no hay sesión QR. Tradicional y ecológico se corrigen
  manualmente con acetato, no automáticamente con el escáner.
- La prueba física es obligatoria antes de entregar calificaciones oficiales.

## Qué significa «promedio» y «desempeño»

- **Aciertos individuales** = cantidad de preguntas donde la marca seleccionada coincide con la clave. **Porcentaje individual** = 100 × aciertos / número total de reactivos (las respuestas en blanco son incorrectas, pero quedan contadas aparte).
- **Promedio del grupo** = media aritmética de los porcentajes de participantes **validados**. Ausentes y pendientes no cuentan en el denominador. Si no hay validados, mostrar “—”, nunca cero.
- **Desempeño individual por tema** = 100 × aciertos en el tema / preguntas del tema para esa persona.
- **Desempeño agregado por tema** = 100 × aciertos validados en el tema / (número de preguntas del tema × participantes validados). Los temas con cantidades distintas **no se promedian sin ponderación** para calcular la calificación general.
- **Aprobación**: ninguna regla por defecto. 16/20 era una hipótesis, no un umbral autorizado. Las etiquetas de refuerzo por tema son diagnósticas y no equivalen automáticamente a una decisión laboral.
- **Definitivo**: al menos una evaluación validada y ninguna hoja sin identificar, duplicada o pendiente. Los ausentes se muestran como ausentes y no penalizan el promedio. Las exportaciones que aún contienen incidencias son **PROVISIONALES**.

## Arquitectura y contratos mantenibles

| Archivo | Responsabilidad |
|---|---|
| `omr_evaluaciones/motor.py` | Única geometría, impresión de folio/QR, HMAC, OMR OpenCV, SQLite, correcciones auditadas y exportación. |
| `omr_evaluaciones/interfaz.py` | Vista de calificación, revisión y entregables; no duplica el diseñador ni decide geometrías. |
| `omr_evaluaciones/demo.py` | Genera marcas sintéticas sobre hojas PDF reales, sin suponer que son escaneos Xerox. |
| `generacion_integrada.py` | Orquesta tres modalidades desde el mismo examen y participantes opcionales; crea la sesión QR si corresponde. |
| `calificar_omr.py` | Compatibilidad para pruebas técnicas; no es el punto de entrada habitual. |
| `requirements-omr.txt` | Dependencias adicionales de lectura; OpenCV, numpy, qrcode/Pillow, pyzbar opcional como segundo lector. |
| `tests/test_motor_omr.py` | Pruebas de tamaños, QR, rotación, desenfoque, duplicados, revisión, Excel y puntuaciones. |
| `tests/benchmark_sintetico.py` | Instrumentación de precisión y cobertura **únicamente sintéticas**. |

### Algoritmo de lectura

1. Generar PDF original, conservar geometría en **puntos de impresión**. `bubble_positions(papel, cantidad)` produce coordenadas para dibujar y reconocer; no duplicar fórmulas en GUI.
2. PDF escaneado → rasterización a **200 DPI de análisis**, preservando original. Se prueban rotaciones 0, 180, 90 y 270°.
3. Encontrar las cuatro marcas negras de las esquinas y estimar la homografía con `cv2.getPerspectiveTransform`/`warpPerspective`. No procesar automáticamente una hoja si no se identifica de forma segura.
4. Detectar QR de encabezado con `cv2.QRCodeDetector` y recorte/segunda lectura mediante pyzbar cuando está disponible. Validar **token, sesión, página y HMAC**. Un QR de otro examen nunca se atribuye a otra persona.
5. En el núcleo interior de cada círculo, comparar fracciones de píxeles oscuros y gris claro. `>= 0.20` oscuro y segunda opción `<0.16`, con diferencia `>=0.13`, representa marca clara. Una marca tenue, doble o sin separación suficiente se pone **en duda**. Un interior limpio `<0.09` oscuro y `<0.24` gris es blanco. **Estos umbrales son provisionales**, seleccionados para las pruebas sintéticas, no calibrados en la Xerox real.
6. Guardar hoja como `validada`, `revisar`, `sin_identificar`, `duplicado`, `descartada`. Un PDF importado dos veces con el mismo SHA/página no duplica calificaciones. Otro PDF con el mismo token pasa a cola de duplicados.
7. Las revisiones guardan **pregunta, decisión, motivo, revisor y fecha**, conservando archivo original y la captura previa a la modificación.

### Persistencia y seguridad

Base `datos/omr/sesiones.sqlite3` y subdirectorios `originales/` (PDF original), `escaneos/` (PNG de cada página), `pruebas_sinteticas/`. Contienen datos de personal y clave de evaluación: **privados y no cifrados**, accesibles para el usuario del equipo. Respaldar el directorio completo con el programa cerrado; aplicar controles de acceso y una política de retención. Los QR no incluyen nombre ni ID. Nunca subir `datos/omr`, ni bases reales ni escaneos, a GitHub o a un servicio externo.

El sistema de calificación no usa OCR ni identificación por caligrafía. Si un QR no se identifica, el evaluador puede corroborar folio e ID impresos, asociar la hoja bajo justificación, **sin adjudicar respuesta alguna** hasta revisión. Tampoco corrige automáticamente marcas múltiples o tachadas.

### Benchmarks sintéticos reproducibles

```bash
python -m pytest -q tests/test_motor_omr.py
python tests/benchmark_sintetico.py demo
# Para visualizar la interfaz integrada donde haya escritorio:
python iniciar.py
# En Linux CI:
xvfb-run -a python tests/smoke_gui.py
```

- Se probaron las 9 combinaciones de 1, 20 y 100 preguntas × Carta/A4/Oficio; rotación ±1.5° y 180°; desenfoque; folios reimportados; respuestas dobles; Excel sin fórmulas de inyección, y retención de ceros de ID.
- **Una medición sintética específica de 20 hojas ×20 reactivos** (400 círculos de respuesta): 20 QR identificados, 19 hojas autovalidadas, 1 retenida correctamente por doble respuesta; en las 380 respuestas de hojas aceptadas se observaron 380 lecturas correctas frente al patrón conocido. Esto representa **100% en las marcas aceptadas artificiales**, no 100% de precisión universal; no incluye las 20 preguntas de la hoja retenida.
- Estas mediciones reproducibles se obtuvieron rasterizando hojas generadas por software, no pasando por la **Xerox VersaLink C7120**, papel, tóner, inclinación física ni compresión real. **La eficacia en el escáner todavía no ha sido medida.** No se puede declarar el módulo listo para uso oficial hasta calibrar con al menos varias tandas reales con respuestas verdaderas conocidas y registrar errores/alertas.
- En la CI de Windows (Python 3.11–3.13), Linux y Docker, agregar matrices con `requirements-omr.txt` sin bloquear el generador tradicional si no está disponible el reconocimiento. Para usuarios Linux, la segunda lectura `pyzbar` podría requerir el paquete del sistema `libzbar0`.

## Fuentes consultadas y licencias

- `https://github.com/Udayraj123/OMRChecker` — MIT, modelo de geometría configurable, registro y lectura OpenCV. No se ha copiado código de este proyecto.
- `https://github.com/muffledcry/scoreform` — MIT, arquitectura de QR, listas, paquetes PDF y revisión. La documentación advierte que necesita revisión humana; no se ha copiado código.
- El proyecto principal conserva los créditos MIT a `UzielLopez/Exam-PDF-Generator`.

## Limitaciones pendientes

- Validación física con la Xerox y calibración de umbrales por escaneos reales de Carta/A4/Oficio.
- No hay cifrado de disco/base ni control multiusuario. No abrir un servidor con estos datos.
- No existe un motor OCR para nombre; los QR son específicos de nuestra hoja y no interpretan hojas ajenas.
- Una hoja que exceda los límites de recorte, contraste, alineación o muestre un QR ilegible irá a revisión; no asignar automáticamente por orden de páginas.
- Una edición/corrección después de emitir un informe final exige nueva versión/acta de entrega en un proceso oficial; el log se mantiene, pero todavía no hay firma electrónica de cierre de sesión.
