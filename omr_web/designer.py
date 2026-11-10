"""Adaptador web del diseñador original, sin duplicar geometría ni calificación.

La plantilla conserva Preguntas/Ejemplo/Guia, las fotos por reactivo viven
en imagenes/ y el logotipo es independiente. Todos los archivos recibidos
se comprueban antes de incorporarlos a la biblioteca SQLite original.
"""
from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import UploadFile

from biblioteca import db_connect, hex_color, load_exam, save_exam
from omr_evaluaciones.motor import read_roster
from preview_pdf import build_preview_pdf
from src.evaluaciones.core import Question, _safe_image, read_questions
from vista_previa import PreviewData
from .service import WebError

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_BOOK_BYTES = 8 * 1024 * 1024
IMAGE = re.compile(r"^[^./\\:][^/\\:]{0,150}\.(png|jpg|jpeg)$",re.I)
INDEXED_IMAGE = re.compile(r"^q([1-9][0-9]{0,2})__(.+)$",re.I)


def filename_of(upload: UploadFile, *, image=False) -> str:
    name = str(upload.filename or "")
    if not name or name in (".","..") or Path(name).name != name or "/" in name or "\\" in name or ":" in name:
        raise WebError("Nombre de archivo inválido.")
    if image and not IMAGE.fullmatch(name):
        raise WebError("Las imágenes deben ser archivos PNG/JPG de nombre simple.")
    return name


async def save_upload(upload: UploadFile, target: Path, limit: int) -> Path:
    total=0
    with target.open("xb") as dest:
        while True:
            block=await upload.read(1024*1024)
            if not block:
                break
            total+=len(block)
            if total>limit:
                raise WebError("Archivo demasiado grande para esta operación.",413)
            dest.write(block)
    await upload.close()
    return target


async def import_exam(db, workbook:UploadFile, *, name:str, title:str,
                      images:list[UploadFile], logo:UploadFile|None,
                      meta:dict):
    filename_of(workbook)
    if not workbook.filename.lower().endswith(".xlsx"):
        raise WebError("Usa la plantilla XLSX de preguntas.")
    if len(images)>100:
        raise WebError("Máximo 100 imágenes por cuestionario.")
    with TemporaryDirectory(prefix="omr_web_diseno_") as tmp:
        root=Path(tmp)
        sheet=await save_upload(workbook,root/"Preguntas.xlsx",MAX_BOOK_BYTES)
        images_dir=root/"imagenes"
        images_dir.mkdir()
        seen=set()
        for upload in images:
            name_image=filename_of(upload,image=True)
            if name_image.lower() in seen:
                raise WebError("Nombre de imagen repetido en el paquete.")
            seen.add(name_image.lower())
            path=await save_upload(upload,images_dir/name_image,MAX_IMAGE_BYTES)
            _safe_image(path,source="Imagen de pregunta")
        logo_path=None
        if logo and logo.filename:
            suffix=Path(filename_of(logo,image=True)).suffix.lower()
            logo_path=await save_upload(logo,root/("logo"+suffix),MAX_IMAGE_BYTES)
            _safe_image(logo_path,source="Logotipo")
        try:
            qs=read_questions(sheet)
            key=save_exam(
                db,nombre=name.strip() or Path(workbook.filename).stem[:100],
                titulo=title.strip() or name.strip() or "Evaluación de conocimientos",
                empresa=str(meta.get("empresa","")),grupo=str(meta.get("grupo","")),
                subtitulo=str(meta.get("subtitulo","")),
                instrucciones=str(meta.get("instrucciones","Selecciona una sola respuesta.")),
                questions=qs,logo=logo_path,
                tamano_papel=str(meta.get("papel","Carta")),
                letra=float(meta.get("letra",9)),
                color_titulo=str(meta.get("color_titulo","#213A4C")),
                color_subtitulo=str(meta.get("color_subtitulo","#5E7180")),
                color_respuestas=str(meta.get("color_respuestas","#213A4C")),
                color_acetato=str(meta.get("color_acetato","#167341")),
                reutilizable=meta.get("modo","ecologico")=="ecologico")
        except (ValueError,TypeError) as error:
            raise WebError(str(error),422) from error
    return {"cuestionario_id":key,"preguntas":len(qs)}


