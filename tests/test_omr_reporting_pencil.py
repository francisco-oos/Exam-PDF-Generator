"""Grafito medio y resultados pedagógicos por tema.

Pruebas 100 % sintéticas: no se sube evidencia Xerox ni personas reales.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np
import pytest

from omr_evaluaciones.motor import (
    OMRStore, RENDER_DPI, PAPERS, bubble_positions, _recognize,
)
from omr_evaluaciones.expedientes import participant_receipt


@pytest.mark.parametrize("shade,expected", [
    (160,"A"),(180,"A"),(184,"A"),(190,None),(220,None),
])
def test_grafito_y_gris_claro_conservan_incertidumbre(shade,expected):
    factor=RENDER_DPI/72
    w,h=PAPERS["Carta"]
    gray=np.full((round(h*factor),round(w*factor)),255,dtype=np.uint8)
    for x,y in bubble_positions("Carta",1)[0]:
        cv2.circle(gray,(round(x*factor),round((h-y)*factor)),
                   round(7.7*factor),155,2,lineType=cv2.LINE_AA)
    x,y=bubble_positions("Carta",1)[0][0]
    cv2.circle(gray,(round(x*factor),round((h-y)*factor)),
               round(4.7*factor),shade,-1,lineType=cv2.LINE_AA)
    answer,issues,levels=_recognize(gray,"Carta",1)
    assert answer==[expected]
    assert (len(issues)==0) if expected else (len(issues)==1)
    assert len(levels)==1


def test_dos_marcas_grafito_medio_no_se_califican():
    factor=RENDER_DPI/72
    w,h=PAPERS["Carta"]
    gray=np.full((round(h*factor),round(w*factor)),255,dtype=np.uint8)
    for i,(x,y) in enumerate(bubble_positions("Carta",1)[0]):
        center=(round(x*factor),round((h-y)*factor))
        cv2.circle(gray,center,round(7.7*factor),155,2)
        if i in (0,1):
            cv2.circle(gray,center,round(4.7*factor),183,-1)
    a,issues,levels=_recognize(gray,"Carta",1)
    assert a==[None]
    assert issues and "marcas" in issues[0]["razon"].lower()


def test_reporte_por_tema_solo_para_resultado_validado(tmp_path):
    store=OMRStore(tmp_path/"omr")
    questions=[
        {"tema":"Reconocer equipos","pregunta":f"Pregunta {i}","correcta":v}
        for i,v in enumerate(("A","B"),1)
    ]+[
        {"tema":"Movimientos","pregunta":f"Pregunta {i}","correcta":v}
        for i,v in enumerate(("C","D","A"),3)
    ]
    sid=store.create_session("Evaluación ficticia",questions,
        [{"id":"P001","nombre":"Persona de prueba"}],"Carta")
    person=store.session(sid)["personal"][0]
    pdf=tmp_path/"pendiente.pdf"
    participant_receipt(store,sid,"P001",pdf)
    with fitz.open(pdf) as doc:
        text=" ".join(p.get_text() for p in doc)
    assert "Pendiente" in text
    assert "Repasar" not in text

    _,state=store.register_page(
        sid,"a"*64,0,np.full((60,60,3),255,np.uint8),person["token"],
        ["A","B","C","A","D"],[], "validada")
    assert state=="validada"
    report=store.results(sid)
    row=report["participantes"][0]
    assert row["aciertos"]==3
    assert row["porcentaje"]==60.0
    assert row["temas"]["Reconocer equipos"]["aciertos"]==2
    assert row["temas"]["Reconocer equipos"]["porcentaje"]==100.0
    assert row["temas"]["Movimientos"]["por_reforzar"]==2
    assert row["temas"]["Movimientos"]["nivel_repaso"]=="Prioridad de repaso"
    assert [x["tema"] for x in row["areas_mejora"]]==["Movimientos"]

    participant_receipt(store,sid,"P001",pdf)
    with fitz.open(pdf) as doc:
        text=" ".join(p.get_text() for p in doc)
    assert "Reconocer equipos" in text
    assert "Movimientos" in text
    assert "Repasar Movimientos" in text
    assert "3/5" not in text or "Preguntas: 5" in text
    # Un reporte individual no revela correctas ni nombres ajenos.
    assert "respuesta correcta" not in text.lower()
