import io
import json
from pathlib import Path
import zipfile

import pytest
from openpyxl import Workbook
from src.evaluaciones.core import ExamError, generate, read_questions, _bubbles


def write_sheet(path, *, correct='B', modify=None):
    w=Workbook();s=w.active;s.title='Preguntas'
    s.append(['Tema','Pregunta','A','B','C','D','Correcta'])
    s.append(['INOVA','¿Cuántos nodos?', 'Uno','Dos','Tres','Cuatro',correct])
    if modify:modify(s)
    w.save(path)
    return path


def test_valid_excel_and_stable_key(tmp_path):
    src=write_sheet(tmp_path/'entrada.xlsx')
    q=read_questions(src)
    assert len(q)==1 and q[0].correct==1 and q[0].options[0]=='Uno'
    o=generate(src,tmp_path/'out','Evaluación','Primera prueba')
    assert {x.name for x in o.iterdir()}=={'Cuadernillo.pdf','Hoja_respuestas.pdf','Acetato_clave.pdf','Clave_docente.pdf','Preguntas_originales.xlsx','manifest.json'}
    import fitz
    key=fitz.open(o/'Clave_docente.pdf')
    assert 'Dos' in key[0].get_text()
    assert 'B' in key[0].get_text()
    sheet=fitz.open(o/'Hoja_respuestas.pdf')
    acetate=fitz.open(o/'Acetato_clave.pdf')
    assert len(sheet)==len(acetate)==1
    assert 'HOJA DE RESPUESTAS' in sheet[0].get_text()
    assert 'HOJA DE RESPUESTAS' not in acetate[0].get_text()
    hashes=json.loads((o/'manifest.json').read_text())['archivos_sha256']
    assert len(hashes)==5


def test_no_png_deleted_no_overwrite(tmp_path):
    (tmp_path/'imagen_familiar.png').write_bytes(b'NO TOCAR')
    src=write_sheet(tmp_path/'preguntas.xlsx')
    one=generate(src,tmp_path/'salidas','Examen','test')
    two=generate(src,tmp_path/'salidas','Examen','test')
    assert one!=two
    assert (tmp_path/'imagen_familiar.png').read_bytes()==b'NO TOCAR'
    assert src.is_file()
    assert (one/'Cuadernillo.pdf').is_file() and (two/'Cuadernillo.pdf').is_file()


def test_missing_header_rejected(tmp_path):
    src=write_sheet(tmp_path/'bad.xlsx',modify=lambda sheet: setattr(sheet['G1'],'value','Clave'))
    with pytest.raises(ExamError,match='Cabeceras'):
        read_questions(src)


def test_formula_rejected(tmp_path):
    src=write_sheet(tmp_path/'bad.xlsx',modify=lambda sheet: setattr(sheet['B2'],'value','=1+1'))
    with pytest.raises(ExamError,match='fórmulas'):
        read_questions(src)


def test_invalid_correct_letter_rejected(tmp_path):
    src=write_sheet(tmp_path/'bad.xlsx',correct='Z')
    with pytest.raises(ExamError,match='A, B, C o D'):
        read_questions(src)


def test_duplicate_options_rejected(tmp_path):
    src=write_sheet(tmp_path/'bad.xlsx',modify=lambda sheet: setattr(sheet['C2'],'value','Dos'))
    with pytest.raises(ExamError,match='distintas'):
        read_questions(src)


def test_blank_between_questions_rejected(tmp_path):
    def update(sheet):
        sheet.append([None]*7)
        sheet.append(['Tema','Otra','A','B','C','D','D'])
    src=write_sheet(tmp_path/'bad.xlsx',modify=update)
    with pytest.raises(ExamError,match='filas vacías'):
        read_questions(src)


def test_symlink_rejected(tmp_path):
    src=write_sheet(tmp_path/'ok.xlsx')
    link=tmp_path/'link.xlsx'
    try:
        link.symlink_to(src)
    except OSError:
        pytest.skip('Windows sin permisos para crear enlaces simbólicos')
    with pytest.raises(ExamError,match='simbólico'):
        read_questions(link)


def test_zip_bomb_rejected(tmp_path):
    p=tmp_path/'bomb.xlsx'
    with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('xl/worksheets/sheet1.xml','x'*(40*1024*1024))
    with pytest.raises(ExamError,match='tamaño descomprimido'):
        read_questions(p)


def test_max_questions_rejected(tmp_path):
    def add(sheet):
        for i in range(2,103):
            sheet.append(['Tema',f'Pregunta {i}','A','B','C','D','D'])
    src=write_sheet(tmp_path/'bad.xlsx',modify=add)
    with pytest.raises(ExamError,match='Máximo 100 preguntas'):
        read_questions(src)


def test_alignment_geometry():
    from src.evaluaciones.core import Question
    q=[Question('Tema','P',('A','B','C','D'),2) for _ in range(20)]
    grid=list(_bubbles(q))
    assert len(grid)==20 and all(len(coords)==4 for _,_,coords in grid)
    assert grid[0][2][0][1]==grid[10][2][0][1]
    assert grid[0][2][0][0]!=grid[10][2][0][0]
    assert len({(p,n) for p,n,_ in grid})==20


def test_text_escaping_does_not_inject_markups(tmp_path):
    src=write_sheet(tmp_path/'c.xlsx',modify=lambda sheet:setattr(sheet['B2'],'value','¿Cuál es <AFU> & geófono?'))
    out=generate(src,tmp_path/'salidas','Título','Demo')
    import fitz
    t=''.join(p.get_text() for p in fitz.open(out/'Cuadernillo.pdf'))
    assert '<AFU>' in t and 'geófono' in t


def test_sparse_sheet_dimension_limit(tmp_path):
    def set_row(sheet):
        sheet['A1048576'] = 'dato'
    src=write_sheet(tmp_path/'sparse.xlsx',modify=set_row)
    with pytest.raises(ExamError,match='demasiadas filas'):
        read_questions(src)