def serialize_exam(db,exam_id:str):
    with TemporaryDirectory(prefix="omr_web_lectura_") as tmp:
        exam=load_exam(db,exam_id,Path(tmp))
        return {
            "id":exam.id,"nombre":exam.nombre,"titulo":exam.titulo,
            "empresa":exam.empresa,"grupo":exam.grupo,
            "subtitulo":exam.subtitulo,"instrucciones":exam.instrucciones,
            "papel":exam.tamano_papel,"letra":exam.letra,
            "modo":"ecologico" if exam.reutilizable else "normal",
            "color_titulo":exam.color_titulo,
            "color_subtitulo":exam.color_subtitulo,
            "color_respuestas":exam.color_respuestas,
            "color_acetato":exam.color_acetato,
            "logo":exam.logo.name if exam.logo else None,
            "revision":exam.revision,
            "preguntas":[{
                "tema":q.section,"pregunta":q.prompt,
                "opciones":list(q.options),"correcta":"ABCD"[q.correct],
                "imagen":q.image.name if q.image else None}
                for q in exam.questions],
        }


def new_questions(items:list[dict], original, replacements=None):
    if not isinstance(items,list) or not 1<=len(items)<=100:
        raise WebError("El cuestionario debe tener de 1 a 100 preguntas.")
    replacements=replacements or {}
    result=[]
    for i,item in enumerate(items,1):
        if not isinstance(item,dict) or not isinstance(item.get("opciones"),list):
            raise WebError(f"Pregunta {i}: faltan las cuatro opciones.")
        opts=item["opciones"]
        letter=str(item.get("correcta","")).upper()
        if len(opts)!=4 or letter not in ("A","B","C","D"):
            raise WebError(f"Pregunta {i}: necesitas A, B, C, D y una clave correcta.")
        # Conservar imagen por índice explícito; una pregunta recién insertada
        # nunca hereda accidentalmente la imagen de otra por cambio de orden.
        keep=item.get("imagen")
        original_image=None
        if isinstance(keep,int) and 0<=keep<len(original.questions):
            original_image=original.questions[keep].image
        photo=replacements.get(i,original_image)
        result.append(Question(
            str(item.get("tema","")),str(item.get("pregunta","")),
            tuple(str(v) for v in opts),"ABCD".index(letter),photo))
    return result


async def update_exam(db,exam_id:str,raw:str,images:list[UploadFile],
                      logo:UploadFile|None):
    try:
        data=json.loads(raw)
        if not isinstance(data,dict):
            raise ValueError("Formato incorrecto.")
    except (ValueError,TypeError) as exc:
        raise WebError("Datos del diseñador inválidos.",422) from exc
    if len(images)>100:
        raise WebError("Máximo 100 imágenes.")
    with TemporaryDirectory(prefix="omr_web_edicion_") as tmp:
        root=Path(tmp)
        exam=load_exam(db,exam_id,root)
        replacements={}
        for upload in images:
            name=filename_of(upload,image=True)
            m=INDEXED_IMAGE.match(name)
            if not m:
                raise WebError("Nombre esperado de imagen: q1__archivo.png.")
            index=int(m.group(1))
            if index in replacements:
                raise WebError("Hay dos imágenes nuevas para la misma pregunta.")
            path=await save_upload(upload,root/name,MAX_IMAGE_BYTES)
            _safe_image(path,source=f"Pregunta {index}")
            replacements[index]=path
        logo_path=exam.logo
        if data.get("quitar_logo") is True:
            logo_path=None
        if logo and logo.filename:
            suffix=Path(filename_of(logo,image=True)).suffix.lower()
            logo_path=await save_upload(logo,root/("nuevo_logo"+suffix),MAX_IMAGE_BYTES)
            _safe_image(logo_path,source="Logotipo")
        items=data.get("preguntas",[])
        questions=new_questions(items,exam,replacements)
        try:
            saved=save_exam(
                db,exam_id=exam_id,
                nombre=str(data.get("nombre",exam.nombre)),
                titulo=str(data.get("titulo",exam.titulo)),
                empresa=str(data.get("empresa",exam.empresa)),
                grupo=str(data.get("grupo",exam.grupo)),
                subtitulo=str(data.get("subtitulo",exam.subtitulo)),
                instrucciones=str(data.get("instrucciones",exam.instrucciones)),
                questions=questions,logo=logo_path,
                tamano_papel=str(data.get("papel",exam.tamano_papel)),
                letra=float(data.get("letra",exam.letra)),
                reutilizable=data.get("modo","ecologico")=="ecologico",
                color_titulo=str(data.get("color_titulo",exam.color_titulo)),
                color_subtitulo=str(data.get("color_subtitulo",exam.color_subtitulo)),
                color_respuestas=str(data.get("color_respuestas",exam.color_respuestas)),
                color_acetato=str(data.get("color_acetato",exam.color_acetato)),
            )
        except (ValueError,TypeError) as error:
            raise WebError(str(error),422) from error
    return {"cuestionario_id":saved,"revision":serialize_exam(db,saved)["revision"]}


