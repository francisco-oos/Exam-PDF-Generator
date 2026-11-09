# Propuesta técnica — OMR web multiusuario (rama experimental)

**Estado:** diseño, sin implementación funcional ni cambios de esquema.  
**Fecha:** 2026-11-09.  
**Rama experimental:** \`feature/omr-web-multiusuario\`.  
**Punto de partida:** commit \`731063865bc47d6043b6db463be836291e0b6129\` de \`feature/bandeja-documental-omr-evidencias\` (PR #13).  
**Referencia de flujos multiusuario:** \`francisco-oos/EvaluacionPersonal\` v1.2.0; **NO unir sus bases de datos ni importar su formato de evaluación por áreas**.

## Objetivo y restricciones

Convertir el generador de cuestionarios, emisión de QR, escaneo OMR,
bandeja documental, acetato digital y exportaciones en un sistema web que
atienda simultáneamente a varios operadores y capturistas en una LAN.
Un equipo servidor conserva la fuente de verdad, PDF originales, HMAC,
respuestas y bitácoras. Navegadores de PC, tabletas y teléfonos interactúan
mediante una API autenticada; no necesitan Python ni una copia de SQLite.

**No sustituir ni romper la versión Tkinter:** la rama actual sigue disponible
para uso y pruebas. No fusionar esta rama sin validación funcional,
concurrencia, seguridad, migración y restauración completa.

## Hallazgos reales del repositorio EvaluacionPersonal

- \`main.py\` + \`app/server.py\`: servidor web local con usuarios individuales
  y acceso a través de la IP del equipo en la Wi-Fi.
- \`app/database.py\`: SQLite central con WAL, \`busy_timeout=30000\`,
  \`BEGIN IMMEDIATE\`, idempotencia por ID cliente y comprobación de revisión
  optimista para evitar sobrescritura de capturas antiguas.
- Cuentas y roles por departamento, sesión HttpOnly/SameSite,
  contraseña individual PBKDF2 y trazabilidad de capturista.
- \`tests/test_database.py\`: prueba de 60 evaluaciones escritas desde
  2 usuarios con \`ThreadPoolExecutor(max_workers=10)\`.
- Exportaciones/respaldos se generan en el servidor.
- **Diferencia:** las evaluaciones de aquel sistema son capturas manuales
  por departamento/áreas; OMR utiliza cuestionarios, versiones inmutables
  de clave, sesiones firmadas, folios, páginas físicas y decisiones por
  reactivo. Reusar los patrones, NO las tablas ni la lógica de puntuación.

## Hallazgos del repositorio OMR

- El motor OMR está separado de la UI Tk: \`omr_evaluaciones/motor.py\`,
  \`documentos.py\` y \`expedientes.py\`. No reescribir el lector ni
  alterar geometría \`bubble_positions\` durante migración.
- \`biblioteca.py\` conserva cuestionarios/versiones e imágenes en SQLite.
- \`web_app.py\` actual solo genera PDF a partir de archivos colocados
  localmente; no dispone de login, bandeja documental OMR, revisión
  simultánea ni APIs para administrar folios.
- Dos SQLite actuales: biblioteca y OMR. No apuntar clientes al archivo
  en una carpeta compartida; la API servidor controla toda escritura.
- Preserve HMAC, UUID, folios emitidos, PDF originales e historial de
  intervenciones humanas al migrar. Migración aditiva y respaldos
  consistentes, **nunca crear sesiones nuevas para reimportar PDF**.

## Arquitectura candidata

\`\`\`text
PC servidor (Windows o Linux, LAN privada)
  ├── Backend Python API (FastAPI + Pydantic)
  │   ├── Autenticación / roles / controles por evaluación
  │   ├── Biblioteca, aplicaciones, participantes y folios
  │   ├── Ingreso de PDF y clasificación criptográfica por página
  │   ├── Cola persistida de trabajos de escaneo; worker OMR aislado
  │   ├── Cola de correcciones y reclamo temporal de hojas (lease)
  │   ├── Revisión optimista + bitácora inmutable de decisiones
  │   └── Exportación oficial / expediente y respaldo verificable
  ├── BD central SQLite/WAL en servidor en primera fase
  │   └── evaluar PostgreSQL al crecer en cargas/escritores
  └── Carpeta local de PDF/PNG originales por SHA-256
        ↑ vía HTTPS LAN, nunca montando SQLite en red
  ├── Navegador administrador / diseñador (PC)
  ├── Navegador capturista 1 (PC / móvil)
  ├── Navegador capturista 2 (PC / móvil)
  └── Navegador coordinador / auditor
\`\`\`

**Frontend recomendado:** React + TypeScript + Vite, compilado a archivos
estáticos que sirve el propio backend; Node solo durante el desarrollo.
Mantener las dos entradas conceptuales aprobadas: **Diseñar e imprimir** y
**Calificar y entregar**, integradas en un solo sitio responsive.
Alternativa simple: HTML/JS del modelo de EvaluacionPersonal, pero no
portar su lógica de capturas al OMR. No abrir una segunda ventana Tk.

**Persistencia:** SQLite WAL con una conexión por solicitud y
transacciones cortas es la opción inicial para un solo PC servidor
y varios capturistas. No ejecutar procesamiento pesado dentro de las
transacciones. No compartir físicamente el .sqlite en SMB.
Preparar repositorio/adaptador para PostgreSQL cuando haya multi-servidor,
escritores sostenidos o pruebas de bloqueo que lo justifiquen.

**Tareas:** almacén persistido para \`queued/running/failed/completed\`,
reintentos con idempotencia y recuperación tras reiniciar. API responde
202 con ID de trabajo; worker renderiza/verifica el PDF, guarda páginas y
reporta avances. No ejecutar OMR completo dentro de una petición HTTP.

## Modelo de trabajo para varios capturistas

1. Administrador crea una evaluación, configura Normal o Ecológico,
   importa lista opcional, genera aplicaciones/folios/QR y imprime.
2. El servidor recibe un PDF, lo archiva íntegro (SHA), inspecciona cada
   QR+HMAC y distribuye páginas a su aplicación. QR ilegible: bandeja
   pendiente, SIN calificar.
3. El motor califica automáticamente respuestas inequívocas y crea
   tareas solo para marcas múltiples, tenues, conflictos y capturas
   manuales. La clasificación automática NO elimina el original.
4. Una **cola de revisión** asigna hojas a capturistas según permiso.
   Reclamar hoja crea un \`lease\` atómico con expiración y \`revision\`.
   Otros usuarios la ven como **En revisión por otro capturista**;
   no pueden guardar sobre ella sin permiso.
5. Al guardar, API exige \`expected_revision\` y \`lease_id\`, dentro
   de una transacción corta; ante colisión devuelve HTTP 409 y no
   sobrescribe cambios. Guardar decisión por reactivo, usuario, momento,
   evidencia y motivo, nunca solo el resultado final.
6. Si el capturista cierra el navegador, el lease caduca; el trabajo
   vuelve a la cola sin perder decisiones ya confirmadas.
7. El coordinador puede reasignar hojas, revisar discrepancias y
   aprobar la hoja definitiva. Exportaciones oficiales ignoran
   resultados en conflicto o sin aprobar.
8. Es posible asignar grupos de hojas de Cabos/Checadores a distintos
   capturistas al mismo tiempo; la bandeja global no pierde páginas
   traspapeladas ni crea notas duplicadas.

**Unicidad obligatoria:** una calificación efectiva por
\`(aplicacion_id, folio)\`; conservar los reescaneos como evidencias y las
decisiones anteriores como eventos. Un mismo empleado podría tener folios
distintos en diferentes aplicaciones y NO es duplicado por nombre.

## Roles candidatos

| Rol | Facultades |
| --- | --- |
| Administrador | Usuarios, permisos, biblioteca y configuración |
| Coordinador | Aplicaciones asignadas, ingestión, distribución de trabajo, resolución de conflictos y aprobación |
| Capturista | Reclamar hojas autorizadas, revisar acetato y capturar decisiones; no editar claves ni emitir resultados finales |
| Auditor / consulta | Solo lectura de bitácora y evidencias de aplicaciones autorizadas |

Los permisos SIEMPRE se comprueban en la API, no solo ocultando botones.
No enviar HMAC, claves de respuestas, PDF ajenos, credenciales o rutas
privadas a usuarios no autorizados.

## Autenticación, red y privacidad

- Una cuenta por persona con contraseña temporal y rotación obligatoria;
  sesiones HttpOnly, SameSite y Secure sobre HTTPS; incluir CSRF en mutaciones.
- Acceso LAN privado o VPN, con TLS incluso si es Wi-Fi interna porque
  transmitirá exámenes y respuestas; no exponer el puerto a Internet.
- PDF privados accesibles por endpoint autenticado con permiso por aplicación
  y filtro por página. El PDF original mezclado solo para roles autorizados.
- Validar tamaño, número de páginas, tipo real, rutas y hashes; almacenar
  archivos por nombre opaco; no permitir upload por ruta arbitraria.
- Auditoría inmutable de accesos, correcciones, aprobaciones y exportaciones;
  respaldos consistentes con verificación de restauración.

## Contratos de API propuestos (por definir en OpenAPI)

- \`POST /api/auth/login\`, \`GET /api/auth/me\`, \`POST /api/auth/logout\`.
- \`GET/POST /api/cuestionarios\`, \`GET/POST /api/aplicaciones\`.
- \`POST /api/aplicaciones/{id}/generar\` (idempotente, nunca regenera folio sin intención).
- \`POST /api/escaneos\` (subir PDF), \`GET /api/trabajos/{id}\`.
- \`GET /api/revision/cola\`, \`POST /api/hojas/{id}/reclamar\`,
  \`POST /api/hojas/{id}/renovar\`, \`POST /api/hojas/{id}/liberar\`.
- \`GET /api/hojas/{id}\`, \`PUT /api/hojas/{id}/decisiones\`
  con \`expected_revision\`, \`lease_id\` e idempotencia.
- \`POST /api/hojas/{id}/aprobar\` (solo coordinador autorizado).
- \`GET /api/aplicaciones/{id}/resultados\`,
  \`POST /api/aplicaciones/{id}/exportar\`.
- \`GET /api/documentos\`, \`GET /api/documentos/{sha}/paginas/{n}\`
  (sin fuga de páginas ajenas).

## Plan de implementación por PRs pequeños

| Etapa | Cambio | Aceptación |
| --- | --- | --- |
| 0 | Congelar contratos actuales y pruebas OMR; snapshot de las dos BD | Golden tests y restauración OK |
| 1 | Encapsular servicio de biblioteca/QR/OMR/documentos sin Tk | Pytest igual al escritorio |
| 2 | Backend mínimo, sesiones de usuario, permisos y OpenAPI | API auth y denegación 401/403 |
| 3 | Ingestión y workers con progreso/recuperación | PDF mixto, duplicado y reinicio |
| 4 | Cola de capturistas con lease+revision | 2 usuarios no pisan el mismo folio |
| 5 | React UI: dos áreas, biblioteca, PDF/acetato, revisión móvil | Playwright en PC/móvil |
| 6 | Expedientes, exportaciones y auditoría por usuario | ZIP privado y una nota efectiva |
| 7 | Pruebas multiusuario, instalación LAN/HTTPS y aceptación física | Cero hojas perdidas, restore OK |

No delegar "migrar toda la app" a un único agente. Coordinar
tareas independientes con límites de archivos y contratos.

## Matriz de pruebas para Claude + CI

- Comparar PDF y SHA generados por Tk y API para la misma configuración
  (comparar contenido semántico/geométrico cuando los metadatos varíen).
- QR de otras aplicaciones dentro del mismo PDF; página sin QR; mismo
  folio en otro lote; folio con respuestas diferentes; HMAC inválido.
- Concurrencia: 2 capturistas reclaman la misma hoja simultáneamente
  (solo 1 éxito); otros 10 reclaman 100 hojas sin repetir.
- Dos revisores guardan con misma revision: 1 acepta y 1 recibe 409;
  bitácora registra solo cambios confirmados.
- Abandono de capturista: recuperar lease vencido y retomar sin perder
  decisiones ya guardadas.
- Reiniciar backend/worker a mitad de PDF de 100 páginas: al restaurar,
  lote archivado y 100 páginas contabilizadas, cero resultados duplicados.
- Autorización: capturista de Cabos no accede a PDF ni clave de Checadores,
  exportaciones de otra aplicación o endpoints de admin.
- Pruebas de interfaz con Playwright: escritorio, tablet, móvil;
  lector/acétato lado a lado en PC y modo adaptable en móvil.
- Restauración real y cálculo de hashes antes/después de la migración.
- Pruebas físicas con Xerox y lápiz n.º 2 siguen obligatorias.
- Control de carga: medir 100, 500, 1000 páginas y 2, 5, 10 capturistas
  sin afirmar escalabilidad hasta documentar tiempos y memoria.

**Claude** puede ayudar como revisor y generador de pruebas/PRs sobre
esta rama, si dispone de acceso al repositorio y entorno de pruebas.
No se considera aceptado nada solo por afirmar que pasó: cada tanda
debe adjuntar pruebas reproducibles, resultado CI, commit SHA,
y un registro de limitaciones. Codex y Claude no editarán simultáneamente
el mismo módulo sin coordinación. No publicar bases ni PDF privados.

## Decisiones que aún requieren aprobación

- Stack frontend final (React/TS recomendado frente a HTML/JS ligero).
- Número aproximado de capturistas y si se operará exclusivamente en Wi-Fi local.
- Política de aprobación final: coordinador por hoja o por lote;
  revisión doble de dudas cuando la evaluación lo exija.
- Política de evidencia/retención y recuperación de datos históricos.

**Estado de esta rama al crear el documento:** diseño y aislamiento
completados; la migración del código y las pruebas del nuevo frontend
**aún no comenzaron**. Ningún PR de la versión estable fue fusionado.
