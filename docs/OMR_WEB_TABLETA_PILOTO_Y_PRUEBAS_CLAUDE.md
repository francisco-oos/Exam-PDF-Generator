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
git switch --track origin/feature/omr-auditoria-evidencias-recorreccion-v1
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


### Iteración Xerox: alineación física, grafito HB y reanálisis sin reimportar

**Evidencia técnica local sobre el paquete privado de prueba reemitido:**
- Lectura guardada por el motor anterior en el piloto Windows: **12, 10 y 1** dudas, tres hojas identificadas.
- Relectura offline del PDF reemitido con cuadrícula detectada por los centros físicos: **2, 1 y 1** dudas.
- Con un criterio adicional para lápiz HB **texturizado, homogéneo y único**: **0, 0 y 1** dudas. Se resuelven los reactivos 3 y 18 (página 1) y 19 (página 2); la duda 9 de la página 3 persiste porque existen dos opciones parcialmente marcadas.
- El criterio no consiste en aceptar un gris más claro sin pruebas. Requiere centro con media de tinta >=64/255, percentil 70 >=74/255, cobertura de píxeles menores a 210 de al menos 82%, contraste muy alto frente a las otras opciones y ausencia de doble marca. Un relleno uniforme muy tenue a gris 190/220 continúa en revisión, al igual que dos opciones con tinta.
- El PDF Xerox de prueba y sus bases personales **no se incluyeron en el repositorio**. Las regresiones de GitHub son datos 100% sintéticos, incluido un escenario con 20 filas comprimidas y un lápiz gris de textura variable.
- Son resultados de investigación del motor local; **no constituyen tasas de precisión estadísticamente verificadas**. Falta comparar manualmente contra las tres páginas y nuevos casos reales independientes, antes de confiar en calificaciones automáticas.

**Por qué el navegador aún mostraba 12/10:** la tabla SQLite contiene la primera lectura. Actualizar el código y recargar Edge no la recalifica: el visor verde recalcula el acetato y las posiciones, pero no reemplaza datos antiguos por efecto de ver la hoja.

**Nueva acción segura:** Administrador → **Bandeja PDF** → **Reanalizar** (sobre el PDF ya archivado) → confirmar → consultar el resultado con los campos pagina, antes, despues, mejora_aplicada y estado. Es un trabajo de servidor normal, no requiere extraer originales de USB. Conserva exactamente SHA, QR, folio, sesión y copia anterior del PNG. Solo reemplaza una lectura automática si reduce dudas y **no hay ninguna revisión humana**; conserva la auditoría técnica. Un reanálisis NO aumenta el contador Ingresos, NO duplica las hojas y NO renombra el PDF.

Si la comparación indica que no se aplicó mejora, comprobar si existen decisiones humanas, lectura ya actualizada o duda legítima. No borrar la base ni rehacer la sesión para forzar una nota.

**Aceptación física propuesta:** consultar las mismas tres hojas después de reanalizar y comparar **12→0, 10→0, 1→1** sobre la copia técnica, sin convertir la pregunta 9 de la tercera hoja en acierto. Repetir en Xerox y distintas intensidades de lápiz, marcas dobles, borrados, inclinaciones y escaneos de otra escala; si hay discordancias, rechazar automatización y mantener revisión humana.


## Evolución experimental: Resultados con evidencia auditada y re-corrección v1

**Rama exclusiva:** feature/omr-auditoria-evidencias-recorreccion-v1,
creada desde el commit 08a72ed8165bf1f5e89011fbbc6a9172a474fb7b
de feature/omr-tablet-lan-multiusuario-v1. **No modificar la rama
estable de prueba ni main**; PR de esta evolución contra esa rama.

### Resultado, evidencia y acetato en una misma vista

En Resultados, seleccionar **Ver evidencia** de un participante con
una única hoja efectiva abre un diseño de dos columnas: resumen de
aciertos, nota, áreas de mejora y acciones a la izquierda; escaneo
archivado y el acetato sobrepuesto a la derecha. Una casilla cambia
la capa; la lectura es exclusiva del servidor y nunca persiste una
imagen sobre la evidencia original. Los responsables se consultan
en el historial por hoja. Un participante ausente o con dos hojas en
conflicto no recibe una evidencia atribuida automáticamente.

