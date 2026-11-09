# Generador de evaluaciones empresariales

Aplicación local para preparar exámenes de opción múltiple: **cuadernillo profesional**, **hoja de respuestas**, **clave de docente** y **clave superponible para acetato**. Una versión fija del examen: no mezcla opciones ni exige escáner.

## Procedencia y licencia

Inspirado en [UzielLopez/Exam-PDF-Generator](https://github.com/UzielLopez/Exam-PDF-Generator), creado por **Uziel Humberto López Meneses** en 2020 bajo licencia **MIT**. Conservamos su atribución y el archivo [`LICENSE`](LICENSE). Esta adaptación es una reimplementación con medidas de seguridad, diseño propio y nuevas funciones, **no es una versión oficial del autor original**.

## Modo ecológico, papel y previsualización exacta

- **Cuadernillo reutilizable** (activado por defecto al diseñar uno nuevo): elimina los campos personales **solo del cuadernillo**; el participante escribe nombre, fecha y grupo en su **hoja de respuestas**. Las páginas del cuadernillo llevan la marca de agua tenue «NO RAYAR NI MANCHAR» detrás del contenido.
- **Tamaño de impresión:** A4 (210 × 297 mm), Carta (8.5 × 11 pulgadas) u Oficio mexicano (8.5 × 13 pulgadas). No mezcles acetatos y hojas de distintos tamaños o generaciones.
- **Letra de opciones y preguntas:** 8–12 puntos en intervalos de 0.5; podrás revisar la cantidad REAL de páginas sin imprimir.
- **Vista ampliada · PDF exacto:** abre una ventana independiente, con navegación de páginas y zoom, que renderiza el PDF completo en memoria mediante PDFium. La vista pequeña al costado sigue siendo orientativa.
- **Color RGB de la hoja de respuestas:** tinta para encabezados y círculos; el papel sigue blanco para gastar menos tinta. La plantilla de acetato continúa verde translúcida.
- Estas opciones también quedan guardadas en cada cuestionario SQLite y se restauran al reabrirlo, con migración no destructiva para bibliotecas anteriores.
- El ejemplo predeterminado contiene **20 preguntas generales** de matemáticas, lenguaje, ciencia y lógica, sin nombres ni procesos de empresas.

[**Guía técnica y de mantenimiento**](docs/MANTENIMIENTO_Y_PRUEBAS.md).

## Cuestionarios reutilizables, colores y plantilla (interfaz de escritorio)

1. En Windows abre `Iniciar_Windows.bat`, o en Linux `Iniciar_Linux.sh`.
2. Pulsa **Descargar plantilla Excel**. El archivo `Plantilla_Cuestionario.xlsx` incluye la pestaña obligatoria **Preguntas**, un **Ejemplo** independiente y una **Guia**. En `Preguntas`, cada fila indica un tema, la pregunta, las cuatro opciones A/B/C/D y la columna **Correcta** con una sola letra A, B, C o D. Las imágenes se indican con el nombre del PNG/JPG en una carpeta `imagenes` junto al Excel.
3. Selecciona el XLSX con **Examinar** o modifica el cuestionario directamente usando **Editar preguntas** (añadir, editar, eliminar). La plantilla y el origen nunca se sobrescriben.
4. Usa los botones **Paleta** del título y del subtítulo; cada uno admite RGB hexadecimal `#RRGGBB`, y la previsualización refleja la selección.
5. Pulsa **Guardar cuestionario** para persistir preguntas, opciones, respuestas correctas, logotipo e imágenes en SQLite. **Mis cuestionarios** permite reabrirlos y editarlos. Al pulsar **Generar documentos**, el examen se guarda también en la biblioteca.
6. La biblioteca permanece en **`datos/biblioteca.sqlite3`** dentro de la carpeta del proyecto; está excluida de Git y no se sube a Internet. Haz copias de seguridad de ese archivo cuando el programa esté cerrado. **La base no está cifrada:** cualquier persona con acceso a ella puede leer las respuestas correctas; protege el equipo y las copias de respaldo.

El acetato ahora imprime cada respuesta correcta como **círculo verde con relleno semitransparente** para facilitar el conteo. Su transparencia real depende del material e impresora: prueba papel y acetato superpuestos **al mismo tamaño y al 100 %**, sin ajuste de escala, antes de uso oficial.

**Nota de modalidades:** la biblioteca editable y el editor de preguntas están en el escritorio Tkinter. La interfaz web Docker ofrece la descarga de plantilla y los colores RGB, pero todavía no incluye el administrador de cuestionarios SQLite.

## Características

- Formatos A4, Carta y Oficio, con diseño corporativo con **nombre de empresa, título, subtítulo, puesto/área, instrucciones y logotipo**.
- Preguntas organizadas por temas, cuatro opciones A–D y **una imagen local opcional por pregunta**.
- Plantilla XLSX editable en Excel o LibreOffice Calc; hasta 100 preguntas.
- Hoja y acetato usan el **mismo modelo geométrico de coordenadas** para superposición manual; el acetato tiene un círculo coloreado semitransparente.
- Salidas por examen en carpeta nueva: `Cuadernillo.pdf`, `Hoja_respuestas.pdf`, `Acetato_clave.pdf`, `Clave_docente.pdf`, copia del Excel, recursos y `manifest.json` con hashes SHA-256.
- Funciona sin conexión tras instalar dependencias. No sube preguntas ni archivos a ningún servidor.
- CLI para procesos automatizados, GUI Tkinter sin Docker y **web local en Docker Compose**, sin instalar Python en Windows.
- **Interfaz de escritorio renovada:** campos libres para empresa y público/grupo; vista previa lateral de cuadernillo, hoja de respuestas y acetato, actualizada al editar. La vista es orientativa; el PDF final con el tamaño seleccionado es la referencia para impresión.

## Iniciar con Docker — recomendado (Windows y Linux)

**Solo necesitas Git y Docker Desktop/Engine; no se instala Python ni sus dependencias en tu equipo.** La interfaz se abre en **http://localhost:8765** y todos los archivos se conservan en `datos/`.

```powershell
git clone --branch feature/docker-interfaz-web --single-branch https://github.com/francisco-oos/Exam-PDF-Generator.git
cd Exam-PDF-Generator
docker compose up --build -d
```

Abre http://localhost:8765 y selecciona el Excel de ejemplo incluido. Para usar tus preguntas, guarda el `.xlsx` en `datos/entradas`; si tiene imágenes, colócalas en `datos/entradas/imagenes`. Los PDF se guardan en `datos/salidas`.

Para parar: `docker compose stop`. Para reiniciar: `docker compose start`. Para actualizar después de recibir cambios: `git pull --ff-only` seguido de `docker compose up --build -d`.

**Guía paso a paso para aprender Git y Docker:** [`DOCKER_Y_GIT.md`](DOCKER_Y_GIT.md). El modo con ventana Tkinter sigue disponible sin Docker para quien prefiera Python instalado.

## Instalar en Windows 10/11 (sin Docker)

1. Descarga el código de `main` con Git o actualiza tu copia con `git pull --ff-only`.
2. Utiliza **Python 3.13, 3.12 o 3.11**, con `py` (Python Launcher). No necesitas instalar otra versión si ya tienes Python 3.13. No necesitas permisos de administrador para ejecutar el programa.
3. Haz doble clic en **`Iniciar_Windows.bat`**. La primera vez crea `.venv`, instala las dependencias y genera una plantilla de ejemplo. La instalación inicial **sí necesita Internet**.
4. En la interfaz selecciona el Excel, indica el título, empresa y área/grupo libre, elige opcionalmente un logotipo y escribe instrucciones. Consulta a la derecha las pestañas Cuadernillo, Respuestas y Acetato antes de generar.
5. Pulsa **Generar documentos** y luego **Abrir resultado**.

Si falla la instalación, abre PowerShell en la carpeta del proyecto y ejecuta `py -3.13 -m venv .venv` y `.venv\Scripts\python.exe -m pip install -r requirements.txt`, o revisa los mensajes que muestra el iniciador. No hace falta activar PowerShell ni cambiar su política de ejecución.

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
  --titulo "Evaluación de cultura general" \
  --subtitulo "20 preguntas de ejemplo" \
  --reutilizable \
  --tamano-papel Carta \
  --letra 9.5
```

## Cómo preparar las preguntas en Excel

La hoja debe llamarse **`Preguntas`**, con las columnas en este orden:

| Tema | Pregunta | A | B | C | D | Correcta | Imagen (opcional) |
|---|---|---|---|---|---|---|---|
| Matemáticas | ¿Cuánto es 7 + 5? | 10 | 11 | 12 | 13 | C | (vacío) |

- `Correcta`: letra A/B/C/D; no escribas el texto completo de la respuesta.
- `Imagen`: **solo el nombre de archivo PNG, JPG o JPEG**, por ejemplo `conexion.jpg`. La imagen debe estar en la carpeta **`imagenes` junto al archivo XLSX**. No ingreses URL, rutas absolutas ni referencias a otras carpetas.
- El **logo** se selecciona de manera independiente en la interfaz (también puede indicarse con `--logo`).
- Se rechazan fórmulas, macros, hojas con cabeceras desordenadas, filas vacías entre preguntas, opciones repetidas e imágenes inválidas.
- `crear_ejemplo.py` crea `ejemplos/Plantilla_20_preguntas.xlsx` y recursos ficticios en `ejemplos/imagenes` para aprender; estos recursos no corresponden a bienes reales.
- La antigua plantilla de siete columnas sigue funcionando; simplemente no incluirá imágenes.

## Imprimir y calificar por acetato

Imprime `Hoja_respuestas.pdf` en papel normal y `Acetato_clave.pdf` en transparencia **al 100 %, tamaño real, sin “ajustar al papel”**. Alinea las marcas de registro de las cuatro esquinas. La clave solo tiene anillos en las respuestas correctas, para que se pueda ver el relleno del participante.

**Importante:** la compatibilidad con una impresora física y los inicios en Windows todavía requieren prueba de campo; la precisión de superposición fue validada en el código y los PDF de Linux. El diseño no promete compatibilidad con lectores OMR automáticos.

## Docker por comandos (opcional; la interfaz web es lo recomendado)

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
- La instalación usa `openpyxl==3.1.5`, `reportlab==5.1.0`, `Pillow>=12,<13`, `pypdfium2==5.15.1` (vista exacta); no se distribuyen fuentes del sistema.
- Ver [`AUDITORIA_SEGURIDAD.md`](AUDITORIA_SEGURIDAD.md) para hallazgos, mitigaciones y verificaciones pendientes.

## Pruebas

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python crear_ejemplo.py
python generar.py --entrada ejemplos/Plantilla_20_preguntas.xlsx --salida salidas
```

La CI incluye Windows/Linux con Python 3.11/3.12/3.13, además de la prueba `Iniciar_Windows.bat --verificar` en Windows 3.13. La impresión física y la experiencia de GUI en Windows requieren pruebas manuales.

## Evaluaciones del usuario (archivos privados)

Los bancos de preguntas de Cabos, Checadores, Sobrestantes y Captura y verificación se conservan **en las carpetas privadas de Drive del evaluador**, nunca en el repositorio público: contienen las respuestas correctas. Cada archivo XLSX respeta las columnas `Tema, Pregunta, A, B, C, D, Correcta, Imagen`, con 20 preguntas y sin medios externos. Para utilizarlos, descárgalos a tu computadora y selecciónalos desde la ventana.

El documento `Acetato_clave.pdf` sigue generado mediante la misma geometría fija que `Hoja_respuestas.pdf`. La previsualización muestra posiciones orientativas y no sustituye la prueba de superposición física al 100 %.

## Editor visual del PDF (escritorio)

Pulsa **Editar diseño · PDF real** en la parte superior del generador. Se abrirá
una ventana grande dividida en dos áreas: herramientas a la izquierda y
renderizado exacto del PDF a la derecha. Permite seleccionar **Cuadernillo**, **Respuestas**
o **Acetato**, recorrer páginas, ajustar zoom, elegir Carta/A4/Oficio, modificar el
texto del encabezado, tamaño de letra y las tres paletas RGB. También puedes
abrir el editor de preguntas, guardar cambios en SQLite y generar los cuatro PDF
sin cerrar esta ventana. Los cambios se reflejan en el PDF real en memoria.

Este editor cambia los parámetros previstos por el generador: **no es un editor
arbitrario de archivos PDF** ni permite arrastrar textos o imágenes libremente
como Acrobat. Si necesitas reordenar, añadir o borrar preguntas, usa **Editar
preguntas**; si deseas reposicionar cajas manualmente, necesitaríamos desarrollar
un editor de maquetación distinto.

## Eliminar cuestionarios sin perderlos por accidente

En **Mis cuestionarios**, selecciona uno y pulsa **Eliminar de biblioteca**.
Se moverá a **Papelera** después de confirmar, preservando las preguntas,
respuestas correctas e imágenes en SQLite. Marca **Mostrar papelera** para
**Restaurar** o **Eliminar definitivamente**. La eliminación definitiva requiere
dos confirmaciones y borra ese cuestionario y sus recursos de la base (los PDF
ya generados permanecen intactos). Respaldar `datos/biblioteca.sqlite3` sigue
siendo recomendable antes de eliminar definitivamente.

## Si Git no puede actualizar por la carpeta `ejemplos`

Las instalaciones antiguas creaban `ejemplos/` como carpeta no rastreada. Al
actualizar puede salir *untracked working tree files would be overwritten by merge*.
En ese caso, **no uses `git clean -fd`**. Con la aplicación cerrada, en PowerShell:

```powershell
$destino = "$HOME\Documents\Respaldo-Ejemplos-$(Get-Date -Format yyyyMMdd-HHmmss)"
Move-Item '.\ejemplos' $destino
git pull --ff-only
```

Con esto conservas el contenido antiguo y permites que Git descargue el ejemplo
genérico rastreado. Los cuestionarios y la base SQLite en `datos/` no se tocan.
