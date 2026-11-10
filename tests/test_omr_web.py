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
        # Una contraseña temporal NO autoriza consultar aplicaciones.
        assert reviewer.get("/api/applications").status_code==403
        changed=reviewer.post("/api/change-password",
            headers={"X-CSRF-Token":reviewer.cookies.get("omr_csrf")},
            json={"anterior":"ClaveCapturaSegura1234",
                  "nueva":"ClaveCapturaDefinitiva1234!"})
        assert changed.status_code==200,changed.text
        login=reviewer.post("/api/login",json={
            "usuario":"captura1","password":"ClaveCapturaDefinitiva1234!"})
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
    # El primer acceso obliga a reemplazar la contraseña temporal;
    # la prueba ejercita el mismo proceso que se exige a una persona real.
    token,csrf,u=svc.login(username,password)
    current=svc.authenticate(token)
    permanent=password+"Nueva!"
    svc.change_password(current,password,permanent)
    token,csrf,u=svc.login(username,permanent)
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



def test_importacion_excel_y_emision_ecologica_de_folios_desde_web(server):
    from io import BytesIO
    from openpyxl import Workbook
    app,c,headers=server
    w=Workbook();s=w.active;s.title="Preguntas"
    s.append(["Tema","Pregunta","A","B","C","D","Correcta","Imagen"])
    s.append(["Material","¿Qué hacer con el material?",
              "Verificar","Descartar","Ignorar","Perder","A",""])
    b=BytesIO();w.save(b)
    response=c.post("/api/library/import?name=Prueba+web&title=Cabos",
        headers=headers,
        files={"file":("preguntas.xlsx",b.getvalue(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code==200,response.text
    exam_id=response.json()["cuestionario_id"]
    assert response.json()["preguntas"]==1
    assert len(c.get("/api/library").json())==1
    application=c.post("/api/applications",headers=headers,json={
        "cuestionario_id":exam_id,"nombre":"Cabos · turno C",
        "modalidad":"ecologico","papel":"Carta",
        "participantes":[{"id":"C001","nombre":"Participante de prueba"},
                         {"id":"C002","nombre":"Otra persona"}]})
    assert application.status_code==200,application.text
    sid=application.json()["sid"]
    assert len(app.state.engine.store.session(sid)["personal"])==2
    download=c.get("/api/applications/"+sid+"/files/Hoja_respuestas.pdf")
    assert download.status_code==200
    assert download.content.startswith(b"%PDF-")
    assert app.state.engine.store.session(sid)["cuestionario_id"]==exam_id
    assert len(c.get("/api/applications").json())==1


def test_material_impresion_aislado_por_rol_y_sin_rutas_de_servidor(server):
    """Ningún capturista/auditor recibe acetato, folios PDF ni paquetes."""
    from io import BytesIO
    from openpyxl import Workbook

    app,admin_client,admin_headers=server
    service=app.state.engine
    workbook=Workbook()
    worksheet=workbook.active
    worksheet.title="Preguntas"
    worksheet.append(["Tema","Pregunta","A","B","C","D","Correcta","Imagen"])
    worksheet.append(["Seguridad","¿Qué hacer?","Comprobar",
                      "Ignorar","Cerrar","Esperar","A",""])
    content=BytesIO()
    workbook.save(content)
    created=admin_client.post(
        "/api/library/import?name=Control+de+material&title=Prueba+de+permisos",
        headers=admin_headers,
        files={"file":("preguntas.xlsx",content.getvalue(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert created.status_code==200,created.text
    applied=admin_client.post("/api/applications",headers=admin_headers,json={
        "cuestionario_id":created.json()["cuestionario_id"],
        "nombre":"Aplicación privada",
        "modalidad":"normal","papel":"Carta",
        "participantes":[{"id":"P001","nombre":"Participante Ficticio"}]})
    assert applied.status_code==200,applied.text
    sid=applied.json()["sid"]
    url="/api/applications/"+sid+"/files/"
    assert "lote_path" not in admin_client.get("/api/applications").text
    for filename in ("Hoja_respuestas.pdf","Acetato_clave.pdf",
                     "Paquetes_individuales.zip"):
        response=admin_client.get(url+filename)
        assert response.status_code==200,(filename,response.text[:120])
    admin=service.authenticate(admin_client.cookies.get("omr_sid"))
    for role,expected in (("capturista",403),("auditor",403),
                          ("coordinador",200)):
        username="test_"+role
        temp="ClaveTemporalPrivada1234!"
        final="ClavePermanentePrivada1234!"
        user_id=service.add_user(admin,username,role,temp,role)
        service.assign(admin,user_id,sid)
        with TestClient(app) as client:
            assert client.post("/api/login",json={
                "usuario":username,"password":temp}).status_code==200
            updated=client.post("/api/change-password",
                headers={"X-CSRF-Token":client.cookies.get("omr_csrf")},
                json={"anterior":temp,"nueva":final})
            assert updated.status_code==200,updated.text
            assert client.post("/api/login",json={
                "usuario":username,"password":final}).status_code==200
            assert "lote_path" not in client.get("/api/applications").text
            for filename in ("Acetato_clave.pdf","Hoja_respuestas.pdf",
                             "Paquetes_individuales.zip","manifest.json"):
                result=client.get(url+filename)
                if role=="coordinador" and filename=="manifest.json":
                    assert result.status_code in (200,404)
                else:
                    assert result.status_code==expected,(role,filename,result.status_code)
            if role=="capturista":
                assert client.get("/api/applications/"+sid+"/questions").status_code==200


def test_revisor_solo_ve_respuestas_no_clave_ni_folios_ajenos(server):
    app,c,headers=server
    svc=app.state.engine
    sid1,sheet1=make_pending(svc)
    sid2,sheet2=make_pending(svc)
    uid=svc.add_user(svc.authenticate(c.cookies.get("omr_sid")),
                     "capturista3","Revisor 3","TemporalRevisor12345!",
                     "capturista")
    svc.assign(svc.authenticate(c.cookies.get("omr_sid")),uid,sid1)
    reviewer=TestClient(app)
    reviewer.post("/api/login",json={
        "usuario":"capturista3","password":"TemporalRevisor12345!"})
    reviewer.post("/api/change-password",
       headers={"X-CSRF-Token":reviewer.cookies.get("omr_csrf")},
       json={"anterior":"TemporalRevisor12345!",
             "nueva":"PermanenteRevisor12345!"})
    reviewer.post("/api/login",json={
        "usuario":"capturista3","password":"PermanenteRevisor12345!"})
    assert reviewer.get("/api/sheets/"+sheet1).status_code==200
    assert reviewer.get("/api/sheets/"+sheet2).status_code==403
    assert reviewer.get("/api/sheets/"+sheet2+"/image").status_code==403
    assert reviewer.get("/api/sheets/"+sheet2+"/overlay?pregunta=1").status_code==403
    assert reviewer.get("/api/sheets/"+sheet1+"/overlay?pregunta=1&acetato=true").status_code==403
    assert reviewer.get("/api/documents/"+"a"*64+"/pages").status_code==403
    assert reviewer.get("/api/applications/"+sid2+"/results").status_code==403
    reviewer.close()


def test_certificado_tls_local_no_exponer_clave(tmp_path,monkeypatch):
    from omr_web.certificate import main
    monkeypatch.setenv("OMR_WEB_DATA",str(tmp_path))
    main(["192.168.0.14"])
    private=tmp_path/"omr"/"certs"/"server.key"
    cert=tmp_path/"omr"/"certs"/"server.pem"
    assert private.exists() and cert.exists()
    assert b"PRIVATE KEY" in private.read_bytes()
    assert b"CERTIFICATE" in cert.read_bytes()
    with pytest.raises(SystemExit,match="No se sobrescribe"):
        main(["192.168.0.14"])
    with pytest.raises(SystemExit,match="privadas"):
        main(["8.8.8.8"])



def test_diez_capturistas_reciben_diez_hojas_diferentes(tmp_path):
    import numpy as np
    svc=WebService(tmp_path,start_workers=False)
    svc.setup(svc._setup_token,"administrador","Admin","AdminSeguro123456")
    token,_,_=svc.login("administrador","AdminSeguro123456")
    admin=svc.authenticate(token)
    questions=[{"tema":"Trabajo","pregunta":"¿Qué corresponde hacer?",
                "correcta":"A"}]
    people=[{"id":f"P{i:03d}","nombre":f"Ficticio {i}"}
            for i in range(1,16)]
    sid=svc.store.create_session("Examen",questions,people,"Carta")
    blank=np.full((2200,1700,3),255,dtype=np.uint8)
    for index,person in enumerate(svc.store.session(sid)["personal"]):
        svc.store.register_page(
            sid,secrets.token_hex(32),index,blank,person["token"],
            [None],[{"pregunta":1,"razon":"Doble marca"}],"revisar")
    reviewers=[user_for(svc,f"revision{i:02d}",f"ClaveRevisor{i:02d}2026!",
                        "capturista",sid,admin)[0]
               for i in range(10)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        claims=list(pool.map(lambda u:svc.claim_next(u,sid),reviewers))
    assert len({claim["hoja_id"] for claim in claims})==10
    assert len({claim["lease"] for claim in claims})==10
    with svc.store.connect() as db:
        active=db.execute("SELECT COUNT(*) FROM web_reclamos WHERE vence>0").fetchone()[0]
    assert active==10
    svc.close()


def test_cinco_capturistas_procesan_50_hojas_sin_duplicados(tmp_path):
    """W10 sintético: operaciones simultáneas, sin sustituir papel físico."""
    import numpy as np

    service=WebService(tmp_path,start_workers=False)
    service.setup(service._setup_token,"administrador","Admin","AdminSeguro123456")
    token,_,_=service.login("administrador","AdminSeguro123456")
    admin=service.authenticate(token)
    participants=[{"id":f"P{i:03d}","nombre":f"Persona de prueba {i}"}
                  for i in range(50)]
    sid=service.store.create_session(
        "Prueba de carga", [{"tema":"Material","pregunta":"Reactivo",
                             "correcta":"A"}],participants,"Carta")
    image=np.full((250,180,3),255,dtype=np.uint8)
    for index,participant in enumerate(service.store.session(sid)["personal"]):
        service.store.register_page(
            sid,secrets.token_hex(32),index,image,participant["token"],
            [None],[{"pregunta":1,"razon":"Marca ambigua"}],"revisar")
    users=[user_for(service,f"captura{i:02d}",f"TemporalRevision{i:02d}!",
                    "capturista",sid,admin)[0] for i in range(5)]

    def complete(user):
        processed=[]
        while True:
            try:
                claim=service.claim_next(user,sid)
            except WebError as exc:
                if exc.status==404:
                    break
                raise
            sheet_id=claim["hoja_id"]
            saved=service.save_decisions(
                user,sheet_id,claim["lease"],claim["revision"],
                [{"pregunta":1,"decision":"A"}],"Revisión de prueba")
            assert saved["estado"]=="validada"
            if not processed:
                # La reserva sigue vigente, pero una hoja validada ya no
                # permite que el capturista cambie respuestas de nuevo.
                with pytest.raises(WebError,match="requiere revisión del coordinador"):
                    service.save_decisions(
                        user,sheet_id,claim["lease"],saved["revision"],
                        [{"pregunta":1,"decision":"B"}],"Edición posterior")
            service.release(user,sheet_id,claim["lease"])
            processed.append(sheet_id)
        return processed

    with ThreadPoolExecutor(max_workers=5) as pool:
        completed=list(pool.map(complete,users))
    sheet_ids=[sid for part in completed for sid in part]
    assert len(sheet_ids)==50
    assert len(set(sheet_ids))==50
    assert service.store.results(sid)["validados"]==50
    with service.store.connect() as db:
        count=db.execute(
            "SELECT COUNT(*) FROM web_eventos WHERE accion='CORRECCION'"
        ).fetchone()[0]
        assert count==50
    with pytest.raises(WebError,match="requiere revisión del coordinador"):
        service.claim(users[0],sheet_ids[0])
    service.close()


def test_modo_produccion_bloqueado_sin_validador_licencia(tmp_path,monkeypatch):
    monkeypatch.setenv("OMR_WEB_MODE","production")
    with pytest.raises(RuntimeError,match="licencia central"):
        create_app(tmp_path,start_workers=False)