**PDF para participante** conserva sólo el resumen de su calificación,
sin clave, acetato ni bitácora interna. **PDF interno con acetato**
conserva el resumen y agrega una página de evidencia auditada horizontal:
escaneo entero, acetato verde, ID, nombre, folio, estado,
aciertos/total y porcentaje **solo si la hoja está validada**,
último responsable y fecha UTC, eventos recientes y SHA del PDF
original. **PDF de evidencia auditada** ofrece esa sola página.
El texto visible "PILOTO / NO ES DOCUMENTO OFICIAL" pertenece a la
COPIA generada; no modifica ni tapa el texto impreso en la hoja.
El escaneo y el PDF original siguen disponibles sin edición.
El expediente interno ZIP incluye una evidencia auditada por
participante con una única hoja validada. Los PDFs que mezclan
aplicaciones se mantienen segregados.

Un resultado automático validado sin corrección humana se distingue
por el historial del motor ("Motor OMR"). Una re-corrección sin
terminar suspende la calificación definitiva, incluso si antes
había obtenido aciertos. No presentar el resultado antiguo como
vigente mientras la aclaración está abierta.

### Re-corrección controlada después de validar

1. Solo Administrador o rol heredado Coordinador, con sesión propia,
   puede usar **Re-corregir**. Los Auxiliares pueden corregir hojas
   pendientes asignadas, nunca reabrir una ya validada ni ver el
   acetato con claves correctas.
2. Se elige un reactivo y un motivo obligatorio (10 o más caracteres).
   El servidor valida estado VALIDADA, identidad/folio, asignación
   y conflicto con la reserva de otro operador.
3. La reapertura inserta entradas INMUTABLES en revisiones,
   web_auditoria_revision y web_eventos, anotando responsable,
   respuesta previa, aciertos previos, motivo y fecha UTC. Revoca
   cualquier aprobación anterior y las reservas viejas; marca
   únicamente ese reactivo como DUDA.
4. En Revisión de hojas se reclama una NUEVA reserva con versión
   optimista. Guardar decisión exige justificación y escribe
   respuesta anterior, respuesta nueva, aciertos antes/después,
   usuario y fecha UTC en la misma transacción que actualiza la
   hoja. La versión previa no se elimina.
5. El resultado se recalcula con la clave de la sesión ORIGINAL,
   nunca la biblioteca modificada posteriormente. Cualquier
   re-reapertura vuelve a requerir motivo y nueva evidencia.
6. La API no permite guardar sobre una hoja validada sin la
   reapertura expresa; conserva las reglas antiguas de error para
   los auxiliares. Ninguna llamada altera PDF o PNG originales.

**Tabla nueva aditiva:** web_auditoria_revision, con claves foráneas
a hojas y usuarios. No migra destructivamente la base Xerox ni cambia
las estructuras del motor OMR. Historial previo del motor sigue
disponible bajo registros_historicos.

### Rutas y permisos

- GET /api/applications/{sid}/results: resumen enriquecido, sin clave
  ni HMAC; solo admin/coordinador/auditor asignado.
- GET /api/sheets/{id}/history: historial de un único folio;
  admin/coordinador/auditor autorizado, sin claves correctas.
- GET /api/sheets/{id}/evidence?acetato=true: PDF derivado;
  acetato exclusivamente admin/coordinador. Sin acetato: vista
  read-only autorizada para auditor.
- POST /api/sheets/{id}/reopen: admin/coordinador con CSRF,
  pregunta y motivo; sin reserva concurrente ajena.
- PUT /api/sheets/{id}/decisions: mantiene reserva exclusiva,
  revisión optimista y motivo obligatorio, añade antes/después.

### Pruebas y aceptación

