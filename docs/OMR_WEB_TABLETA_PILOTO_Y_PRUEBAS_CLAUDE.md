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
