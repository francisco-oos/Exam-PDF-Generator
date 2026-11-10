"""PDF derivado de evidencia: original físico y QR nunca se modifican.

Uso exclusivo interno del piloto. La puntuación validada y el acetato
se dibujan FUERA del escaneo, sin ocultar marcas ni atribuir notas pendientes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import cv2
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen.canvas import Canvas
from omr_evaluaciones.motor import render_review_with_acetato


def line(pdf, text, x, y, width, *, size=9, leading=13, strong=False, limit=3):
    font="Helvetica-Bold" if strong else "Helvetica"
    pdf.setFont(font,size)
    for part in simpleSplit(str(text).replace("\n"," "),font,size,width)[:limit]:
        pdf.drawString(x,y,part)
        y-=leading
    return y


def audit_evidence_pdf(store,sheet_id,*,acetato=True,history=None):
    """Genera bytes PDF de una sola hoja y participante autorizado.

    Las comprobaciones de permisos se aplican antes de llamar a esta
    función. Ruta escaneada restringida a /omr/escaneos, no rutas del cliente.
    """
    with store.connect() as db:
        record=db.execute("SELECT * FROM hojas WHERE id=?",(sheet_id,)).fetchone()
    if record is None or not record["token"]:
        raise ValueError("Hoja inexistente o no identificada.")
    path=Path(record["imagen"]).resolve()
    if not path.is_relative_to((store.root/"escaneos").resolve()) or not path.is_file():
        raise ValueError("No se encontró el escaneo dentro del almacén autorizado.")
    session=store.session(record["sesion_id"])
    person=next((x for x in session["personal"]
                 if x["token"]==record["token"]),None)
    if not person:
        raise ValueError("La hoja no corresponde al participante.")
    original=cv2.imread(str(path))
    if original is None:
        raise ValueError("No se pudo abrir el escaneo original.")
    display=render_review_with_acetato(
        original,session["papel"],session["preguntas"],
        show_acetato=bool(acetato),issue_numbers=[],already_aligned=True)
    report=store.results(record["sesion_id"])
    result=next((x for x in report["participantes"] if x["id"]==person["id"]),None)
    valid=bool(result and result["estado"]=="validado" and
               record["estado"]=="validada")
    history=history or {}
    changes=history.get("cambios",[])
    legacy=history.get("registros_historicos",[])
    approval=history.get("aprobacion")
    latest=changes[-1] if changes else None
    last_name=(latest["operador"] if latest else
               legacy[-1]["revisor"] if legacy else "Motor OMR")
    last_time=(latest["fecha"] if latest else
               legacy[-1]["fecha"] if legacy else record["creada"])

    w,h=landscape(A4)
    out=BytesIO()
    pdf=Canvas(out,pagesize=(w,h),pageCompression=1)
    pdf.setTitle("Evidencia auditada "+person["folio"])
    pdf.setAuthor("OMR - Centro de Control - Piloto")
    pdf.setFillColorRGB(.09,.21,.29)
    pdf.setFont("Helvetica-Bold",13)
    pdf.drawString(22,h-25,"EVIDENCIA DE EVALUACION - COPIA DERIVADA")
    pdf.setFont("Helvetica",8)
    pdf.drawRightString(w-22,h-25,"PILOTO / NO ES DOCUMENTO OFICIAL")
    pdf.setStrokeColorRGB(.8,.85,.88)
    pdf.line(22,h-35,w-22,h-35)
    # Toda la hoja escaneada y sus marcas siguen completas a la izquierda.
    x0=22; y0=35; top=h-43
    width=353; height=top-y0
    factor=min(width/display.width,height/display.height)
    dw,dh=display.width*factor,display.height*factor
    pdf.drawImage(ImageReader(display),x0,top-dh,width=dw,height=dh)
    pdf.setStrokeColorRGB(.8,.85,.88)
    pdf.rect(x0,top-dh,dw,dh,stroke=1,fill=0)

    x=393; max_width=w-x-22; y=h-55
    pdf.setFillColorRGB(.1,.24,.32)
    y=line(pdf,"RESULTADO DE LA EVALUACION",x,y,max_width,
           size=12,strong=True,leading=17)
    y-=5
    fields=[
        ("Participante",person["nombre"]),
        ("ID",person["id"]),("Folio",person["folio"]),
        ("Evaluacion",session.get("nombre_evaluacion") or session["titulo"]),
        ("Sesion",record["sesion_id"]),
        ("Estado","VALIDADA" if valid else "EN REVISION / ACLARACION"),
    ]
    for title,value in fields:
        pdf.setFillColorRGB(.36,.42,.46)
        y=line(pdf,title+":",x,y,max_width,size=8,strong=True,leading=10)
        pdf.setFillColorRGB(.1,.21,.28)
        y=line(pdf,value,x,y,max_width,size=9,leading=12,limit=2)
        y-=3
    pdf.setStrokeColorRGB(.82,.85,.88)
    pdf.line(x,y+4,w-22,y+4);y-=14
    if valid:
        pdf.setFillColorRGB(.10,.38,.29)
        y=line(pdf,f"{result['aciertos']} de {result['preguntas']} aciertos - "
               f"{result['porcentaje']}%",x,y,max_width,
               size=14,strong=True,leading=19)
    else:
        pdf.setFillColorRGB(.56,.30,.08)
        y=line(pdf,"RESULTADO PENDIENTE",x,y,max_width,
               size=12,strong=True,leading=17)
        y=line(pdf,"Sin nota definitiva hasta resolver la aclaracion.",
               x,y,max_width,size=8,leading=12)
    y-=10
    pdf.setFillColorRGB(.12,.24,.32)
    y=line(pdf,"Ultima revision: "+last_name,x,y,max_width,
           size=9,strong=True,limit=2)
    y=line(pdf,"Fecha UTC: "+str(last_time),x,y,max_width,size=8)
    if approval:
        y=line(pdf,"Aprobo: "+approval["operador"]+" "+approval["fecha"],
               x,y,max_width,size=8,limit=2)
    y-=10
    y=line(pdf,"HISTORIAL DE CAMBIOS",x,y,max_width,
           size=10,strong=True,leading=13)
    for entry in changes[-4:]:
        old=entry["anterior"] or "—"
        new=entry["nueva"] or "—"
        q="P"+str(entry["pregunta"]) if entry["pregunta"] else "Hoja"
        y=line(pdf,entry["tipo"]+" "+q+": "+old+" > "+new,
               x,y,max_width,size=8,strong=True)
        y=line(pdf,entry["operador"]+" · "+entry["fecha"],
               x,y,max_width,size=7,leading=10,limit=2)
        y-=4
    if not changes:
        y=line(pdf,"Sin cambios realizados desde esta interfaz.",
               x,y,max_width,size=8)
    y=max(34,y-7)
    pdf.setFillColorRGB(.35,.40,.44)
    line(pdf,"PDF original SHA256: "+record["archivo_sha"],x,y,max_width,
         size=7,leading=10,limit=2)
    pdf.setFont("Helvetica",7)
    pdf.drawString(22,17,"Original archivado intacto. Acetato: "+(
        "SI" if acetato else "NO"))
    pdf.drawRightString(w-22,17,"UTC "+datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M"))
    pdf.showPage();pdf.save()
    return out.getvalue()