tests/test_omr_evidencia_auditoria.py usa personas ficticias y
escaneo sintético en un directorio temporal: pendiente → validada
(2/2) → reabierta (sin nota definitiva) → re-corrección (1/2).
Valida eventos históricos, antes/después, permisos, PDF individual
con evidencia anexa, SHA del PNG original intacto y persistencia
al reiniciar el servicio. Las suites originales siguen ejecutándose.

La prueba física se hará **sólo en copia Xerox aislada y respaldada**.
Confirmar la geometría de los 20 círculos y el contraste del acetato,
abrir PDF individual, cotejar nota con el registro, reabrir un reactivo
ficticio, cambiar decisión y verificar que el registro indique quién
y por qué. Confirmar que el original no cambió y que un Auxiliar
no puede reabrir ni descargar la clave. No fusionar ni integrar
licencia central sin aprobación física y cierre de CI.



## Reparación de evidencia en copia de worktree y diseño con imágenes (10/11/2026)

**Escenario Xerox real reportado:** al instalar la rama experimental en otra
carpeta, SQLite seguía guardando rutas absolutas de los PNG escaneados en
la instalación anterior. Resultados mostraba nota, folio y participante,
pero el visor y los PDF auditados fallaban con "No se encontró el escaneo
dentro del almacén autorizado". **No era un error del reconocimiento OMR.**

### Localización segura del PNG al copiar un piloto

