# Instalar con Docker y aprender Git (Windows y Linux)

Este proyecto genera un **cuadernillo PDF**, una **hoja de respuestas**, una **clave docente** y una **plantilla de acetato**. No requiere instalar Python ni bibliotecas en el sistema anfitrión: todo se ejecuta dentro de Docker.

## Antes de empezar

En Windows 10/11 necesitas:

- **Git para Windows:** <https://git-scm.com/downloads/win>.
- **Docker Desktop:** <https://docs.docker.com/desktop/setup/install/windows-install/>. Debe estar **abierto** y con el motor Linux iniciado. Docker Desktop suele usar WSL 2; sigue sus instrucciones si te pide activarlo.
- Un navegador web y conexión a Internet solo durante la primera descarga/construcción. **No necesitas Python, pip, Java ni LibreOffice.**

En Linux necesitas Git, Docker Engine y el plugin de `docker compose`. Para ejecutar Docker sin `sudo`, debes configurar permisos del daemon conforme a las instrucciones oficiales; eso da privilegios elevados y conviene evaluarlo con cuidado.

## 1. Comprobar herramientas

Abre PowerShell (Windows) o Terminal (Linux):

```powershell
git --version
docker --version
docker compose version
docker info
```

- `git --version` dice si Git está disponible.
- `docker --version` muestra el cliente Docker.
- `docker compose version` verifica el plugin de Compose.
- **`docker info` comprueba que el MOTOR está ejecutándose**. Si falla en Windows, abre Docker Desktop y confirma que haya iniciado.

## 2. Descargar el repositorio (solo una vez)

Desde PowerShell en Windows:

```powershell
New-Item -ItemType Directory -Force "$HOME\Documents\Herramientas"
cd "$HOME\Documents\Herramientas"
git clone https://github.com/francisco-oos/Exam-PDF-Generator.git
cd Exam-PDF-Generator
git status
git branch --show-current
```

Explicación:

- `mkdir`/`New-Item` crea una carpeta para proyectos.
- `cd` cambia de carpeta.
- `git clone` descarga el repositorio y su historial. por defecto descarga la rama estable `main`, que reúne la interfaz empresarial y Docker.
- `git status` muestra si hay cambios locales; debe indicar *working tree clean*.
- `git branch --show-current` confirma la rama activa.

Si ya tienes `Exam-PDF-Generator` clonado, **no vuelvas a ejecutar `git clone` dentro de la misma carpeta**. Desde su carpeta usa:

```powershell
git fetch origin main:refs/remotes/origin/main
git switch -c main --track origin/main
```

Si tu rama local `main` ya existe, utiliza `git switch main`; si deseas conservar modificaciones locales, revisa antes `git status` y no las descartes.

## 3. Construir el contenedor y ejecutarlo

Con Docker Desktop abierto, desde la carpeta del repositorio:

```powershell
docker compose up --build -d
docker compose ps
```

- `docker compose up` crea y pone a funcionar el servicio definido en `compose.yaml`.
- `--build` construye la imagen a partir del `Dockerfile`, con Python y las bibliotecas **dentro del contenedor**.
- `-d` lo deja ejecutándose, sin ocupar la terminal.
- `docker compose ps` comprueba el estado; busca `running` y, después del arranque, `healthy`.

Abre **<http://localhost:8765>** en tu navegador. El servicio solo se publica en `127.0.0.1` (tu computadora), no en la red local. No lo abras a Internet.

## 4. Preparar el examen

En el Explorador de Windows abre `Exam-PDF-Generator\datos\entradas`. Ahí puedes colocar tus hojas `Mi_Examen.xlsx`.

La plantilla Excel incluye la hoja `Preguntas` y estas columnas:

| Tema | Pregunta | A | B | C | D | Correcta | Imagen (opcional) |
|---|---|---|---|---|---|---|---|

La respuesta correcta se escribe como **A**, **B**, **C** o **D**. Las imágenes opcionales de preguntas deben ser PNG o JPG y quedar en `datos\entradas\imagenes`, usando solo su **nombre de archivo** en la columna `Imagen`. Los logotipos también pueden colocarse en `datos\entradas\imagenes` y se eligen en la pantalla web.

Hay un **examen de ejemplo incluido**, disponible desde el selector sin copiar nada. Los datos y números de serie de ejemplo son ficticios.

