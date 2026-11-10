"""Relectura administrativa del PDF ya archivado, conservando evidencia humana."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import cv2
import fitz
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from omr_evaluaciones.motor import (
    PAPERS, RENDER_DPI, bubble_positions, create_forms_pdf,
)
from omr_web.app import create_app


def make_scan(store, sid, temp: Path) -> Path:
    """Genera PDF ficticio con QR auténtico y dos marcas nítidas."""
    paper="Carta"
    original=create_forms_pdf(store,sid,temp/"printed.pdf")
    with fitz.open(original) as doc:
        pix=doc[0].get_pixmap(matrix=fitz.Matrix(
            RENDER_DPI/72.,RENDER_DPI/72.),alpha=False)
        image=np.frombuffer(pix.samples,dtype=np.uint8).reshape(
            pix.height,pix.width,pix.n).copy()
    w,h=PAPERS[paper];factor=RENDER_DPI/72.
    for i,positions in enumerate(bubble_positions(paper,2)):
        x,y=positions[i]
        cx,cy=round(x*factor),round((h-y)*factor)
        cv2.circle(image,(cx,cy),round(5.5*factor),
                   (110,110,110),-1,lineType=cv2.LINE_AA)
    dest=temp/"scan.pdf"
    canvas=Canvas(str(dest),pagesize=PAPERS[paper])
    canvas.drawImage(ImageReader(Image.fromarray(image)),0,0,width=w,height=h)
    canvas.showPage();canvas.save()
    return dest


def test_reanalyze_archived_pdf_improves_only_machine_reading(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    svc=app.state.engine
    svc.setup(svc._setup_token,"administrador","Admin",
              "ClaveTemporalSegura1234!")
    sid=svc.store.create_session(
        "Evaluación ficticia",
        [{"tema":"Equipo","pregunta":"Reactivo 1","correcta":"A"},
         {"tema":"Equipo","pregunta":"Reactivo 2","correcta":"B"}],
        [{"id":"P001","nombre":"Persona de prueba"}],"Carta")
    source=make_scan(svc.store,sid,tmp_path)
    with TestClient(app) as client:
        login=client.post("/api/login",json={
            "usuario":"administrador","password":"ClaveTemporalSegura1234!"})
        assert login.status_code==200
        header={"X-CSRF-Token":client.cookies.get("omr_csrf")}
        scanned=client.post("/api/scans",headers=header,files={
            "file":("scan.pdf",source.read_bytes(),"application/pdf")})
        assert scanned.status_code==200,scanned.text
        svc._process_pending()
        first=client.get("/api/jobs/"+scanned.json()["trabajo_id"]).json()
        assert first["estado"]=="terminado",first
        digest=first["resultado"]["sha"]
        original=svc.store.pages(sid)[0]
        assert original["estado"]=="validada",original
        first_doc=client.get("/api/documents").json()[0]
        assert first_doc["veces_recibido"]==1
        original_id=original["id"]
        original_token=original["token"]
        old_image=original["imagen"]

        # Simular un resultado del lector anterior, sin revisión humana.
        with svc.store.connect() as db:
            db.execute("""UPDATE hojas SET estado='revisar',
                respuestas_json=?,dudas_json=? WHERE id=?""",(
                json.dumps([None,None]),
                json.dumps([{"pregunta":1,"razon":"Lector antiguo"},
                            {"pregunta":2,"razon":"Lector antiguo"}]),
                original_id))
        # Solo el administrador con CSRF puede iniciar nueva lectura.
        assert client.post(f"/api/documents/{digest}/reanalyze").status_code==403
        bad=client.post("/api/documents/"+("z"*64)+"/reanalyze",
                        headers=header)
        assert bad.status_code==422
        re=client.post(f"/api/documents/{digest}/reanalyze",headers=header)
        assert re.status_code==200,re.text
        dup=client.post(f"/api/documents/{digest}/reanalyze",headers=header)
        assert dup.status_code==200,dup.text
        assert dup.json()["trabajo_id"]==re.json()["trabajo_id"]
        assert dup.json()["reutilizado"] is True
        svc._process_pending()
        finish=client.get("/api/jobs/"+re.json()["trabajo_id"]).json()
        assert finish["estado"]=="terminado",finish
        data=finish["resultado"]["aplicaciones"][0]
        assert data["reprocesadas"]==1,data
        assert client.get("/api/documents").json()[0]["veces_recibido"]==1
        assert data["comparacion"]==[{
            "pagina":1,"antes":2,"despues":0,
            "estado":"validada","mejora_aplicada":True}],data
        after=svc.store.pages(sid)
        assert len(after)==1
        assert after[0]["id"]==original_id
        assert after[0]["token"]==original_token
        assert after[0]["imagen"]!=old_image
        assert Path(old_image).is_file(), "Se conserva evidencia previa"
        assert after[0]["respuestas"]==["A","B"]
        assert after[0]["dudas"]==[]

        # La segunda relectura no debe duplicar la hoja.
        repeated=client.post(f"/api/documents/{digest}/reanalyze",headers=header)
        svc._process_pending()
        second=client.get("/api/jobs/"+repeated.json()["trabajo_id"]).json()
        assert second["estado"]=="terminado",second
        assert second["resultado"]["aplicaciones"][0]["comparacion"][0]["despues"]==0
        assert len(svc.store.pages(sid))==1

        # Un capturista corrigió una marca: el lector no podrá borrarla.
        with svc.store.connect() as db:
            db.execute("""UPDATE hojas SET estado='revisar',
                respuestas_json=?,dudas_json=? WHERE id=?""",(
                json.dumps([None,"B"]),
                json.dumps([{"pregunta":1,"razon":"Duda humana"}]),
                original_id))
        svc.store.review(original_id,1,"B","Marca cotejada con original",
                         reviewer="Auxiliar")
        manually_reviewed=svc.store.pages(sid)[0]
        assert manually_reviewed["respuestas"]==["B","B"]
        assert manually_reviewed["estado"]=="validada"
        final=client.post(f"/api/documents/{digest}/reanalyze",headers=header)
        svc._process_pending()
        result=client.get("/api/jobs/"+final.json()["trabajo_id"]).json()
        assert result["estado"]=="terminado"
        assert svc.store.pages(sid)[0]["respuestas"]==["B","B"]
        assert len(svc.store.pages(sid))==1
        assert result["resultado"]["aplicaciones"][0]["reprocesadas"]==0
    svc.close()
