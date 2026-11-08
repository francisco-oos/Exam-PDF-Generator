"""Generación segura y determinista de exámenes impresos y acetatos (sin OMR).

Un solo lector XLSX (openpyxl) y un solo modelo geométrico para hoja + clave.
Ningún archivo de usuario se borra y las opciones no se reordenan.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from datetime import datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Iterable
from uuid import uuid4
import json
import math
import os
import re
import shutil
import unicodedata
from zipfile import ZipFile, BadZipFile

from openpyxl import load_workbook
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether, PageBreak, Image as PdfImage, Table, TableStyle
from reportlab.pdfgen.canvas import Canvas
from PIL import Image as PILImage, ImageOps, UnidentifiedImageError

HEADERS = ('Tema', 'Pregunta', 'A', 'B', 'C', 'D', 'Correcta')
IMAGE_HEADER = 'Imagen'
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
MAX_BYTES = 8 * 1024 * 1024
MAX_ZIP_EXPANDED = 35 * 1024 * 1024
MAX_QUESTIONS = 100
MAX_QUESTION_CHARS = 650
MAX_OPTION_CHARS = 300
PAGE_W, PAGE_H = A4
TINT = colors.HexColor('#213a4c')
MUTED = colors.HexColor('#5e7180')
RADIUS = 8.6


class ExamError(ValueError):
    """Examen inválido; mensaje seguro para usuario."""


@dataclass(frozen=True)
class Question:
    section: str
    prompt: str
    options: tuple[str, str, str, str]
    correct: int  # 0, 1, 2, 3
    image: Path | None = None  # Archivo opcional dentro de imagenes/ junto al XLSX


def _font():
    regular = None
    bold = None
    candidates = [
        (Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'arial.ttf',
         Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'arialbd.ttf'),
        (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
         Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')),
        (Path('/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf'),
         Path('/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf')),
    ]
    for normal, heavy in candidates:
        if normal.is_file() and heavy.is_file():
            regular, bold = normal, heavy
            break
    if regular:
        if 'ExamFont' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('ExamFont', str(regular)))
            pdfmetrics.registerFont(TTFont('ExamFontBold', str(bold)))
        return 'ExamFont', 'ExamFontBold'
    return 'Helvetica', 'Helvetica-Bold'


def _text(value: object, *, label: str, limit: int) -> str:
    if value is None:
        raise ExamError(f'{label}: valor obligatorio vacío.')
    if isinstance(value, bool):
        raise ExamError(f'{label}: no puede ser verdadero/falso.')
    value = str(value).strip()
    if not value:
        raise ExamError(f'{label}: valor obligatorio vacío.')
    if len(value) > limit:
        raise ExamError(f'{label}: excede {limit} caracteres.')
    if any(ord(c) < 32 and c not in '\t\n' for c in value):
        raise ExamError(f'{label}: contiene caracteres de control.')
    return value


def _inspect_archive(path: Path) -> None:
    try:
        with ZipFile(path, 'r') as archive:
            files = archive.infolist()
            if len(files) > 300:
                raise ExamError('XLSX con demasiados archivos internos.')
            total = 0
            for info in files:
                total += info.file_size
                if info.file_size > MAX_ZIP_EXPANDED or total > MAX_ZIP_EXPANDED:
                    raise ExamError('XLSX excede el tamaño descomprimido permitido.')
                if info.file_size > 1_000_000 and info.compress_size < 100 and info.file_size / max(info.compress_size, 1) > 200:
                    raise ExamError('XLSX tiene un patrón de compresión sospechoso.')
                lower = info.filename.lower()
                if 'vbaproject.bin' in lower or lower.startswith('xl/externallinks/'):
                    raise ExamError('No se permiten macros ni vínculos externos en la plantilla.')
    except (BadZipFile, OSError) as exc:
        raise ExamError('El archivo no es un XLSX válido.') from exc


def _safe_image(path: Path, *, source: str) -> Path:
    """Comprueba un recurso local (logo o imagen de pregunta), sin enlaces/URL."""
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ExamError(f'{source}: la imagen debe ser un archivo regular local, no un enlace.')
    if path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
        raise ExamError(f'{source}: solamente PNG o JPEG.')
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ExamError(f'{source}: imagen de más de 4 MB.')
    try:
        with PILImage.open(path) as img:
            if img.format not in ('PNG', 'JPEG'):
                raise ExamError(f'{source}: contenido distinto de PNG/JPEG.')
            if img.width * img.height > MAX_IMAGE_PIXELS or min(img.size) < 1:
                raise ExamError(f'{source}: dimensiones fuera de límite.')
            img.verify()
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ExamError(f'{source}: imagen ilegible o dañada.') from exc
    return path.resolve()


def _question_image(name: object, base: Path, row: int) -> Path | None:
    if name is None or str(name).strip() == '':
        return None
    name = _text(name, label=f'Fila {row}/Imagen', limit=160)
    # La carpeta autorizada está al lado del XLSX; nunca interpretar rutas arbitrarias.
    if name in ('.', '..') or '/' in name or chr(92) in name or ':' in name or Path(name).name != name:
        raise ExamError(f'Fila {row}/Imagen: escribe solo el nombre, sin carpetas ni rutas.')
    folder = base.parent / 'imagenes'
    if folder.is_symlink():
        raise ExamError(f'Fila {row}/Imagen: carpeta de imágenes no puede ser enlace.')
    return _safe_image(folder / name, source=f'Fila {row}/Imagen')


def _pdf_image(path: Path, max_width: float, max_height: float) -> PdfImage:
    """Desvincula el PDF del archivo original, normalizando EXIF y dimensiones."""
    with PILImage.open(path) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((1500, 1500), PILImage.Resampling.LANCZOS)
        w, h = im.size
        ratio = min(max_width / w, max_height / h)
        buf = BytesIO()
        im.save(buf, format='PNG', optimize=False)
    buf.seek(0)
    img = PdfImage(buf, width=w*ratio, height=h*ratio)
    img.hAlign='CENTER'
    return img


def read_questions(path: Path) -> list[Question]:
    path = Path(path).expanduser()
    if path.is_symlink():
        raise ExamError('No se permite una plantilla que sea un enlace simbólico.')
    if not path.is_file():
        raise ExamError('No se encuentra el archivo XLSX indicado.')
    if path.suffix.lower() != '.xlsx':
        raise ExamError('Se requiere archivo .xlsx (sin macros).')
    if path.stat().st_size > MAX_BYTES:
        raise ExamError('El XLSX supera 8 MB.')
    _inspect_archive(path)
    try:
        book = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    except Exception as exc:
        raise ExamError('No se pudo abrir el Excel. Comprueba que no esté dañado.') from exc
    try:
        if 'Preguntas' not in book.sheetnames:
            raise ExamError('Falta la hoja llamada "Preguntas".')
        sheet = book['Preguntas']
        if (sheet.max_row is not None and sheet.max_row > 300) or (sheet.max_column is not None and sheet.max_column > 8):
            raise ExamError('La hoja Preguntas tiene demasiadas filas o columnas; limpia el Excel y usa la plantilla.')
        rows = sheet.iter_rows(min_row=1, max_row=301, max_col=8)
        try:
            header = next(rows)
        except StopIteration:
            raise ExamError('El Excel está vacío.')
        seen_headers = tuple(str(c.value or '').strip() for c in header)
        if seen_headers[:7] != HEADERS or seen_headers[7] not in ('', IMAGE_HEADER):
            raise ExamError('Cabeceras incorrectas. Deben ser: '+', '.join(HEADERS)+', Imagen (opcional).')
        has_images = seen_headers[7] == IMAGE_HEADER
        questions = []
        has_blank_after_data = False
        for no, row in enumerate(rows, start=2):
            values = [cell.value for cell in row]
            if all(v is None or not str(v).strip() for v in values):
                has_blank_after_data = True
                continue
            if no > 300:
                raise ExamError('La hoja Preguntas tiene demasiadas filas.')
            if has_blank_after_data:
                raise ExamError(f'Fila {no}: no puede haber filas vacías entre preguntas.')
            if any(cell.data_type == 'f' for cell in row):
                raise ExamError(f'Fila {no}: no se permiten fórmulas.')
            if len(questions) >= MAX_QUESTIONS:
                raise ExamError(f'Máximo {MAX_QUESTIONS} preguntas.')
            topic = _text(values[0], label=f'Fila {no}/Tema', limit=90)
            prompt = _text(values[1], label=f'Fila {no}/Pregunta', limit=MAX_QUESTION_CHARS)
            opts = tuple(_text(v, label=f'Fila {no}/Opción {letter}', limit=MAX_OPTION_CHARS)
                         for letter, v in zip('ABCD', values[2:6]))
            if len({x.casefold() for x in opts}) != 4:
                raise ExamError(f'Fila {no}: las cuatro opciones deben ser distintas.')
            letter = _text(values[6], label=f'Fila {no}/Correcta', limit=1).upper()
            if letter not in 'ABCD':
                raise ExamError(f'Fila {no}: respuesta correcta debe ser A, B, C o D.')
            questions.append(Question(topic,prompt,opts,'ABCD'.index(letter),
                                      _question_image(values[7],path,no) if has_images else None))
        if not questions:
            raise ExamError('La plantilla no contiene preguntas.')
        return questions
    finally:
        book.close()


def _slug(text: str) -> str:
    value = unicodedata.normalize('NFKD', text)
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r'[^A-Za-z0-9_-]+','-',value).strip('-').lower()
    return value[:36] or 'examen'


def _canvas_header(c: Canvas, title: str, subtitle: str, label: str, normal: str, bold: str):
    c.setFillColor(TINT)
    c.setFont(bold,13)
    c.drawCentredString(PAGE_W/2,PAGE_H-74,label)
    c.setFont(normal,9)
    c.drawCentredString(PAGE_W/2,PAGE_H-93,title[:66])
    c.drawCentredString(PAGE_W/2,PAGE_H-108,subtitle[:74])


def _alignment(c: Canvas):
    c.setLineWidth(.75)
    c.setStrokeColor(TINT)
    for x,y in ((37,PAGE_H-38),(PAGE_W-37,PAGE_H-38),(37,37),(PAGE_W-37,37)):
        c.line(x-6,y,x+6,y)
        c.line(x,y-6,x,y+6)


def _bubbles(questions: list[Question]):
    """Yield (page index, question number, [(x,y),...]) for BOTH sheets."""
    rows = 10 if len(questions) <= 20 else 20
    per_page = 2*rows
    row_height = 36 if rows==10 else 23
    for index, q in enumerate(questions):
        offset = index % per_page
        col, row = divmod(offset,rows)
        start = 53 if col==0 else 312
        y = PAGE_H-235-row*row_height
        yield index//per_page, index+1, [(start+69+j*29,y) for j in range(4)]


def _answer_sheet(path: Path, questions: list[Question], title: str, subtitle: str, *, acetate: bool, normal: str, bold: str):
    c = Canvas(str(path), pagesize=A4,pageCompression=1)
    c.setTitle('Acetato de clave' if acetate else 'Hoja de respuestas')
    slots = list(_bubbles(questions))
    pages = math.ceil(len(questions)/(20 if len(questions)<=20 else 40))
    for page in range(pages):
        if not acetate:
            _canvas_header(c,title,subtitle,'HOJA DE RESPUESTAS',normal,bold)
            c.setFont(normal,9.3);c.drawString(49,PAGE_H-142,'Nombre: ___________________________________________')
            c.drawString(49,PAGE_H-162,'Fecha: _______________    Grupo/puesto: _______________')
            c.setFont(normal,8);c.setFillColor(MUTED)
            c.drawString(50,PAGE_H-192,'Marca una sola respuesta (A, B, C o D) en cada pregunta.')
        for current, number, coords in slots:
            if current!=page:continue
            y=coords[0][1]
            if not acetate:
                c.setFillColor(TINT);c.setFont(bold,9);c.drawRightString(coords[0][0]-22,y-3,str(number)+'.')
                for k,(x,yy) in enumerate(coords):
                    c.setStrokeColor(TINT);c.setLineWidth(1.1)
                    c.circle(x,yy,RADIUS,stroke=1,fill=0)
                    c.setFont(normal,7.4);c.drawCentredString(x,yy-RADIUS-12,'ABCD'[k])
            else:
                k=questions[number-1].correct;x,yy=coords[k]
                c.setStrokeColor(colors.HexColor('#167341'));c.setLineWidth(2.7)
                c.circle(x,yy,RADIUS+4.0,stroke=1,fill=0)
        _alignment(c)
        c.setFont(normal,7.2)
        c.setFillColor(MUTED if not acetate else TINT)
        c.drawCentredString(PAGE_W/2,22,
           ('CLAVE PARA ACETATO - SUPERPONER AL 100 % / SIN AJUSTAR' if acetate
            else 'Imprimir al 100 % / sin ajustar al papel')+f'  ·  Página {page+1}/{pages}')
        c.showPage()
    c.save()


def _exam_pdf(path: Path,questions: list[Question],title: str,subtitle: str,
              normal: str,bold: str, *, empresa: str = '', puesto: str = '',
              instrucciones: str = '', logo: Path | None = None):
    paper_width = PAGE_W - 94
    styles = {
        'eyebrow':ParagraphStyle('Eyebrow',fontName=bold,fontSize=8.7,leading=12,textColor=TINT,spaceAfter=5),
        'title':ParagraphStyle('ExTitle',fontName=bold,fontSize=17,leading=22,spaceAfter=4,textColor=TINT),
        'subtitle':ParagraphStyle('ExSub',fontName=normal,fontSize=10,leading=14,spaceAfter=7,textColor=MUTED),
        'section':ParagraphStyle('ExSect',fontName=bold,fontSize=10,leading=14,spaceBefore=14,spaceAfter=6,textColor=TINT,keepWithNext=True),
        'question':ParagraphStyle('ExQuestion',fontName=bold,fontSize=10,leading=14,spaceBefore=8,spaceAfter=5,textColor=TINT),
        'answer':ParagraphStyle('ExAnswer',fontName=normal,fontSize=9.2,leading=13,leftIndent=17,spaceAfter=3),
        'small':ParagraphStyle('ExSmall',fontName=normal,fontSize=8.5,leading=12,spaceAfter=6,textColor=MUTED),
        'instructions':ParagraphStyle('Instr',fontName=normal,fontSize=9,leading=13,spaceAfter=7,textColor=TINT),
    }
    head = [Paragraph('EVALUACIÓN DE CONOCIMIENTOS',styles['eyebrow']),
            Paragraph(escape(title),styles['title']),Paragraph(escape(subtitle),styles['subtitle'])]
    if empresa:
        head.insert(0,Paragraph(escape(empresa).upper(),styles['eyebrow']))
    if puesto:
        head.append(Paragraph('Puesto / área: '+escape(puesto),styles['small']))
    if logo:
        logopic = _pdf_image(logo,65,65)
        header_table=Table([[logopic,head]],colWidths=[85,paper_width-85])
    else:
        header_table=Table([[head]],colWidths=[paper_width])
    header_table.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LINEBELOW',(0,0),(-1,-1),1.2,colors.HexColor('#177B8E')),
        ('BOTTOMPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
    ]))
    story=[header_table,Spacer(1,13),
           Paragraph('Nombre: _________________________________________   Fecha: __________________',styles['small']),
           Paragraph('Número / folio: __________________________   Grupo / turno: __________________',styles['small'])]
    if not instrucciones:
        instrucciones='Lee cada reactivo. Marca UNA respuesta en la hoja separada. No escribas tus respuestas en el cuadernillo.'
    # Sin interpretación HTML del usuario; se aceptan instrucciones en texto plano.
    story += [Spacer(1,6),Paragraph('<b>INSTRUCCIONES</b>',styles['eyebrow']),
              Paragraph(escape(instrucciones).replace('\n','<br/>'),styles['instructions']),
              Paragraph(f'<b>{len(questions)} preguntas</b> · Cuatro opciones por pregunta · Una respuesta correcta.',styles['small'])]
    last_topic=None
    for index,q in enumerate(questions,1):
        if q.section!=last_topic:
            story.append(Paragraph(escape(q.section).upper(),styles['section']))
            last_topic=q.section
        block=[Paragraph(f'{index:02d}. {escape(q.prompt)}',styles['question'])]
        if q.image:
            block.append(Spacer(1,3))
            block.append(_pdf_image(q.image,300,175))
            block.append(Spacer(1,5))
        block.extend(Paragraph(f'{letter})  {escape(opt)}',styles['answer']) for letter,opt in zip('abcd',q.options))
        story.append(KeepTogether(block))
    def footer(c: Canvas, doc):
        c.saveState()
        c.setStrokeColor(colors.HexColor('#CEDDE4'));c.setLineWidth(.65)
        c.line(47,42,PAGE_W-47,42)
        c.setFillColor(MUTED);c.setFont(normal,7)
        c.drawString(47,29,(empresa[:55] if empresa else 'Evaluación de conocimientos'))
        c.drawRightString(PAGE_W-47,29,f'Cuadernillo · Página {doc.page} · Responder en hoja aparte')
        c.restoreState()
    SimpleDocTemplate(str(path),pagesize=A4,leftMargin=47,rightMargin=47,topMargin=42,bottomMargin=56,
                      title=title,author=(empresa or 'Generador local de exámenes')).build(
                      story,onFirstPage=footer,onLaterPages=footer)


def _key_pdf(path:Path,questions:list[Question],title:str,normal:str,bold:str, *, empresa:str='',puesto:str=''):
    styles={
        't':ParagraphStyle('KeyT',fontName=bold,fontSize=14,leading=18,spaceAfter=12),
        'k':ParagraphStyle('KeyQ',fontName=normal,fontSize=9.4,leading=15,spaceAfter=5),
        'c':ParagraphStyle('KeyC',fontName=normal,fontSize=9,leading=12,spaceAfter=12,textColor=MUTED),
    }
    story=[Paragraph('CLAVE DE CORRECCIÓN · '+escape(title),styles['t'])]
    if empresa or puesto:
        story.append(Paragraph(escape(' · '.join(filter(None,(empresa,puesto)))),styles['c']))
    for i,q in enumerate(questions,1):
        letter='ABCD'[q.correct]
        story.append(Paragraph(f'<b>{i:02d}. {letter}</b> — {escape(q.prompt)}',styles['k']))
        story.append(Paragraph('Correcta: '+escape(q.options[q.correct]),styles['c']))
    SimpleDocTemplate(str(path),pagesize=A4,leftMargin=52,rightMargin=52,topMargin=45,bottomMargin=45).build(story)


def generate(entrada: Path, salida: Path, titulo: str, subtitulo: str,
             *, empresa: str = '', puesto: str = '', instrucciones: str = '',
             logo: Path | None = None) -> Path:
    titulo=_text(titulo,label='Título',limit=90)
    subtitulo=_text(subtitulo,label='Subtítulo',limit=90)
    empresa=_text(empresa,label='Empresa',limit=100) if empresa.strip() else ''
    puesto=_text(puesto,label='Puesto',limit=85) if puesto.strip() else ''
    instrucciones=_text(instrucciones,label='Instrucciones',limit=650) if instrucciones.strip() else ''
    entrada=Path(entrada).expanduser()
    questions=read_questions(entrada)
    safe_logo=_safe_image(Path(logo),source='Logotipo') if logo else None
    normal,bold=_font()
    root=Path(salida).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    if not root.is_dir():
        raise ExamError('Ruta de salida no es una carpeta.')
    # Solo se crea una carpeta única; nunca reemplaza PDFs anteriores.
    dirname=_slug(titulo)+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:7]
    folder=root/dirname
    folder.mkdir(mode=0o700,exist_ok=False)
    try:
        files={
           'Cuadernillo.pdf':lambda p:_exam_pdf(p,questions,titulo,subtitulo,normal,bold,
                    empresa=empresa,puesto=puesto,instrucciones=instrucciones,logo=safe_logo),
           'Hoja_respuestas.pdf':lambda p:_answer_sheet(p,questions,titulo,subtitulo,acetate=False,normal=normal,bold=bold),
           'Acetato_clave.pdf':lambda p:_answer_sheet(p,questions,titulo,subtitulo,acetate=True,normal=normal,bold=bold),
           'Clave_docente.pdf':lambda p:_key_pdf(p,questions,titulo,normal,bold,empresa=empresa,puesto=puesto),
        }
        for name,action in files.items():
            action(folder/name)
        shutil.copyfile(entrada,folder/'Preguntas_originales.xlsx')
        # Conservar los archivos usados para modificar el examen en el futuro.
        for image in {q.image for q in questions if q.image}:
            folder.joinpath('imagenes').mkdir(exist_ok=True)
            shutil.copyfile(image,folder/'imagenes'/image.name)
        if safe_logo:
            folder.joinpath('recursos').mkdir(exist_ok=True)
            shutil.copyfile(safe_logo,folder/'recursos'/('logo'+safe_logo.suffix.lower()))
        hashes={p.relative_to(folder).as_posix():sha256(p.read_bytes()).hexdigest()
                for p in sorted(folder.rglob('*')) if p.is_file()}
        manifest={'titulo':titulo,'subtitulo':subtitulo,'empresa':empresa,'puesto':puesto,
                  'instrucciones':instrucciones,'preguntas':len(questions),
                  'fecha_generacion':datetime.now().astimezone().isoformat(),
                  'formato':'A4; clave y hoja comparten coordenadas; impresión al 100%',
                  'archivo_origen':str(entrada.name),'archivos_sha256':hashes}
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        shutil.rmtree(folder)
        raise
    return folder
