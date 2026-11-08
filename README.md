# Generador de evaluaciones empresariales

Aplicación local para preparar exámenes de opción múltiple: **cuadernillo profesional**, **hoja de respuestas**, **clave de docente** y **clave superponible para acetato**. Una versión fija del examen: no mezcla opciones ni exige escáner.

## Procedencia y licencia

Inspirado en [UzielLopez/Exam-PDF-Generator](https://github.com/UzielLopez/Exam-PDF-Generator), creado por **Uziel Humberto López Meneses** en 2020 bajo licencia **MIT**. Conservamos su atribución y el archivo [`LICENSE`](LICENSE). Esta adaptación es una reimplementación con medidas de seguridad, diseño propio y nuevas funciones, **no es una versión oficial del autor original**.

## Características

- Formato A4 y diseño corporativo con **nombre de empresa, título, subtítulo, puesto/área, instrucciones y logotipo**.
- Preguntas organizadas por temas, cuatro opciones A–D y **una imagen local opcional por pregunta**.
- Plantilla XLSX editable en Excel o LibreOffice Calc; hasta 100 preguntas.
- Hoja y acetato usan el **mismo modelo geométrico de coordenadas** para superposición manual.
- Salidas por examen en carpeta nueva: `Cuadernillo.pdf`, `Hoja_respuestas.pdf`, `Acetato_clave.pdf`, `Clave_docente.pdf`, copia del Excel, recursos y `manifest.json` con hashes SHA-256.
- Funciona sin conexión tras instalar dependencias. No sube preguntas ni archivos a ningún servidor.
- CLI para procesos automatizados, GUI de escritorio y Docker opcional (solo CLI).

## Instalar en Windows 10/11

1. Descarga el ZIP de la rama de trabajo de GitHub y selecciona **Extraer todo** (no abras el programa dentro del ZIP).
2. Instala **Python 3.11 o 3.12**, asegurándote de incluir `py` (Python Launcher). No necesitas permisos de administrador para ejecutar el programa.
3. Haz doble clic en **`Iniciar_Windows.bat`**. La primera vez crea `.venv`, instala las dependencias y genera una plantilla de ejemplo. La instalación inicial **sí necesita Internet**.
4. En la interfaz selecciona el Excel, indica título, empresa y puesto, elige opcionalmente un logotipo y escribe instrucciones.
5. Pulsa **Generar documentos** y luego **Abrir resultado**.

Si falla la instalación, abre PowerShell en la carpeta del proyecto y ejecuta `py -3.11 -m venv .venv` y `.venv\Scripts\python.exe -m pip install -r requirements.txt`, o revisa los mensajes que muestra el iniciador. No hace falta activar PowerShell ni cambiar su política de ejecución.

## Linux

```bash
bash ./Iniciar_Linux.sh
```

Si no hay escritorio (o para usarlo como servicio puntual):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python crear_ejemplo.py
.venv/bin/python generar.py \
  --entrada ejemplos/Plantilla_20_preguntas.xlsx \
  --salida salidas \
  --titulo "Evaluación de campo" \
  --empresa "Empresa de ejemplo" \
  --puesto "Cabos" \
  --logo ejemplos/imagenes/logo_ejemplo.png
```

## Cómo preparar las preguntas en Excel

La hoja debe llamarse **`Preguntas`**, con las columnas en este orden:

| Tema | Pregunta | A | B | C | D | Correcta | Imagen (opcional) |
|---|---|---|---|---|---|---|---|
| SERCEL | ¿Qué caracteriza al DFU? | ... | ... | ... | ... | B | conector_ejemplo.png |

- `Correcta`: letra A/B/C/D; no escribas el texto completo de la respuesta.
- `Imagen`: **solo el nombre de archivo PNG, JPG o JPEG**, por ejemplo `conexion.jpg`. La imagen debe estar en la carpeta **`imagenes` junto al archivo XLSX**. No ingreses URL, rutas absolutas ni referencias a otras carpetas.
- El **logo** se selecciona de manera independiente en la interfaz (también puede indicarse con `--logo`).
- Se rechazan fórmulas, macros, hojas con cabeceras desordenadas, filas vacías entre preguntas, opciones repetidas e imágenes inválidas.
- `crear_ejemplo.py` crea `ejemplos/Plantilla_20_preguntas.xlsx` y recursos ficticios en `ejemplos/imagenes` para aprender; estos recursos no corresponden a bienes reales.
- La antigua plantilla de siete columnas sigue funcionando; simplemente no incluirá imágenes.

## Imprimir y calificar por acetato

Imprime `Hoja_respuestas.pdf` en papel normal y `Acetato_clave.pdf` en transparencia **al 100 %, tamaño real, sin “ajustar al papel”**. Alinea las marcas de registro de las cuatro esquinas. La clave solo tiene anillos en las respuestas correctas, para que se pueda ver el relleno del participante.

**Importante:** la compatibilidad con una impresora física y los inicios en Windows todavía requieren prueba de campo; la precisión de superposición fue validada en el código y los PDF de Linux. El diseño no promete compatibilidad con lectores OMR automáticos.

## Docker opcional (sin interfaz)

```bash
docker build -t generador-examenes .
docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v "$PWD/ejemplos:/entrada:ro" -v "$PWD/salidas:/salida" generador-examenes \
  --entrada /entrada/Plantilla_20_preguntas.xlsx --salida /salida \
  --titulo "Examen" --empresa "Empresa"
```

En Windows PowerShell ajusta las rutas de los volúmenes según Docker Desktop. No necesitas Docker si usas `Iniciar_Windows.bat`.

## Seguridad y límites

- Solo lectura XLSX y PNG/JPEG locales; no ejecuta macros ni interpreta direcciones de Internet del Excel.
- Rechaza rutas de imagen externas, enlaces simbólicos, imágenes dañadas, dimensiones excesivas y archivos >4 MB.
- No borra archivos personales ni sobrescribe exámenes previos; siempre abre una carpeta nueva.
- Límite de XLSX y de cantidad/longitud de preguntas; se conservan originales y referencias para reproducir la generación.
- Los logotipos e imágenes se incrustan en el cuadernillo, **no** en el acetato, cuya geometría permanece fija.
- La instalación usa `openpyxl==3.1.5`, `reportlab==5.1.0`, `Pillow>=12,<13`; no se distribuyen fuentes del sistema.
- Ver [`AUDITORIA_SEGURIDAD.md`](AUDITORIA_SEGURIDAD.md) para hallazgos, mitigaciones y verificaciones pendientes.

## Pruebas

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python crear_ejemplo.py
python generar.py --entrada ejemplos/Plantilla_20_preguntas.xlsx --salida salidas
```

La CI está preparada para Windows/Linux y Python 3.11/3.12. **No declares compatibilidad Windows confirmada hasta ver la ejecución de los workflows y probar el iniciador físicamente.**
