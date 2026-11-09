# Manual único — diseño, folios, lectura OMR y entrega

**Alcance:** este repositorio contiene un solo diseñador de exámenes y un
apartado de calificación. El OMR de folios es una modalidad de la misma
evaluación, **no otro generador ni otra base de preguntas**. La lectura real usa
OpenCV, QR firmado con HMAC y revisión humana. Las pruebas sintéticas no
certifican todavía precisión en la Xerox VersaLink C7120.

## Procedimiento para el personal (Windows 10/11 o Linux)

La modalidad seleccionada define **solo el cuadernillo**: normal o ecológico.
La **lista opcional** determina si la hoja universal lleva un QR firmado y
los datos del participante. La misma hoja y el mismo acetato sirven para
ambas modalidades, tanto con como sin lista.

1. Ejecutar `Iniciar_Windows.bat` o `Iniciar_Linux.sh`; se abre una sola ventana.
2. Cargar/editar preguntas y completar los datos institucionales del examen.
3. Si se desea identificar a los participantes, descargar la plantilla,
   rellenar **Participantes**, respetar `ID_personal` como texto y pulsar
   **Cargar lista**. La hoja **Ejemplo** no se importa. Para evaluación
   anónima, pulsar **Quitar lista** (o no cargarla).
4. Elegir **Normal** para cuadernillos individuales o **Ecológico** para un
   cuadernillo reutilizable. La opción folio/QR ya no es modalidad independiente.
5. Ver la hoja de respuestas y el acetato en la vista PDF exacta:
   - Sin lista: nombre, folio e ID en blanco, **sin QR**; marcar respuestas
     y calificar manualmente con el acetato.
   - Con lista: nombre, ID, folio y QR individual; se pueden **escanear
     o calificar con el mismo acetato**, sin cambiar burbujas ni marcas.
6. **Generar PDF de examen**. En **Normal con lista** se obtienen paquetes
   por participante con el cuadernillo y hoja QR coincidentes. En
   **Ecológico con lista** se imprime un cuadernillo común y una hoja QR
   por participante. El QR es el mismo dentro de un paquete y en el lote,
   sin crear otra sesión de examen.
7. El **Acetato_clave.pdf** comparte **exactamente** la geometría de
   `Hoja_respuestas.pdf`, con o sin QR. Nunca intercambiar claves entre
   evaluaciones distintas; imprimir al 100 % sin ajustar.
8. Para la corrección automática, entrar en **Calificar y entregar**,
   consultar **Historial** y abrir la sesión que figura en
   `Sesion_OMR.txt`. Esta sesión existe **solo si se cargó lista**.
9. Escanear las hojas en PDF multipágina. Perfil inicial a validar
   físicamente con la Xerox VersaLink C7120: **300 dpi, escala de grises**,
   sin recortar QR ni marcas de las esquinas. Importar el PDF, revisar
   marcas ambiguas y duplicados, y exportar el Excel.
10. Si hay folios sin QR legible, cotejar folio e ID con evidencia y
    registrar revisión justificada. Nunca asignar una identidad
    únicamente por orden de las hojas. Una calificación con incidencias
    sigue siendo **PROVISIONAL**.

## Contratos que debe cumplir cada versión

- **Dos modalidades de cuadernillo**: normal y ecológico.
- **Una hoja de respuestas geométrica universal** y **un acetato** con
  idénticas posiciones de burbujas, independientemente de los participantes.
- **Lista vacía = sin QR**. Lista validada = **QR/HMAC por persona**
  en cualquiera de los dos modos y sesión de calificación persistida.
- El lector OMR sólo acepta QR de la sesión correspondiente, no hojas
  genéricas y sin QR. La corrección manual siempre puede usar el acetato.
- El cuadernillo ecológico no contiene datos personales, aunque la hoja sí.
- No sobrescribir fuentes ni sesiones históricas: una modificación del
  examen requiere un lote y una sesión nueva.
- Los PDF escaneados, las claves y las listas son **privados y no cifrados**.
  Respaldar y no subir a GitHub.
- No declarar resultados oficiales sin probar impresión y escaneo físicos.

## Recuperación de un escaneo que aparece «SIN IDENTIFICAR»

Si el PDF original procede de la Xerox, no tienes que volver a imprimirlo
solo porque el lector antiguo no reconociera sus QR.

1. Actualiza la rama y abre **Calificar y entregar → Escanear PDF**.
2. Selecciona otra vez el **mismo PDF escaneado**. El lector busca QR con
   varias ampliaciones; tolera las marcas grises que antes quedaban por
   encima del umbral fijo de 85 y rectifica con cuatro esquinas.
3. Un QR con firma HMAC válida localiza automáticamente su aplicación,
   aunque varias evaluaciones compartan el mismo título. Los registros
   nuevos conservan **nombre de Biblioteca, ID de cuestionario, revisión,
   modalidad y carpeta del lote**.
4. Si una hoja antigua estaba **sin identificar** y no tiene correcciones
   humanas, se **reprocesa sobre el mismo registro** (sin duplicarlo),
   conservando el PDF original y el PNG de evidencia previa. El historial
   de relecturas queda auditado. **Nunca sobrescribir decisiones manuales.**
5. En **Revisión** selecciona la hoja. La superposición de acetato digital
   verde usa las mismas coordenadas de burbujas del PDF impreso; para las
   manchas o dobles marcas se resaltan reactivos en naranja. El acetato
   existe solo en memoria; no dibuja encima del PDF ni de los escaneos
   archivados.
6. Si la identificación sigue fallando, verifica en el papel original
   **ID + folio** y pulsa **Vincular por ID y folio**. La hoja queda
   en revisión, **nunca calificada automáticamente**. Luego usa
   **Capturar hoja completa** para escoger A/B/C/D/BLANCO en cada reactivo;
   se requiere revisor y justificación, quedan auditadas TODAS las
   decisiones, y puedes pasar a la siguiente hoja.
7. Si las cuatro marcas no se detectan, el programa **no fuerza**
   la superposición de acetato; informa que no puede garantizarla.
   Vuelve a escanear sin cortar márgenes o haz la corrección manual.

**Caso físico de referencia:** dos hojas escaneadas de prueba por una Xerox
VersaLink C7120 (9 de noviembre de 2026). El problema se reprodujo
localmente: marcas oscuras impresas con valores de gris aproximados
110–130 que un umbral fijo de 85 descartaba. El QR de una hoja era legible
a resolución normal; el de la otra requirió ampliar la zona superior
derecha. En una hoja, el reactivo 9 queda ambiguo por marcas adicionales.
Este archivo real se analizó localmente y **no se incorporó al repositorio**.
La compatibilidad de lectura no equivale a calibración de precisión oficial.

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
| `generacion_integrada.py` | Orquesta normal/ecológico y activa QR en ambos únicamente al importar participantes. |
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
