"""Biblioteca local de cuestionarios reutilizables en SQLite.

La base es la fuente persistente: almacena identidad, preguntas, claves y
recursos de imagen como BLOB. Para usar el motor PDF se materializa una
plantilla temporal, sin depender de la ruta de importación original.
No contiene servidor ni sincronización remota.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import json
import re
import sqlite3

from openpyxl import Workbook

from src.evaluaciones.core import ExamError, Question, _safe_image, read_questions

DEFAULT_COLOR_TITLE = '#213A4C'
DEFAULT_COLOR_SUBTITLE = '#5E7180'
COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


def hex_color(value: str, label: str = 'Color') -> str:
    if not isinstance(value, str) or not COLOR_RE.fullmatch(value):
        raise ExamError(f'{label}: usa un color RGB hexadecimal como #123ABC.')
    return value.upper()


def db_connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=10000')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS cuestionarios (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            empresa TEXT NOT NULL DEFAULT '',
            grupo TEXT NOT NULL DEFAULT '',
            titulo TEXT NOT NULL,
            subtitulo TEXT NOT NULL DEFAULT '',
            instrucciones TEXT NOT NULL DEFAULT '',
            color_titulo TEXT NOT NULL,
            color_subtitulo TEXT NOT NULL,
            preguntas_json TEXT NOT NULL,
            logo_archivo TEXT,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS recursos (
            cuestionario_id TEXT NOT NULL,
            nombre TEXT NOT NULL,
            contenido BLOB NOT NULL,
            sha256 TEXT NOT NULL,
            PRIMARY KEY (cuestionario_id, nombre),
            FOREIGN KEY (cuestionario_id) REFERENCES cuestionarios(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_cuestionarios_actualizado
            ON cuestionarios(actualizado_en DESC);
    ''')
    return conn


@dataclass(frozen=True)
class StoredExam:
    id: str
    nombre: str
    empresa: str
    grupo: str
    titulo: str
    subtitulo: str
    instrucciones: str
    color_titulo: str
    color_subtitulo: str
    questions: tuple[Question, ...]
    logo: Path | None
    revision: int


def _check_questions(questions: list[Question] | tuple[Question, ...]):
    if not 1 <= len(questions) <= 100:
        raise ExamError('La biblioteca admite entre 1 y 100 preguntas.')
    for i, q in enumerate(questions, 1):
        if not q.section.strip() or len(q.section) > 90:
            raise ExamError(f'Pregunta {i}: tema vacío o demasiado largo.')
        if not q.prompt.strip() or len(q.prompt) > 650:
            raise ExamError(f'Pregunta {i}: enunciado vacío o demasiado largo.')
        if len(q.options) != 4 or any(not o.strip() or len(o) > 300 for o in q.options):
            raise ExamError(f'Pregunta {i}: necesitas cuatro respuestas completas.')
        if len({o.strip().casefold() for o in q.options}) != 4:
            raise ExamError(f'Pregunta {i}: las respuestas deben ser distintas.')
        if q.correct not in (0,1,2,3):
            raise ExamError(f'Pregunta {i}: respuesta correcta inválida.')


def _metadata(nombre: str, titulo: str, empresa: str, grupo: str, subtitulo: str,
              instrucciones: str, color_titulo: str, color_subtitulo: str):
    values = ((nombre, 'Nombre', 120), (titulo, 'Título', 90),
              (empresa, 'Empresa', 100), (grupo, 'Área/grupo', 85),
              (subtitulo, 'Subtítulo', 90), (instrucciones, 'Instrucciones', 650))
    for value, label, limit in values:
        if not isinstance(value,str) or len(value.strip()) > limit:
            raise ExamError(f'{label}: texto inválido o excede {limit} caracteres.')
    if not nombre.strip() or not titulo.strip():
        raise ExamError('El nombre en la biblioteca y el título son obligatorios.')
    return hex_color(color_titulo,'Color del título'), hex_color(color_subtitulo,'Color del subtítulo')


def save_exam(db_path: Path, *, nombre: str, empresa: str, grupo: str, titulo: str,
              subtitulo: str, instrucciones: str, questions: list[Question] | tuple[Question,...],
              color_titulo: str = DEFAULT_COLOR_TITLE,
              color_subtitulo: str = DEFAULT_COLOR_SUBTITLE,
              logo: Path | None = None, exam_id: str | None = None) -> str:
    """Guarda o actualiza por ID, conservando la misma identidad y aumentando revisión."""
    color_titulo, color_subtitulo = _metadata(nombre,titulo,empresa,grupo,subtitulo,
                                                instrucciones,color_titulo,color_subtitulo)
    questions=tuple(questions)
    _check_questions(questions)
    if exam_id is not None and not re.fullmatch(r'[0-9a-f]{32}',exam_id):
        raise ExamError('ID de biblioteca inválido.')
    exam_id = exam_id or uuid4().hex
    resources: dict[str, bytes] = {}
    serial=[]
    for number, q in enumerate(questions,1):
        image_name = None
        if q.image is not None:
            path=_safe_image(Path(q.image),source=f'Pregunta {number}/Imagen')
            image_name=f'pregunta_{number:03d}{path.suffix.lower()}'
            resources[image_name]=path.read_bytes()
        serial.append({'tema':q.section,'pregunta':q.prompt,'opciones':list(q.options),
                       'correcta':'ABCD'[q.correct],'imagen':image_name})
    logo_name=None
    if logo:
        safe_logo=_safe_image(Path(logo),source='Logotipo')
        logo_name='logo'+safe_logo.suffix.lower()
        resources[logo_name]=safe_logo.read_bytes()
    now=datetime.now(timezone.utc).isoformat()
    with db_connect(db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        old=conn.execute('SELECT creado_en,revision FROM cuestionarios WHERE id=?',(exam_id,)).fetchone()
        version=int(old['revision'])+1 if old else 1
        created=old['creado_en'] if old else now
        conn.execute('''INSERT INTO cuestionarios
          (id,nombre,empresa,grupo,titulo,subtitulo,instrucciones,color_titulo,color_subtitulo,
           preguntas_json,logo_archivo,creado_en,actualizado_en,revision)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET
          nombre=excluded.nombre,empresa=excluded.empresa,grupo=excluded.grupo,
          titulo=excluded.titulo,subtitulo=excluded.subtitulo,instrucciones=excluded.instrucciones,
          color_titulo=excluded.color_titulo,color_subtitulo=excluded.color_subtitulo,
          preguntas_json=excluded.preguntas_json,logo_archivo=excluded.logo_archivo,
          actualizado_en=excluded.actualizado_en,revision=excluded.revision''',
            (exam_id,nombre.strip(),empresa.strip(),grupo.strip(),titulo.strip(),subtitulo.strip(),
             instrucciones.strip(),color_titulo,color_subtitulo,json.dumps(serial,ensure_ascii=False),
             logo_name,created,now,version))
        conn.execute('DELETE FROM recursos WHERE cuestionario_id=?',(exam_id,))
        conn.executemany('INSERT INTO recursos(cuestionario_id,nombre,contenido,sha256) VALUES (?,?,?,?)',
              [(exam_id,name,blob,sha256(blob).hexdigest()) for name,blob in resources.items()])
    return exam_id


def list_exams(db_path: Path) -> list[dict]:
    with db_connect(db_path) as conn:
        rows=conn.execute('''SELECT id,nombre,grupo,titulo,actualizado_en,revision,
                              json_array_length(preguntas_json) AS total
                              FROM cuestionarios ORDER BY actualizado_en DESC, nombre''').fetchall()
        return [dict(r) for r in rows]


def delete_exam(db_path: Path, exam_id: str):
    with db_connect(db_path) as conn:
        conn.execute('DELETE FROM cuestionarios WHERE id=?',(exam_id,))


def _resources(conn,exam_id):
    return {row['nombre']:(bytes(row['contenido']),row['sha256'])
            for row in conn.execute('SELECT nombre,contenido,sha256 FROM recursos WHERE cuestionario_id=?',(exam_id,))}


def load_exam(db_path: Path, exam_id: str, workdir: Path) -> StoredExam:
    """Materializa en una carpeta aislada, también las imágenes BLOB originales."""
    with db_connect(db_path) as conn:
        row=conn.execute('SELECT * FROM cuestionarios WHERE id=?',(exam_id,)).fetchone()
        if row is None:
            raise ExamError('No se encontró el cuestionario guardado.')
        items=json.loads(row['preguntas_json'])
        resources=_resources(conn,exam_id)
    folder=Path(workdir)/exam_id
    folder.mkdir(parents=True,exist_ok=True)
    images_dir=folder/'imagenes'
    images_dir.mkdir(exist_ok=True)
    def restore(name: str, subdir: Path) -> Path:
        if name not in resources or '/' in name or '\\' in name or Path(name).name!=name:
            raise ExamError('La biblioteca tiene un recurso de imagen inválido.')
        data,digest=resources[name]
        if sha256(data).hexdigest()!=digest:
            raise ExamError('Error de integridad en las imágenes guardadas.')
        path=subdir/name
        path.write_bytes(data)
        _safe_image(path,source='Recurso de biblioteca')
        return path
    questions=[]
    for d in items:
        photo=restore(d['imagen'],images_dir) if d['imagen'] else None
        questions.append(Question(d['tema'],d['pregunta'],tuple(d['opciones']),
                                  'ABCD'.index(d['correcta']),photo))
    logo=restore(row['logo_archivo'],folder) if row['logo_archivo'] else None
    return StoredExam(id=row['id'],nombre=row['nombre'],empresa=row['empresa'],grupo=row['grupo'],
       titulo=row['titulo'],subtitulo=row['subtitulo'],instrucciones=row['instrucciones'],
       color_titulo=row['color_titulo'],color_subtitulo=row['color_subtitulo'],
       questions=tuple(questions),logo=logo,revision=row['revision'])


def export_workbook(questions: list[Question] | tuple[Question,...], target: Path) -> Path:
    """Exporta una copia editable que entiende el motor y protege las fuentes originales."""
    questions=tuple(questions)
    _check_questions(questions)
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    folder=target.parent/'imagenes'
    folder.mkdir(parents=True,exist_ok=True)
    wb=Workbook()
    sheet=wb.active
    sheet.title='Preguntas'
    sheet.append(('Tema','Pregunta','A','B','C','D','Correcta','Imagen'))
    for no,q in enumerate(questions,1):
        image_name=''
        if q.image is not None:
            path=_safe_image(Path(q.image),source=f'Pregunta {no}/Imagen')
            image_name=f'pregunta_{no:03d}{path.suffix.lower()}'
            copy=folder/image_name
            if path.resolve()!=copy.resolve():
                copy.write_bytes(path.read_bytes())
        sheet.append((q.section,q.prompt,*q.options,'ABCD'[q.correct],image_name))
    for col,width in [('A',23),('B',55),('C',30),('D',30),('E',30),('F',30),('G',13),('H',26)]:
        sheet.column_dimensions[col].width=width
    wb.save(target)
    return target
