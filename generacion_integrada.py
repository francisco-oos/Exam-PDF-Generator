"""Preparar una evaluación: dos modalidades de cuadernillo, una hoja universal.

La lista de participantes es el ÚNICO interruptor de QR y calificación OMR:
- Con lista: QR/HMAC individual en hoja universal en ambos modos.
- Sin lista: misma hoja, campos en blanco y sin QR para corrección manual.
Se genera siempre un acetato con la misma geometría de las burbujas.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import shutil

from reportlab.lib import colors

from src.evaluaciones.core import (
    ExamError, _exam_pdf, _font, generate, paper_dimensions, read_questions,
)
from omr_evaluaciones.motor import (
    OMRStore, create_acetato_omr, create_forms_pdf,
    create_generic_acetato_pdf, create_generic_forms_pdf, read_roster,
)

MODOS = ('normal', 'ecologico')


def preparar_examen(entrada: Path, salida: Path, titulo: str, subtitulo: str, *,
                    modo_examen: str = 'ecologico',
                    lista_personal: str | Path | None = None,
                    omr_root: Path | None = None, **opciones) -> Path:
    """Genera los materiales y, con lista, una sesión OMR del MISMO examen.

    Normal + lista: PDF QR en lote, cuadernillo y misma hoja QR por persona.
    Ecológico + lista: un cuadernillo reutilizable y PDF QR en lote.
    Sin lista en ambos: misma hoja sin QR ni folio y un acetato compatible.
    La clave HMAC de cada sesión nunca se incluye en el PDF ni en manifiestos.
    """
    if modo_examen not in MODOS:
        raise ExamError('Selecciona normal o ecológico. El QR depende de cargar personal.')
    lista = Path(lista_personal).expanduser() if lista_personal else None
    personas = read_roster(lista) if lista else []
    opciones = dict(opciones)

    if personas:
        # El escáner necesita tinta oscura; no basta con marcas negras de registro.
        from biblioteca import hex_color
        ink = hex_color(opciones.get('color_respuestas', '#213A4C'),
                        'Color de la hoja de respuestas')
        rgb = tuple(int(ink[pos:pos+2], 16) for pos in (1, 3, 5))
        gray = sum(a*b for a,b in zip(rgb, (0.299, 0.587, 0.114)))
        if gray > 160:
            raise ExamError(
                'Para calificar con QR, el color de las burbujas debe ser oscuro '
                '(por ejemplo, #213A4C).'
            )

    opciones['reutilizable'] = modo_examen == 'ecologico'
    # El generador estándar valida primero preguntas, papeles, recursos y tintas.
    carpeta = generate(entrada, salida, titulo, subtitulo, **opciones)
    sesion = None
    try:
        questions = read_questions(Path(entrada))
        respuestas = [
            {'tema': q.section, 'pregunta': q.prompt, 'correcta': 'ABCD'[q.correct]}
            for q in questions
        ]
        papel = opciones.get('tamano_papel', 'A4')
        config = {
            'empresa': opciones.get('empresa', ''),
            'grupo': opciones.get('puesto', ''),
            'subtitulo': subtitulo,
            'color_titulo': opciones.get('color_titulo', '#213A4C'),
            'color_respuestas': opciones.get('color_respuestas', '#213A4C'),
        }
        if personas:
            # El examen mantiene el tipo elegido para el historial, pero
            # su QR/HMAC depende exclusivamente de la presencia de lista.
            data_root = (Path(omr_root) if omr_root is not None else
                         Path(__file__).resolve().parent / 'datos' / 'omr')
            store = OMRStore(data_root)
            sesion = store.create_session(titulo, respuestas, personas, papel,
                                          modo_examen)
            create_forms_pdf(store, sesion, carpeta / 'Hoja_respuestas.pdf',
                             **config)
            create_acetato_omr(
                store, sesion, carpeta / 'Acetato_clave.pdf',
                color=opciones.get('color_acetato', '#167341'),
            )
            (carpeta / 'Sesion_OMR.txt').write_text(
                'Sesión para escanear y calificar: '+sesion+'\n'
                'Calificar y entregar -> Historial -> seleccionar esta sesión.\n',
                encoding='utf-8',
            )
            if modo_examen == 'normal':
                # Cada juego lleva la misma identidad y el MISMO QR que el lote.
                # Jamás crear una sesión distinta para los paquetes individuales.
                normal, bold = _font()
                size = paper_dimensions(papel)
                col_t = colors.HexColor(config['color_titulo'])
                col_s = colors.HexColor(opciones.get('color_subtitulo', '#5E7180'))
                paquetes = carpeta / 'Por_participante'
                paquetes.mkdir(exist_ok=True)
                with ZipFile(carpeta / 'Paquetes_individuales.zip', 'w',
                             compression=ZIP_DEFLATED) as z:
                    for number, persona in enumerate(personas, 1):
                        subdir = paquetes / f"{number:04d}_{persona['id']}"
                        subdir.mkdir()
                        cuadernillo = subdir / 'Cuadernillo.pdf'
                        hoja = subdir / 'Hoja_respuestas.pdf'
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
                        create_forms_pdf(store, sesion, hoja,
                                         person_ids=[persona['id']], **config)
                        for archivo in (cuadernillo, hoja):
                            z.write(archivo, archivo.relative_to(paquetes))
        else:
            # Mismo formato de burbujas/acetato que el OMR, sin QR ni sesión.
            create_generic_forms_pdf(
                respuestas, titulo, papel, carpeta / 'Hoja_respuestas.pdf',
                **config,
            )
            create_generic_acetato_pdf(
                respuestas, papel, carpeta / 'Acetato_clave.pdf',
                color=opciones.get('color_acetato', '#167341'),
            )

        if personas:
            detalle = (
                'Hoja universal con folio, ID, nombre y QR firmado por persona. '
                'Puede calificarse con escáner o con el acetato de esta misma carpeta.'
            )
        else:
            detalle = (
                'Hoja universal sin QR, con espacios para escribir nombre y grupo. '
                'Corrección manual con el acetato de esta misma carpeta.'
            )
        cuaderno = (
            'Se genera un cuadernillo y una hoja por persona (además del lote).'
            if modo_examen == 'normal' and personas else
            'Se genera un cuadernillo normal genérico.' if modo_examen == 'normal'
            else 'Se genera UN cuadernillo reutilizable para todas las personas.'
        )
        (carpeta / 'LEEME_IMPRESION.txt').write_text(
            f'Modalidad: {modo_examen}\nParticipantes: {len(personas)}\n'
            + cuaderno + '\n' + detalle
            + '\nImprime al 100 %, sin ajustar escala; mantén el mismo papel.\n',
            encoding='utf-8',
        )
        manifest_path = carpeta / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.update({
            'modo_examen': modo_examen,
            'participantes': len(personas),
            'sesion_omr': sesion,
            'folio_qr_habilitado': bool(personas),
            'formato_hoja': 'universal-omr-v1',
        })
        # La exportación reemplaza el PDF genérico provisional; actualizar hashes.
        manifest['archivos_sha256'] = {
            p.relative_to(carpeta).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob('*')) if p.is_file() and p != manifest_path
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        return carpeta
    except Exception:
        # No ocultar fallos; no dejar el lote incompleto como impresión válida.
        shutil.rmtree(carpeta, ignore_errors=True)
        raise
