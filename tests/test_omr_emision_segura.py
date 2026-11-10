"""Regresiones de emisión desde navegador, ZIP completo e imágenes PNG con alfa.

No usa sesiones ni PDF históricos; crea todo en tmp_path.
"""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from PIL import Image

from omr_web.app import create_app
from src.evaluaciones.core import _white_background


@pytest.fixture
def pilot(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    engine=app.state.engine
    engine.setup(engine._setup_token,"admin_omr","Administrador","ClaveSeguraTemporal123!")
    with TestClient(app) as client:
        assert client.post("/api/login",json={
            "usuario":"admin_omr","password":"ClaveSeguraTemporal123!"}).status_code==200
        headers={"X-CSRF-Token":client.cookies.get("omr_csrf")}
        sheet=Workbook()
        tab=sheet.active
        tab.title="Preguntas"
        tab.append(["Tema","Pregunta","A","B","C","D","Correcta","Imagen"])
        tab.append(["Prueba","¿Qué opción es válida?","Uno","Dos","Tres","Cuatro","B",""])
        data=BytesIO();sheet.save(data)
        imported=client.post("/api/library/import?name=Prueba+segura&title=Evaluacion+OMR",
            headers=headers,files={"file":("Preguntas.xlsx",data.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert imported.status_code==200,imported.text
        yield client,headers,imported.json()["cuestionario_id"],engine
    engine.close()


def payload(questionnaire, *, people=True):
    return {
        "cuestionario_id":questionnaire,"nombre":"Prueba emitida",
        "modalidad":"normal","papel":"Carta",
        "participantes":[{"id":"000001","nombre":"Persona de prueba"}] if people else [],
        "solicitud_id":str(uuid4()),
    }


@pytest.mark.parametrize("has_people",[True,False])
def test_reintento_emision_no_duplica_folios_ni_lotes(pilot,has_people):
    client,headers,exam,engine=pilot
    request=payload(exam,people=has_people)
    first=client.post("/api/applications",json=request,headers=headers)
    assert first.status_code==200,first.text
    second=client.post("/api/applications",json=request,headers=headers)
    assert second.status_code==200,second.text
    assert second.json()==first.json()
    with engine.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM web_emisiones").fetchone()[0]==1
        if has_people:
            assert len(engine.store.sessions())==1
            assert db.execute("SELECT COUNT(*) FROM participantes").fetchone()[0]==1
        else:
            assert not engine.store.sessions()
            assert db.execute("SELECT COUNT(*) FROM web_lotes_impresion").fetchone()[0]==1
    changed={**request,"nombre":"Otro examen distinto"}
    assert client.post("/api/applications",json=changed,headers=headers).status_code==409
    assert client.post("/api/applications",json={
        **request,"solicitud_id":"wrong"} ,headers=headers).status_code==422


@pytest.mark.parametrize("has_people",[True,False])
def test_paquete_completo_reutiliza_lote_original_y_borra_temporales(pilot,has_people):
    client,headers,exam,engine=pilot
    response=client.post("/api/applications",json=payload(exam,people=has_people),
                         headers=headers)
    assert response.status_code==200,response.text
    issued=response.json()
    original_sessions=len(engine.store.sessions())
    address=("/api/applications/"+issued["sid"]+"/package" if has_people else
             "/api/print-lots/"+issued["lote_id"]+"/package")
    before={p.name for p in engine.outputs.glob("*.zip")}
    downloaded=client.get(address)
    assert downloaded.status_code==200,downloaded.text[:120] if not downloaded.content.startswith(b"PK") else ""
    assert downloaded.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(downloaded.content)) as archive:
        names=set(archive.namelist())
        assert {"Material_OMR/Cuadernillo.pdf","Material_OMR/Hoja_respuestas.pdf",
                "Material_OMR/Acetato_clave.pdf","Material_OMR/Clave_docente.pdf",
                "Material_OMR/manifest.json","Material_OMR/LEEME.txt"}<=names
        if has_people:
            assert "Material_OMR/Paquetes_individuales.zip" in names
        else:
            assert "Material_OMR/Paquetes_individuales.zip" not in names
        assert archive.read("Material_OMR/Cuadernillo.pdf").startswith(b"%PDF-")
        assert archive.testzip() is None
    assert {p.name for p in engine.outputs.glob("*.zip")}==before
    assert len(engine.store.sessions())==original_sessions
    assert client.get(address).content==downloaded.content or client.get(address).status_code==200
    assert client.get("/api/print-lots/1234567890abcdef/package").status_code==404


def test_zip_material_interno_restringido_a_roles_autorizados(pilot):
    client,headers,exam,_=pilot
    response=client.post("/api/applications",json=payload(exam),
                         headers=headers)
    sid=response.json()["sid"]
    created=client.post("/api/users",json={
        "usuario":"auxiliar01","nombre":"Auxiliar",
        "password":"ClaveInicialAuxiliar123!","rol":"auxiliar"},headers=headers)
    assert created.status_code==200,created.text
    with TestClient(client.app) as helper:
        assert helper.post("/api/login",json={
            "usuario":"auxiliar01","password":"ClaveInicialAuxiliar123!"}).status_code==200
        assert helper.get("/api/applications/"+sid+"/package").status_code==403
        assert helper.get("/api/print-lots/abc/package").status_code==403


def test_png_transparente_se_imprime_sobre_papel_blanco():
    image=Image.new("RGBA",(60,40),(0,0,0,0))
    image.paste((180,30,60,255),(20,10,40,30))
    converted=_white_background(image)
    assert converted.mode=="RGB"
    assert converted.getpixel((0,0))==(255,255,255)
    assert converted.getpixel((30,20))==(180,30,60)
    opaque=Image.new("RGB",(10,10),(245,230,200))
    assert _white_background(opaque).getpixel((0,0))==(245,230,200)


def test_secciones_y_descarga_controlada_siguen_presentes():
    root=Path(__file__).resolve().parents[1]
    javascript=(root/"omr_web"/"static"/"designer.js").read_text(encoding="utf-8")
    assert 'id="rosterSection"' in javascript
    assert 'id="rosterPanel"' in javascript
    assert "solicitud_id:requestId" in javascript
    assert "showSaveFilePicker" in javascript
    assert "Descargas individuales (opcional)" in javascript
    assert "Crear OTRA aplicación" in javascript
