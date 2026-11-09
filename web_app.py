"""Interfaz web local opcional para ejecutar el generador desde Docker.

Solo lista archivos de /datos/entradas y del ejemplo incluido. No recibe
archivos arbitrarios por HTTP ni envía información a servicios externos.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import parse_qs, quote, unquote, urlsplit
import os
import re

from src.evaluaciones.core import ExamError, MAX_BYTES, generate

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('EXAM_DATA_DIR', '/datos')).resolve()
INPUTS = DATA / 'entradas'
OUTPUTS = DATA / 'salidas'
EXAMPLES = ROOT / 'ejemplos'
PORT = int(os.environ.get('EXAM_PORT', '8765'))
TOKEN = token_urlsafe(32)
MAX_FORM_SIZE = 16 * 1024
DOWNLOADS = frozenset({
    'Cuadernillo.pdf', 'Hoja_respuestas.pdf', 'Acetato_clave.pdf',
    'Clave_docente.pdf', 'Preguntas_originales.xlsx', 'manifest.json',
})

CSS = """
:root{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;color:#17354a;background:#f2f6f9}
*{box-sizing:border-box}body{margin:0;min-height:100vh}.layout{display:grid;grid-template-columns:260px minmax(0,780px);gap:32px;justify-content:center;padding:30px}
aside{background:#17354a;color:white;border-radius:17px;padding:29px 24px;align-self:start;min-height:540px}
aside strong{font-size:24px}aside small{color:#c3e4e7}aside p{font-size:14px;line-height:1.55;color:#d1dce5}
main{background:white;border:1px solid #d9e3e9;border-radius:17px;box-shadow:0 8px 30px #17354a10;padding:29px 32px}
h1{font-size:26px;margin:0 0 9px}h2{font-size:18px;margin:25px 0 12px}.lead{color:#5a6c7a;line-height:1.55}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}label{display:block;font-size:13px;font-weight:650;margin:14px 0 6px}
input,select,textarea{display:block;width:100%;border:1px solid #cdd9e0;border-radius:8px;padding:11px;color:#14364b;background:#fff;font:inherit}
textarea{min-height:90px;resize:vertical}.btn{display:inline-block;background:#087f89;color:white;text-decoration:none;border:0;border-radius:9px;padding:12px 19px;font-size:15px;font-weight:700;cursor:pointer;margin-top:18px}
.ghost{background:#e9f1f5;color:#17354a}.hint{font-size:12px;color:#607485;line-height:1.6}.notice{background:#e7f6f5;border-left:4px solid #087f89;padding:14px;margin:18px 0}.error{background:#fff1ef;border-left-color:#b13424}
code{background:#edf3f5;padding:3px 5px;border-radius:4px}ul{line-height:1.9}a{color:#087685} .links a{display:inline-block;margin:3px 10px 6px 0}
footer{font-size:11px;color:#6d7d89;margin-top:18px}.muted{color:#627888}
@media(max-width:850px){.layout{display:block;padding:14px}aside{min-height:auto;margin-bottom:12px}main{padding:20px}.grid{grid-template-columns:1fr}}
"""


def _is_regular(path: Path, root: Path) -> bool:
    """Reject symlinks, including a symlink on the path between root and file."""
    try:
        if path.is_symlink() or not path.is_file() or root.is_symlink():
            return False
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root.resolve(strict=True)):
            return False
        relative = path.relative_to(root)
        parent = root
        for piece in relative.parts[:-1]:
            parent = parent / piece
            if parent.is_symlink():
                return False
        return True
    except (OSError, ValueError):
        return False


def available_exam_files():
    """Identifier is only an index into this server-created list; never a user path."""
    files = []
    for root, tag in ((INPUTS, 'Mis exámenes'), (EXAMPLES, 'Ejemplo incluido')):
        if not root.is_dir() or root.is_symlink():
            continue
        for f in sorted(root.glob('*.xlsx'), key=lambda p: p.name.casefold()):
            if _is_regular(f, root) and f.stat().st_size <= MAX_BYTES:
                files.append((f, f'{tag} · {f.name}'))
    return files


def available_logos():
    files = [(None, 'Sin logotipo')]
    for root, tag in ((INPUTS, 'Mis recursos'), (INPUTS / 'imagenes', 'Imágenes propias'),
                      (EXAMPLES / 'imagenes', 'Ejemplo incluido')):
        if not root.is_dir() or root.is_symlink():
            continue
        for f in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            if f.suffix.lower() in ('.png', '.jpg', '.jpeg') and _is_regular(f, root) and f.stat().st_size <= 4*1024*1024:
                files.append((f, f'{tag} · {f.name}'))
    return files


def _page(body: str, title='Generador de evaluaciones') -> bytes:
    return (f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(title)}</title><style>{CSS}</style></head><body>'
            f'<div class="layout"><aside><small>EVALUACIONES</small><h2>Diseña, imprime<br>y evalúa.</h2>'
            f'<p>01 · Datos institucionales</p><p>02 · Preguntas desde Excel</p>'
            f'<p>03 · Cuadernillo, hoja y acetato</p>'
            f'<p>Sin cuentas, sin subir datos a Internet y sin instalar Python en Windows.</p>'
            f'</aside><main>{body}<footer>Herramienta local · Uso privado · Licencia MIT · '
            f'Para imprimir las hojas y el acetato usa escala 100 %.</footer></main></div></body></html>').encode('utf-8')


def _options(items) -> str:
    return ''.join(f'<option value="{i}">{escape(label)}</option>' for i, (_, label) in enumerate(items))


def _form() -> bytes:
    files = available_exam_files()
    logos = available_logos()
    if not files:
        return _page('<h1>Falta la plantilla de ejemplo</h1><p>Revisa la construcción de la imagen Docker.</p>')
    body = f'''<h1>Preparar evaluación</h1>
    <p class="lead">Un examen fijo, diseñado en Excel. Generaremos cuatro PDF listos para imprimir.</p>
    <div class="notice">Coloca tus archivos <b>.xlsx</b> en <code>datos/entradas</code> de tu computadora.
    Las imágenes de preguntas se guardan en <code>datos/entradas/imagenes</code> con el nombre indicado en el Excel.</div>
    <form action="/generar" method="post" accept-charset="utf-8">
    <input type="hidden" name="token" value="{TOKEN}">
    <div class="grid"><div><label>Empresa / encabezado</label><input name="empresa" maxlength="100" placeholder="Nombre de empresa"></div>
    <div><label>Área, público o grupo (libre)</label><input name="puesto" maxlength="85" placeholder="Ej. Alumnos, personal técnico, proveedores"></div></div>
    <label>Título de la evaluación</label><input name="titulo" maxlength="90" required value="Evaluación de conocimientos">
    <label>Subtítulo</label><input name="subtitulo" maxlength="90" required value="Aplicación práctica de conocimientos">
    <label>Excel de preguntas</label><select name="archivo">{_options(files)}</select>
    <label>Logotipo (opcional)</label><select name="logo">{_options(logos)}</select>
    <label>Instrucciones al participante</label>
    <textarea name="instrucciones" maxlength="650">Lee cada pregunta y elige una sola opción. Marca las respuestas únicamente en la hoja separada.</textarea>
    <button type="submit" class="btn">Generar documentos</button>
    </form>
    <h2>Antes de empezar</h2><p class="hint">La hoja del Excel se llama <b>Preguntas</b>. Columnas:
    Tema, Pregunta, A, B, C, D, Correcta, Imagen (opcional). Mantén los encabezados y no introduzcas fórmulas.
    El archivo de ejemplo ya está incluido en el menú.</p>
    <p class="hint">Los resultados se guardan automáticamente en <code>datos/salidas</code> de tu computadora;
    no se sobrescriben exámenes anteriores.</p>'''
    return _page(body)


def _result(folder: Path) -> bytes:
    name = escape(folder.name)
    links = ''.join(f'<a href="/descargar/{quote(folder.name)}/{quote(f)}">{escape(f)}</a>'
                    for f in ('Cuadernillo.pdf', 'Hoja_respuestas.pdf', 'Acetato_clave.pdf', 'Clave_docente.pdf'))
    return _page(f'<h1>Documentos generados</h1><div class="notice">'
                 f'Se guardó una copia completa en <code>datos/salidas/{name}</code>.</div>'
                 f'<div class="links">{links}</div>'
                 '<p class="hint">El acetato y la hoja comparten coordenadas, pero antes de evaluar '
                 'a personal debes comprobar físicamente una impresión al 100 %.</p>'
                 '<a class="btn ghost" href="/">Preparar otro examen</a>')


class Handler(BaseHTTPRequestHandler):
    server_version = 'ExamenesLocales/1.0'

    def _respond(self, code: int, content: bytes, *, kind='text/html; charset=utf-8', extra=None):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(content)

    def _safe_host(self) -> bool:
        return self.headers.get('Host', '') in (f'localhost:{PORT}', f'127.0.0.1:{PORT}')

    def do_GET(self):
        if not self._safe_host():
            self._respond(HTTPStatus.FORBIDDEN, b'Host no permitido', kind='text/plain; charset=utf-8')
            return
        path = urlsplit(self.path).path
        if path == '/':
            self._respond(HTTPStatus.OK, _form())
        elif path == '/salud':
            self._respond(HTTPStatus.OK, b'OK', kind='text/plain; charset=utf-8')
        elif path.startswith('/descargar/'):
            self._download(path)
        else:
            self._respond(HTTPStatus.NOT_FOUND, _page('<h1>Página no encontrada</h1>'))

    def _download(self, route: str):
        parts = route.split('/')
        if len(parts) != 4 or parts[0] or parts[1] != 'descargar':
            self._respond(HTTPStatus.NOT_FOUND, b'No encontrado', kind='text/plain')
            return
        folder, name = unquote(parts[2]), unquote(parts[3])
        if not re.fullmatch(r'[a-z0-9_-]{5,150}', folder) or name not in DOWNLOADS:
            self._respond(HTTPStatus.NOT_FOUND, b'No encontrado', kind='text/plain')
            return
        dest = OUTPUTS / folder / name
        if not _is_regular(dest, OUTPUTS):
            self._respond(HTTPStatus.NOT_FOUND, b'No encontrado', kind='text/plain')
            return
        if dest.stat().st_size > 24 * 1024 * 1024:
            self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, b'Archivo demasiado grande para navegador; utiliza la carpeta local.', kind='text/plain')
            return
        self._respond(HTTPStatus.OK, dest.read_bytes(), kind=('application/pdf' if name.endswith('.pdf') else
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if name.endswith('.xlsx') else 'application/json'),
                    extra={'Content-Disposition': f'attachment; filename="{name}"'})

    def do_POST(self):
        if not self._safe_host() or urlsplit(self.path).path != '/generar':
            self._respond(HTTPStatus.FORBIDDEN, b'No permitido', kind='text/plain')
            return
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/x-www-form-urlencoded':
            self._respond(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, _page('<h1>Formato de formulario no permitido</h1>'))
            return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_FORM_SIZE:
            self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, _page('<h1>Solicitud demasiado grande</h1>'))
            return
        try:
            fields = parse_qs(self.rfile.read(length).decode('utf-8'), keep_blank_values=True,
                              strict_parsing=True, max_num_fields=12)
            def field(name):
                vals = fields.get(name, [''])
                if len(vals) != 1:
                    raise ValueError('Campo duplicado.')
                return vals[0]
            if field('token') != TOKEN:
                self._respond(HTTPStatus.FORBIDDEN, _page('<h1>Formulario no autorizado</h1>'))
                return
            files, logos = available_exam_files(), available_logos()
            def choose(name, options):
                v = field(name)
                if not v.isdecimal() or len(v) > 3:
                    raise ValueError('Selecciona una opción disponible.')
                i = int(v)
                if i >= len(options):
                    raise ValueError('Selección fuera de rango.')
                return options[i][0]
            exam = choose('archivo', files)
            logo = choose('logo', logos)
            titulo, subtitulo = field('titulo'), field('subtitulo')
            empresa, puesto, instrucciones = field('empresa'), field('puesto'), field('instrucciones')
            if max(map(len, (titulo, subtitulo, empresa, puesto, instrucciones))) > 650:
                raise ValueError('Texto demasiado largo.')
            OUTPUTS.mkdir(parents=True, exist_ok=True)
            folder = generate(exam, OUTPUTS, titulo, subtitulo, empresa=empresa,
                              puesto=puesto, instrucciones=instrucciones, logo=logo)
            self._respond(HTTPStatus.OK, _result(folder))
        except (ExamError, OSError, ValueError, UnicodeError) as exc:
            msg = escape(str(exc))
            self._respond(HTTPStatus.BAD_REQUEST, _page(
                f'<h1>No se pudo generar</h1><div class="notice error">{msg}</div>'
                '<a href="/">Volver al formulario</a>'))


def main():
    if not (1 <= PORT <= 65535):
        raise SystemExit('Puerto inválido')
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Generador local listo: http://localhost:{PORT}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
