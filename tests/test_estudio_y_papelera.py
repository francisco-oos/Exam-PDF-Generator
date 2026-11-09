"""Papelera recuperable y relación entre ajustes visuales y PDF real."""
from pathlib import Path
import sqlite3

import pytest
from PIL import Image
from biblioteca import save_exam, list_exams, delete_exam, restore_exam, purge_exam, load_exam, db_connect
from src.evaluaciones.core import Question, ExamError
from preview_pdf import render_document_preview
from vista_previa import PreviewData


def store(tmp_path):
    photo=tmp_path/'ilustracion.png'
    Image.new('RGB', (75,55), '#216986').save(photo)
    db=tmp_path/'biblioteca.sqlite3'
    q=[Question('Matemáticas','¿Cuánto es uno más uno?',('Uno','Dos','Tres','Cuatro'),1,photo)]
    key=save_exam(db,nombre='Examen de práctica',titulo='Preguntas',subtitulo='Prueba',
        empresa='',grupo='',instrucciones='Lee las preguntas.',questions=q)
    return db,key


def test_papelera_oculta_y_restauracion_conserva_claves(tmp_path):
    db,exam_id=store(tmp_path)
    assert len(list_exams(db))==1
    delete_exam(db,exam_id)
    assert list_exams(db)==[]
    assert len(list_exams(db,trash=True))==1
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM recursos').fetchone()[0]==1
    with pytest.raises(ExamError,match='No se encontró'):
        load_exam(db,exam_id,tmp_path/'sin_acceso')
    restore_exam(db,exam_id)
    exam=load_exam(db,exam_id,tmp_path/'recuperado')
    assert exam.questions[0].correct==1
    assert exam.questions[0].image.is_file()
    assert exam.revision==1
    assert list_exams(db,trash=True)==[]


def test_borrado_definitivo_exige_papelera_y_borra_recursos(tmp_path):
    db,exam_id=store(tmp_path)
    with pytest.raises(ExamError,match='papelera'):
        purge_exam(db,exam_id)
    delete_exam(db,exam_id)
    with pytest.raises(ExamError,match='Restáuralo'):
        save_exam(db,exam_id=exam_id,nombre='Intento',titulo='Título',subtitulo='',
          empresa='',grupo='',instrucciones='',questions=[Question('T','Q',('a','b','c','d'),0)])
    purge_exam(db,exam_id)
    assert list_exams(db)==list_exams(db,trash=True)==[]
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM recursos').fetchone()[0]==0
    with pytest.raises(ExamError):restore_exam(db,exam_id)


def test_migracion_aditiva_preserva_legacy(tmp_path):
    db,exam_id=store(tmp_path)
    with sqlite3.connect(db) as conn:
        assert 'eliminado_en' in {x[1] for x in conn.execute('PRAGMA table_info(cuestionarios)')}
    delete_exam(db,exam_id)
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT eliminado_en FROM cuestionarios').fetchone()[0]


def test_ids_invalidos_nunca_alteran_registros(tmp_path):
    db,exam_id=store(tmp_path)
    for invalid in ('; DROP TABLE cuestionarios','../','',exam_id.upper()):
        with pytest.raises(ExamError):delete_exam(db,invalid)
        with pytest.raises(ExamError):purge_exam(db,invalid)
    assert len(list_exams(db))==1


def test_vista_pdf_mantiene_opciones_visualizadas(tmp_path):
    db,eid=store(tmp_path)
    loaded=load_exam(db,eid,tmp_path/'cache')
    data=PreviewData(titulo='Prueba de diseño',subtitulo='Texto',questions=loaded.questions,
        tamano_papel='Carta',letra=11,reutilizable=True,
        color_titulo='#901F38',color_subtitulo='#2B67AA',color_respuestas='#157C9D')
    img,total=render_document_preview(data,'Cuadernillo',0,800)
    assert img.width==800 and total>=1
    answer,count=render_document_preview(data,'Respuestas',0,700)
    assert answer.width==700 and count==1