La API de hoja, acetato y evidencia auditada consulta el registro por ID
autorizado y construye exclusivamente:
\`<OMR_WEB_DATA>/omr/escaneos/<sesion_id>/<hoja_id>.png\`.
Solo se permite una ruta real dentro de \`omr/escaneos\`. No se sigue
cualquier ruta absoluta vieja fuera de la copia, ni se modifican hashes,
PNG, folios, respuestas, QR, notas o versiones por consultar un archivo.
La lectura queda operativa aun si se borra la carpeta origen. Regresión
automática: \`test_worktree_copia_reutiliza_imagen_archivada_con_ruta_absoluta_anterior\`.

**Si falta el archivo físicamente en la copia**, el sistema responde
404 con el diagnóstico y no rescata contenido personal desde otra
instalación. En ese caso detener ambos servidores, respaldar la carpeta
de destino y verificar qué carpeta faltó al copiar.

Para normalizar las rutas de TODA la base, con el servidor detenido y
un respaldo ya comprobado, utilizar la herramienta existente:

\`\`\`powershell
$raiz = 'C:\Users\Control de Material\Documents\dev-Francisco\Exam-PDF-Generator-Auditoria'
cd $raiz
$datos = (Resolve-Path '.\datos\omr_web_prueba_xerox').Path
.\.venv-omr-web\Scripts\python.exe -m omr_web.relocate --data-dir "$datos"
# Revisar "apto" y "problemas" antes de aplicar:
.\.venv-omr-web\Scripts\python.exe -m omr_web.relocate --data-dir "$datos" --apply --confirm-stopped
\`\`\`

Si el diagnóstico encuentra un PDF original u otro archivo pendiente
que falta, NO aplicar ni inventar archivos: restaurar primero la copia
completa, o continuar usando el lector seguro de imágenes derivadas.

### Dos formas aprobadas de introducir fotos de preguntas

1. **Imagen PEGADA en Excel**: en la hoja **Preguntas**, anclar la foto
   a la fila de su reactivo, por ejemplo **H2** para la pregunta de
   la fila 2. La importación extrae el dibujo del XLSX, lo verifica,
   lo asocia por fila y lo incorpora a la biblioteca. No se adjunta
   otra vez mediante el selector "Fotos mencionadas en columna Imagen".
2. **Imagen como archivo**: poner en la columna **Imagen (H)** el nombre
   exacto de un PNG/JPG (por ejemplo \`equipo.png\`), adjuntarlo en
   importación, y comprobar que la biblioteca lo enlazó a esa pregunta.
   La imagen no referenciada se rechaza, no desaparece silenciosamente.
   No combinar una foto pegada y un nombre de archivo en la misma fila:
   se rechaza por ambiguo.

La plantilla mantiene sus hojas Preguntas, Ejemplo y Guia; no cambia la
lista de columnas aprobadas ni interpreta fórmulas como respuestas.
No se asocian dos fotos a una misma fila. El **logotipo es un recurso
separado**; se sube en el campo Logotipo y no se trata como una foto
de reactivo. Todas las fotos son PNG/JPG locales validados y limitados
en tamaño. No se suben XLSX, imágenes ni escaneos privados a GitHub.

### Medidas y posicionamiento después de importar

En **Diseñar cuestionario**, abrir el reactivo en su acordeón:
- Ancho máximo: **30–165 mm** (por defecto 106 mm).
- Alto máximo: **15–90 mm** (por defecto 62 mm).
- Alineación: **Izquierda / Centrada / Derecha**.

La imagen se adapta al rectángulo indicado **conservando su proporción**;
no se estira, y ReportLab realiza la paginación cuando aumenta su
altura. El **ancho del logotipo** se ajusta entre **10 y 28 mm** (23 mm
por defecto); en hoja OMR se acota al encabezado reservado para no mover
QR, marcas de calibración, círculos ni acetato. Si la foto viene PEGADA
en Excel, su escala de impresión se modifica aquí: el anclaje H2 define
la pregunta, no las dimensiones de salida.

Guardar diseño conserva medidas en la biblioteca SQLite con migración
aditiva (\`logo_ancho_mm\` y tres propiedades de cada reactivo).
Aplicaciones ya emitidas mantienen los folios y clave de su versión.
Las nuevas impresiones Normal/Ecológica reutilizan esas medidas en el
cuadernillo y paquetes individuales; la hoja universal OMR nunca cambia
su cuadrícula.

### Vista previa permanente y archivos aún sin guardar

La interfaz ahora presenta secciones plegables:
**Importar preguntas y crear cuestionario**, **Biblioteca**, **Diseñar
cuestionario** y **Emitir e imprimir**. A la derecha queda un visor
PDF real separado que no desaparece al plegar una sección ni al abrir
o cerrar una pregunta. Hay un botón **Actualizar vista previa** y
re-renderización automática después de cambios.

Cuando se elige una foto o logotipo nuevo, el navegador envía el
archivo mediante \`/api/library/{id}/preview-live\` a una carpeta
temporal aislada y lo descarta al cerrar la petición. **No crea una
revisión de biblioteca, sesión ni folio**. Se muestra como vista
temporal hasta usar **Guardar diseño**; después, imprimir solo cuando
los cambios estén confirmados. No confundir la vista previa con
material definitivo.

Pruebas agregadas al conjunto \`tests/test_omr_web_designer.py\`:
adjuntos nuevos antes de guardar, no mutación de biblioteca, foto y
logo extraídos del PDF por color, medidas/alineación y generación en
ambas modalidades, Excel con foto H2 + logo hasta el cuadernillo final,
JSON de biblioteca con foto identificada por nombre, rechazo de medidas
inválidas. Validación sintáctica Node de \`designer.js\` en CI.

### Aceptación física prevista

Sobre copia privada aislada del Xerox: abrir Resultados, seleccionar
el folio de Francisco, comprobar que se ve el PNG y acetato; descargar
PDF auditado y verificar el mismo folio, nota y hoja, manteniendo el
original intacto. En Generar exámenes: importar una plantilla con foto
incrustada, probar una segunda por nombre de archivo, cargar un logo,
cambiar dimensiones/alineación, comparar previsualización Cuadernillo /
Respuestas / Acetato, guardar y generar modo Normal y Ecológico. Revisar
físicamente tamaño y colocación en Carta/Oficio, especialmente con
cuadernillos de varias páginas. **No fusionar al flujo estable ni
producción antes de cerrar CI y esta aceptación física.**


## Conciliación, reescaneos y cola multiadministrador · PR #15 (10 noviembre)

**Regla de calificación:** un nuevo PDF o una nueva página con el mismo QR/folio jamás modifica la hoja previamente calificada. Las reimportaciones equivalentes se registran como repetidas; las discrepantes se conservan como `duplicado`, sin emitir nota definitiva hasta resolver el conflicto. Sólo administración/coordinación puede **descartar el reescaneo** con motivo de al menos 10 caracteres, conservando ambos originales y la auditoría; nunca se reemplaza silenciosamente la nota histórica. Si la hoja inicial aún no está validada, hay que revisarla primero.

**Concurrencia:** cada comprobación de folio y alta de hoja se realiza bajo `BEGIN IMMEDIATE` en SQLite para evitar dos hojas efectivas por carrera. Una única cola de PDF por instalación de datos emplea un candado exclusivo del sistema operativo para coordinar incluso múltiples procesos FastAPI; solamente quien lo posee recupera trabajos interrumpidos. El identificador SHA-256 deduplica ingresos simultáneos idénticos que aún están pendientes o procesándose; el estado indica posición real de cola, sin prometer minutos. Las reclamaciones de revisión siguen siendo exclusivas por hoja (lease de cinco minutos, versión optimista, bitácora). **No copiar un archivo SQLite abierto entre equipos.**

**Conciliación y cierre:** `GET /api/applications/{sid}/closure` muestra cada persona de la lista en estado pendiente por `SIN_ESCANEO`, `REVISION_PENDIENTE`, `DUPLICADO_POR_RESOLVER` o `APROBACION_PENDIENTE`. Es un reporte por folio, no una baja ni descuento de participantes. También informa hojas sin identificar, revisiones ocupadas y PDFs esperando procesamiento. `POST /api/applications/{sid}/close` sólo cierra cuando esos contadores están en cero y todas las hojas válidas tienen aprobación 2/2; tras cerrar se bloquea la incorporación de notas, incluso desde el motor. Los ZIP descargados antes del cierre deben considerarse **provisionales** y no comprobantes definitivos.

**Pruebas requeridas:** subir un mismo folio en PDFs con respuestas iguales y distintas; comprobar la invariabilidad de la nota original y la resolución documentada, importar en paralelo con administradores diferentes, reiniciar un trabajador con PDFs en cola, reclamar/guardar desde varias tabletas, observar listado íntegro de ausencias y verificar bloqueo del cierre hasta aprobar 2/2. Ejecutar sobre datos ficticios y luego sobre copia de Xerox, nunca sobre producción. No fusionar la PR hasta las pruebas físicas y autorización expresa.

**Reserva al guardar:** cuando quedan dudas se mantiene el lease actual y se incrementa su revisión. Al guardar la última duda como validada se incrementa la revisión, se libera el lease en la MISMA transacción y la interfaz muestra un acuse; el siguiente operador ya puede aprobar 2/2. Un cliente/pestaña anterior no puede volver a modificar esa hoja validada.

**Windows / lock exclusivo:** no se lee el byte del candado mientras otro proceso lo reserva, porque Windows usa bloqueo obligatorio y esa lectura falla con `PermissionError`. Se comprueba únicamente el tamaño del archivo y se solicita `LK_NBLCK` en espera controlada. Reenviar la misma ruta tampoco debe borrar el PDF que tiene un trabajo activo; las copias temporales distintas sí se eliminan una vez identificadas por SHA.

**Reanálisis mientras alguien revisa:** si existe un lease activo para una hoja, el motor no sustituye sus respuestas/dudas ni aplica mejora automática sobre ese mismo PDF. Devuelve `repetida`; el operador conserva la versión visible. Se puede reanalizar después de liberar o expirar la reserva, siempre que todavía no se hayan guardado decisiones humanas.

**Entrega provisional y definitiva:** el motor de escritorio conserva su modo histórico de exportación. En la WEB, el ZIP y su Excel se rotulan PROVISIONALES mientras la evaluación sigue abierta, aunque todas las marcas estén legibles; después de cierre y aprobación se rotulan DEFINITIVOS. El manifiesto incorpora `estado_evaluacion` y `entrega`. El reporte personal también advierte cuándo el resultado sigue provisional. No se alteran las columnas existentes ni se elimina un folio faltante.


## Auditoría de descargas y simulaciones de operación (10/11/2026)

**Menos redundancia visible, sin eliminar formatos ni API.** La tarea
Crear evaluación contiene los PDF de impresión: Cuadernillo, Hoja de
respuestas, Acetato y Paquetes individuales. Calificar → Resultados
concentra ZIP oficial (provisional hasta cierre) y ZIP interno con
bitácoras/evidencias. Cada persona ofrece UNA entrada a su ficha, con
PDF individual limpio para entregar y PDF interno auditado para cotejo.
El PDF de la sola hoja se conserva en un desplegable avanzado para
investigación, no junto al PDF individual como tercera opción equivalente.
Nunca entregar acetato o ZIP interno como reporte individual.

**Inicio por tarea:** admin elige Crear o Calificar; auxiliar solo
Calificar; auditor histórico solo Consultar. Los menús se filtran por
perfil y tarea, conservando las validaciones del servidor. Cambiar de
sección, de aplicación o de hoja libera explícitamente la reserva
previa, con confirmación si hay trabajo pendiente. Si falla la
liberación, se permanece en la revisión. No se repite la emisión de
folios para completar escaneos de otra jornada.

**Aprobación 2/2 independiente:** una calificación validada por el motor
puede aprobarla un humano admin/coordinador. Si hubo CORRECCION humana,
quien hizo la última corrección NO puede firmar su segunda aprobación.
Un segundo admin/coordinador autorizado debe hacerlo. Se prohíbe
sobrescribir una firma vigente por otro clic o sesión concurrente.
Al reabrir, se suspende la nota, se anula firma anterior y se audita
la transición; hace falta corregir y volver a aprobar.

### Matriz de escenarios (automáticos + aceptación física)

| Caso | Entrada y estado esperado |
|---|---|
| F01 | Normal con lista: QR por participante y calificación de sesión correcta |
| F02 | Ecológico con lista: cuadernillo común, hojas QR individuales |
| F03 | Normal sin lista: universal sin QR; calificación manual con acetato |
| F04 | Ecológico sin lista: universal sin QR; no crear sesión ficticia |
| F05 | PDF sin QR identificable: bandeja, motivo, captura íntegra manual |
| F06 | QR ilegible: retener evidencia, no inventar identidad |
| F07 | Lápiz tenue: duda pendiente hasta elegir A/B/C/D/BLANCO |
| F08 | Dos marcas o borrones: cotejo humano y motivo escrito |
| F09 | Corrección parcial: guarda versión, mantiene lease mientras hay dudas |
| F10 | Dos auxiliares reclaman mismo folio: segundo 409 y sin sobrescritura |
| F11 | Pestaña vieja guarda: 409 y se conserva última decisión |
| F12 | Cambiar tarea/hoja: liberar reserva sin eliminar corrección ya guardada |
| F13 | Dos administradores suben PDF idéntico: SHA dedupe y cola serial |
| F14 | Folio en PDFs distintos: conflicto auditable, no cambiar nota anterior |
| F15 | Reanálisis mientras se revisa: no sustituir selección/imagen reservada |
| F16 | Rectificación aprobada: suspender nota, abrir duda, bitácora antes/después |
| F17 | Misma cuenta corrige y pretende aprobar: 409 y segunda firma requerida |
| F18 | Dos administradores aprueban al tiempo: una firma, otra recibe 409 |
| F19 | Personas ausentes/sin identificar: lista íntegra y cierre bloqueado |
| F20 | Cerrada: ningún reescaneo modifica notas, ZIP oficial definitivo |
| F21 | Antes de cerrar: resultados y expedientes etiquetados provisionales |
| F22 | Informe individual vs interno: rutas, roles y contenido distintos |
| F23 | Reinicio durante cola: retomar trabajos sin dos procesamientos a la vez |
| F24 | Copia Xerox reubicada: verificar SHA y rutas seguras antes de iniciar |

Las nuevas regresiones están en tests/test_omr_flujos_operativos.py:
ausentes, dudas de grafito, dobles marcas, edición simultánea, corrección
parcial, pestaña vieja, rectificación tras aprobar, segunda firma,
aprobaciones simultáneas y cierre con hojas desconocidas. Se ejecutan
con una base temporal ficticia, sin tocar Xerox. Las lecturas reales de
grafito/hojas Xerox y las interfaces en tableta quedan por verificar
físicamente antes del merge.


### Descargas individuales seguras y limpieza de temporales

Al exportar un PDF personal, el nombre es ahora único por folio,
distingue PARTICIPANTE/INTERNO_AUDITADO y PROVISIONAL/DEFINITIVO.
Dos participantes ya no descargan por defecto el mismo nombre
Resultado_sesion.pdf. El enlace de la ficha recalca provisional
si la aplicación no está cerrada. Los ZIP/PDF creados en web_exportaciones
para atender una solicitud se eliminan SOLO después de servir la respuesta;
los originales de escáner, PNG evidenciales, lotes de impresión, SQLite y
respaldos NO se eliminan. Los temporales viejos de versiones anteriores
no se purgan automáticamente. Regresión: test_archivos_exportados_se_nombran_por_folio_y_no_acumulan_temporales.


### Bandeja de trabajos multiadministrador

La pantalla **Importar escaneos** presenta una cola persistente de
30 trabajos recientes, ordenados por recepción, con ID acotado,
operador, estado (pendiente/procesando/terminado/error), posición FIFO
y reintento explícito para fallidos. GET /api/jobs usa el rol en el
servidor: admin puede ver la cola completa; coordinador únicamente
sus ingresos; auxiliares y auditores reciben 403. La respuesta nunca
incluye rutas absolutas, claves ni el contenido del PDF. La vista se
actualiza cada 3.5 segundos solo mientras está abierta y no cambia
el candado global de procesamiento, que sigue siendo exclusivo.
El ID original de un trabajo reintentado se conserva.


**Nota de simulación de PDF:** para validar nombre de archivo,
descarga y eliminación de temporales, el test crea imágenes ficticias
rectificadas de 1700 × 2200 píxeles (Carta a 200 dpi). Una imagen de
240 × 190 px no tiene las cuatro marcas ni la geometría homologada:
el sistema debe rechazar el acetato alineado. Eso NO es un fallo de
Xerox ni prueba de lectura de lápiz real.


**Segundo control sin firmas a ciegas:** se eliminó el botón
Aprobar 2/2 de la tabla general. El segundo operador debe abrir la ficha
individual, confrontar escaneo/acetato/folio/nota e historial, confirmar
explícitamente el cotejo y entonces puede aprobar. El botón permanece
deshabilitado hasta la confirmación, y el servidor exige rol autorizado,
evaluación abierta, hoja validada, ausencia de otro lease y (si hubo
corrección manual) persona distinta del último corrector. La confirmación
visual no sustituye la comprobación en papel físico.


### Revisión prolongada y actualización compartida

Una hoja pendiente usa lease de 5 minutos. Mientras el navegador
conserve la misma hoja de revisión, el frontend envía un heartbeat
autenticado cada 45 segundos a POST /api/sheets/{id}/renew, que extiende
5 minutos desde la última renovación. No modifica respuestas, versión,
puntajes ni historial. Si otro navegador robó la sesión, el token cambió
o expiró, la API responde 409 y NO se revive la reserva anterior.
El frontend informa al usuario, deshabilita los botones de guardar y
conserva visibles sus decisiones sin guardar para cotejo. La siguiente
persona puede reclamar tras expiración; al cerrar sesión/cambiar tarea
se libera de inmediato. La lista de hojas se actualiza cada 4.5 segundos
en pantalla de revisión para reflejar ocupaciones ajenas. Pruebas
test_renovar_reserva_lenta_sin_cambiar_revision_ni_otra_cuenta y
test_una_reserva_que_vencio_no_resucita_con_heartbeat.
