# Módulo OMR — hojas personalizadas con QR, escaneo, revisión y Excel

**Alcance:** nuevo módulo local de Exam-PDF-Generator. Construido como una ventana Tkinter separada que conserva el generador actual. El PDF escaneado **sí se analiza** mediante OpenCV y QR; no es la simulación HTML anterior. Las pruebas con PDF creados artificialmente demuestran integración, **no precisión certificada de la Xerox VersaLink C7120**.

## Uso en Windows 10/11

1. Actualizar el repositorio cuando se apruebe el PR correspondiente y cerrar la aplicación anterior.
2. En la carpeta principal, con el entorno virtual del generador ya creado, instalar los complementos de OMR:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-omr.txt
   .\.venv\Scripts\python.exe calificar_omr.py
   ```

   Después también estará disponible el botón **Calificar · folios QR** en la barra superior del generador. Si no hay dependencias, el botón informa qué instalar sin impedir usar el editor de cuestionarios.
3. Elegir modo **Personalizado** para habilitar Hojas QR, Escanear PDF, Revisión, Resultados y Excel. Elegir Tradicional o Ecológico mantiene las pantallas de evaluación impresa existentes y oculta las etapas que no corresponden.
4. Importar la plantilla XLSX de Preguntas del generador, o usar 20 reactivos ficticios solo para practicar.
5. Importar **Plantilla_Personal_OMR.xlsx** con `ID_personal`, `Nombre`, `Area_adscripcion`, `Grupo`, `Turno`. El ID se lee como texto y conserva ceros iniciales. Validar y crear sesión. El cuestionario y la clave quedan congelados en un hash/revisión de esa aplicación.
6. Generar **Hojas_OMR_Folios_QR.pdf**: una por persona, con nombre, ID, folio visible, QR firmado, cuatro marcas de registro y burbujas A/B/C/D. **La clave correcta no aparece en la hoja**. Un QR contiene exclusivamente versión, sesión, token aleatorio, número de página y HMAC; no contiene nombre ni ID personal.
7. Imprimir las hojas al **100%** sin «ajustar al papel». Aplicar el cuadernillo ecológico si así se prefiere; la hoja QR es separada. Escanear todas las hojas en un solo PDF con Xerox VersaLink C7120. Perfil inicial a probar: **300 dpi, escala de grises, PDF multipágina**, sin recortar esquinas ni QR. Esta recomendación requiere verificación física.
8. Cargar PDF en **Escanear PDF**. El motor ejecuta la lectura en un hilo de trabajo sin bloquear Tk, archiva el original y cada página y conserva su hash SHA-256. Identifica QR/HMAC, rectifica la hoja con cuatro marcas, compara el oscurecimiento interior de cada círculo y marca los casos dudosos.
9. **Revisión:** listado de participantes / hojas problemáticas a la izquierda; la imagen escaneada, marcas resaltadas, cambio de escala y conmutador de imagen original a la derecha. Elegir opción correcta A/B/C/D, blanco o descartar duplicado, justificar y firmar. Para una hoja sin QR, la identificación manual requiere verificar ID **y** folio; no se adjudica automáticamente respuesta alguna: hay que revisar reactivos o reescanear.
10. **Resultados:** porcentaje y aciertos por persona, temas y grupo. **Exportar Excel oficial** sin clave ni bitácora sensible, o **Excel interno** que incluye incidencias. Sesiones y evidencias quedan en `datos/omr/`, que no debe subirse a GitHub.

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
| `omr_evaluaciones/interfaz.py` | Tkinter; menú según modalidad, selector de fuentes, resultados y revisión visual; no decide notas ni geometrías. |
| `omr_evaluaciones/demo.py` | Genera marcas sintéticas sobre hojas PDF reales, sin suponer que son escaneos Xerox. |
| `calificar_omr.py` | Punto de entrada Windows/Linux independiente. |
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
# Para visualizar interfaz donde haya escritorio:
python calificar_omr.py
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
