"""Integridad, edición, almacenamiento y reversibilidad local de cuestionarios."""
from pathlib import Path
import json
import sqlite3
import pytest
from PIL import Image
from openpyxl import load_workbook
from src.evaluaciones.core import ExamError, Question, generate, read_questions
from biblioteca import (save_exam, load_exam, list_exams, export_workbook,
                        DEFAULT_COLOR_TITLE, DEFAULT_COLOR_SUBTITLE, hex_color)


def questions(tmp_path):
    (tmp_path/'imagenes').mkdir(exist_ok=True)
    img=tmp_path/'imagenes'/'un_equipo.png'
    Image.new('RGB',(120,65),'#c7d9e3').save(img)
    return [Question('Seguridad','¿Cuál es el procedimiento válido?',
             ('Avisar','Omitir','Borrar','Inventar'),0,img)]


def test_library_roundtrip_and_edit_after_source_removed(tmp_path):
    initial=tmp_path/'origen';initial.mkdir()
    q=questions(initial)
    logo=initial/'logo.png';Image.new('RGB',(85,60),'#085774').save(logo)
    db=tmp_path/'store'/'biblioteca.sqlite3'
    eid=save_exam(db,nombre='Cuestionario Alfa',empresa='Compañía',grupo='Grupo A',
        titulo='Evaluación',subtitulo='Entrenamiento',instrucciones='Lee todo.',
        color_titulo='#123ABC',color_subtitulo='#ABCDEF',questions=q,logo=logo)
    assert len(list_exams(db))==1
    import shutil
    shutil.rmtree(initial)
    exam=load_exam(db,eid,tmp_path/'cache')
    assert exam.questions[0].image.is_file()
    assert exam.logo.is_file()
    assert exam.color_titulo=='#123ABC'
    assert exam.questions[0].options[0]=='Avisar'
    export=export_workbook(exam.questions,tmp_path/'cache'/eid/'Preguntas.xlsx')
    assert read_questions(export)[0].correct==0
    updated=list(exam.questions)
    updated[0]=Question('Seguridad','¿Qué debes registrar?',('Equipo','Lugar','Fecha','Todo'),3,updated[0].image)
    same_id=save_exam(db,exam_id=eid,nombre=exam.nombre,empresa=exam.empresa,
        grupo=exam.grupo,titulo=exam.titulo,subtitulo=exam.subtitulo,
        instrucciones=exam.instrucciones,color_titulo=exam.color_titulo,
        color_subtitulo=exam.color_subtitulo,questions=updated,logo=exam.logo)
    assert same_id==eid
    changed=load_exam(db,eid,tmp_path/'cache2')
    assert changed.revision==2
    assert changed.questions[0].correct==3
    assert '¿Qué debes registrar?'==changed.questions[0].prompt
    outfile=export_workbook(changed.questions,tmp_path/'cache2'/'Preguntas.xlsx')
    result=generate(outfile,tmp_path/'salidas','Evaluación','Entrenamiento',
                    color_titulo=changed.color_titulo,color_subtitulo=changed.color_subtitulo)
    assert (result/'Acetato_clave.pdf').is_file()
    assert json.loads((result/'manifest.json').read_text())['color_titulo']=='#123ABC'


def test_invalid_entry_does_not_modify_db(tmp_path):
    db=tmp_path/'lib.sqlite3'
    q=questions(tmp_path)
    with pytest.raises(ExamError,match='RGB'):
        save_exam(db,nombre='A',titulo='T',grupo='',empresa='',subtitulo='',instrucciones='',questions=q,
                  color_titulo='red')
    assert not db.exists()
    with pytest.raises(ExamError,match='distintas'):
        q[0]=Question('X','Q',('igual','igual','otro','cuatro'),0)
        save_exam(db,nombre='A',titulo='T',grupo='',empresa='',subtitulo='',instrucciones='',questions=q)


def test_template_is_blank_and_has_guide():
    p=Path(__file__).resolve().parents[1]/'plantillas'/'Plantilla_Cuestionario.xlsx'
    w=load_workbook(p)
    assert w.sheetnames==['Preguntas','Ejemplo','Guia']
    s=w['Preguntas']
    assert [s.cell(1,col).value for col in range(1,9)]==['Tema','Pregunta','A','B','C','D','Correcta','Imagen']
    assert s['B2'].value is None
    assert w['Ejemplo']['G2'].value=='B'


def test_transparent_filled_acetate_and_colors(tmp_path):
    import fitz
    db=tmp_path/'q';db.mkdir()
    q=questions(db)
    source=export_workbook(q,tmp_path/'q'/'Preguntas.xlsx')
    folder=generate(source,tmp_path/'outputs','Título prueba','Subtítulo prueba',
                    color_titulo='#CF3054',color_subtitulo='#2459C7')
    with fitz.open(folder/'Cuadernillo.pdf') as doc:
        page=doc[0]
        assert 'Título prueba' in page.get_text()
        spans=[span for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for span in line['spans']]
        assert any('Título prueba' in span['text'] and span['color']==int('CF3054',16) for span in spans)
        assert any('Subtítulo prueba' in span['text'] and span['color']==int('2459C7',16) for span in spans)
    with fitz.open(folder/'Acetato_clave.pdf') as doc:
        drawings=doc[0].get_drawings()
        assert any(x.get('fill') is not None and x.get('fill_opacity',1)<1 for x in drawings),drawings[:3]


def test_invalid_color_rejected(tmp_path):
    assert hex_color('#ef903a')=='#EF903A'
    for color in ('#GGGGGG','green','123ABC','rgba(0,0,0,1)','##ABCDEF'):
        with pytest.raises(ExamError,match='RGB'):hex_color(color)


def test_browser_downloads_ready_to_fill_template(monkeypatch):
    from http.server import ThreadingHTTPServer
    from urllib.request import urlopen
    import threading
    import web_app as web
    server=ThreadingHTTPServer(('127.0.0.1',0),web.Handler)
    monkeypatch.setattr(web,'PORT',server.server_address[1])
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    try:
        with urlopen(f'http://127.0.0.1:{web.PORT}/plantilla',timeout=5) as r:
            data=r.read()
            assert r.status==200 and data[:2]==b'PK'
            assert 'Plantilla_Cuestionario.xlsx' in r.headers['Content-Disposition']
        with urlopen(f'http://127.0.0.1:{web.PORT}/',timeout=5) as r:
            html=r.read().decode('utf-8')
            assert 'type="color" name="color_titulo"' in html
            assert 'type="color" name="color_subtitulo"' in html
    finally:
        server.shutdown();server.server_close();t.join(timeout=5)
