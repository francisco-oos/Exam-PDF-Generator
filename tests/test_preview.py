"""Pruebas de vista previa sin dependencia de pantalla física."""
from pathlib import Path
import pytest
from PIL import Image, ImageChops
from src.evaluaciones.core import Question, _bubbles, PAGE_H
from vista_previa import PreviewData, render_preview


def exam_data():
    questions=[Question('Operación',f'¿Cuál es la acción correcta {i}?',
                        ('Contar físicamente','Verificar fuente','Inventar serie','Borrar histórico'),1)
               for i in range(1,21)]
    return PreviewData(empresa='Empresa de ejemplo',grupo='Equipo administrativo',
                       titulo='Evaluación de seguridad operativa',
                       subtitulo='Examen interno de conocimientos',
                       instrucciones='Marca únicamente la hoja de respuestas.',
                       questions=tuple(questions))


def test_three_previews_are_images_without_writing(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    previews=[render_preview(exam_data(),view,390) for view in ('Cuadernillo','Respuestas','Acetato')]
    assert all(isinstance(p,Image.Image) and p.size[0]==390 for p in previews)
    assert ImageChops.difference(previews[0],previews[1]).getbbox() is not None
    assert ImageChops.difference(previews[1],previews[2]).getbbox() is not None
    assert not list(tmp_path.iterdir())


def test_generic_group_changes_cover_preview():
    a=exam_data()
    b=PreviewData(empresa=a.empresa,grupo='Aspirantes a beca',titulo=a.titulo,
                  subtitulo=a.subtitulo,instrucciones=a.instrucciones,questions=a.questions)
    assert ImageChops.difference(render_preview(a),render_preview(b)).getbbox() is not None


def test_answer_coordinates_shared_with_pdf_engine():
    d=exam_data()
    first=next(iter(_bubbles(list(d.questions))))
    page,n,xy=first
    assert page==0 and n==1 and len(xy)==4
    assert 0 < PAGE_H-xy[1][1] < 842
    img=render_preview(d,'Acetato',595)
    # El segundo círculo corresponde a B: su contorno verde se representa
    # en las coordenadas de _bubbles con inversión del eje vertical.
    x,y=xy[1]; ry=int(PAGE_H-y)
    red,green,blue=img.getpixel((round(x),ry-12))
    assert green>red and green>blue


def test_invalid_mode():
    with pytest.raises(ValueError):render_preview(exam_data(),'No permitido')
