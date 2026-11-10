# OMR Web Multiusuario · Piloto para tableta y futuro servidor de oficina

**Rama:** `feature/omr-tablet-lan-multiusuario-v1`  
**Base:** `feature/omr-web-multiusuario` (a su vez derivada del PR #13).  
**Estado:** piloto web implementado con instalación aislada y pruebas CI; la aceptación física y producción están pendientes.  
**Fecha:** 2026-11-09.  
**Responsable de pruebas físicas:** Claude, con revisión humana y evidencia local.

## 1. Arquitectura que está implementada

El mismo repositorio conserva la aplicación de escritorio (Tk) intacta.
La nueva carpeta `omr_web/` contiene:

- `service.py`: usuarios, autenticación, permisos por aplicación, SQLite WAL,
  reservas de hoja de 5 minutos, versión optimista, bitácora con identidad
  del capturista, importación de PDF mediante trabajador de cola persistente.
- `app.py`: FastAPI/JSON; backend para cuestionarios, aplicaciones, PDF,
  revisión, acetato digital, resultados, evidencias y exportaciones.
- `static/index.html`, `styles.css`, `app.js`: frontend adaptable PC/tableta
  y teléfono, totalmente local y sin CDN ni Node para instalación.
- `run.py`: servidor local, bloqueo de modo producción sin licencia real,
  controles HTTPS para acceso desde otros dispositivos.
- `certificate.py`: certificado HTTPS temporal de piloto para una IP LAN.
- `runtime.py`: una ruta estable de datos, independientemente del
  directorio desde el cual Windows o Linux inicia el servidor.
- `doctor.py`: diagnóstico previo de dependencias nativas, Python,
  disco, SQLite, puerto y requisitos de TLS.
- `relocate.py`: comprobación de evidencia y reparación de rutas
  absolutas después de copiar el piloto a otro equipo; nunca automática.
- Iniciadores `Instalar_OMR_Web_*` y `Iniciar_OMR_Web_*`:
  instalación única y arranque posterior sin conexión.

Reutiliza sin reescribir los motores probados:
`biblioteca.py`, `generacion_integrada.py`,
`omr_evaluaciones/motor.py`, `documentos.py`, `expedientes.py`.

**Una sola fuente de verdad por piloto:** por defecto
`datos/omr_web_piloto/omr/sesiones.sqlite3`, los PDF/PNG originales
y `datos/omr_web_piloto/biblioteca.sqlite3`. El escritorio conserva
`datos/omr/` y `datos/biblioteca.sqlite3` sin compartir escrituras.
Las tablas web nuevas son aditivas: `web_usuarios`,
`web_sesiones`, `web_asignaciones`, `web_reclamos`,
`web_eventos`, `web_trabajos` y `web_aprobaciones`.
No existe SQLite replicada por capturista ni se comparte el archivo en SMB.

**Diferencia con EvaluacionPersonal:** se reutilizan sus patrones de
cuentas, red local y revisión optimista, pero no se comparten bases,
usuarios, calificaciones ni sus tablas de puestos/departamentos.

## 2. Instalar primero en laptop Windows

**Prerrequisitos:** Windows 10/11 x64, Python 3.11–3.13 de 64 bits,
Git y navegador actual (Edge, Chrome o Firefox). La primera instalación
requiere Internet; las posteriores ejecuciones funcionan sin reinstalar.
Reservar espacio de almacenamiento para PDF, PNG y respaldos; el
diagnóstico avisa por debajo de 500 MiB libres. En Linux también se
requiere `libzbar0` del sistema operativo.

1. Clonar el repositorio seleccionando únicamente la rama experimental:

```powershell
git clone https://github.com/francisco-oos/Exam-PDF-Generator.git
cd Exam-PDF-Generator
git fetch origin
git switch --track origin/feature/omr-tablet-lan-multiusuario-v1
```

2. Instalar **una sola vez** (con Internet):

```powershell
.\Instalar_OMR_Web_Windows.bat
```

  El instalador utiliza Python compatible, instala las dependencias
  de `requirements-web.txt` en el entorno aislado
  `.venv-omr-web/` y ejecuta el diagnóstico.

3. Arrancar sin conexión, sin `pip install` al abrir:

```powershell
.\Iniciar_OMR_Web_Windows.bat
```

  Abre `http://127.0.0.1:8877`, crea el administrador con el
  código mostrado en la misma consola y una contraseña de al menos
  12 caracteres. Luego asigna usuarios y aplicaciones. Para comprobar
  el entorno sin iniciar el servidor:

```powershell
.\Iniciar_OMR_Web_Windows.bat --verificar
```

4. Por defecto, **las nuevas aplicaciones se guardan sólo en**
  `datos/omr_web_piloto/`. El directorio puede cambiarse con
  `OMR_WEB_DATA`; si es relativo se interpreta desde el repositorio.
  No se comparte nunca una misma SQLite entre Tk y web ejecutándose.

5. **Respaldo seguro:** detener el servidor y Tk antes de copiar;
  respaldar la carpeta completa del piloto (ambas SQLite, originales,
  escaneos, entradas, salidas, evidencias y directorios auxiliares).
  No basta copiar sólo `sesiones.sqlite3` durante operaciones WAL.
  Las copias contienen datos personales, claves de examen y HMAC;
  conservarlas en almacenamiento cifrado y fuera de GitHub.

6. **Restaurar sin sobrescribir:** copiar el respaldo completo a otra
  carpeta, por ejemplo `datos/omr_web_restore/`. Antes de arrancarla,
  ejecutar el diagnóstico de rutas sobre la copia. El chequeo predeterminado
  es de solo lectura y la reparación requiere bandera explícita:

```powershell
$env:OMR_WEB_DATA = "datos/omr_web_restore"
.\.venv-omr-web\Scripts\python.exe -m omr_web.relocate
# Si confirma todos los archivos, y con ambos procesos detenidos:
.\.venv-omr-web\Scripts\python.exe -m omr_web.relocate --apply --confirm-stopped
.\Iniciar_OMR_Web_Windows.bat
```

  La reparación preserva folios, notas, usuarios y revisiones; valida
  la copia de cada PDF original con SHA-256. Si falta evidencia o
  no corresponde el lote, **no aplica cambios parciales**.
  Al restaurar a tableta cambia la variable al nuevo directorio en
  ese equipo. No apuntar la nueva aplicación al respaldo original.

7. En Linux ejecutar `bash Instalar_OMR_Web_Linux.sh` y luego
  `bash Iniciar_OMR_Web_Linux.sh`. Usar un usuario local dedicado
  y un volumen protegido; no habilitar un servicio de arranque
  automático hasta pasar la prueba en laptop y la restauración.

8. **Limitación:** un ZIP con bases de otra prueba no puede convertirse
  simplemente en una nueva evaluación: su clave HMAC, folios y
  datos deben conservarse juntos. Inspeccionar la estructura real de
  la copia antes de restaurar; no importar automáticamente datos.zip.


## 3. Acceso de otros capturistas por Wi-Fi LAN (HTTPS)

No exponer HTTP sin cifrar al Wi-Fi, porque se intercambian contraseñas,
PDF personales y resultados. Para una prueba temporal **después de aprobar la laptop**, en una LAN controlada:

1. Conocer la IP fija de la tableta en la red, por ejemplo `192.168.1.40`
   (sustituir por la IP REAL que aparezca en el equipo).
2. Instalar dependencias y generar el certificado **una sola vez**:

```powershell
.\.venv-omr-web\Scripts\python.exe -m omr_web.certificate 192.168.1.40
```

3. En esa ventana de PowerShell, activar servidor LAN cifrado:

```powershell
$env:OMR_WEB_BIND = "0.0.0.0"
$env:OMR_WEB_CERT = "datos/omr_web_piloto/omr/certs/server.pem"
$env:OMR_WEB_KEY = "datos/omr_web_piloto/omr/certs/server.key"
.\Iniciar_OMR_Web_Windows.bat
```

4. Abrir desde otro teléfono/computadora `https://IP_DE_LA_TABLETA:8877`.
   Se necesita confiar en el certificado mediante un procedimiento
   aprobado por la administración local; **un certificado autofirmado
   no equivale a TLS de producción confiable**. Si no se tiene esa
   confianza o un proxy TLS seguro, probar solo en localhost.

5. No publicar el puerto en Internet, no poner la clave privada en Git,
   correo, ZIP o chats, y proteger la tableta con contraseña y cifrado.

## 3A. Recuperación del diseñador aprobado (rama piloto)

**Hallazgo que motivó este cambio:** la primera adaptación web había
reducido la biblioteca a XLSX sin imágenes ni metadatos y obligaba a
cargar personal, pese a que el motor original permitía ambas modalidades
y lista opcional. Se corrigió la interfaz, sin reescribir la geometría
de hoja ni acetato.

| Aspecto | Comportamiento verificado por diseño |
| --- | --- |
| Perfil administrador | Importa/edita preguntas y opciones A-D, imágenes, logotipo, títulos, subtítulos, empresa, grupo, instrucciones, colores, papel y tipografía; genera y descarga |
| Perfil auxiliar | Cuenta propia con contraseña temporal, revisión de hojas asignadas, decisión A-D/BLANCO justificada; no descarga claves ni diseña |
| Normal + personal | Cuadernillo/hoja QR por persona; paquetes ZIP individuales y lote |
| Ecológico + personal | Cuadernillo reutilizable y hojas QR con identidad y folio |
| Normal/Ecológico sin personal | Hoja universal sin QR ni folio; acetato físico para calificación manual, sin sesión de OMR inventada |
| Plantilla preguntas | `Plantilla_Cuestionario.xlsx` de Preguntas/Ejemplo/Guia; las rutas de fotos son solo nombres en la columna Imagen |
| Plantilla personal | `Plantilla_Personal_OMR.xlsx`, CSV o captura manual; ID/Nombre obligatorios, Área/Grupo/Turno opcionales |
| Vista PDF | Cuadernillo, Respuestas, Acetato generados en memoria por `preview_pdf.py`; QR de ejemplo NO válido para calificación real |
| Biblioteca SQLite | Una identidad/revisión por cuestionario. Se conserva la clave y recursos BLOB con SHA-256; las sesiones ya impresas no se modifican al editar |

**Código conectado:** `omr_web/designer.py` (importación y validación de
archivos, edición, vistas y personal), `omr_web/static/designer.js`
(formularios y tres vistas PDF), `omr_web/app.py` (endpoints admin),
`omr_web/service.py` (dos modalidades, lote manual, alias auxiliar).
Se reutiliza `biblioteca.save_exam/load_exam`,
`src.evaluaciones.core.read_questions` y
`generacion_integrada.preparar_examen`; no existe otro motor de
evaluación independiente.

**Permisos:** la API aplica `admin` en biblioteca, plantillas,
vista previa, lotes de impresión y emisión. `auxiliar` se almacena
como `capturista` para no alterar la tabla de cuentas instalada.
Los roles de coordinador y auditor se conservan para datos históricos,
pero el operador sólo necesita los dos perfiles mencionados.

**Precauciones:** cada edición de la biblioteca incrementa su revisión;
el QR y clave de cada aplicación impresa son inmutables. Los archivos
PNG/JPG se validan y almacenan en la biblioteca, y la vista previa
no sustituye la comprobación impresa al 100%. En modo sin lista no
hay calificación automática por QR, únicamente acetato manual.

### Pruebas nuevas de regresión

`tests/test_omr_web_designer.py` usa sólo registros ficticios y verifica:
plantillas originales, importación con fotos/logotipo, edición posterior
sin perder imágenes, normal/ecológico con y sin participantes, campos
opcionales, vistas de los tres PDF y separación de claves frente al
perfil auxiliar. Las ejecuciones deben aprobarse en la matriz Windows/
Linux y confirmarse en la laptop real antes de instalar en tableta.

## 4. Cómo se opera

- **Diseñar e imprimir**: el administrador importa XLSX de preguntas
  o selecciona un cuestionario existente; elige normal/ecológico,
  papel y lista de participantes; genera cuadernillo, acetato, hojas QR.
  La generación crea folios nuevos; NO repetir para completar escaneos.
- **Importar escaneos**: administrador/coordinador sube PDF completo; el
  servidor conserva su SHA, identifica página por QR/HMAC y procesa
  cada grupo autorizado. Sin QR queda en Bandeja PDF para identificar
  manualmente. Trabajo en segundo plano con estado consultable.
- **Capturistas**: desde aplicación asignada ven hojas pendientes,
  reclaman una (lease de 5 minutos), leen imagen y selección de reactivo,
  deciden A/B/C/D/BLANCO, registran motivo y guardan. La respuesta no
  se sustituye si la versión del navegador está desactualizada.
- **Captura íntegra**: para una hoja completamente dudosa, resolver todos
  los reactivos en una sola operación transaccional, con motivos.
- **Acetato digital**: el capturista ve un resaltado de la zona dudosa
  sin clave; los coordinadores pueden solicitar el acetato con la clave.
- **Bandeja documental**: solo el administrador ve PDF originales mixtos
  de distintas evaluaciones; puede vincular una hoja sin QR por ID+folio
  exacto, con evidencia y captura manual posterior.
- **Resultados**: los administradores/coordinadores autorizados descargan
  XLSX/ZIP oficial o expediente interno; el resultado individual no
  muestra los demás participantes ni la clave.

## 5. Autorización, seguridad y límites de esta fase

- Roles: `admin`, `coordinador`, `capturista`, `auditor`.
  Los permisos por aplicación se verifican en el backend.
- Descargas de material de impresión (incluidos acetato con clave, PDFs de
  participantes, paquetes y manifiesto) reservadas a administrador o
  coordinador asignado; capturistas y auditores reciben 403 incluso si
  conocen el enlace. La API de aplicaciones no expone rutas del servidor.
- Sesión HttpOnly, SameSite Strict y token CSRF. Contraseñas PBKDF2-SHA256
  con sal, cambio obligatorio de claves temporales.
- Las correcciones se registran en `revisiones` y `web_eventos`.
  Solo uno puede reclamar la hoja; un reclamo ajeno devuelve HTTP 409.
- PDF originales por SHA-256 inmutable. Un escaneo mezclado no se entrega
  íntegro a un capturista que no esté autorizado para sus páginas.
- Cola en SQLite reanudable tras cierre. Los PDF originales se conservan.
- **Licencias:** el servidor declara explícitamente
  `PILOTO SIN VALIDACIÓN DE LICENCIA CENTRAL`. Cualquier intento de
  arrancar en `OMR_WEB_MODE=production` queda bloqueado.
  Todavía **NO hay integración con Tracking Core o el servidor de
  licencias del propietario**. Conectarla será una fase posterior.
- No se ejecutó todavía una instalación real en tableta ni una prueba
  de concurrencia física desde varios teléfonos. CI no la sustituye.
- La interfaz web no replica todavía todas las herramientas visuales
  avanzadas del editor Tkinter (arrastre de diseño, logotipos y organización
  visual extensa de PDF). Se preserva el escritorio para esas tareas.

## 6. Pruebas automatizadas

Ejecutar desde la raíz:

```powershell
.\.venv-omr-web\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv-omr-web\Scripts\python.exe -m pytest -q tests/test_omr_web.py
.\.venv-omr-web\Scripts\python.exe -m pytest -q
```

Las pruebas web verifican:
- Primer administrador y token de consola; autenticación y CSRF.
- Cambio forzoso de contraseñas temporales.
- Dos capturistas intentan reclamar la misma hoja al mismo tiempo:
  solo uno puede obtenerla.
- Cinco capturistas procesan 50 hojas sintéticas concurrentes sin folios
  repetidos; no sustituye W10 de papel físico, RAM ni tiempos reales.
- Una hoja validada ya no puede reabrirse ni editarse por capturista;
  solo el coordinador o administrador puede corregirla con auditoría.
- Revisión optimista: el segundo guardado desactualizado devuelve HTTP 409.
- Bitácora y respuestas completas válidas sin exponer clave.
- Persistencia de cola al reiniciar, reimportación idempotente.
- Lote Cabos/Checadores mezclado, separado por QR.
- Importación XLSX y generación de hojas firmadas desde la web.
- Restricción de evidencias, respuestas y aplicaciones ajenas.
- Certificado TLS con clave privada local y sin sobrescritura.
- Diagnóstico de instalación sin CDN, Node, conexión recurrente ni mezcla
  de datos/entorno Tk.
- Reubicación sintética entre laptop y tableta: imágenes, original SHA,
  notas y bitácora iguales; abortar si falta un archivo.
- Las suites de origen del editor Tk continúan ejecutándose en Windows/Linux.

## 7. Relevo a Claude para aceptación física

**No publicar** los archivos reales suministrados por el propietario.
Los ZIP de datos/plantillas y el PDF del escáner deben tratarse como
material privado; copiar a un entorno local aislado, nunca versionarlos.
Referencias de la conversación (PRIVADAS, sólo para pruebas físicas):
- `datos.zip`: 2 sesiones OMR, 4 participantes y 2 hojas ya archivadas.
- `evaluacion-de-conocimientos_20261109_130901_54fcd8b(1).zip`:
  paquete impreso con cuadernillo/acetato/hojas firmadas.
- `Prueba evaluacion_09112026131837.PDF`: 3 páginas Xerox de otra prueba.

No se han subido los ZIP ni el PDF real a GitHub ni se han ejecutado
en CI. Se conservan como originales para la laptop, no como fixtures
del repositorio. Copiar en el equipo a una carpeta privada fuera de Git
o `datos/pruebas_fisicas/` (ignorada por Git); registrar su SHA-256.
Primero se inspecciona la estructura de `datos.zip` y se prueba sobre
una copia aislada. No perder la clave HMAC al separar escaneos de sesiones.
Las imágenes de Xerox y lápiz #2 requieren revisión humana.

Claude debe colaborar como **tester**, no rehacer la arquitectura sin un
reporte de falla. Casos de aceptación:

| Caso | Prueba | Esperado |
|---|---|---|
| W01 | Inicio en laptop Windows y luego tableta | Python, API, frontend, cuenta y biblioteca |
| W02 | Abrir desde segundo dispositivo por HTTPS | Sesión por capturista y sin archivos compartidos |
| W03 | 2 capturistas reclaman mismo folio | Uno obtiene hoja y otro ve ocupada/409 |
| W04 | Dos correcciones con revisión anterior | La obsoleta se rechaza; no pisa la correcta |
| W05 | Lote mixto Cabos/Checadores | QR firmado determina la aplicación |
| W06 | QR ilegible | Página archivada sin nota, vinculación ID+folio auditada |
| W07 | Escanear folios de una aplicación en dos días | Una sola sesión, sin resultados duplicados |
| W08 | 1 marca incorrecta, 2 marcas y lápiz tenue #2 | Validar con papel, comparación y acetato |
| W09 | Captura íntegra de 20+ reactivos | Todos se registran o ninguno (rollback) |
| W10 | 3 a 5 capturistas con 50 hojas | Sin repetidas, con tiempos y memoria |
| W11 | Cortar alimentación del servidor durante lectura | Recuperar original/trabajo sin duplicar |
| W12 | Exportar expediente de PDF mixto | Sin evidencias de otra evaluación |
| W13 | Restaurar backup SQLite y documentos | Hash, folios, anotaciones sin pérdida |
| W14 | Roles y acceso entre aplicaciones | 401/403; ningún dato ajeno |
| W15 | Intento iniciar como producción sin licencia | Rechazo explícito, sin activación ficticia |
| W16 | Apagar Wi-Fi tras instalar en laptop | Inicio, QR y revisión local sin conexión ni pip |
| W17 | Restauración de copia en otra ruta/equipo | HASH, imágenes, folios, respuestas y bitácoras idénticos |
| W18 | Capturista intenta abrir acetato y paquetes | 403; no recibe claves ni folios PDF |

Registrar resultado PASA/FALLA, tiempo, versión, navegador, SO,
número de hojas, perfil de lápiz, página afectada y mensaje exacto.
Si encuentra fallo, crear prueba de regresión y commit en ESTA rama.

## 8. Integración posterior al servidor de producción

Una vez aceptada la prueba física, integrar como **servicio independiente**
dentro de la infraestructura de oficina:
- Adaptador de licencias al sistema maestro, sujeto a la política del dueño.
- Autenticación/roles federados si procede, sin reutilizar contraseñas.
- Reverse proxy HTTPS, monitorización y respaldos centralizados.
- Versiones y contratos de intercambio firmados para resultados agregados.
- Evitar abrir puertos directos del servidor de office al exterior.

**No fusionar a main ni conectar con Tracking Core** antes de que el
usuario apruebe resultados de Claude y se pruebe la restauración.


## Prueba física Xerox — reparación de visor, exportaciones y segunda vía de calificación

**Evidencia real compartida por el operador:** el PDF de 3 páginas, reemitido
únicamente como prueba con QR nuevos, fue leído en el piloto: total 3,
sin identificar 0, aplicaciones 2 (2 páginas + 1 página), validadas 0,
revisar 3. Este resultado **no** demuestra que las 20 marcas se lean
correctamente: una hoja registró 12 dudas y hubo que verificar visualmente.
Los QR originales perdidos no pueden reconstruir su HMAC: el paquete
Xerox fue prueba y no certificación histórica.

**Errores reproducidos y correcciones:**
- Las rutas de PDF individual y ZIP invocaban `participant_receipt` y
  `export_session_bundle` sin importarlos en `omr_web/app.py`; devolvían
  `NameError` e HTTP 500. Se importan desde
  `omr_evaluaciones/expedientes.py`. Un PDF individual con notas todavía
  pendientes se entrega como *provisional*; no se inventan aciertos.
- En el visor de revisión se eliminó el botón de resaltado de una sola
  ocasión. Los checks **Resaltar reactivo** y **Superponer acetato** conservan
  estado mientras se cambia de pregunta/hoja. La capa no altera el PNG ni
  el PDF original; el recuadro se dibuja fino y separado de las burbujas.
  El acetato sólo lo pueden activar admin/coordinador: un auxiliar no recibe
  claves correctas. Si la imagen falla, se muestra la evidencia original.
- El motor de impresión OMR no recibía el logotipo, aunque el cuadernillo
  sí. Ahora hoja normal QR, hoja genérica sin QR y previsualización PDF
  admiten logo dentro de un espacio reservado del encabezado, sin mover
  marcadores, burbujas ni QR. También se transmite el color de subtítulo.
  Los colores originales de título, subtítulo, respuestas y acetato
  siguen siendo independientes. Los recursos nuevos se ven después de
  **Guardar diseño**; editar la biblioteca jamás cambia una hoja ya emitida.
- La Bandeja PDF permite reintentar cargar la imagen de una página y
  conserva el original por SHA-256.

### Dos modalidades de **calificación** (distintas de Normal/Ecológico de impresión)

**1. Automática QR**: PDF de escáner → descifrar identidad mediante QR
firmado HMAC + token de sesión → rectificar imagen por cuatro marcadores →
medir marcas → revisión individual de dudas → resultado. El QR y la clave
de la sesión real deben existir y corresponderse.

**2. Manual con acetato y biblioteca**: subir PDF sin QR validable →
Bandeja PDF → Ver páginas → **Identificar manualmente y seleccionar examen**
(sólo páginas pendientes, sin dueño) → seleccionar cuestionario almacenado,
papel Carta/A4/Oficio, ID, nombre, grupo y motivo → el servidor crea
**otra sesión de captura manual**, un folio **interno nuevo**,
`cuestionario_id`, revisión, y copia de evidencia. Las 20 respuestas
permanecen **SIN REVISAR**, sin ninguna puntuación automática. Revisar
manualmente cada marca y guardar captura completa con justificación;
el resultado no se valida hasta que se resuelvan todas. Los auxiliares
pueden revisar aplicaciones asignadas sin ver acetato/clave; sólo el
administrador efectúa vinculaciones de identidad.

**Limitación intencional:** las sesiones manuales iniciales son una por
página vinculada. El folio interno no se presenta como el QR impreso ni
suplanta el folio perdido. No se permite vincular manualmente una página
que ya fue procesada por una sesión QR. El usuario debe cotejar la
identidad de la hoja física y la revisión correcta del cuestionario:
el sistema no la deduce por OCR ni por título parecido.

**Validación requerida antes de tableta o producción:** pruebas con el
PDF original y reemitido en copia aislada, imprimir al 100% una hoja
de control con logo y colores, verificar físicamente la coincidencia
de la superposición verde/naranja en las 20 preguntas, comprobar que
cada rol sólo acceda a lo permitido y que las exportaciones provisionales
no se interpreten como definitivas. No fusionar `main` hasta la
aceptación física y enlace del validador de licencias.

### Calibración adicional de marcas Xerox

La comprobación directa en las tres páginas de prueba detectó que dos
hojas antiguas tenían una separación interior de círculos de alrededor
de 50 píxeles/fila, mientras la tercera y la geometría nominal usan
aproximadamente 54 píxeles/fila a 200 DPI. Eso acumulaba desplazamiento
vertical en los últimos reactivos, aunque el QR y los cuatro cuadrados
estuvieran perfectamente identificados. `_bubble_centers_in_scan`
localiza contornos circulares, verifica cuatro columnas y progresión
regular de filas, y sólo si cumple tolerancias usa esas coordenadas
medidas para `_recognize` y `render_review_with_acetato`.
**Nunca** modifica `bubble_positions` ni el formato PDF de impresión.
Si faltan demasiados círculos, hay ruido o paso irregular, conserva la
geometría nominal y solicita revisión humana; no aumenta automáticamente
notas por proximidad. Pruebas sintéticas en
`tests/test_omr_grid_calibration.py`, incluyendo doble marca,
geometría actual, geometría comprimida y rejilla inválida. Ninguna
imagen identificable del usuario se agregó al repositorio.


### Prueba de imágenes en Excel y en el diseñador web

El importador admite tres rutas, siempre con PNG/JPEG de hasta 4 MB por imagen:

1. **Columna Imagen del XLSX**: escribir el nombre exacto (por ejemplo,
   equipo.png) en la columna H de la pestaña Preguntas y seleccionar
   ese archivo en el campo Imágenes de reactivos. No introducir rutas
   completas de Windows ni de otras carpetas. Si sobra una foto
   seleccionada o falta una foto referenciada, mostrar error 422.
2. **Foto pegada en Excel**: admite un dibujo PNG/JPEG anclado a la
   misma fila del reactivo, desde la fila 2. Completa internamente
   la referencia en H. Rechaza fotos fuera de una fila de reactivo,
   dos fotos para el mismo reactivo o imagen incrustada que compite
   con un nombre escrito; nunca adivina la asociación.
3. **Foto seleccionada en la interfaz web**: una imagen por reactivo
   desde Diseñar cuestionario. El archivo pendiente se conserva
   aunque se agreguen o eliminen otras preguntas antes de Guardar
   diseño. Quitar imagen y Quitar logotipo descartan selecciones
   pendientes. La vista PDF incorpora la fotografía después de guardar.

**Salida:** las imágenes de los reactivos se incrustan en el Cuadernillo,
no sobre las burbujas de la hoja de respuestas. El logo sí aparece
en la cabecera del Cuadernillo y de la Hoja OMR (con o sin QR).
El Acetato muestra las respuestas correctas, no las fotos.
Los recursos se conservan como BLOB con SHA-256 en la biblioteca.

**Regresión:** tests/test_omr_web_designer.py verifica imports por nombre,
fotos incrustadas de varias filas (sin intercambiar), edición con
adjuntos web, PDF real y vista previa, archivo corrupto, referencia
ausente y foto sobrante. src/evaluaciones/core.py cierra el iterador
XML ante errores para liberar el archivo XLSX en Windows. El importador
recupera las imágenes insertadas aunque openpyxl cierre su stream.

No sustituye la comprobación física de impresión 100%, visor Edge/Chrome,
superposición de acetato y escaneo Xerox; hacerla en copia aislada,
sin modificar la base principal ni las calificaciones oficiales.


### Iteración de lápiz y orientación por tema

Las capturas del piloto mostraron 12 dudas en la primera hoja marcada
con lápiz y una en la hoja marcada con plumón negro. Es un dato
observado de esa importación, **no** una evaluación automática de la
precisión definitiva del lector. Los aros verdes del visor son la
clave del acetato: no indican lo que leyó el motor.

El motor añade un criterio conservador para grafito de intensidad
media: una sola burbuja bien rellena, homogénea y separada de las otras
tres. Grafito muy tenue, tachones, dobles marcas y diferencias pequeñas
siguen en la cola de revisión. No se extrapola la sensibilidad de
capturas de pantalla: repetir el PDF real en la misma base de prueba,
comparar preguntas dudosas y verificar que ninguna respuesta incorrecta
se convierta en acierto. No reescribir decisiones humanas. Regresión
sintética en tests/test_omr_reporting_pencil.py con negro/gris medio,
190/220 tenue y dos rellenos.

En la interfaz Revisión de hojas, el selector de reactivos muestra
**DUDA** delante de los pendientes, incluye números navegables y salta
a la siguiente duda al guardar una decisión. La lectura indecisa se
identifica como **PENDIENTE DE REVISIÓN**: nunca como si fuera un blanco
confirmado. El resaltado naranja y el acetato verde conservan sus
controles independientes. No se atribuye acierto por la visualización.

La exportación PDF individual y la tabla de Resultados incluyen
temas por reforzar, aciertos/preguntas por tema y sugerencias de
estudio, sin mostrar respuestas correctas. Es información orientativa
basada en **esta evaluación**, no certificación de competencia.
Solo los participantes con una única hoja validada tienen
diagnóstico por temas; hojas dudosas, pendientes y ausentes indican
que falta verificación. Las agrupaciones corresponden literalmente
a los valores Tema de la plantilla (sin inventar competencias
externas). La prueba sintética confirma un tema de 2/2 y otro
de 1/3, así como ausencia de recomendaciones cuando no hay
calificación validada.

Revisar aceptación en Edge Windows con importación nueva del PDF
de tres páginas: comprobar cambio de 12/10/1 dudas, validar la
coincidencia exacta de cada marca con el folio, descargar reporte
por persona y comparar con respuesta humana. Si se repite el mismo
PDF, el motor sólo actualiza una lectura pendiente con menos dudas
y sin revisiones humanas: conserva registro histórico y los PDF.