def preview_exam(db,exam_id:str,config:dict,view:str) -> bytes:
    if view not in ("Cuadernillo","Respuestas","Acetato"):
        raise WebError("Vista inválida.",422)
    with TemporaryDirectory(prefix="omr_web_preview_") as tmp:
        exam=load_exam(db,exam_id,Path(tmp))
        choices=config.get("preguntas")
        questions=tuple(new_questions(choices,exam)) if choices is not None else exam.questions
        mode=str(config.get("modo","ecologico" if exam.reutilizable else "normal"))
        paper=str(config.get("papel",exam.tamano_papel))
        if mode not in ("normal","ecologico") or paper not in ("Carta","A4","Oficio"):
            raise WebError("Papel o modalidad inválidos.",422)
        try:
            options={key:hex_color(str(config.get(key,getattr(exam,key))),key)
                     for key in ("color_titulo","color_subtitulo","color_respuestas","color_acetato")}
            setting=PreviewData(
                questions=questions,
                empresa=str(config.get("empresa",exam.empresa)),
                grupo=str(config.get("grupo",exam.grupo)),
                titulo=str(config.get("titulo",exam.titulo)),
                subtitulo=str(config.get("subtitulo",exam.subtitulo)),
                instrucciones=str(config.get("instrucciones",exam.instrucciones)),
                logo=exam.logo if config.get("quitar_logo") is not True else None,
                tamano_papel=paper,letra=float(config.get("letra",exam.letra)),
                reutilizable=mode=="ecologico",modo_examen=mode,
                cantidad_personas=1 if config.get("con_personal") else 0,
                participante_id="P001",participante_nombre="Persona ficticia",
                **options)
            return build_preview_pdf(setting,view)
        except (ValueError,TypeError) as error:
            raise WebError(str(error),422) from error


def resource(db,exam_id:str,name:str):
    if not re.fullmatch(r"(?:logo|pregunta_[0-9]{3})\.(?:png|jpg|jpeg)",name):
        raise WebError("Recurso inválido.",404)
    with db_connect(db) as conn:
        row=conn.execute("SELECT contenido,sha256 FROM recursos "
                         "WHERE cuestionario_id=? AND nombre=?",
                         (exam_id,name)).fetchone()
    if row is None:
        raise WebError("Imagen no encontrada.",404)
    content=bytes(row["contenido"])
    if sha256(content).hexdigest()!=row["sha256"]:
        raise WebError("Recurso de biblioteca alterado.",409)
    return content,"image/png" if name.lower().endswith(".png") else "image/jpeg"


async def import_roster(upload:UploadFile):
    filename=filename_of(upload)
    if Path(filename).suffix.lower() not in (".xlsx",".csv"):
        raise WebError("La lista debe ser CSV o XLSX.")
    with TemporaryDirectory(prefix="omr_web_personal_") as tmp:
        source=await save_upload(upload,Path(tmp)/("Personal"+Path(filename).suffix.lower()),MAX_BOOK_BYTES)
        try:
            people=read_roster(source)
        except (ValueError,TypeError) as error:
            raise WebError(str(error),422) from error
    return {"participantes":people,"cantidad":len(people)}
