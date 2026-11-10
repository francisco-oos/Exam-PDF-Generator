"""Dos maneras de calificar: QR firmado o vinculación manual a biblioteca.

No atribuir identidad por OCR, ni dar resultados automáticos a hojas sin QR.
Prueba con PDF ficticio, en directorio aislado, sin los ZIP privados del usuario.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from biblioteca import save_exam
from src.evaluaciones.core import Question
from omr_evaluaciones.motor import create_generic_forms_pdf
from omr_web.app import create_app


def test_archivo_sin_qr_asociacion_manual_exige_todas_las_respuestas(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    service=app.state.engine
    service.setup(service._setup_token,"administrador","Admin ficticio",
                  "ClaveSegura123456!")
    with TestClient(app) as c:
        assert c.post("/api/login",json={
            "usuario":"administrador","password":"ClaveSegura123456!"}).status_code==200
        headers={"X-CSRF-Token":c.cookies.get("omr_csrf")}
        source=save_exam(service.library,
            nombre="Cabos de prueba",titulo="Evaluación de cabos",
            empresa="Empresa ficticia",grupo="Turno C",subtitulo="Prueba",
            instrucciones="Marca una respuesta",
            questions=[Question("Seguridad",f"Pregunta simulada {n}",
               ("Opción A","Opción B","Opción C","Opción D"),(n-1)%4)
               for n in range(1,21)],tamano_papel="Carta")
        original=create_generic_forms_pdf([
            {"tema":"Seguridad","pregunta":f"Pregunta simulada {n}",
             "correcta":"ABCD"[(n-1)%4]} for n in range(1,21)],
             "Evaluación ficticia","Carta",tmp_path/"scan_sin_qr.pdf")
        admin=service.authenticate(c.cookies.get("omr_sid"))
        job=service.add_job(admin,original)
        service._process_pending()
        imported=service.job(admin,job)
        assert imported["estado"]=="terminado"
        assert imported["resultado"]["sin_identificar"]==1
        digest=imported["resultado"]["sha"]
        assert service.inbox.pages(digest)[0]["estado"]=="pendiente"
        assert not service.store.sessions()

        request={"cuestionario_id":source,"id":"P001",
                 "nombre":"Participante simulado","papel":"Carta",
                 "motivo":"Identidad verificada contra registro físico"}
        linked=c.post(f"/api/documents/{digest}/pages/0/manual",
                      json=request,headers=headers)
        assert linked.status_code==200,linked.text
        result=linked.json()
        assert result["modo"]=="manual"
        assert result["requiere_captura_completa"] is True
        assert result["biblioteca"]=="Cabos de prueba"
        assert result["folio"].startswith("EX-")
        sid=result["sesion_id"]
        detail=c.get("/api/sheets/"+result["hoja_id"])
        assert detail.status_code==200
        assert detail.json()["participante"]=="Participante simulado"
        assert detail.json()["biblioteca"]=="Cabos de prueba"
        assert detail.json()["revision_biblioteca"]==1
        assert detail.json()["folio"]==result["folio"]
        page=service.store.pages(sid)[0]
        assert page["estado"]=="revisar"
        assert len(page["dudas"])==20
        assert all(x is None for x in page["respuestas"])
        assert service.store.results(sid)["validados"]==0
        assert service.inbox.pages(digest)[0]["estado"]=="manual_pendiente"
        assert c.post(f"/api/documents/{digest}/pages/0/manual",
                      json=request,headers=headers).status_code==409
        assert len(service.store.sessions())==1

        claim=c.post("/api/sheets/"+result["hoja_id"]+"/claim",headers=headers)
        assert claim.status_code==200,claim.text
        lease=claim.json()
        changes=[{"pregunta":i,"decision":"ABCD"[(i-1)%4]}
                 for i in range(1,21)]
        reviewed=c.put("/api/sheets/"+result["hoja_id"]+"/decisions",
            headers=headers,json={"lease":lease["lease"],
               "expected_revision":lease["revision"],
               "cambios":changes,
               "motivo":"Veinte marcas cotejadas con hoja escaneada"})
        assert reviewed.status_code==200,reviewed.text
        assert service.store.results(sid)["validados"]==1
        assert c.get("/api/applications/"+sid+"/participants/P001/result").status_code==200
        assert service.inbox.pages(digest)[0]["estado"]=="procesada_manual"
    service.close()


def test_manual_no_acepta_datos_incorrectos_ni_inventa_folios(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    svc=app.state.engine
    svc.setup(svc._setup_token,"administrador","Admin","ClaveSegura123456!")
    with TestClient(app) as c:
        c.post("/api/login",json={"usuario":"administrador","password":"ClaveSegura123456!"})
        headers={"X-CSRF-Token":c.cookies.get("omr_csrf")}
        uri="/api/documents/"+("f"*64)+"/pages/0/manual"
        bad=c.post(uri,headers=headers,json={
            "cuestionario_id":"nada","id":"P001","nombre":"Persona",
            "motivo":"Justificación ficticia de prueba"})
        assert bad.status_code==422
        assert not svc.store.sessions()
        assert c.post(uri,json={},headers=headers).status_code in (422,409)
        assert not svc.store.sessions()
    svc.close()
