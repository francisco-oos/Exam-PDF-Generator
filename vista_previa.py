"""Vista ilustrativa local para el diseñador de evaluaciones.

No genera claves finales ni envía datos a servicios externos. La hoja y el
acetato reutilizan _bubbles() del motor, de modo que sus centros coinciden
con la geometría del PDF. El cuadernillo es una vista orientativa; el PDF
es el documento definitivo.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps
from src.evaluaciones.core import Question, _bubbles, _safe_image, PAPER_SIZES, PAGE_W, PAGE_H, RADIUS

INK = '#213a4c'
DARK = '#132d41'
TEAL = '#0b7988'
MUTED = '#617382'
LIGHT = '#eaf2f5'
GREEN = '#167341'
SIZE = (595, 842)  # A4, escala aproximada en puntos para pantalla


@dataclass(frozen=True)
class PreviewData:
    empresa: str = ''
    grupo: str = ''
    titulo: str = 'Evaluación de conocimientos'
    subtitulo: str = ''
    instrucciones: str = ''
    questions: tuple[Question, ...] = ()
    logo: Path | None = None
    color_titulo: str = '#213A4C'
    color_subtitulo: str = '#5E7180'
    color_respuestas: str = '#213A4C'
    color_acetato: str = '#167341'
    tamano_papel: str = 'A4'
    letra: float = 9.0
    reutilizable: bool = False


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windir = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    names = [windir / ('arialbd.ttf' if bold else 'arial.ttf'),
             windir / ('segoeuib.ttf' if bold else 'segoeui.ttf'),
             Path('/usr/share/fonts/truetype/dejavu/') / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')]
    for path in names:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


def _lines(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int = 0) -> list[str]:
    """Separación por píxeles sin dividir caracteres acentuados arbitrariamente."""
    result: list[str] = []
    for paragraph in (text or '').splitlines() or ['']:
        parts = paragraph.split()
        if not parts:
            result.append('')
            continue
        current = ''
        for word in parts:
            candidate = f'{current} {word}'.strip()
            if draw.textlength(candidate, font=font) <= width:
                current = candidate
            else:
                if current:
                    result.append(current)
                    current = word
                else:
                    # Cortar palabras anómalamente largas para no salir del A4.
                    while word and draw.textlength(word, font=font) > width:
                        n = max(1,len(word)//2)
                        while n < len(word) and draw.textlength(word[:n+1],font=font)<=width:
                            n+=1
                        result.append(word[:n])
                        word=word[n:]
                    current=word
        if current:
            result.append(current)
    if max_lines and len(result)>max_lines:
        result=result[:max_lines]
        tail=result[-1]
        while tail and draw.textlength(tail+'…',font=font)>width:
            tail=tail[:-1]
        result[-1]=tail+'…'
    return result


def _write(draw, xy, text, font, fill=INK, max_width=485, max_lines=0, leading=4):
    x,y=xy
    lines=_lines(draw,text,font,max_width,max_lines)
    height=font.size+leading if hasattr(font,'size') else 16+leading
    for line in lines:
        draw.text((x,y),line,font=font,fill=fill)
        y+=height
    return y


def _logo(image: Image.Image, path: Path | None):
    if not path:
        return False
    try:
        safe=_safe_image(Path(path),source='Logotipo')
        with Image.open(safe) as src:
            pic=ImageOps.exif_transpose(src).convert('RGB')
            pic.thumbnail((78,65),Image.Resampling.LANCZOS)
        image.paste(pic,(50+(78-pic.width)//2,48+(65-pic.height)//2))
        return True
    except (OSError,ValueError):
        return False


def _cover_page(d: PreviewData) -> Image.Image:
    im=Image.new('RGB',SIZE,'white')
    dr=ImageDraw.Draw(im)
    haslogo=_logo(im,d.logo)
    startx=150 if haslogo else 52
    dr.text((startx,49), (d.empresa or 'ORGANIZACIÓN / EMPRESA').upper()[:63],
            font=_font(12,bold=True),fill=TEAL)
    y=_write(dr,(startx,70),'EVALUACIÓN DE CONOCIMIENTOS',_font(12,bold=True),INK,MAX_WIDTH:=SIZE[0]-startx-50,2)
    y=_write(dr,(startx,y+5), d.titulo or 'Título de la evaluación', _font(22,bold=True),d.color_titulo,MAX_WIDTH,3,4)
    y=_write(dr,(startx,y+4), d.subtitulo or 'Subtítulo opcional', _font(13),d.color_subtitulo,MAX_WIDTH,2)
    if d.grupo:
        y=_write(dr,(startx,y+7),'Área / grupo: '+d.grupo,_font(12),MUTED,MAX_WIDTH,2)
    header_bottom=max(y+15,176)
    dr.line((52,header_bottom,542,header_bottom),fill=TEAL,width=3)

    y=header_bottom+23
    if not d.reutilizable:
        dr.text((52,y),'Nombre: ______________________________________',font=_font(11),fill=INK)
        dr.text((52,y+26),'Fecha: ____________     Folio: __________________',font=_font(11),fill=INK)
        y+=70
    else:
        # Marca discreta y fuera del texto principal. La vista exacta renderiza el PDF.
        dr.text((68,805),'NO RAYAR NI MANCHAR · CUADERNILLO REUTILIZABLE',
                font=_font(8,bold=True),fill='#9AA6AE')
    dr.text((52,y),'INSTRUCCIONES',font=_font(12,bold=True),fill=TEAL)
    y=_write(dr,(52,y+23), d.instrucciones or 'Lee cada pregunta y marca una opción en la hoja separada.',
             _font(11),INK,490,4,6)
    y+=14
    total=len(d.questions)
    dr.text((52,y),f'{total or "—"} preguntas · Cuatro opciones por pregunta · Una respuesta correcta',
            font=_font(10),fill=MUTED)
    y+=37
    if d.questions:
        q=d.questions[0]
        dr.text((52,y),q.section.upper(),font=_font(12,bold=True),fill=TEAL)
        y+=24
        y=_write(dr,(52,y),'01. '+q.prompt,_font(12,bold=True),DARK,488,5,6)+11
        if q.image:
            try:
                with Image.open(q.image) as raw:
                    pic=ImageOps.exif_transpose(raw).convert('RGB')
                    pic.thumbnail((265,100),Image.Resampling.LANCZOS)
                im.paste(pic,(int((595-pic.width)/2),int(y)))
                y+=pic.height+13
            except OSError:
                pass
        for letter,choice in zip('ABCD',q.options):
            if y>=764:break
            y=_write(dr,(66,y),f'{letter}) {choice}',_font(10),INK,469,3,3)+6
        if y<765 and len(d.questions)>1:
            dr.text((52,y+7),'Siguientes preguntas…',font=_font(10),fill=MUTED)
    else:
        dr.rounded_rectangle((52,y,540,y+104),radius=9,fill=LIGHT)
        _write(dr,(70,y+20),'Selecciona un Excel válido para mostrar aquí la primera pregunta.',
               _font(12),MUTED,460,3)
    dr.line((52,795,543,795),fill='#D1DBE2',width=1)
    dr.text((52,808),d.empresa[:60] or 'Evaluación',font=_font(9),fill=MUTED)
    dr.text((392,808),'Cuadernillo · Vista inicial',font=_font(9),fill=MUTED)
    return im


def _sheet_page(d: PreviewData, *, acetate: bool) -> Image.Image:
    im=Image.new('RGB',SIZE,'white')
    dr=ImageDraw.Draw(im)
    if not acetate:
        dr.text((210,61),'HOJA DE RESPUESTAS',font=_font(14,bold=True),fill=d.color_respuestas)
        _write(dr,(145,85),d.titulo,_font(11),d.color_titulo,340,1)
        _write(dr,(145,101),d.subtitulo,_font(10),d.color_subtitulo,340,1)
        dr.text((49,141),'Nombre: ___________________________________________',font=_font(10),fill=d.color_respuestas)
        dr.text((49,161),'Fecha: _______________   Grupo / área: _______________',font=_font(10),fill=d.color_respuestas)
        dr.text((50,192),'Marca una sola respuesta (A, B, C o D) por pregunta.',font=_font(9),fill=d.color_respuestas)
    for page,no,pts in _bubbles(list(d.questions)):
        if page!=0:continue
        if not acetate:
            dr.text((pts[0][0]-38,int(PAGE_H-pts[0][1]-7)),f'{no}.',font=_font(10,bold=True),fill=INK)
            for letter,(x,y) in zip('ABCD',pts):
                dr.ellipse((int(x-RADIUS),int(PAGE_H-y-RADIUS),int(x+RADIUS),int(PAGE_H-y+RADIUS)),
                           outline=d.color_respuestas,width=2)
                dr.text((x-4,int(PAGE_H-y+RADIUS+5)),letter,font=_font(8),fill=d.color_respuestas)
        else:
            correct=d.questions[no-1].correct
            x,y=pts[correct]
            ry=PAGE_H-y
            dr.ellipse((int(x-RADIUS-4),int(ry-RADIUS-4),int(x+RADIUS+4),int(ry+RADIUS+4)),
                       outline=d.color_acetato,fill=tuple(round(255*.74+int(d.color_acetato[i:i+2],16)*.26) for i in (1,3,5)),width=3)
    # _bubbles usa coordenadas de PDF con origen abajo; la imagen tiene origen arriba.
    for x,y in ((37,38),(558,38),(37,805),(558,805)):
        dr.line((x-6,y,x+6,y),fill=INK,width=1)
        dr.line((x,y-6,x,y+6),fill=INK,width=1)
    footer='CLAVE PARA ACETATO · IMPRIMIR AL 100 %' if acetate else 'HOJA DE RESPUESTAS · IMPRIMIR AL 100 %'
    dr.text((160,811),footer,font=_font(9),fill=INK)
    return im


def render_preview(data: PreviewData, view: str = 'Cuadernillo', width: int = 405) -> Image.Image:
    """Obtiene una imagen PIL de vista previa, sin escribir datos en disco.

    view: 'Cuadernillo', 'Respuestas' o 'Acetato'.
    """
    if view=='Cuadernillo':page=_cover_page(data)
    elif view=='Respuestas':page=_sheet_page(data,acetate=False)
    elif view=='Acetato':page=_sheet_page(data,acetate=True)
    else:raise ValueError('Vista de examen no admitida.')
    width=max(220,min(int(width),595))
    return page.resize((width,round(width*PAGE_H/PAGE_W)),Image.Resampling.LANCZOS)