En el navegador, elige el Excel, título, empresa, puesto, instrucciones y logotipo opcional. Pulsa **Generar documentos**. Los PDF se descargan desde los enlaces en pantalla y quedan archivados en `datos\salidas\<carpeta_del_examen>`. Cada generación usa una carpeta nueva y conserva el Excel original y los recursos empleados.

**Al imprimir** la hoja de respuestas y la plantilla para acetato, usa tamaño **A4** y escala **100 %**, sin «Ajustar a página». Comprueba la alineación física antes de evaluar al personal.

## 5. Comandos cotidianos

```powershell
docker compose ps                  # Estado del contenedor
docker compose logs --tail 80      # Ver mensajes recientes
docker compose stop                # Detener sin borrar archivos
docker compose start               # Volver a iniciar
docker compose down                # Retirar el contenedor, conservar datos
docker compose up --build -d       # Reconstruir tras actualizar el código
```

**Tus datos viven en `datos/`**, en el disco del anfitrión; `docker compose down` no los borra. No uses `git clean -fdx` ni elimines manualmente `datos/` si contiene exámenes importantes.

## 6. Aprender a actualizar con Git

Desde la carpeta del proyecto:

```powershell
git status
git log -5 --oneline
git pull --ff-only
docker compose up --build -d
```

- `git status`: cambios locales y rama activa.
- `git log -5 --oneline`: cinco commits recientes; un commit es un registro de cambios con identificador.
- `git pull --ff-only`: descarga e integra actualizaciones **sin crear una fusión automática**. Si tienes cambios que chocan, se detiene para revisarlos.
- `docker compose up --build -d`: reconstruye para incorporar el código nuevo.

Para ver diferencias antes de actualizar: `git fetch origin` y `git log --oneline HEAD..origin/main`.

## 7. Linux: ruta equivalente

```bash
mkdir -p ~/Herramientas
cd ~/Herramientas
git clone https://github.com/francisco-oos/Exam-PDF-Generator.git
cd Exam-PDF-Generator
# Si tu usuario no tiene UID/GID 1000, indica los suyos al contenedor:
HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose up --build -d
```

Abre <http://localhost:8765>. Si el UID/GID no es 1000, exporta esas variables en el mismo terminal para `docker compose` (o escribe los valores en un archivo `.env` local). Los archivos se guardarán con los permisos de tu usuario anfitrión.

## 8. Solución de problemas

| Mensaje / situación | Qué revisar |
|---|---|
| `docker: command not found` | Instalar Docker Desktop y abrir una terminal nueva. |
| `Cannot connect to the Docker daemon` | Abrir Docker Desktop; esperar a que inicie Linux containers. |
| Puerto 8765 ocupado | Detener la aplicación que lo usa o cambiar el puerto **del lado izquierdo** en `compose.yaml` y el navegador. |
| Error al escribir `datos/salidas` | Permisos del directorio; en Linux pasar `HOST_UID` y `HOST_GID`. |
| No aparece tu Excel | Copia un `.xlsx` válido directamente a `datos/entradas`, refresca la página. No es suficiente que esté en Descargas. |
| Imagen no encontrada | Copia el PNG/JPG a `datos/entradas/imagenes` y escribe solo el nombre en Excel. |
| El acetato no coincide | Reimprime ambas hojas A4 al 100 %, sin escalado. No uses claves de otros exámenes. |
| Error al arrancar | `docker compose logs --tail 80` y revisar el mensaje. |

## 9. Seguridad y límites

- La web se publica únicamente en `127.0.0.1:8765` y requiere un token de formulario contra envíos involuntarios desde otras páginas.
- No permite subir archivos por HTTP: los Excel e imágenes se copian localmente a `datos/entradas`.
- El servicio no tiene permisos de administrador en el contenedor; el sistema de archivos es de solo lectura excepto `/tmp` y el volumen de trabajo.
- El contenedor tiene acceso a Internet por defecto a nivel de Docker para posibles necesidades administrativas. La aplicación no hace solicitudes de red externas; si necesitas aislamiento estricto, se puede añadir una política de red en otra revisión.
- **No expongas el puerto al exterior**, ni montes otras carpetas personales o empresariales dentro del contenedor.
- Solo se ha probado automáticamente el generador en Windows y Linux; el modo Docker se someterá a CI y la impresión física sigue pendiente.
