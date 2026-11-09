"""Regresión web offline y dos capturistas, sin archivos reales.

Pruebas negativas: permisos, concurrencia, revisión optimista, privacidad,
sesiones y recuperación. El motor OMR sigue probándose en la suite original.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
import sqlite3
import json
import pytest
from fastapi.testclient import TestClient

from omr_evaluaciones.motor import create_forms_pdf
from omr_web.app import create_app
from omr_web.service import WebService, WebError


@pytest.fixture()
def server(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    service=app.state.engine
    service.setup(service._setup_token,"administrador","Admin Prueba",
                  "ClaveTemporalSegura1234!")
    client=TestClient(app)
    r=client.post("/api/login",json={
        "usuario":"administrador","password":"ClaveTemporalSegura1234!"})
    assert r.status_code==200,r.text
    csrf=client.cookies.get("omr_csrf")
    assert csrf
    yield app,client,{"X-CSRF-Token":csrf}
    client.close()
    service.close()


def test_primer_arranque_sin_cuenta_y_token_obligatorio(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    c=TestClient(app)
    assert c.get("/api/setup/status").json()["necesita_configuracion"] is True
    assert c.post("/api/setup",json={"token":"incorrecto","usuario":"admin",
        "nombre":"Admin","password":"123456789012"}).status_code==403
    assert c.get("/api/applications").status_code==401
    app.state.engine.close()


def test_seguridad_login_csrf_roles_y_asignaciones(server):
    app,c,headers=server
    svc=app.state.engine
    # CSRF: una cookie de sesión por sí sola nunca autoriza mutaciones.
    assert c.post("/api/users",json={"usuario":"captura1","nombre":"Uno",
        "password":"ClaveCapturaSegura1234","rol":"capturista"}).status_code==403
    created=c.post("/api/users",headers=headers,json={
        "usuario":"captura1","nombre":"Uno",
        "password":"ClaveCapturaSegura1234","rol":"capturista"})
    assert created.status_code==200,created.text
    assert "password_hash" not in created.text
    uid=created.json()["id"]
    sid=svc.store.create_session("Cabos",[
        {"tema":"Operativo","pregunta":"Reactivo 1","correcta":"A"},
        {"tema":"Operativo","pregunta":"Reactivo 2","correcta":"B"}],
        [{"id":"A001","nombre":"Persona Ficticia"}],"Carta")
    r=c.post("/api/assignments",headers=headers,
             json={"usuario_id":uid,"sesion_id":sid})
    assert r.status_code==200,r.text
    with TestClient(app) as reviewer:
        login=reviewer.post("/api/login",json={
            "usuario":"captura1","password":"ClaveCapturaSegura1234"})
        assert login.status_code==200
        assert reviewer.get("/api/applications").json()[0]["id"]==sid
        assert reviewer.get("/api/users").status_code==403
        assert reviewer.post("/api/applications",json={},headers={
            "X-CSRF-Token":reviewer.cookies.get("omr_csrf")}).status_code in (403,422)
        assert reviewer.get("/api/applications/"+sid+"/results").status_code==403
        assert reviewer.get("/api/applications/"+sid+"/questions").status_code==200
        response=reviewer.get("/api/applications/"+sid+"/questions")
        assert "correcta" not in response.text
        assert "clave_hmac" not in response.text


def make_pending(svc,sid=None):
    if sid is None:
        sid=svc.store.create_session("Prueba de Cabos",[
            {"tema":"Trabajo","pregunta":"¿Qué hacer primero?","correcta":"A"},
            {"tema":"Seguridad","pregunta":"¿Cómo responder?","correcta":"D"}],
            [{"id":"A001","nombre":"Participante Ficticio"}],"Carta")
    tok=svc.store.session(sid)["personal"][0]["token"]
    import numpy as np
    blank=np.full((2200,1700,3),255,dtype=np.uint8)
    uid,_=svc.store.register_page(sid,secrets.token_hex(32),0,blank,tok,
             [None,None],[{"pregunta":1,"razon":"Marca doble"},
                          {"pregunta":2,"razon":"Lápiz tenue"}],"revisar")
    return sid,uid


def user_for(svc,username,password,role, sid,admin):
    uid=svc.add_user(admin,username,username,password,role)
    svc.assign(admin,uid,sid)
    token,csrf,u=svc.login(username,password)
    return svc.authenticate(token),token,csrf


def test_concurrencia_dos_capturistas_un_solo_reclamo(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    svc.setup(svc._setup_token,"administrador","Admin","AdminSeguro123456")
    token,csrf,_=svc.login("administrador","AdminSeguro123456")
    admin=svc.authenticate(token)
    sid,sheet=make_pending(svc)
    a,*_=user_for(svc,"capturista1","CapturistaUno2026!","capturista",sid,admin)
    b,*_=user_for(svc,"capturista2","CapturistaDos2026!","capturista",sid,admin)
    def attempt(u):
        try:
            return svc.claim(u,sheet)["lease"]
        except WebError as exc:
            return exc.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,(a,b)))
    assert sum(isinstance(x,str) for x in results)==1
    assert results.count(409)==1
    assert svc.store.pages(sid)[0]["estado"]=="revisar"
    svc.close()


def test_revision_optimista_y_bitacora_integras(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    svc.setup(svc._setup_token,"administrador","Admin","AdminSeguro123456")
    token,csrf,_=svc.login("administrador","AdminSeguro123456")
    admin=svc.authenticate(token)
    sid, sheet=make_pending(svc)
    user,*_=user_for(svc,"capturista1","CapturistaUno2026!","capturista",sid,admin)
    claimed=svc.claim(user,sheet)
    lease=claimed["lease"]
    first=svc.save_decisions(user,sheet,lease,0,
                 [{"pregunta":1,"decision":"A"}],"Cotejo de evidencia")
    assert first["revision"]==1 and first["pendientes"]==1
    with pytest.raises(WebError) as old:
        svc.save_decisions(user,sheet,lease,0,
                 [{"pregunta":2,"decision":"B"}],"Cliente desactualizado")
    assert old.value.status==409
    final=svc.save_decisions(user,sheet,lease,1,
                 [{"pregunta":2,"decision":"BLANCO"}],"Marca doble verificada")
    assert final["estado"]=="validada"
    results=svc.store.results(sid)
    assert results["validados"]==1
    assert len(svc.store.revisions(sid))==2
    assert len(svc.list_events(user,sid))>=3
    svc.release(user,sheet,lease)
    svc.approve(admin,sheet)
    with svc.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM web_aprobaciones").fetchone()[0]==1
    svc.close()


def test_api_correccion_guarda_decision_y_no_expone_clave(server):
    app,c,headers=server
    sid,sheet=make_pending(app.state.engine)
    claim=c.post("/api/sheets/"+sheet+"/claim",headers=headers)
    assert claim.status_code==200,claim.text
    lease=claim.json()["lease"]
    obj=c.get("/api/sheets/"+sheet)
    assert obj.status_code==200
    assert obj.json()["preguntas"][0]["numero"]==1
    assert "correcta" not in obj.text
    result=c.put("/api/sheets/"+sheet+"/decisions",headers=headers,json={
        "lease":lease,"expected_revision":0,
        "cambios":[{"pregunta":1,"decision":"A"}],
        "motivo":"Revisión sobre evidencia escaneada"})
    assert result.status_code==200,result.text
    assert result.json()["revision"]==1
    assert c.get("/api/sheets/"+sheet+"/image").status_code==200
    assert c.get("/api/applications/"+sid+"/results").status_code==200
    assert "clave_hmac" not in c.get("/api/applications/"+sid+"/results").text


def test_escaneo_en_segundo_plano_y_reinicio_sin_duplicar(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    svc.setup(svc._setup_token,"administrador","Admin","AdminSeguro123456")
    token,csrf,_=svc.login("administrador","AdminSeguro123456")
    admin=svc.authenticate(token)
    sid=svc.store.create_session("Cabos",[
        {"tema":"A","pregunta":"Pregunta 1","correcta":"A"}],
        [{"id":"A001","nombre":"Ficticio"}],"Carta")
    paper=create_forms_pdf(svc.store,sid,tmp_path/"un_folio.pdf")
    jid=svc.add_job(admin,paper)
    svc.close()
    # Simular cierre entre la recepción de PDF y su lectura.
    resumed=WebService(tmp_path,start_workers=False)
    resumed._process_pending()
    status=resumed.job(admin,jid)
    assert status["estado"]=="terminado"
    assert status["resultado"]["total"]==1
    assert len(resumed.inbox.documents())==1
    assert len(resumed.store.pages(sid))==1
    # El mismo lote no crea una segunda hoja.
    jid2=resumed.add_job(admin,paper)
    resumed._process_pending()
    assert resumed.job(admin,jid2)["estado"]=="terminado"
    assert len(resumed.store.pages(sid))==1
    assert resumed.inbox.documents()[0]["veces_recibido"]==2
    resumed.close()


def test_rutas_privadas_y_archivos_restringidos(server):
    app,c,headers=server
    svc=app.state.engine
    sid,sheet=make_pending(svc)
    assert c.get("/api/applications/"+sid+"/files/../../datos/omr/sesiones.sqlite3").status_code==404
    assert c.get("/api/documents/"+"f"*64+"/pages").status_code==200
    assert c.get("/api/documents").status_code==200
    assert "ruta" not in c.get("/api/documents").text


def test_no_se_duplica_calificacion_en_pdf_con_identidad_distinta(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    svc.setup(svc._setup_token,"administrador","Admin","AdminSeguro123456")
    tok,_,_=svc.login("administrador","AdminSeguro123456")
    admin=svc.authenticate(tok)
    s1=svc.store.create_session("Cabos",[
        {"tema":"A","pregunta":"P1","correcta":"A"}],
        [{"id":"01","nombre":"Uno"}],"Carta")
    s2=svc.store.create_session("Checadores",[
        {"tema":"A","pregunta":"P1","correcta":"B"}],
        [{"id":"02","nombre":"Dos"}],"Carta")
    from pypdf import PdfReader,PdfWriter
    combined=PdfWriter()
    for sid in (s1,s2):
        path=create_forms_pdf(svc.store,sid,tmp_path/(sid+".pdf"))
        combined.append(PdfReader(str(path)))
    mixed=tmp_path/"mixed.pdf"
    with mixed.open("wb") as f: combined.write(f)
    job=svc.add_job(admin,mixed)
    svc._process_pending()
    data=svc.job(admin,job)
    assert data["estado"]=="terminado",data
    assert data["resultado"]["total"]==2
    assert len(data["resultado"]["aplicaciones"])==2
    assert len(svc.store.pages(s1))==1
    assert len(svc.store.pages(s2))==1
    svc.close()
