"""Regresión del diseñador web contra las modalidades aprobadas del motor.

No usa los ZIP privados: toda imagen, participante y pregunta es ficticio.
"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from PIL import Image

from omr_web.app import create_app


def workbook(image=""):
    book=Workbook()
    sheet=book.active
    sheet.title="Preguntas"
    sheet.append(["Tema","Pregunta","A","B","C","D","Correcta","Imagen"])
    sheet.append(["Seguridad","¿Cuál es el procedimiento correcto?",
                  "Avisar","Ignorar","Descartar","Esperar","A",image])
    target=BytesIO()
    book.save(target)
    return target.getvalue()


def picture(color="#224466"):
    target=BytesIO()
    Image.new("RGB",(120,90),color).save(target,format="PNG")
    return target.getvalue()


@pytest.fixture
def server(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    svc=app.state.engine
    svc.setup(svc._setup_token,"administrador","Administrador",
              "ClaveSeguraTemporal123!")
    with TestClient(app) as client:
        login=client.post("/api/login",json={
            "usuario":"administrador","password":"ClaveSeguraTemporal123!"})
        assert login.status_code==200
        yield app,client,{"X-CSRF-Token":client.cookies.get("omr_csrf")}
    svc.close()


def import_questionnaire(client,headers,*,with_images=False):
    files=[("file",("cuestionario.xlsx",workbook("equipo.png" if with_images else ""),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    if with_images:
        files.extend([
            ("images",("equipo.png",picture(),"image/png")),
            ("logo",("logo.png",picture("#338855"),"image/png"))])
    resp=client.post("/api/library/import?name=Prueba+Cabos&title=Examen+seguridad",
        headers=headers,files=files,data={
            "empresa":"Empresa ficticia","grupo":"Area de nodos",
            "subtitulo":"Turno C","instrucciones":"Marca una sola respuesta",
            "papel":"Oficio","letra":"10.5","modo":"normal",
            "color_titulo":"#114466","color_subtitulo":"#446688",
            "color_respuestas":"#213A4C","color_acetato":"#167341"})
    assert resp.status_code==200,resp.text
    return resp.json()["cuestionario_id"]


def test_plantillas_aprobadas_y_perfiles_separados(server):
    app,client,headers=server
    for kind in ("preguntas","personal"):
        resp=client.get("/api/templates/"+kind)
        assert resp.status_code==200
        assert resp.content[:2]==b"PK"
    wb=load_workbook(BytesIO(client.get("/api/templates/preguntas").content))
    assert wb.sheetnames==["Preguntas","Ejemplo","Guia"]
    assert list(wb["Preguntas"].values)[0]==(
        "Tema","Pregunta","A","B","C","D","Correcta","Imagen")
    wb.close()
    assert client.get("/api/templates/otro").status_code==404

    created=client.post("/api/users",headers=headers,json={
        "usuario":"auxiliar01","nombre":"Ayudante ficticio",
        "password":"ClaveInicialAuxiliar123!","rol":"auxiliar"})
    assert created.status_code==200,created.text
    users=client.get("/api/users").json()
    assert next(x for x in users if x["usuario"]=="auxiliar01")["rol"]=="capturista"
    with TestClient(app) as helper:
        assert helper.post("/api/login",json={
            "usuario":"auxiliar01","password":"ClaveInicialAuxiliar123!"}).status_code==200
        csrf={"X-CSRF-Token":helper.cookies.get("omr_csrf")}
        assert helper.post("/api/change-password",headers=csrf,json={
            "anterior":"ClaveInicialAuxiliar123!",
            "nueva":"ClaveDefinitivaAuxiliar123!"}).status_code==200
        assert helper.post("/api/login",json={
            "usuario":"auxiliar01","password":"ClaveDefinitivaAuxiliar123!"}).status_code==200
        assert helper.get("/api/library").status_code==403
        assert helper.get("/api/templates/preguntas").status_code==403
        assert helper.get("/api/print-lots").status_code==403
        assert helper.post("/api/roster/import",headers={
            "X-CSRF-Token":helper.cookies.get("omr_csrf")},
            files={"file":("Personal.csv",b"ID_personal,Nombre\nP1,Test\n")}).status_code==403


def test_importar_imagen_logo_y_editar_cuestionario_sin_perder_originales(server):
    app,c,headers=server
    exam_id=import_questionnaire(c,headers,with_images=True)
    detail=c.get("/api/library/"+exam_id)
    assert detail.status_code==200,detail.text
    data=detail.json()
    assert data["empresa"]=="Empresa ficticia"
    assert data["grupo"]=="Area de nodos"
    assert data["letra"]==10.5
    assert data["modo"]=="normal"
    assert data["papel"]=="Oficio"
    assert data["color_subtitulo"]=="#446688"
    assert data["logo"]=="logo.png"
    assert data["preguntas"][0]["imagen"]=="pregunta_001.png"
    img=c.get("/api/library/"+exam_id+"/images/pregunta_001.png")
    assert img.status_code==200
    assert img.content==picture()
    assert c.get("/api/library/"+exam_id+"/images/logo.png").content==picture("#338855")
    assert c.get("/api/library/"+exam_id+"/images/../logo.png").status_code in (404,405)

    data["titulo"]="Examen corregido"
    data["preguntas"][0]["pregunta"]="¿Cómo se reporta?"
    data["preguntas"][0]["correcta"]="B"
    data["preguntas"][0]["imagen"]=0
    changed=c.post("/api/library/"+exam_id+"/edit",headers=headers,files=[
        ("payload",(None,json.dumps(data,ensure_ascii=False))),
        ("images",("q1__reemplazo.png",picture("#992255"),"image/png"))])
    assert changed.status_code==200,changed.text
    updated=c.get("/api/library/"+exam_id).json()
    assert updated["revision"]==2
    assert updated["preguntas"][0]["correcta"]=="B"
    assert updated["preguntas"][0]["pregunta"]=="¿Cómo se reporta?"
    assert updated["preguntas"][0]["imagen"]=="pregunta_001.png"
    assert c.get("/api/library/"+exam_id+"/images/pregunta_001.png").content==picture("#992255")


@pytest.mark.parametrize("mode",["normal","ecologico"])
@pytest.mark.parametrize("with_people",[False,True])
def test_modalidad_y_personal_opcional_en_web(server,mode,with_people):
    app,c,headers=server
    exam_id=import_questionnaire(c,headers)
    people=([
        {"id":"P0001","nombre":"Persona ficticia 1","area":"Area A","grupo":"G1","turno":"Día"},
        {"id":"P0002","nombre":"Persona ficticia 2","area":"","grupo":"","turno":""}
    ] if with_people else [])
    response=c.post("/api/applications",headers=headers,json={
        "cuestionario_id":exam_id,"nombre":"Aplicación ficticia",
        "modalidad":mode,"papel":"Carta","participantes":people})
    assert response.status_code==200,response.text
    result=response.json()
    assert result["con_personal"]==with_people
    assert result["tipo"]==("omr" if with_people else "manual")
    base=("/api/applications/"+result["sid"]+"/files/" if with_people else
          "/api/print-lots/"+result["lote_id"]+"/files/")
    for name in ("Cuadernillo.pdf","Hoja_respuestas.pdf","Acetato_clave.pdf",
                 "Clave_docente.pdf"):
        file=c.get(base+name)
        assert file.status_code==200,(name,file.status_code)
        assert file.content.startswith(b"%PDF-")
    if with_people:
        ses=app.state.engine.store.session(result["sid"])
        assert ses["modo"]==mode
        assert len(ses["personal"])==2
        first=next(p for p in ses["personal"] if p["id"]=="P0001")
        assert first["area"]=="Area A"
        assert first["grupo"]=="G1"
        assert first["turno"]=="Día"
        assert c.get(base+"Paquetes_individuales.zip").status_code==(
            200 if mode=="normal" else 404)
    else:
        assert result["sid"] is None
        assert len(app.state.engine.store.sessions())==0
        assert c.get(base+"Paquetes_individuales.zip").status_code==404
        assert c.get("/api/print-lots").json()[0]["id"]==result["lote_id"]
        with app.state.engine.store.connect() as db:
            lot=db.execute("SELECT ruta FROM web_lotes_impresion WHERE id=?",
                           (result["lote_id"],)).fetchone()
        manifest=json.loads((app.state.engine.root/lot["ruta"]/"manifest.json").read_text())
        assert manifest["folio_qr_habilitado"] is False
        assert manifest["sesion_omr"] is None
        assert manifest["modo_examen"]==mode


def test_vista_previa_3_pdfs_y_sin_revelar_clave_a_auxiliares(server):
    app,c,headers=server
    exam_id=import_questionnaire(c,headers,with_images=True)
    payload={"modo":"ecologico","papel":"Oficio",
             "con_personal":False,"titulo":"Vista ficticia"}
    for mode in ("normal","ecologico"):
        for person in (False,True):
            for view in ("Cuadernillo","Respuestas","Acetato"):
                preview=c.post("/api/library/"+exam_id+"/preview?view="+view,
                               headers=headers,json={**payload,"modo":mode,
                                                     "con_personal":person})
                assert preview.status_code==200,(view,preview.text[:150])
                assert preview.headers["content-type"].startswith("application/pdf")
                assert preview.content.startswith(b"%PDF-")
    assert c.post("/api/library/"+exam_id+"/preview?view=Incorrecta",
                  headers=headers,json={}).status_code==422


def test_logo_visible_en_hoja_de_respuestas_omr_y_preview(server):
    import fitz
    app,c,headers=server
    eid=import_questionnaire(c,headers,with_images=True)
    preview=c.post("/api/library/"+eid+"/preview?view=Respuestas",
                   headers=headers,json={"con_personal":False,"papel":"Oficio"})
    assert preview.status_code==200,preview.text[:150]
    with fitz.open(stream=preview.content,filetype="pdf") as pdf:
        assert len(pdf[0].get_images(full=True))>=1
    generated=c.post("/api/applications",headers=headers,json={
        "cuestionario_id":eid,"modalidad":"normal","papel":"Oficio",
        "participantes":[{"id":"P1","nombre":"Persona ficticia"}]})
    assert generated.status_code==200,generated.text
    pdf=c.get("/api/applications/"+generated.json()["sid"]+"/files/Hoja_respuestas.pdf")
    assert pdf.status_code==200
    with fitz.open(stream=pdf.content,filetype="pdf") as doc:
        assert len(doc[0].get_images(full=True))>=2  # Logo y QR


def test_personal_xlsx_preserva_ceros_y_rechaza_formato_invalido(server):
    app,c,headers=server
    wb=Workbook();ws=wb.active
    ws.append(["ID_personal","Nombre","Area_adscripcion","Grupo","Turno"])
    ws.append(["000027","Participante simulado","Control Operativo","A","Día"])
    ws.append(["000028","Otro participante",None,None,None])
    b=BytesIO();wb.save(b)
    r=c.post("/api/roster/import",headers=headers,
             files={"file":("Personal.xlsx",b.getvalue(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code==200,r.text
    people=r.json()["participantes"]
    assert r.json()["cantidad"]==2
    assert people[0]=={"id":"000027","nombre":"Participante simulado",
                       "area":"Control Operativo","grupo":"A","turno":"Día"}
    assert people[1]["area"]==""
    assert c.post("/api/roster/import",headers=headers,
                  files={"file":("mal.txt",b"incorrecto")}).status_code==400


def test_vista_previa_no_emite_folios_ni_muta_sesiones(server):
    app,c,headers=server
    eid=import_questionnaire(c,headers)
    assert not app.state.engine.store.sessions()
    for view in ("Cuadernillo","Respuestas","Acetato"):
        response=c.post("/api/library/"+eid+"/preview?view="+view,
                        headers=headers,json={
                            "modo":"normal","papel":"Carta",
                            "con_personal":True})
        assert response.status_code==200,response.text
    assert not app.state.engine.store.sessions()


def test_editar_clave_biblioteca_no_cambia_evaluacion_ya_impresa(server):
    app,c,headers=server
    eid=import_questionnaire(c,headers)
    def application():
        r=c.post("/api/applications",headers=headers,json={
            "cuestionario_id":eid,"modalidad":"ecologico","papel":"Carta",
            "participantes":[{"id":"A0001","nombre":"Persona ficticia"}]})
        assert r.status_code==200,r.text
        return app.state.engine.store.session(r.json()["sid"])

    original=application()
    assert original["preguntas"][0]["correcta"]=="A"
    data=c.get("/api/library/"+eid).json()
    data["preguntas"][0]["correcta"]="B"
    data["preguntas"][0]["imagen"]=None
    updated=c.post("/api/library/"+eid+"/edit",headers=headers,
                   data={"payload":json.dumps(data)})
    assert updated.status_code==200,updated.text
    assert app.state.engine.store.session(original["id"])["preguntas"][0]["correcta"]=="A"
    new=application()
    assert new["preguntas"][0]["correcta"]=="B"
    assert new["cuestionario_id"]==eid
    assert new["revision_biblioteca"]==2


def test_clave_no_sale_a_auxiliar_asignado(server):
    app,c,headers=server
    eid=import_questionnaire(c,headers)
    r=c.post("/api/applications",headers=headers,json={
        "cuestionario_id":eid,"modalidad":"ecologico","papel":"Carta",
        "participantes":[{"id":"P1","nombre":"Persona"}]})
    assert r.status_code==200,r.text
    sid=r.json()["sid"]
    helper=c.post("/api/users",headers=headers,json={
        "usuario":"aux02","nombre":"Auxiliar","password":"AuxiliarSegura123456!",
        "rol":"auxiliar"})
    uid=helper.json()["id"]
    assert c.post("/api/assignments",headers=headers,
        json={"usuario_id":uid,"sesion_id":sid}).status_code==200
    with TestClient(app) as reviewer:
        assert reviewer.post("/api/login",json={
            "usuario":"aux02","password":"AuxiliarSegura123456!"}).status_code==200
        csrf={"X-CSRF-Token":reviewer.cookies.get("omr_csrf")}
        assert reviewer.post("/api/change-password",headers=csrf,json={
            "anterior":"AuxiliarSegura123456!","nueva":"AuxiliarFinal123456!"}).status_code==200
        assert reviewer.post("/api/login",json={
            "usuario":"aux02","password":"AuxiliarFinal123456!"}).status_code==200
        csrf={"X-CSRF-Token":reviewer.cookies.get("omr_csrf")}
        assert reviewer.get("/api/applications").json()[0]["id"]==sid
        safe=reviewer.get("/api/applications/"+sid+"/questions")
        assert safe.status_code==200
        assert "correcta" not in safe.text
        assert reviewer.get("/api/applications/"+sid+"/files/Acetato_clave.pdf").status_code==403
        assert reviewer.get("/api/library/"+eid).status_code==403
        assert reviewer.post("/api/library/"+eid+"/preview",
                             headers=csrf,json={}).status_code==403
        assert reviewer.post("/api/applications",headers=csrf,json={
            "cuestionario_id":eid,"participantes":[]}).status_code==403


def _pdf_embeds_colors(pdf_data):
    """Comprobar recursos visuales en el PDF, no solo BLOB guardados."""
    import fitz
    from PIL import Image
    found=[]
    with fitz.open(stream=pdf_data,filetype="pdf") as pdf:
        for page in pdf:
            for element in page.get_images(full=True):
                payload=pdf.extract_image(element[0])["image"]
                with Image.open(BytesIO(payload)) as picture:
                    color=picture.convert("RGB").resize((1,1)).getpixel((0,0))
                found.append(color)
    return found


def _near_color(colors,wanted,tolerance=25):
    return any(max(abs(a-b) for a,b in zip(rgb,wanted))<=tolerance
               for rgb in colors)


@pytest.mark.parametrize("mode",["normal","ecologico"])
@pytest.mark.parametrize("roster",[[],[{"id":"P001","nombre":"Persona ficticia"}]])
def test_imagen_de_columna_excel_y_logo_visibles_en_pdf_final(server,mode,roster):
    app,c,headers=server
    eid=import_questionnaire(c,headers,with_images=True)
    expected_photo=(0x22,0x44,0x66)
    expected_logo=(0x33,0x88,0x55)

    preview=c.post("/api/library/"+eid+"/preview?view=Cuadernillo",
                   headers=headers,json={"modo":mode,"con_personal":bool(roster)})
    assert preview.status_code==200,preview.text[:180]
    colors=_pdf_embeds_colors(preview.content)
    assert _near_color(colors,expected_photo),colors
    assert _near_color(colors,expected_logo),colors

    response=c.post("/api/applications",headers=headers,json={
        "cuestionario_id":eid,"modalidad":mode,"papel":"Carta",
        "participantes":roster})
    assert response.status_code==200,response.text
    out=response.json()
    base=("/api/applications/"+out["sid"]+"/files/" if roster else
          "/api/print-lots/"+out["lote_id"]+"/files/")
    actual=c.get(base+"Cuadernillo.pdf")
    assert actual.status_code==200,actual.text[:180]
    colors=_pdf_embeds_colors(actual.content)
    assert _near_color(colors,expected_photo),colors
    assert _near_color(colors,expected_logo),colors
    sheet=c.get(base+"Hoja_respuestas.pdf")
    assert sheet.status_code==200
    assert _near_color(_pdf_embeds_colors(sheet.content),expected_logo)


def test_imagen_agregada_desde_interfaz_reemplazo_y_reordenacion(server):
    app,c,headers=server
    eid=import_questionnaire(c,headers,with_images=True)
    original=c.get("/api/library/"+eid).json()
    original["preguntas"].append({
        "tema":"Prueba de campo","pregunta":"¿Qué operación corresponde?",
        "opciones":["A uno","B dos","C tres","D cuatro"],"correcta":"B",
        "imagen":None})
    original["preguntas"][0]["imagen"]=0
    camera=picture("#C52C91")
    new_logo=picture("#BFE52A")
    changed=c.post("/api/library/"+eid+"/edit",headers=headers,files=[
        ("payload",(None,json.dumps(original,ensure_ascii=False))),
        ("images",("q2__foto_nueva.png",camera,"image/png")),
        ("logo",("actualizado.png",new_logo,"image/png"))])
    assert changed.status_code==200,changed.text
    exam=c.get("/api/library/"+eid).json()
    assert exam["revision"]==2
    assert len(exam["preguntas"])==2
    assert exam["preguntas"][0]["imagen"]=="pregunta_001.png"
    assert exam["preguntas"][1]["imagen"]=="pregunta_002.png"
    assert c.get("/api/library/"+eid+"/images/pregunta_002.png").content==camera
    assert c.get("/api/library/"+eid+"/images/logo.png").content==new_logo
    preview=c.post("/api/library/"+eid+"/preview?view=Cuadernillo",
                   headers=headers,json={})
    assert preview.status_code==200,preview.text[:180]
    colors=_pdf_embeds_colors(preview.content)
    assert _near_color(colors,(0xC5,0x2C,0x91)),colors
    assert _near_color(colors,(0xBF,0xE5,0x2A)),colors
    assert _near_color(colors,(0x22,0x44,0x66)),colors

    # Eliminar pregunta 1 debe conservar FOTO de la antigua pregunta 2;
    # la asociación viene de sourceIndex, no del número en pantalla.
    exam["preguntas"]=[{**exam["preguntas"][1],"imagen":1}]
    after=c.post("/api/library/"+eid+"/edit",headers=headers,
                 data={"payload":json.dumps(exam,ensure_ascii=False)})
    assert after.status_code==200,after.text
    revised=c.get("/api/library/"+eid).json()
    assert revised["revision"]==3
    assert len(revised["preguntas"])==1
    assert revised["preguntas"][0]["imagen"]=="pregunta_001.png"
    assert c.get("/api/library/"+eid+"/images/pregunta_001.png").content==camera
    assert c.get("/api/library/"+eid+"/images/pregunta_002.png").status_code==404


def test_imagen_invalida_y_imagen_no_referenciada_devuelven_422(server):
    app,c,headers=server
    required_xlsx=workbook("equipo.png")
    invalid=c.post("/api/library/import?name=Imagen+mala&title=Ensayo",
         headers=headers,files=[
             ("file",("preguntas.xlsx",required_xlsx,
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
             ("images",("equipo.png",b"No es realmente PNG","image/png"))])
    assert invalid.status_code==422,invalid.text
    assert "imagen" in invalid.text.lower()

    absent=c.post("/api/library/import?name=Foto+ausente&title=Ensayo",
        headers=headers,files={
            "file":("preguntas.xlsx",required_xlsx,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert absent.status_code==422,absent.text

    extras=c.post("/api/library/import?name=Foto+sin+columna&title=Ensayo",
        headers=headers,files=[
          ("file",("preguntas.xlsx",workbook(""),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
          ("images",("equipo.png",picture(),"image/png"))])
    assert extras.status_code==422,extras.text
    assert "columna Imagen" in extras.text

    eid=import_questionnaire(c,headers)
    exam=c.get("/api/library/"+eid).json()
    corrupted=c.post("/api/library/"+eid+"/edit",headers=headers,files=[
        ("payload",(None,json.dumps(exam))),
        ("images",("q1__mala.png",b"Content failed","image/png"))])
    assert corrupted.status_code==422,corrupted.text
    assert c.get("/api/library/"+eid).json()["revision"]==1


def test_foto_incrustada_en_excel_no_se_ignora_silenciosamente(server):
    from openpyxl.drawing.image import Image as XlsxImage
    app,c,headers=server
    workbook_object=load_workbook(BytesIO(workbook("")))
    photo=XlsxImage(BytesIO(picture("#8844bb")))
    workbook_object["Preguntas"].add_image(photo,"H2")
    data=BytesIO();workbook_object.save(data);workbook_object.close()
    r=c.post("/api/library/import?name=Excel+con+dibujo&title=Evaluacion",
             headers=headers,files={
               "file":("preguntas.xlsx",data.getvalue(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code==422,r.text
    assert "fotos pegadas" in r.text
