"""Pruebas de identidad visual, imágenes seguras y continuidad de las hojas."""
from pathlib import Path
import json
import pytest
from PIL import Image
from openpyxl import Workbook

from src.evaluaciones.core import ExamError, generate, read_questions, _bubbles


def workbook(path, image=''):
    w=Workbook();s=w.active;s.title='Preguntas'
    s.append(['Tema','Pregunta','A','B','C','D','Correcta','Imagen'])
    s.append(['DFU','¿Qué tipo?', 'Uno','Dos','Tres','Cuatro','B',image])
    w.save(path)
    return path


def make_png(path, color='#14506b'):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB',(220,90),color).save(path)
    return path


def test_professional_layout_includes_brand_and_image(tmp_path):
    src=workbook(tmp_path/'examen.xlsx','pieza.png')
    make_png(tmp_path/'imagenes'/'pieza.png')
    logo=make_png(tmp_path/'logo.png', '#0d7f88')
    out=generate(src,tmp_path/'salidas','Control de nodos','Evaluación periódica',
                 empresa='Empresa de prueba',puesto='Sobrestantes',
                 instrucciones='Lee cada pregunta y marca solo una opción.',logo=logo)
    import fitz
    with fitz.open(out/'Cuadernillo.pdf') as pdf:
        content='\n'.join(p.get_text() for p in pdf)
        assert 'Empresa de prueba' in content
        assert 'Sobrestantes' in content
        assert 'INSTRUCCIONES' in content
        assert sum(len(p.get_images()) for p in pdf)>=2
    assert (out/'imagenes'/'pieza.png').is_file()
    assert (out/'recursos'/'logo.png').is_file()
    manifest=json.loads((out/'manifest.json').read_text())
    assert 'imagenes/pieza.png' in manifest['archivos_sha256']
    assert 'recursos/logo.png' in manifest['archivos_sha256']
    assert manifest['empresa']=='Empresa de prueba'


def test_blocks_path_traversal_and_urls(tmp_path):
    for invalid in ['../a.png','C:\\bad.png','https://example.com/logo.jpg','/tmp/a.jpg']:
        p=workbook(tmp_path/'base.xlsx',invalid)
        with pytest.raises(ExamError,match='sin carpetas ni rutas'):
            read_questions(p)


def test_blocks_invalid_image_type_and_corruption(tmp_path):
    x=workbook(tmp_path/'p.xlsx','fake.jpg')
    folder=tmp_path/'imagenes';folder.mkdir()
    (folder/'fake.jpg').write_text('no soy una imagen')
    with pytest.raises(ExamError,match='imagen ilegible'):
        read_questions(x)
    x=workbook(tmp_path/'p.xlsx','mal.svg')
    (folder/'mal.svg').write_text('<svg></svg>')
    with pytest.raises(ExamError,match='PNG o JPEG'):
        read_questions(x)


def test_rejects_external_symlink(tmp_path):
    src=workbook(tmp_path/'p.xlsx','pieza.png')
    real=make_png(tmp_path/'real.png')
    folder=tmp_path/'imagenes';folder.mkdir()
    try:(folder/'pieza.png').symlink_to(real)
    except OSError:pytest.skip('El sistema no admite symlink en esta prueba.')
    with pytest.raises(ExamError,match='no un enlace'):
        read_questions(src)


def test_no_extra_column_required_legacy(tmp_path):
    w=Workbook();s=w.active;s.title='Preguntas'
    s.append(['Tema','Pregunta','A','B','C','D','Correcta'])
    s.append(['AFU','P?', 'a','b','c','d','A'])
    p=tmp_path/'legacy.xlsx';w.save(p)
    assert len(read_questions(p))==1
    assert read_questions(p)[0].image is None


def test_acetate_never_displays_answer_letters(tmp_path):
    p=workbook(tmp_path/'base.xlsx')
    out=generate(p,tmp_path/'salidas','Examen','Prueba')
    import fitz
    with fitz.open(out/'Acetato_clave.pdf') as pdf:
        assert 'RESPUESTAS' not in pdf[0].get_text().upper()
    with fitz.open(out/'Hoja_respuestas.pdf') as pdf:
        assert 'HOJA DE RESPUESTAS' in pdf[0].get_text()


def test_image_count_and_rows(tmp_path):
    p=workbook(tmp_path/'base.xlsx')
    assert len(read_questions(p))==1
    assert len(list(_bubbles(read_questions(p))))==1


def test_discard_invalid_logo_before_writing(tmp_path):
    p=workbook(tmp_path/'base.xlsx')
    bad=tmp_path/'logo.png';bad.write_text('fake')
    with pytest.raises(ExamError,match='imagen ilegible'):
        generate(p,tmp_path/'salidas','Título','Subtitulo',logo=bad)
    assert not (tmp_path/'salidas').exists()
