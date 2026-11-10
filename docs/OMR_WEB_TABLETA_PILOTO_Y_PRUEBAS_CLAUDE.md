# OMR Web Multiusuario · Piloto para tableta y futuro servidor de oficina

**Rama:** `feature/omr-tablet-lan-multiusuario-v1`  
**Base:** `feature/omr-web-multiusuario` (a su vez derivada del PR #13).  
**Estado:** piloto funcional con backend y frontend web; NO habilitado para producción ni como licencia comercial.  
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

Reutiliza sin reescribir los motores probados:
`biblioteca.py`, `generacion_integrada.py`,
`omr_evaluaciones/motor.py`, `documentos.py`, `expedientes.py`.

**Una sola fuente de verdad:** `datos/omr/sesiones.sqlite3` y sus PDFs/PNG
originales. Las tablas web nuevas son aditivas: `web_usuarios`,
`web_sesiones`, `web_asignaciones`, `web_reclamos`,
`web_eventos`, `web_trabajos` y `web_aprobaciones`.
No existe SQLite replicada por capturista ni se comparte el archivo en SMB.

**Diferencia con EvaluacionPersonal:** se reutilizan sus patrones de
cuentas, red local y revisión optimista, pero no se comparten bases,
usuarios, calificaciones ni sus tablas de puestos/departamentos.

## 2. Preparar el equipo servidor sin perder datos

1. En la tableta o PC Windows, instalar Git y Python 3.11–3.13.
2. Clonar el repositorio y seleccionar la rama experimental:

```powershell
git clone https://github.com/francisco-oos/Exam-PDF-Generator.git
cd Exam-PDF-Generator
git fetch origin
git switch --track origin/feature/omr-tablet-lan-multiusuario-v1
```

3. Si ya existen datos reales, antes de probar **cerrar Tk/servidor** y
   copiar `datos/omr/` y `datos/biblioteca.sqlite3` enteros a una
   carpeta de respaldo aislada. **Primero probar con una copia** de los datos.
   Esta rama crea nuevas tablas al iniciarse y no se recomienda alternar
   escritor web/Tk simultáneos sobre la misma base.
4. Para piloto local ejecutar:

```powershell
.\Iniciar_OMR_Web_Windows.bat
```

5. Abrir `http://127.0.0.1:8877` en la misma tableta. En el primer inicio
   tomar el **código de instalación de la consola** y crear el usuario
   administrador con contraseña individual de al menos 12 caracteres.
   El código no se guarda en GitHub ni se comparte por mensajes.
6. Administrar capturistas desde **Usuarios**. Cada uno recibirá su propia
   cuenta y una contraseña temporal que debe cambiar al entrar.

El script instala `requirements-web.txt`, incluido el motor OMR. El
frontend funciona sin conexión a Internet después de la instalación.

## 3. Acceso de otros capturistas por Wi-Fi LAN (HTTPS)

No exponer HTTP sin cifrar al Wi-Fi, porque se intercambian contraseñas,
PDF personales y resultados. Para una prueba temporal en una LAN controlada:

1. Conocer la IP fija de la tableta en la red, por ejemplo `192.168.1.40`
   (sustituir por la IP REAL que aparezca en el equipo).
2. Instalar dependencias y generar el certificado **una sola vez**:

```powershell
.\.venv\Scripts\python.exe -m omr_web.certificate 192.168.1.40
```

3. En esa ventana de PowerShell, activar servidor LAN cifrado:

```powershell
$env:OMR_WEB_BIND = "0.0.0.0"
$env:OMR_WEB_CERT = "datos/omr/certs/server.pem"
$env:OMR_WEB_KEY = "datos/omr/certs/server.key"
.\Iniciar_OMR_Web_Windows.bat
```

4. Abrir desde otro teléfono/computadora `https://IP_DE_LA_TABLETA:8877`.
   Se necesita confiar en el certificado mediante un procedimiento
   aprobado por la administración local; **un certificado autofirmado
   no equivale a TLS de producción confiable**. Si no se tiene esa
   confianza o un proxy TLS seguro, probar solo en localhost.

5. No publicar el puerto en Internet, no poner la clave privada en Git,
   correo, ZIP o chats, y proteger la tableta con contraseña y cifrado.

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
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests/test_omr_web.py
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas web verifican:
- Primer administrador y token de consola; autenticación y CSRF.
- Cambio forzoso de contraseñas temporales.
- Dos capturistas intentan reclamar la misma hoja al mismo tiempo:
  solo uno puede obtenerla.
- Revisión optimista: el segundo guardado desactualizado devuelve HTTP 409.
- Bitácora y respuestas completas válidas sin exponer clave.
- Persistencia de cola al reiniciar, reimportación idempotente.
- Lote Cabos/Checadores mezclado, separado por QR.
- Importación XLSX y generación de hojas firmadas desde la web.
- Restricción de evidencias, respuestas y aplicaciones ajenas.
- Certificado TLS con clave privada local y sin sobrescritura.

## 7. Relevo a Claude para aceptación física

**No publicar** los archivos reales suministrados por el propietario.
Los ZIP de datos/plantillas y el PDF del escáner deben tratarse como
material privado; copiar a un entorno local aislado, nunca versionarlos.
Referencias de la conversación:
- `datos.zip`: 2 sesiones OMR, 4 participantes y 2 hojas ya archivadas.
- `evaluacion-de-conocimientos_20261109_130901_54fcd8b(1).zip`:
  paquete impreso con cuadernillo/acetato/hojas firmadas.
- `Prueba evaluacion_09112026131837.PDF`: 3 páginas Xerox de otra prueba.

Claude debe colaborar como **tester**, no rehacer la arquitectura sin un
reporte de falla. Casos de aceptación:

| Caso | Prueba | Esperado |
|---|---|---|
| W01 | Inicio limpio en tableta Windows | Python, server, UI, login y libros |
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
