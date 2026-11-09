"""Color, transparencia y geometría de los PDF exportados; datos sintéticos."""
import json
import sqlite3

import fitz
import pytest

from biblioteca import export_workbook, save_exam, load_exam, db_connect
from src.evaluaciones.core import Question, generate, ExamError, _bubbles, paper_dimensions


@pytest.mark.parametrize('paper', ['A4', 'Carta', 'Oficio'])
@pytest.mark.parametrize('count', [1, 20, 100])
def test_rgb_y_superposicion_pdf(tmp_path, paper, count):
    questions = [Question('Tema', f'Pregunta {i}', ('Uno', 'Dos', 'Tres', 'Cuatro'), i % 4)
                 for i in range(count)]
    source = export_workbook(questions, tmp_path/'fuente.xlsx')
    folder = generate(source, tmp_path/'salidas', 'Examen', '',
                      tamano_papel=paper, color_acetato='#B020D0')
    expected = (176/255, 32/255, 208/255)
    slots = list(_bubbles(questions, paper_dimensions(paper)))
    with fitz.open(folder/'Acetato_clave.pdf') as acetate, fitz.open(folder/'Hoja_respuestas.pdf') as sheet:
        assert len(acetate) == len(sheet)
        total = 0
        for index, page in enumerate(acetate):
            circles = [d for d in page.get_drawings() if d['fill'] is not None]
            correct = [(n, xy) for p, n, xy in slots if p == index]
            assert len(circles) == len(correct)
            outlines = [d for d in sheet[index].get_drawings() if len(d['items']) == 4 and d['items'][0][0] == 'c']
            for drawing, (number, xy) in zip(circles, correct):
                assert drawing['color'] == pytest.approx(expected, abs=.001)
                assert drawing['fill'] == pytest.approx(expected, abs=.001)
                assert drawing['fill_opacity'] == pytest.approx(.26)
                x, y = xy[questions[number-1].correct]
                center = (drawing['rect'].tl + drawing['rect'].br)/2
                assert center.x == pytest.approx(x, abs=.01)
                assert center.y == pytest.approx(page.rect.height-y, abs=.01)
                assert any(abs(((d['rect'].tl+d['rect'].br)/2)-center) < .01 for d in outlines)
                total += 1
        assert total == count
    assert json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['color_acetato'] == '#B020D0'


def test_migracion_con_datos_y_respaldo(tmp_path):
    db = tmp_path/'biblioteca.sqlite3'
    questions = [Question('Tema', 'Pregunta', ('a', 'b', 'c', 'd'), 2)]
    key = save_exam(db, nombre='Prueba', titulo='Prueba', empresa='', grupo='',
                    subtitulo='', instrucciones='', questions=questions, color_acetato='#CC2233')
    assert load_exam(db, key, tmp_path/'cache').color_acetato == '#CC2233'
    with sqlite3.connect(db) as conn:
        conn.execute('ALTER TABLE cuestionarios DROP COLUMN color_acetato')
    with db_connect(db) as conn:
        assert conn.execute('SELECT color_acetato FROM cuestionarios').fetchone()[0] == '#167341'
    backups = list(tmp_path.glob('*.bak'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute('SELECT id FROM cuestionarios').fetchone()[0] == key
        assert 'color_acetato' not in {r[1] for r in conn.execute('PRAGMA table_info(cuestionarios)')}
    loaded = load_exam(db, key, tmp_path/'cache')
    assert loaded.questions == tuple(questions)
    assert len(list(tmp_path.glob('*.bak'))) == 1


def test_color_invalido_no_crea_salida(tmp_path):
    with pytest.raises(ExamError, match='acetato'):
        generate(tmp_path/'no-existe.xlsx', tmp_path/'salida', 'Examen', '', color_acetato='red')
    assert not (tmp_path/'salida').exists()
