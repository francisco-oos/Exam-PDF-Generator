"""Re-corrección sin pérdida de evidencia, PDF auditado y permisos.

Fixturas locales ficticias: sin ZIP Xerox real, contraseñas de usuarios
reales, QR privados ni archivos fuera del directorio temporal.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
import numpy as np
from fastapi.testclient import TestClient

from omr_web.app import create_app


def _new_session(svc,seed="A001"):
    sid=svc.store.create_session(
        "Prueba de revisión auditada",[
            {"tema":"Seguridad","pregunta":"Pregunta uno","correcta":"A"},
            {"tema":"Material","pregunta":"Pregunta dos","correcta":"B"}],
        [{"id":seed,"nombre":"Persona ficticia"}],"Carta")
    token=svc.store.session(sid)["personal"][0]["token"]
    image=np.full((2200,1700,3),255,dtype=np.uint8)
    sheet,kind=svc.store.register_page(
        sid,seed.encode().hex().ljust(64,"0"),0,image,token,
        [None,None],
        [{"pregunta":1,"razon":"Grafito tenue"},
         {"pregunta":2,"razon":"Tachadura posible"}],"revisar")
    assert kind=="revisar"
    return sid,sheet


def _login(client,name,password):
    response=client.post("/api/login",json={
        "usuario":name,"password":password})
    assert response.status_code==200,response.text
    return {"X-CSRF-Token":client.cookies.get("omr_csrf")}


def test_pdf_lateral_reapertura_nota_historial_y_persistencia(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    svc=app.state.engine
    svc.setup(svc._setup_token,"adminprueba","Admin de prueba",
              "ClaveTemporalSegura123!")
    with TestClient(app) as c:
        head=_login(c,"adminprueba","ClaveTemporalSegura123!")
        admin=svc.authenticate(c.cookies.get("omr_sid"))
        sid,sheet=_new_session(svc)
        source=Path(svc.store.pages(sid)[0]["imagen"])
        old_sha=hashlib.sha256(source.read_bytes()).hexdigest()
        # Una hoja pendiente nunca genera nota definitiva.
        pending=c.get("/api/sheets/"+sheet+"/evidence")
        assert pending.status_code==200,pending.text[:150]
        with fitz.open(stream=pending.content,filetype="pdf") as pdf:
            text=pdf[0].get_text()
            assert "RESULTADO PENDIENTE" in text
            assert "PILOTO" in text

        first=c.post("/api/sheets/"+sheet+"/claim",headers=head)
        assert first.status_code==200,first.text
        lease=first.json()
        reviewed=c.put("/api/sheets/"+sheet+"/decisions",headers=head,json={
            "lease":lease["lease"],"expected_revision":lease["revision"],
            "cambios":[{"pregunta":1,"decision":"A"},
                       {"pregunta":2,"decision":"B"}],
            "motivo":"Cotejo del papel por auxiliar de prueba"})
        assert reviewed.status_code==200,reviewed.text
        assert reviewed.json()["estado"]=="validada"
        history=c.get("/api/sheets/"+sheet+"/history").json()
        assert len(history["cambios"])==2
        assert history["cambios"][0]["anterior"]=="BLANCO"
        assert history["cambios"][0]["nueva"]=="A"
        assert history["cambios"][0]["operador"]=="Admin de prueba"
        assert history["cambios"][0]["aciertos_despues"]==2
        assert c.post("/api/sheets/"+sheet+"/release",headers=head,
                      json={"lease":lease["lease"]}).status_code==200

        report=c.get("/api/applications/"+sid+"/results").json()
        p=report["participantes"][0]
        assert p["hoja_id"]==sheet and p["estado"]=="validado"
        assert p["aciertos"]==2 and p["preguntas"]==2
        assert p["porcentaje"]==100.
        assert p["areas_mejora"]==[]

        evidence=c.get("/api/sheets/"+sheet+"/evidence?acetato=true")
        assert evidence.status_code==200
        with fitz.open(stream=evidence.content,filetype="pdf") as pdf:
            assert len(pdf)==1
            text=pdf[0].get_text()
            assert "2 de 2 aciertos" in text
            assert "Admin de prueba" in text
            assert "PILOTO" in text
            assert len(pdf[0].get_images(full=True))>=1
        receipt=c.get("/api/applications/"+sid+"/participants/A001/result")
        assert receipt.status_code==200,receipt.text[:120]
        with fitz.open(stream=receipt.content,filetype="pdf") as pdf:
            assert len(pdf)>=2
            assert "Resultado individual" in pdf[0].get_text()
            assert "EVIDENCIA" in pdf[-1].get_text()

        # No se puede alterar silenciosamente una hoja cerrada.
        blocked=c.post("/api/sheets/"+sheet+"/claim",headers=head)
        assert blocked.status_code==200
        direct=c.put("/api/sheets/"+sheet+"/decisions",headers=head,json={
            "lease":blocked.json()["lease"],
            "expected_revision":blocked.json()["revision"],
            "cambios":[{"pregunta":1,"decision":"B"}],
            "motivo":"Intento directo sin reapertura"})
        assert direct.status_code==409
        assert c.post("/api/sheets/"+sheet+"/release",headers=head,
                      json={"lease":blocked.json()["lease"]}).status_code==200

        assert c.post("/api/sheets/"+sheet+"/reopen",json={
            "pregunta":1,"motivo":"Aclaracion por apelacion"}).status_code==403
        short=c.post("/api/sheets/"+sheet+"/reopen",headers=head,json={
            "pregunta":1,"motivo":"x"})
        assert short.status_code==422
        opened=c.post("/api/sheets/"+sheet+"/reopen",headers=head,json={
            "pregunta":1,"motivo":"Se solicita nuevo cotejo de la pregunta 1"})
        assert opened.status_code==200,opened.text
        assert opened.json()["aciertos_anteriores"]==2
        assert svc.store.pages(sid)[0]["estado"]=="revisar"
        assert c.get("/api/applications/"+sid+"/results").json()[
            "participantes"][0]["aciertos"] is None
        with fitz.open(stream=c.get(
                "/api/sheets/"+sheet+"/evidence").content,filetype="pdf") as pdf:
            assert "RESULTADO PENDIENTE" in pdf[0].get_text()
        again=c.post("/api/sheets/"+sheet+"/reopen",headers=head,json={
            "pregunta":1,"motivo":"Reapertura repetida mientras hay duda"})
        assert again.status_code==409

        lease=c.post("/api/sheets/"+sheet+"/claim",headers=head)
        assert lease.status_code==200,lease.text
        fixed=c.put("/api/sheets/"+sheet+"/decisions",headers=head,json={
            "lease":lease.json()["lease"],
            "expected_revision":lease.json()["revision"],
            "cambios":[{"pregunta":1,"decision":"B"}],
            "motivo":"Aclaración tras observar la marca en la copia física"})
        assert fixed.status_code==200,fixed.text
        assert fixed.json()["estado"]=="validada"
        final=c.get("/api/applications/"+sid+"/results").json()
        assert final["participantes"][0]["aciertos"]==1
        history=c.get("/api/sheets/"+sheet+"/history").json()
        assert [x["tipo"] for x in history["cambios"]]==[
            "CORRECCION","CORRECCION","REAPERTURA","CORRECCION"]
        last=history["cambios"][-1]
        assert (last["anterior"],last["nueva"])==("A","B")
        assert (last["aciertos_antes"],last["aciertos_despues"])==(2,1)
        assert "marca" in last["motivo"]
        assert hashlib.sha256(source.read_bytes()).hexdigest()==old_sha
        assert len(svc.store.pages(sid))==1
    svc.close()

    second=create_app(tmp_path,start_workers=False)
    assert len(second.state.engine.sheet_history(
        second.state.engine.authenticate(
            _auth_token_for_test(second,"adminprueba","ClaveTemporalSegura123!")),
        sheet)["cambios"])==4
    second.state.engine.close()


def _auth_token_for_test(app,name,password):
    token,csrf,user=app.state.engine.login(name,password)
    return token


def test_auxiliar_sin_acetato_no_reabre_hojas_ni_consulta_historial(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    svc=app.state.engine
    svc.setup(svc._setup_token,"adminprueba","Admin",
              "ClaveTemporalSegura123!")
    with TestClient(app) as c:
        headers=_login(c,"adminprueba","ClaveTemporalSegura123!")
        admin=svc.authenticate(c.cookies.get("omr_sid"))
        sid,sheet=_new_session(svc)
        uid=svc.add_user(admin,"auxiliar01","Auxiliar de prueba",
                         "ClaveInicialPrueba123!","capturista")
        svc.assign(admin,uid,sid)
        with TestClient(app) as helper:
            h1=_login(helper,"auxiliar01","ClaveInicialPrueba123!")
            changed=helper.post("/api/change-password",headers=h1,json={
                "anterior":"ClaveInicialPrueba123!",
                "nueva":"ClaveDefinitivaPrueba123!"})
            assert changed.status_code==200,changed.text
            _login(helper,"auxiliar01","ClaveDefinitivaPrueba123!")
            h2={"X-CSRF-Token":helper.cookies.get("omr_csrf")}
            assert helper.get("/api/sheets/"+sheet+"/history").status_code==403
            assert helper.get("/api/sheets/"+sheet+"/evidence").status_code==403
            assert helper.get(
                "/api/sheets/"+sheet+"/evidence?acetato=false").status_code==403
            assert helper.post("/api/sheets/"+sheet+"/reopen",
                headers=h2,json={"pregunta":1,
                    "motivo":"Quiero modificar la clave ya revisada"}).status_code==403
        assert c.get("/api/sheets/"+sheet+"/history").status_code==200
    svc.close()



def test_expediente_zip_incluye_evidencia_auditada_sin_sustituir_original(tmp_path):
    """Una hoja de aplicación real entra al ZIP interno con PDF auditado."""
    from io import BytesIO
    from zipfile import ZipFile
    from omr_evaluaciones.motor import create_forms_pdf

    app=create_app(tmp_path,start_workers=False)
    svc=app.state.engine
    svc.setup(svc._setup_token,"adminprueba","Admin",
              "ClaveTemporalSegura123!")
    sid=svc.store.create_session(
        "Evaluación con evidencia",[
            {"tema":"Seguridad","pregunta":"Seguridad","correcta":"A"}],
        [{"id":"P004","nombre":"Persona ficticia 4"}],"Carta")
    pdf=create_forms_pdf(svc.store,sid,tmp_path/"hoja_original.pdf")
    source_sha=hashlib.sha256(pdf.read_bytes()).hexdigest()
    with TestClient(app) as c:
        headers=_login(c,"adminprueba","ClaveTemporalSegura123!")
        user=svc.authenticate(c.cookies.get("omr_sid"))
        job=svc.add_job(user,pdf)
        svc._process_pending()
        result=svc.job(user,job)
        assert result["estado"]=="terminado",result
        assert result["resultado"]["sha"]==source_sha
        sheet=svc.store.pages(sid)[0]
        if sheet["estado"]=="revisar":
            claim=svc.claim(user,sheet["id"])
            svc.save_decisions(user,sheet["id"],claim["lease"],
                claim["revision"],[{"pregunta":1,"decision":"A"}],
                "Cotejo físico del examen de prueba")
            svc.release(user,sheet["id"],claim["lease"])
        assert svc.store.pages(sid)[0]["estado"]=="validada"
        original=svc.inbox.original(source_sha)
        sha_before=hashlib.sha256(original.read_bytes()).hexdigest()
        archive=c.get("/api/applications/"+sid+"/export?internal=true")
        assert archive.status_code==200,archive.text[:150]
        with ZipFile(BytesIO(archive.content)) as zipped:
            names=zipped.namelist()
            audited=[x for x in names if x.startswith(
                "Evidencias_auditadas/") and x.endswith(".pdf")]
            assert len(audited)==1,names
            with fitz.open(stream=zipped.read(audited[0]),filetype="pdf") as rendered:
                text=rendered[0].get_text()
                assert "1 de 1 aciertos" in text
                assert "PILOTO" in text
                assert "Persona ficticia 4" in text
            assert "Evidencias_Ordenadas.pdf" in names
            assert "Bitacora_Revisiones_Detallada.pdf" in names
            with fitz.open(stream=zipped.read(
                    "Bitacora_Revisiones_Detallada.pdf"),filetype="pdf") as history:
                assert "Bitacora detallada" in history[0].get_text()
            import json
            manifest=json.loads(zipped.read("Manifiesto.json"))
            assert audited[0] in manifest["archivos_sha256"]
            assert manifest["archivos_sha256"][audited[0]]==hashlib.sha256(
                zipped.read(audited[0])).hexdigest()
        assert hashlib.sha256(original.read_bytes()).hexdigest()==sha_before
    svc.close()
