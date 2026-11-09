"""Regresiones de impresión: tamaño, reutilización, vista exacta y persistencia."""
from dataclasses import replace
from pathlib import Path
from shutil import copyfile
import json
import sqlite3

import fitz
import pytest
from openpyxl import Workbook

from biblioteca import load_exam, save_exam
from preview_pdf import render_document_preview
from src.evaluaciones.core import (
    ExamError, Question, _bubbles, generate, paper_dimensions,
    read_questions, validated_font_size,
)
from vista_previa import PreviewData


@pytest.fixture
def workbook(tmp_path):
    w=Workbook();s=w.active;s.title='Preguntas'
    s.append(['Tema','Pregunta','A','B','C','D','Correcta','Imagen'])
    for i in range(1,21):
        s.append(['Tema',f'¿Qué acción corresponde a la pregunta {i}?',
                  'Verificar','Revisar','Conservar','Archivar','B',''])
    path=tmp_path/'preguntas.xlsx';w.save(path)
    return path


@pytest.mark.parametrize('paper,expected',[
    ('A4',(595.276,841.89)),('Carta',(612,792)),('Oficio',(612,936)),
])
def test_paper_sizes_and_reusable_booklet(workbook,tmp_path,paper,expected):
    out=generate(workbook,tmp_path/'pdfs','Evaluación de prueba','Versión de ejemplo',
                 tamano_papel=paper,reutilizable=True,
                 color_respuestas='#236FA4',letra=10.5)
    with fitz.open(out/'Cuadernillo.pdf') as pdf:
        for page in pdf:
            assert abs(page.rect.width-expected[0]) < 1
            assert abs(page.rect.height-expected[1]) < 1
            assert 'NO RAYAR NI MANCHAR' in page.get_text()
            assert 'Nombre:' not in page.get_text()
            assert 'Número / folio:' not in page.get_text()
    with fitz.open(out/'Hoja_respuestas.pdf') as pdf:
        assert abs(pdf[0].rect.height-expected[1]) < 1
        assert 'Nombre:' in pdf[0].get_text()
    with fitz.open(out/'Acetato_clave.pdf') as pdf:
        assert abs(pdf[0].rect.height-expected[1]) < 1
        assert 'Nombre:' not in pdf[0].get_text()
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['tamano_papel']==paper
    assert manifest['reutilizable'] is True
    assert manifest['color_respuestas']=='#236FA4'
    assert manifest['letra']==10.5


def test_standard_booklet_retains_identification(workbook,tmp_path):
    out=generate(workbook,tmp_path/'out','Examen','Sub',reutilizable=False)
    with fitz.open(out/'Cuadernillo.pdf') as pdf:
        assert 'Nombre:' in pdf[0].get_text()
        assert 'NO RAYAR NI MANCHAR' not in pdf[0].get_text()


def test_coordinates_aligned_on_all_sizes():
    q=[Question('Tema',f'Pregunta {i}',('A1','B2','C3','D4'),1) for i in range(100)]
    for size in ('A4','Carta','Oficio'):
        w,h=paper_dimensions(size)
        slots=list(_bubbles(q,(w,h)))
        assert len(slots)==100
        for page,n,points in slots:
            assert 0<=page<=2
            assert 38 < min(y for x,y in points) and max(y for x,y in points) < h-190
            assert 38 < min(x for x,y in points) and max(x for x,y in points) < w-38
        assert len({(p,n) for p,n,xy in slots})==100


def test_invalid_settings_rejected_before_output(workbook,tmp_path):
    for kwargs in [{'tamano_papel':'Legal'}, {'letra':7}, {'letra':12.2},
                   {'color_respuestas':'red'}, {'reutilizable':'si'}]:
        with pytest.raises(ExamError):
            generate(workbook,tmp_path/'salida','Título','Subtítulo',**kwargs)
    assert not (tmp_path/'salida').exists()


def test_full_document_preview_uses_real_page_count(workbook):
    questions=tuple(read_questions(workbook))
    data=PreviewData(titulo='Examen para vista ampliada',questions=questions,
                     tamano_papel='Carta',letra=12,reutilizable=True)
    for view in ('Cuadernillo','Respuestas','Acetato'):
        img,total=render_document_preview(data,view,0,700)
        assert img.width==700 and img.height>700
        assert total>=1
    image,total=render_document_preview(data,'Cuadernillo',2,600)
    assert image.width==600 and total>=1  # Página solicitada se acota al total.


def test_library_migrates_old_schema_and_remembers_preferences(workbook,tmp_path):
    db=tmp_path/'antigua.sqlite3'
    # Recrea el esquema anterior para probar la migración sin editar datos reales.
    with sqlite3.connect(db) as conn:
        conn.execute('''CREATE TABLE cuestionarios (id TEXT PRIMARY KEY,nombre TEXT NOT NULL,
         empresa TEXT NOT NULL DEFAULT '',grupo TEXT NOT NULL DEFAULT '',titulo TEXT NOT NULL,
         subtitulo TEXT NOT NULL DEFAULT '',instrucciones TEXT NOT NULL DEFAULT '',
         color_titulo TEXT NOT NULL,color_subtitulo TEXT NOT NULL,preguntas_json TEXT NOT NULL,
         logo_archivo TEXT,creado_en TEXT NOT NULL,actualizado_en TEXT NOT NULL,
         revision INTEGER NOT NULL DEFAULT 1)''')
    questions=read_questions(workbook)
    key=save_exam(db,nombre='Banco de pruebas',titulo='Examen',subtitulo='Prueba',
                  empresa='',grupo='',instrucciones='',questions=questions,
                  reutilizable=True,tamano_papel='Oficio',letra=8.5,
                  color_respuestas='#A32F51')
    loaded=load_exam(db,key,tmp_path/'restaurado')
    assert len(loaded.questions)==20
    assert loaded.reutilizable is True
    assert loaded.tamano_papel=='Oficio'
    assert loaded.letra==8.5
    assert loaded.color_respuestas=='#A32F51'
    new_id=save_exam(db,nombre='Banco de pruebas',titulo='Examen',subtitulo='Prueba',
                  empresa='',grupo='',instrucciones='',questions=loaded.questions,
                  reutilizable=False,tamano_papel='Carta',letra=9.0,
                  color_respuestas='#234567',exam_id=key)
    assert new_id==key
    assert load_exam(db,key,tmp_path/'restaurado2').revision==2


def test_demo_is_generic():
    q=read_questions(Path(__file__).resolve().parents[1]/'ejemplos'/'Plantilla_20_preguntas.xlsx')
    assert len(q)==20
    body=' '.join([x.section+' '+x.prompt+' '+' '.join(x.options) for x in q]).upper()
    assert not any(x in body for x in ('AFU','DFU','SERCEL','INOVA','TX','ALMACÉN','NODOS'))


def test_font_validation():
    for val in (8,9.5,12):assert validated_font_size(val)==val
    for val in (7.5,12.5,9.3,'x',float('nan')):
        with pytest.raises(ExamError):validated_font_size(val)
