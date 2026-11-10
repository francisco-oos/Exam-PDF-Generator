"""Cuadrículas sintéticas: la Xerox puede comprimir separación de reactivos.

Sin subir escaneos privados al repositorio. Las marcas aisladas, ambiguas y
de geometría corrupta no deben convertirse en calificaciones automáticas.
"""
import cv2
import numpy as np

from omr_evaluaciones.motor import (
    PAPERS, _bubble_centers_in_scan, _recognize,
    render_review_with_acetato,
)


def make_synthetic(*, legacy=False, double=False, irregular=False):
    scale=200/72
    w,h=PAPERS["Carta"]
    image=np.full((round(h*scale),round(w*scale)),255,dtype=np.uint8)
    rows=[]
    for i in range(20):
        row=[]
        y=round((595+i*50) if legacy else (227+i*19.3)*scale)
        if irregular and i>=13:
            y+=90
        for j in range(4):
            x=round((73+23*j)*scale+(4+2*j if legacy else 0))
            cv2.circle(image,(x,y),round(7.7*scale),115,3)
            if j==i%4 or (double and i==9 and j==((i+1)%4)):
                cv2.circle(image,(x,y),round(4.7*scale),75,-1)
            row.append((x,y))
        rows.append(row)
    return image,rows


def test_scan_legacy_calibra_20_filas_y_4_columnas():
    scan,expected=make_synthetic(legacy=True)
    centers=_bubble_centers_in_scan(scan,"Carta",20)
    assert len(centers)==20
    for index in (0,8,19):
        for option in range(4):
            assert abs(centers[index][option][0]-expected[index][option][0])<4
            assert abs(centers[index][option][1]-expected[index][option][1])<4
    answers,issues,_=_recognize(scan,"Carta",20)
    assert answers==["ABCD"[i%4] for i in range(20)]
    assert issues==[]


def test_formato_actual_no_se_desplaza_ni_cambia_claves():
    scan,expected=make_synthetic()
    centers=_bubble_centers_in_scan(scan,"Carta",20)
    assert all(abs(centers[i][0][1]-expected[i][0][1])<4 for i in range(20))
    answers,issues,_=_recognize(scan,"Carta",20)
    assert answers==["ABCD"[i%4] for i in range(20)]
    assert not issues


def test_dos_marcas_siguen_en_revision_incluso_con_calibracion():
    scan,_=make_synthetic(legacy=True,double=True)
    answers,issues,_=_recognize(scan,"Carta",20)
    assert answers[9] is None
    assert any(issue["pregunta"]==10 for issue in issues)
    assert sum(a is None for a in answers)==1


def test_contornos_irregulares_no_crean_cuadricula_inventada():
    scan,_=make_synthetic(legacy=True,irregular=True)
    original=_bubble_centers_in_scan(scan,"Carta",20)
    scale=200/72
    assert original[19][0][1]==round((227+19*19.3)*scale)


def test_acetato_y_resaltado_calibrados_sobre_fila_real_20():
    scan,grid=make_synthetic(legacy=True)
    bgr=cv2.cvtColor(scan,cv2.COLOR_GRAY2BGR)
    questions=[
        {"tema":"Prueba","pregunta":f"Reactivo {i+1}",
         "correcta":"ABCD"[i%4]} for i in range(20)]
    normal=np.asarray(render_review_with_acetato(
        bgr,"Carta",questions,show_acetato=False,
        issue_numbers=(),already_aligned=True))
    high=np.asarray(render_review_with_acetato(
        bgr,"Carta",questions,show_acetato=False,
        issue_numbers=[20],already_aligned=True))
    # El recuadro debe quedar alrededor del renglón real 20, no en
    # la posición vertical nominal que produce el desplazamiento.
    y=grid[19][0][1]
    assert np.any(high[y-32:y+32,150:500] != normal[y-32:y+32,150:500])
    wrong=round((227+19*19.3)*(200/72))
    assert not np.any(high[wrong-12:wrong+12,150:500] !=
                      normal[wrong-12:wrong+12,150:500])
