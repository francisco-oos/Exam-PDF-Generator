"""API OMR web para una tableta/PC servidor; clientes vía navegador.

Arranque:
    python -m omr_web.run
Producción: SOLO cuando exista integración real de licencias, HTTPS,
respaldo y aceptación de seguridad. Esta versión declara PILOTO explícito.
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from omr_evaluaciones.documentos import sha_file
from .service import WebError, WebService

MAX_UPLOAD = 100 * 1024 * 1024
FILE_NAMES = frozenset({
    "Cuadernillo.pdf", "Hoja_respuestas.pdf", "Acetato_clave.pdf",
    "Paquetes_individuales.zip", "Clave_docente.pdf", "manifest.json",
})


class SetupPayload(BaseModel):
    token: str
    usuario: str
    nombre: str
    password: str


class LoginPayload(BaseModel):
    usuario: str
    password: str


class PasswordPayload(BaseModel):
    anterior: str
    nueva: str


class NewUser(BaseModel):
    usuario: str
    nombre: str
    password: str
    rol: str = "capturista"


class Assignment(BaseModel):
    usuario_id: str
    sesion_id: str


class NewApplication(BaseModel):
    cuestionario_id: str
    nombre: str = ""
    modalidad: str = "ecologico"
    papel: str = "Carta"
    participantes: list[dict] = Field(min_length=1,max_length=500)


class ClaimPayload(BaseModel):
    pass


class LeasePayload(BaseModel):
    lease: str


class EditPayload(BaseModel):
    lease: str
    expected_revision: int
    cambios: list[dict]
    motivo: str


def create_app(data_dir: Path | None = None, *, start_workers=True):
    if os.getenv("OMR_WEB_MODE","pilot")!="pilot":
        raise RuntimeError(
            "La licencia central no está integrada: modo producción bloqueado.")
    root = Path(data_dir or os.getenv("OMR_WEB_DATA", "datos"))
    web = FastAPI(title="OMR · Centro de control", version="0.1.0")
    engine = WebService(root, start_workers=start_workers)
    web.state.engine = engine

    @web.exception_handler(WebError)
    async def on_error(_request: Request, error: WebError):
        return JSONResponse(status_code=error.status,content={"error":str(error)})

    @web.on_event("shutdown")
    def stop_engine():
        engine.close()

    def user_of(request: Request):
        return engine.authenticate(request.cookies.get("omr_sid"))

    def write_user(request: Request, x_csrf_token: str | None = Header(None)):
        # No dependemos de CORS; las peticiones de otros orígenes no pueden
        # adjuntar este encabezado de seguridad sin pasar preflight.
        return engine.authenticate(request.cookies.get("omr_sid"),
                                   x_csrf_token,write=True)

    def set_cookies(response: Response,request: Request,token: str,csrf: str):
        secure=request.url.scheme == "https"
        response.set_cookie("omr_sid",token,max_age=10*3600,
                            secure=secure,httponly=True,samesite="strict",path="/")
        response.set_cookie("omr_csrf",csrf,max_age=10*3600,
                            secure=secure,httponly=False,samesite="strict",path="/")
        response.headers["Cache-Control"] = "no-store"

    @web.middleware("http")
    async def origin_guard(request: Request,call_next):
        if request.method in ("POST","PUT","PATCH","DELETE"):
            origin=request.headers.get("origin")
            host=request.headers.get("host","")
            if origin:
                from urllib.parse import urlsplit
                u=urlsplit(origin)
                if u.netloc.lower()!=host.lower() or u.scheme!=request.url.scheme:
                    return JSONResponse(status_code=403,
                                        content={"error":"Origen no autorizado."})
        result=await call_next(request)
        result.headers["X-Content-Type-Options"]="nosniff"
        result.headers["Referrer-Policy"]="no-referrer"
        result.headers["X-Frame-Options"]="DENY"
        result.headers["Cache-Control"]="no-store"
        return result

    @web.get("/api/health")
    def health():
        return {"ok":True,"version":"0.1.0","modo":"piloto-local"}

    @web.get("/api/setup/status")
    def setup_status():
        return {"necesita_configuracion":engine.needs_setup,
                "modo":"PILOTO SIN VALIDACIÓN DE LICENCIA CENTRAL"}

    @web.post("/api/setup")
    def setup(payload: SetupPayload):
        return engine.setup(payload.token,payload.usuario,payload.nombre,
                            payload.password)

    @web.post("/api/login")
    def login(payload: LoginPayload,request: Request,response: Response):
        token,csrf,person=engine.login(payload.usuario,payload.password)
        set_cookies(response,request,token,csrf)
        return {"usuario":person}

    @web.post("/api/logout")
    def logout(request: Request,response: Response,_user=Depends(write_user)):
        engine.logout(request.cookies.get("omr_sid"))
        response.delete_cookie("omr_sid",path="/")
        response.delete_cookie("omr_csrf",path="/")
        return {"ok":True}

    @web.get("/api/me")
    def me(user=Depends(user_of)):
        return {"usuario":engine._public_user(user),
                "modo":"piloto-local","licencia":"integración pendiente"}

    @web.post("/api/change-password")
    def change_password(payload: PasswordPayload,user=Depends(write_user)):
        engine.change_password(user,payload.anterior,payload.nueva)
        return {"ok":True,"reiniciar_sesion":True}

    @web.get("/api/users")
    def users(user=Depends(user_of)):
        return engine.list_users(user)

    @web.post("/api/users")
    def add_user(payload: NewUser,user=Depends(write_user)):
        return {"id":engine.add_user(user,payload.usuario,payload.nombre,
                                    payload.password,payload.rol)}

    @web.post("/api/assignments")
    def assign(payload: Assignment,user=Depends(write_user)):
        engine.assign(user,payload.usuario_id,payload.sesion_id)
        return {"ok":True}

    @web.get("/api/library")
    def library(user=Depends(user_of)):
        engine.require(user,roles={"admin"})
        if not engine.library.exists():
            return []
        from biblioteca import list_exams
        return list_exams(engine.library)

    @web.post("/api/library/import")
    async def import_questionnaire(file:UploadFile=File(...),name:str="",
                                   title:str="",user=Depends(write_user)):
        """Importa un Excel de preguntas existente sin alterar otros exámenes.

        No confía en rutas enviadas desde el teléfono. Limita peso y
        expansión XLSX antes de analizar la plantilla del generador.
        """
        engine.require(user,roles={"admin"})
        if not file.filename or not file.filename.lower().endswith(".xlsx"):
            raise WebError("Se requiere una plantilla de preguntas XLSX.")
        from tempfile import TemporaryDirectory
        from zipfile import ZipFile,BadZipFile
        from src.evaluaciones.core import read_questions
        from biblioteca import save_exam
        with TemporaryDirectory(prefix="omr_import_") as temporary:
            book=Path(temporary)/"Preguntas.xlsx"
            total=0
            with book.open("wb") as dst:
                while True:
                    part=await file.read(1024*1024)
                    if not part:break
                    total+=len(part)
                    if total>8*1024*1024:
                        raise WebError("La plantilla supera 8 MB.",413)
                    dst.write(part)
            try:
                with ZipFile(book) as archive:
                    members=archive.infolist()
                    if (len(members)>180 or
                        sum(item.file_size for item in members)>25*1024*1024 or
                        any("externalLink" in item.filename for item in members)):
                        raise WebError("Contenido XLSX no permitido.")
            except BadZipFile as exc:
                raise WebError("Excel no válido.") from exc
            questions=read_questions(book)
            if not questions:
                raise WebError("No se encontraron preguntas.")
            exam_id=save_exam(
                engine.library,
                nombre=name.strip() or Path(file.filename).stem[:100],
                titulo=title.strip() or name.strip() or "Evaluación de conocimientos",
                empresa="",grupo="",subtitulo="Evaluación de conocimientos",
                instrucciones="Selecciona una sola respuesta por pregunta.",
                questions=questions,tamano_papel="Carta")
        await file.close()
        return {"cuestionario_id":exam_id,"preguntas":len(questions)}

    @web.get("/api/applications")
    def applications(user=Depends(user_of)):
        return engine.visible_sessions(user)

    @web.post("/api/applications")
    def create_application(data: NewApplication,user=Depends(write_user)):
        return engine.create_application(
            user,data.cuestionario_id,data.nombre,data.modalidad,
            data.papel,data.participantes)

    @web.get("/api/applications/{sid}/questions")
    def questions(sid: str,user=Depends(user_of)):
        return engine.questions(user,sid)

    @web.get("/api/applications/{sid}/files/{filename}")
    def download_material(sid: str,filename: str,user=Depends(user_of)):
        engine.require(user,sid=sid)
        if filename not in FILE_NAMES:
            raise WebError("Archivo no permitido.",404)
        if filename=="Clave_docente.pdf":
            engine.require(user,roles={"admin","coordinador"})
        session=engine.store.session(sid)
        folder=Path(session.get("lote_path") or "")
        if not folder.is_absolute():
            folder=(engine.root/folder).resolve()
        try:
            approved=folder.resolve().is_relative_to(
                (engine.root/"salidas").resolve())
            target=(folder/filename).resolve()
            approved=approved and target.parent==folder.resolve()
        except (ValueError,OSError):
            approved=False
        if not approved or not target.is_file():
            raise WebError("Material de impresión no disponible.",404)
        return FileResponse(target,filename=filename)

    @web.get("/api/applications/{sid}/sheets")
    def list_sheets(sid: str,todos:bool=False,user=Depends(user_of)):
        return engine.list_sheets(user,sid,include_done=todos)

    @web.post("/api/applications/{sid}/claim-next")
    def claim_next(sid:str,user=Depends(write_user)):
        return engine.claim_next(user,sid)

    @web.get("/api/sheets/{sheet_id}")
    def sheet(sheet_id: str,user=Depends(user_of)):
        return engine.get_sheet(user,sheet_id)

    @web.get("/api/sheets/{sheet_id}/image")
    def sheet_image(sheet_id: str,user=Depends(user_of)):
        engine.get_sheet(user,sheet_id)
        with engine.store.connect() as db:
            rec=db.execute("SELECT imagen FROM hojas WHERE id=?",
                           (sheet_id,)).fetchone()
        if not rec:
            raise WebError("Evidencia inexistente.",404)
        path=Path(rec["imagen"]).resolve()
        if not path.is_relative_to((engine.store.root/"escaneos").resolve()):
            raise WebError("Ruta de evidencia no autorizada.",403)
        if not path.is_file():
            raise WebError("No existe la imagen archivada.",404)
        return FileResponse(path,media_type="image/png")

    @web.get("/api/sheets/{sheet_id}/overlay")
    def sheet_overlay(sheet_id:str,pregunta:int=1,acetato:bool=False,
                      user=Depends(user_of)):
        """Resalta el reactivo, nunca modifica el PDF ni el PNG original.

        El acetato con respuestas CORRECTAS está reservado a coordinador/admin;
        el capturista solo ve la zona de burbujas.
        """
        detail=engine.get_sheet(user,sheet_id)
        if not 1<=pregunta<=len(detail["preguntas"]):
            raise WebError("Reactivo fuera de rango.")
        if acetato:
            engine.require(user,roles={"admin","coordinador"})
        from omr_evaluaciones.motor import render_review_with_acetato
        import cv2
        from io import BytesIO
        from PIL import Image
        with engine.store.connect() as db:
            image_path=db.execute("SELECT imagen FROM hojas WHERE id=?",
                                  (sheet_id,)).fetchone()["imagen"]
        source=Path(image_path).resolve()
        if not source.is_relative_to((engine.store.root/"escaneos").resolve()):
            raise WebError("La evidencia no está en la carpeta permitida.",403)
        bitmap=cv2.imread(str(source))
        if bitmap is None:
            raise WebError("No se pudo recuperar el escaneo.",404)
        sess=engine.store.session(detail["sesion_id"])
        try:
            picture=render_review_with_acetato(
                bitmap,sess["papel"],sess["preguntas"],
                show_acetato=acetato,issue_numbers=[pregunta],
                already_aligned=True)
        except ValueError as exc:
            raise WebError(str(exc),422) from exc
        picture.thumbnail((1400,1900))
        stream=BytesIO()
        picture.save(stream,format="JPEG",quality=80)
        return Response(stream.getvalue(),media_type="image/jpeg")

    @web.post("/api/documents/{digest}/pages/{page}/link")
    def link_pending(digest:str,page:int,data:dict,user=Depends(write_user)):
        engine.require(user,roles={"admin"})
        sid=str(data.get("sesion_id",""))
        engine.store.session(sid)
        name=engine.inbox.bind_manual_pending(
            digest,page,sid,str(data.get("id","")),
            str(data.get("folio","")),user["nombre"],
            str(data.get("motivo","")))
        return {"nombre":name,"estado":"manual_pendiente",
                "aviso":"Revisar TODOS los reactivos antes de calificar."}

    @web.post("/api/sheets/{sheet_id}/claim")
    def claim(sheet_id:str,user=Depends(write_user)):
        return engine.claim(user,sheet_id)

    @web.post("/api/sheets/{sheet_id}/release")
    def release(sheet_id:str,data:LeasePayload,user=Depends(write_user)):
        engine.release(user,sheet_id,data.lease)
        return {"ok":True}

    @web.put("/api/sheets/{sheet_id}/decisions")
    def decisions(sheet_id:str,data:EditPayload,user=Depends(write_user)):
        return engine.save_decisions(user,sheet_id,data.lease,
                                     data.expected_revision,data.cambios,
                                     data.motivo)

    @web.post("/api/sheets/{sheet_id}/approve")
    def approve(sheet_id:str,user=Depends(write_user)):
        engine.approve(user,sheet_id)
        return {"ok":True}

    @web.post("/api/scans")
    async def upload(file: UploadFile=File(...),user=Depends(write_user)):
        engine.require(user,roles={"admin","coordinador"})
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise WebError("El escaneo debe estar en formato PDF.")
        name=uuid4().hex
        target=engine.incoming/(name+".pdf")
        total=0
        try:
            with target.open("xb") as dst:
                while True:
                    chunk=await file.read(1024*1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total>MAX_UPLOAD:
                        raise WebError("PDF demasiado grande; máximo 100 MB.",413)
                    dst.write(chunk)
            if total<10 or target.open("rb").read(5)!=b"%PDF-":
                raise WebError("El archivo no tiene cabecera PDF.")
            jid=engine.add_job(user,target)
            return {"trabajo_id":jid,"estado":"pendiente"}
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @web.get("/api/jobs/{job_id}")
    def job(job_id:str,user=Depends(user_of)):
        return engine.job(user,job_id)

    @web.post("/api/jobs/{job_id}/retry")
    def retry(job_id:str,user=Depends(write_user)):
        engine.retry_job(user,job_id)
        return {"ok":True}

    @web.get("/api/documents")
    def documents(user=Depends(user_of)):
        engine.require(user,roles={"admin","coordinador"})
        items=engine.inbox.documents()
        if user["rol"]!="admin":
            # Los PDFs mezclados pueden contener hojas ajenas. Un coordinador
            # solo puede ver los lotes cuyas páginas identificadas pertenezcan
            # TODAS a sus aplicaciones asignadas.
            with engine.store.connect() as db:
                assigned={r[0] for r in db.execute(
                    "SELECT sesion_id FROM web_asignaciones WHERE usuario_id=?",
                    (user["id"],))}
            items=[d for d in items if all(
                p["sesion_id"] in assigned for p in engine.inbox.pages(d["sha"]))]
        return [{key:d[key] for key in
                 ("sha","nombre","paginas","pendientes","veces_recibido","recibido")}
                for d in items]

    @web.get("/api/documents/{digest}/pages")
    def document_pages(digest:str,user=Depends(user_of)):
        engine.require(user,roles={"admin"})
        return engine.inbox.pages(digest)

    @web.get("/api/documents/{digest}/pages/{page}/image")
    def document_preview(digest:str,page:int,user=Depends(user_of)):
        engine.require(user,roles={"admin"})
        from PIL import Image
        from io import BytesIO
        image=engine.inbox.render_page(digest,page,scale=0.9)
        image.thumbnail((1200,1600))
        buffer=BytesIO()
        image.save(buffer,format="JPEG",quality=78)
        return Response(buffer.getvalue(),media_type="image/jpeg")

    @web.get("/api/applications/{sid}/results")
    def results(sid:str,user=Depends(user_of)):
        engine.require(user,roles={"admin","coordinador","auditor"},sid=sid)
        data=engine.store.results(sid)
        return {"sesion_id":sid,"promedio":data["promedio"],
                "validados":data["validados"],"pendientes":data["pendientes"],
                "ausentes":data["ausentes"],
                "participantes":[{key:p[key] for key in
                    ("id","folio","nombre","estado","aciertos","porcentaje")}
                    for p in data["participantes"]]}

    @web.get("/api/applications/{sid}/events")
    def events(sid:str,user=Depends(user_of)):
        return engine.list_events(user,sid)

    @web.get("/api/applications/{sid}/export")
    def export(sid:str,internal:bool=False,user=Depends(user_of)):
        engine.require(user,roles={"admin","coordinador"},sid=sid)
        path=engine.outputs/(uuid4().hex+".zip")
        export_session_bundle(engine.store,engine.inbox,sid,path,
                              internal=internal)
        return FileResponse(path,filename=("Expediente_" if internal else
                            "Resultados_")+sid+".zip",
                            media_type="application/zip")

    @web.get("/api/applications/{sid}/participants/{person_id}/result")
    def participant_result(sid:str,person_id:str,user=Depends(user_of)):
        engine.require(user,roles={"admin","coordinador"},sid=sid)
        target=engine.outputs/(uuid4().hex+".pdf")
        participant_receipt(engine.store,sid,person_id,target)
        return FileResponse(target,filename="Resultado_"+sid+".pdf",
                            media_type="application/pdf")

    static_dir=Path(__file__).resolve().parent/"static"
    @web.get("/")
    def homepage():
        return FileResponse(static_dir/"index.html",media_type="text/html")

    web.mount("/static",StaticFiles(directory=static_dir),name="static")
    return web
