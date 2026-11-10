"""Pruebas suplementarias de tonos para insertar en tests/ del repo OMR.

Son imágenes SINTÉTICAS a geometría nativa, no pruebas físicas Xerox.
Un tono ilegible puede quedar en duda, pero NUNCA producir una opción
incorrecta y validada silenciosamente. Se ejecuta contra el motor REAL.
"""
from __future__ import annotations
import cv2
import numpy as np
import pytest

from omr_evaluaciones.motor import PAPERS,RENDER_DPI,bubble_positions,_recognize

COLORS_RGB={
    "2B_fuerte":(50,50,50),
    "HB_medio":(150,150,150),
    "HB_tenue":(196,196,196),
    "negro_color":(24,24,24),
    "azul_oscuro":(42,68,145),
    "azul_claro":(112,180,235),
    "rojo":(198,58,49),
    "verde":(48,142,75),
    "amarillo":(237,212,70),
    "morado":(133,86,171),
}


def synthetic(color, *, n=20, double=False, erase=False):
    """Rellenos BGR/RGB generados con contornos idénticos al PDF OMR."""
    w,h=PAPERS["Carta"]
    factor=RENDER_DPI/72.0
    rgb=np.full((round(h*factor),round(w*factor),3),255,dtype=np.uint8)
    points=bubble_positions("Carta",n)
    answers="ACDBACDBACDBACDBACDB"[:n]
    for q,pts in enumerate(points):
        for j,(x,y) in enumerate(pts):
            center=round(x*factor),round((h-y)*factor)
            cv2.circle(rgb,center,round(7.7*factor),(125,125,125),2,lineType=cv2.LINE_AA)
            if j=="ABCD".index(answers[q]) or (double and q==3 and j==0):
                ink=COLORS_RGB[color]
                cv2.circle(rgb,center,round(4.7*factor),ink,-1,lineType=cv2.LINE_AA)
        if erase and q==7:
            x,y=pts["ABCD".index(answers[q])]
            cv2.circle(rgb,(round(x*factor),round((h-y)*factor)),
                       round(4.3*factor),(226,226,226),-1)
    return cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),answers


@pytest.mark.parametrize("tone",list(COLORS_RGB))
def test_cualquier_tono_o_es_correcto_o_genera_duda(tone):
    gray,expected=synthetic(tone)
    got,issues,_=_recognize(gray,"Carta",len(expected))
    pending={issue.get("pregunta") for issue in issues}
    for i,(actual,wanted) in enumerate(zip(got,expected),1):
        assert actual in (wanted,None),(
            f"P0: tono {tone}, reactivo {i}, asignación falsa {actual} (esperado {wanted})")
        if actual is None:
            assert i in pending,(
                f"P0: tono {tone}, reactivo {i} sin respuesta ni duda visible")


def test_grafito_2b_fuerte_sin_dudas_en_20_preguntas():
    gray,expected=synthetic("2B_fuerte")
    got,issues,_=_recognize(gray,"Carta",20)
    assert got==list(expected)
    assert not issues


def test_dos_marcas_de_distinto_color_no_asignan_opcion_arbitraria():
    gray,expected=synthetic("negro_color",double=True)
    got,issues,_=_recognize(gray,"Carta",20)
    assert got[3] is None
    assert any(issue.get("pregunta")==4 for issue in issues)


def test_borradura_parcial_no_asigna_letra_erronea():
    gray,expected=synthetic("HB_tenue",erase=True)
    got,issues,_=_recognize(gray,"Carta",20)
    assert got[7] in (expected[7],None)
    if got[7] is None:
        assert any(issue.get("pregunta")==8 for issue in issues)
