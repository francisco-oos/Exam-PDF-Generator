"""Servicio único: diseña una vez e imprime según modalidad y participantes.

No crea un editor ni una segunda plantilla de preguntas. El cuadernillo y la
hoja convencional vienen de src.evaluaciones.core; únicamente las hojas con QR
usan la geometría registrada por el lector OMR.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import shutil

from reportlab.lib import colors

from src.evaluaciones.core import (
    ExamError, _answer_sheet, _exam_pdf, _font, generate, paper_dimensions,
    read_questions,
)
from omr_evaluaciones.motor import (
    OMRStore, create_acetato_omr, create_forms_pdf, read_roster,
)

MODOS = ('normal', 'ecologico', 'folio')


def preparar_examen(entrada: Path, salida: Path, titulo: str, subtitulo: str, *,
                    modo_examen: str = 'ecologico',
                    lista_personal: str | Path | None = None,
                    omr_root: Path | None = None, **opciones) -> Path:
    """Prepara una carpeta coherente y deja la sesión QR asociada al mismo examen.

    - Normal: sin lista, documentos genéricos; con lista, juego por persona.
    - Ecológico: cuadernillo único; hojas de respuestas individuales si hay lista.
    - Folio: sin lista, salida ecológica genérica; con lista, QR/OMR y acetato
      con exactamente las coordenadas de la lectura y un folio por persona.
    """
    if modo_examen not in MODOS:
        raise ExamError('Tipo de examen no reconocido.')
    lista = Path(lista_personal).expanduser() if lista_personal else None
    personas = read_roster(lista) if lista else []
    opciones = dict(opciones)
    if modo_examen == 'folio' and personas:
        # Las burbujas no pueden ser casi blancas: en un escáner las marcas
        # de registro negras seguirían visibles, pero las opciones no.
        from biblioteca import hex_color
        ink = hex_color(opciones.get('color_respuestas', '#213A4C'),
                        'Color de la hoja de respuestas')
        rgb = tuple(int(ink[pos:pos+2], 16) for pos in (1,3,5))
        gray = sum(a*b for a,b in zip(rgb, (0.299,0.587,0.114)))
        if gray > 160:
            raise ExamError('Para folio/QR el color de burbujas debe ser oscuro '
                            '(p. ej. #213A4C) para que el escáner las reconozca.')
    opciones['reutilizable'] = modo_examen != 'normal'
    # Generar verifica Excel, colores, papel, imagen y logotipo ANTES de imprimir.
    carpeta = generate(entrada, salida, titulo, subtitulo, **opciones)
    sesion = None
    try:
        if personas:
            questions = read_questions(Path(entrada))
            normal, bold = _font()
            size = paper_dimensions(opciones.get('tamano_papel', 'A4'))
            col_t = colors.HexColor(opciones.get('color_titulo', '#213A4C'))
            col_s = colors.HexColor(opciones.get('color_subtitulo', '#5E7180'))
            col_a = colors.HexColor(opciones.get('color_respuestas', '#213A4C'))
            col_acetato = colors.HexColor(opciones.get('color_acetato', '#167341'))
            if modo_examen == 'folio':
                db_root = Path(omr_root) if omr_root is not None else Path(__file__).resolve().parent / 'datos' / 'omr'
                store = OMRStore(db_root)
                data = [{'tema': q.section, 'pregunta': q.prompt,
                         'correcta': 'ABCD'[q.correct]} for q in questions]
                sesion = store.create_session(titulo, data, personas,
                                              opciones.get('tamano_papel', 'A4'),
                                              'personalizado')
                # Reemplaza la hoja y el acetato genéricos por el PAR COMPATIBLE
                # con OMR. Nunca entregar un acetato convencional para QR.
                create_forms_pdf(
                    store, sesion, carpeta / 'Hoja_respuestas.pdf',
                    empresa=opciones.get('empresa', ''),
                    grupo=opciones.get('puesto', ''),
                    subtitulo=subtitulo,
                    color_titulo=opciones.get('color_titulo', '#213A4C'),
                    color_respuestas=opciones.get('color_respuestas', '#213A4C'),
                )
                create_acetato_omr(
                    store, sesion, carpeta / 'Acetato_clave.pdf',
                    color=opciones.get('color_acetato', '#167341'),
                )
                (carpeta / 'Sesion_OMR.txt').write_text(
                    'Sesión para escanear y calificar: '+sesion+'\n'
                    'Abrir Calificar y entregar -> Historial -> esta sesión.\n',
                    encoding='utf-8',
                )
            else:
                # La hoja del lote mantiene los centros del acetato convencional.
                _answer_sheet(
                    carpeta / 'Hoja_respuestas.pdf', questions, titulo, subtitulo,
                    acetate=False, normal=normal, bold=bold,
                    title_color=col_t, subtitle_color=col_s,
                    size=size, answer_color=col_a, acetate_color=col_acetato,
                    participantes=personas,
                )
                if modo_examen == 'normal':
                    # Un juego independiente por persona, útil al enviar o imprimir
                    # individualmente, sin alterar el cuestionario original.
                    paquetes = carpeta / 'Por_participante'
                    paquetes.mkdir(exist_ok=True)
                    with ZipFile(carpeta / 'Paquetes_individuales.zip', 'w',
                                 compression=ZIP_DEFLATED) as zipfile:
                        for n, persona in enumerate(personas, 1):
                            identificador = persona['id']
                            subdir = paquetes / f'{n:04d}_{identificador}'
                            subdir.mkdir()
                            cuadernillo = subdir / 'Cuadernillo.pdf'
                            respuestas = subdir / 'Hoja_respuestas.pdf'
                            _exam_pdf(
                                cuadernillo, questions, titulo, subtitulo, normal, bold,
                                empresa=opciones.get('empresa', ''),
                                puesto=opciones.get('puesto', ''),
                                instrucciones=opciones.get('instrucciones', ''),
                                logo=opciones.get('logo'),
                                color_titulo=col_t, color_subtitulo=col_s,
                                size=size, font_size=float(opciones.get('letra', 9)),
                                reusable=False, participante=persona,
                            )
                            _answer_sheet(
                                respuestas, questions, titulo, subtitulo,
                                acetate=False, normal=normal, bold=bold,
                                title_color=col_t, subtitle_color=col_s,
                                size=size, answer_color=col_a,
                                acetate_color=col_acetato,
                                participantes=[persona],
                            )
                            for archivo in (cuadernillo, respuestas):
                                zipfile.write(archivo, archivo.relative_to(paquetes))
        instrucciones = {
            'normal': 'Cuadernillo y hoja normales. Con participantes: hojas agrupadas '
                      'y juegos en Por_participante/ o Paquetes_individuales.zip.',
            'ecologico': 'Un cuadernillo reutilizable. Con participantes: '
                         'Hoja_respuestas.pdf tiene hojas identificadas por persona.',
            'folio': 'Con participantes: Hoja_respuestas.pdf contiene folios y QR firmados; '
                     'Acetato_clave.pdf coincide con SUS burbujas OMR. '
                     'Calificar desde el menú -> Historial y elegir la sesión.',
        }
        if modo_examen == 'folio' and not personas:
            instrucciones['folio'] = ('Sin lista de personal se generaron '
                'cuadernillo y hoja genéricos. NO se generaron folios ni códigos QR.')
        (carpeta / 'LEEME_IMPRESION.txt').write_text(
            f'Tipo: {modo_examen}\nParticipantes: {len(personas)}\n'
            + instrucciones[modo_examen]
            + '\nImprimir sin ajustar escala: 100 % y mismo tamaño de papel.\n',
            encoding='utf-8',
        )
        manifest_path = carpeta / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.update({
            'modo_examen': modo_examen,
            'participantes': len(personas),
            'sesion_omr': sesion,
            'folio_qr_habilitado': bool(sesion),
        })
        # Los archivos modificados por la modalidad deben tener hash actualizado.
        manifest['archivos_sha256'] = {
            p.relative_to(carpeta).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob('*')) if p.is_file() and p != manifest_path
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                 encoding='utf-8')
        return carpeta
    except Exception:
        # Nunca dejar PDFs a medias ni ocultar un fallo de personalización.
        shutil.rmtree(carpeta, ignore_errors=True)
        raise
