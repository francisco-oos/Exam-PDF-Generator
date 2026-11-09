"""Bandeja documental local para el OMR: originales inmutables y hojas vinculadas.

Los documentos se registran ANTES de la lectura, por SHA-256. Una página
desconocida permanece en Bandeja, sin asignación ni nota. Las sesiones OMR
existentes siguen siendo la autoridad para QR/HMAC y calificaciones.

Las operaciones de PDF crean derivados; jamás reescriben el escaneo original.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pypdfium2 as pdfium

from .motor import MAX_PDF_SIZE, OMRStore, export_report, scan_document


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pdf_length(path):
    doc=pdfium.PdfDocument(str(path))
    try:
        count=len(doc)
        if not 1<=count<=1500:
            raise ValueError("El PDF debe contener entre 1 y 1500 páginas.")
        for index in range(count):
            page=doc[index]
            try:
                w,h=page.get_size()
            finally:
                page.close()
            if not 100<=w<=1500 or not 100<=h<=2000:
                raise ValueError(f"Página {index+1}: dimensiones fuera de rango.")
        return count
    finally:
        doc.close()


class EvidenceStore:
    """Un archivo puede tener páginas de muchas aplicaciones o pendientes."""

    def __init__(self, store: OMRStore):
        self.store=store
        self.root=store.root/"documentos"
        self.root.mkdir(parents=True,exist_ok=True)
        self._init()

    def _db(self):
        return self.store.connect()

    def _init(self):
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documentos_recibidos(
                    sha TEXT PRIMARY KEY,
                    nombre_fuente TEXT NOT NULL,
                    ruta TEXT NOT NULL,
                    tamano INTEGER NOT NULL,
                    paginas INTEGER NOT NULL,
                    recibido TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documento_paginas(
                    sha TEXT NOT NULL,
                    pagina INTEGER NOT NULL,
                    sesion_id TEXT,
                    folio TEXT,
                    nombre TEXT,
                    estado TEXT NOT NULL DEFAULT 'pendiente',
                    hoja_id TEXT,
                    diagnostico TEXT,
                    PRIMARY KEY(sha,pagina),
                    FOREIGN KEY(sha) REFERENCES documentos_recibidos(sha)
                );
                CREATE TABLE IF NOT EXISTS documento_bitacora(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sha TEXT NOT NULL,
                    pagina INTEGER,
                    sesion_id TEXT,
                    accion TEXT NOT NULL,
                    detalle TEXT NOT NULL,
                    responsable TEXT NOT NULL,
                    fecha TEXT NOT NULL,
                    FOREIGN KEY(sha) REFERENCES documentos_recibidos(sha)
                );
                CREATE INDEX IF NOT EXISTS idx_doc_page_sid
                    ON documento_paginas(sesion_id,estado);
                CREATE INDEX IF NOT EXISTS idx_doc_events_sha
                    ON documento_bitacora(sha,fecha);
            """)

    def _event(self,db,sha,page,action,detail="",sid=None,actor="Sistema OMR"):
        db.execute("""
            INSERT INTO documento_bitacora(
                sha,pagina,sesion_id,accion,detalle,responsable,fecha)
            VALUES(?,?,?,?,?,?,?)
        """,(sha,page,sid,action,str(detail)[:700],str(actor)[:100],_utc()))

    def ingest(self,source:Path):
        """Archiva de forma atómica antes de clasificar. Reimportar es inocuo."""
        source=Path(source)
        if not source.is_file() or source.suffix.lower()!=".pdf":
            raise ValueError("Selecciona un archivo PDF existente.")
        size=source.stat().st_size
        if size<5 or size>MAX_PDF_SIZE:
            raise ValueError("El PDF supera 100 MB o está vacío.")
        with source.open("rb") as stream:
            if stream.read(5)!=b"%PDF-":
                raise ValueError("La cabecera no corresponde a un PDF.")
        count=_pdf_length(source)
        # Calcular el hash mientras se copia al espacio privado. No se usa el
        # nombre suministrado por el usuario como ruta de archivo.
        temp=self.root/("."+uuid4().hex+".tmp")
        digest=hashlib.sha256()
        try:
            with source.open("rb") as inp,temp.open("xb") as out:
                for chunk in iter(lambda:inp.read(1024*1024),b""):
                    out.write(chunk)
                    digest.update(chunk)
                out.flush()
                os.fsync(out.fileno())
            sha=digest.hexdigest()
            archived=self.root/(sha+".pdf")
            if archived.exists():
                if _sha256(archived)!=sha:
                    raise OSError("El archivo previamente archivado no coincide con su SHA-256.")
                temp.unlink()
            else:
                os.replace(temp,archived)
            with self._db() as db:
                current=db.execute(
                    "SELECT * FROM documentos_recibidos WHERE sha=?",(sha,)
                ).fetchone()
                if current is None:
                    db.execute("""
                        INSERT INTO documentos_recibidos(
                            sha,nombre_fuente,ruta,tamano,paginas,recibido)
                        VALUES(?,?,?,?,?,?)
                    """,(sha,source.name,str(archived),size,count,_utc()))
                    db.executemany("""
                        INSERT INTO documento_paginas(sha,pagina,estado)
                        VALUES(?,?,'pendiente')
                    """,[(sha,i+1) for i in range(count)])
                    self._event(db,sha,None,"ARCHIVADO",
                                f"{source.name}; {count} páginas")
            return self.document(sha),current is not None
        finally:
            temp.unlink(missing_ok=True)

    def document(self,sha):
        with self._db() as db:
            row=db.execute("SELECT * FROM documentos_recibidos WHERE sha=?",
                           (sha,)).fetchone()
        if row is None:
            raise ValueError("Documento no registrado en la bandeja.")
        return dict(row)

    def documents(self):
        with self._db() as db:
            return [dict(r) for r in db.execute("""
                SELECT d.*,
                       (SELECT COUNT(*) FROM documento_paginas p
                        WHERE p.sha=d.sha AND p.sesion_id IS NULL)
                       AS sin_identificar,
                       (SELECT COUNT(*) FROM documento_paginas p
                        WHERE p.sha=d.sha AND p.hoja_id IS NOT NULL)
                       AS con_evidencia,
                       (SELECT COUNT(DISTINCT p.sesion_id)
                        FROM documento_paginas p WHERE p.sha=d.sha)
                       AS evaluaciones
                FROM documentos_recibidos d ORDER BY d.recibido DESC,d.sha DESC
            """)]

    def pages(self,sha):
        with self._db() as db:
            return [dict(r) for r in db.execute("""
                SELECT p.*,
                       COALESCE(s.nombre_evaluacion,s.titulo) AS evaluacion
                FROM documento_paginas p
                LEFT JOIN sesiones s ON s.id=p.sesion_id
                WHERE p.sha=? ORDER BY p.pagina
            """,(sha,))]

    def audit(self,sha=None,sid=None):
        with self._db() as db:
            if sha:
                rows=db.execute(
                    "SELECT * FROM documento_bitacora WHERE sha=? ORDER BY id",
                    (sha,))
            elif sid:
                rows=db.execute(
                    "SELECT * FROM documento_bitacora WHERE sesion_id=? ORDER BY id",
                    (sid,))
            else:
                rows=db.execute(
                    "SELECT * FROM documento_bitacora ORDER BY id")
            return [dict(row) for row in rows]

    def inspect(self,sha,inspection):
        """Registra la clasificación de TODAS las páginas, incluso desconocidas.

        No cambia enlaces manuales ni resultados previos. La inspección solo
        propone identidad QR, que ya verificó HMAC en el motor.
        """
        doc=self.document(sha)
        scanned=inspection.get("paginas",[])
        if len(scanned)!=doc["paginas"] or sorted(
                page.get("pagina") for page in scanned)!=list(
                    range(1,doc["paginas"]+1)):
            raise ValueError("La inspección no cubre todas las páginas del PDF.")
        with self._db() as db:
            for item in scanned:
                page_num=item["pagina"]
                current=db.execute("""
                    SELECT * FROM documento_paginas WHERE sha=? AND pagina=?
                """,(sha,page_num)).fetchone()
                new_sid=item.get("sesion_id")
                if (current["hoja_id"] or current["estado"]=="identificada_manual"
                        or (current["sesion_id"] and new_sid is None)):
                    # Un fallo transitorio del lector no quita una identidad
                    # verificada anteriormente ni una revisión humana.
                    continue
                if (current["sesion_id"] and new_sid and
                        current["sesion_id"]!=new_sid):
                    self._event(db,sha,page_num,"CONFLICTO_SESION",
                                "QR discrepa de la vinculación previa",
                                current["sesion_id"])
                    continue
                state="identificada_qr" if new_sid else "sin_identificar"
                diagnosis=item.get("diagnostico","")
                values=(new_sid,item.get("folio"),item.get("nombre"),
                        state,diagnosis,sha,page_num)
                if (current["sesion_id"],current["folio"],current["estado"])!=(
                        new_sid,item.get("folio"),state):
                    db.execute("""
                        UPDATE documento_paginas
                        SET sesion_id=?,folio=?,nombre=?,estado=?,diagnostico=?
                        WHERE sha=? AND pagina=?
                    """,values)
                    self._event(db,sha,page_num,
                                "QR_VALIDADO" if new_sid else "SIN_IDENTIFICAR",
                                diagnosis or item.get("folio",""),
                                new_sid)

    def migrate_legacy(self):
        """Integra los PDF previos de originales/<sesión>/ sin recalificarlos.

        La procedencia histórica se conserva por hoja cuando hay token
        registrado y perteneciente a la sesión. Las hojas antiguas sin QR
        quedan sin identificar en la bandeja. No altera notas/revisiones.
        """
        with self.store.connect() as db:
            history=[dict(r) for r in db.execute("""
                SELECT DISTINCT sesion_id,archivo_sha FROM hojas
                ORDER BY sesion_id,archivo_sha
            """)]
        migrated=0
        for entry in history:
            sid=entry["sesion_id"]
            source=self.store.root/"originales"/sid/(entry["archivo_sha"]+".pdf")
            if not source.is_file():
                continue
            doc,repeated=self.ingest(source)
            if doc["sha"]!=entry["archivo_sha"]:
                # El original guardado se ha cambiado; no asociarlo a la
                # lectura previa por coincidencia de nombre.
                continue
            with self.store.connect() as db:
                scans=[dict(row) for row in db.execute("""
                    SELECT h.id,h.token,h.pagina,h.estado,
                           p.folio,p.nombre
                    FROM hojas h
                    LEFT JOIN participantes p ON p.sesion_id=h.sesion_id
                       AND p.token=h.token
                    WHERE h.sesion_id=? AND h.archivo_sha=?
                """,(sid,entry["archivo_sha"]))]
            with self._db() as db:
                for scan in scans:
                    page_num=scan["pagina"]+1
                    if not scan["token"] or not scan["folio"]:
                        # El origen se conoce, pero NO la persona.
                        continue
                    previous=db.execute("""
                        SELECT * FROM documento_paginas
                        WHERE sha=? AND pagina=?
                    """,(doc["sha"],page_num)).fetchone()
                    if previous is None or previous["hoja_id"]:
                        continue
                    if previous["sesion_id"] and previous["sesion_id"]!=sid:
                        continue
                    db.execute("""
                        UPDATE documento_paginas SET sesion_id=?,folio=?,
                            nombre=?,hoja_id=?,estado=?,
                            diagnostico='Migrado del historial OMR'
                        WHERE sha=? AND pagina=?
                    """,(sid,scan["folio"],scan["nombre"],scan["id"],
                         scan["estado"],doc["sha"],page_num))
                    self._event(db,doc["sha"],page_num,
                                "MIGRADO_HISTORICO",
                                "Se conservó la calificación existente",
                                sid)
                    migrated+=1
        return {"fuentes_revisadas":len(history),
                "hojas_vinculadas":migrated}

    def record_report(self,sha,sid,report):
        """Asocia el ID de la hoja OMR al documento archivado."""
        self.document(sha)
        with self._db() as db:
            for entry in report.get("detalles",[]):
                page_num=entry["pagina"]
                row=db.execute("""
                    SELECT * FROM documento_paginas WHERE sha=? AND pagina=?
                """,(sha,page_num)).fetchone()
                if row is None or row["sesion_id"]!=sid:
                    raise ValueError("Intento de asociar una hoja a otra sesión.")
                new_id=entry["id"]
                status=entry["estado"]
                if row["hoja_id"] and row["hoja_id"]!=new_id:
                    raise ValueError("La página ya está asociada a otra hoja OMR.")
                db.execute("""
                    UPDATE documento_paginas SET hoja_id=?,estado=?,
                        diagnostico=?
                    WHERE sha=? AND pagina=?
                """,(new_id,status,entry.get("diagnostico",""),
                     sha,page_num))
                if row["hoja_id"]!=new_id or row["estado"]!=status:
                    self._event(db,sha,page_num,"OMR_"+status.upper(),
                                "Hoja "+new_id,sid)

    def link_manual(self,sha,page_num,sid,person_id,folio,reviewer,reason):
        """Identifica una página sin QR, pero NO asigna notas automáticamente."""
        if not str(reason).strip() or not str(reviewer).strip():
            raise ValueError("El enlace manual requiere motivo y revisor.")
        doc=self.document(sha)
        item=next((p for p in self.pages(sha) if p["pagina"]==page_num),None)
        if item is None or item["sesion_id"] not in (None,sid):
            raise ValueError("Esta hoja pertenece a otra evaluación verificada.")
        if item["hoja_id"] and item["estado"]!="sin_identificar":
            raise ValueError("Esta página ya tiene una hoja asociada.")
        session=self.store.session(sid)
        participant=next((p for p in session["personal"]
                          if p["id"]==person_id and p["folio"]==folio),None)
        if participant is None:
            raise ValueError("El ID y folio no coinciden en esta aplicación.")
        report=scan_document(self.store,sid,Path(doc["ruta"]),
                             page_indices=[page_num-1])
        result=report["detalles"][0]
        sheet_id=result["id"]
        if result["estado"]=="duplicado":
            raise ValueError("Folio ya utilizado: revisar el conflicto.")
        # Si en la segunda lectura el QR se validó, aceptar solo al mismo titular.
        with self.store.connect() as db:
            row=db.execute("SELECT token FROM hojas WHERE id=?",
                           (sheet_id,)).fetchone()
        if row["token"] not in (None,participant["token"]):
            raise ValueError("El QR indica un participante distinto.")
        if row["token"] is None:
            self.store.identify_page(sheet_id,person_id,folio,reason,reviewer)
        with self._db() as db:
            db.execute("""
                UPDATE documento_paginas SET sesion_id=?,folio=?,nombre=?,
                    estado='identificada_manual',hoja_id=?,
                    diagnostico='Identidad revisada por ID y folio'
                WHERE sha=? AND pagina=?
            """,(sid,folio,participant["nombre"],sheet_id,sha,page_num))
            self._event(db,sha,page_num,"IDENTIFICADA_MANUAL",
                        reason,sid,reviewer)
        return sheet_id


def create_organized_pdf(src:Path,dest:Path,page_order,rotations=None):
    """Exporta una copia reordenada y girada, con páginas 0-based.

    Ni recorta ni modifica el documento original. No usa Ghostscript.
    """
    from pypdf import PdfReader,PdfWriter
    src,dest=Path(src),Path(dest)
    if src.resolve()==dest.resolve():
        raise ValueError("El PDF organizado debe tener otro nombre.")
    if src.stat().st_size>MAX_PDF_SIZE:
        raise ValueError("PDF de origen demasiado grande.")
    reader=PdfReader(str(src),strict=False)
    if reader.is_encrypted:
        raise ValueError("No se admiten PDF cifrados.")
    selected=list(page_order)
    if not selected or len(selected)>1500 or any(
            type(i) is not int or i<0 or i>=len(reader.pages)
            for i in selected):
        raise ValueError("Selecciona páginas existentes para exportar.")
    rotations=rotations or {}
    writer=PdfWriter()
    for idx in selected:
        angle=rotations.get(idx,0)
        if type(angle) is not int or angle%90!=0:
            raise ValueError("Solo se permiten giros de 90 grados.")
        page=writer.add_page(reader.pages[idx])
        if angle%360:
            page.rotate(angle%360)
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_name("."+dest.name+"."+uuid4().hex+".tmp")
    try:
        with temp.open("wb") as handle:
            writer.write(handle)
        os.replace(temp,dest)
    finally:
        temp.unlink(missing_ok=True)
    return dest


def export_expediente(store:OMRStore,evidence:EvidenceStore,sid:str,
                      output:Path,*,internal=False):
    """ZIP de una aplicación: Excel + PDF vinculado + bitácora y hashes.

    Exportación POR SESIÓN: un PDF mixto nunca provoca filtrar datos de
    otra evaluación al entregable. Los originales puros solo se incluyen
    en el paquete INTERNO. Los mixtos se exportan filtrados.
    """
    sid=str(sid)
    session=store.session(sid)
    target=Path(output)
    if target.suffix.lower()!=".zip":
        raise ValueError("Selecciona un archivo ZIP.")
    from pypdf import PdfReader,PdfWriter
    records=[]
    with evidence._db() as db:
        records=[dict(row) for row in db.execute("""
            SELECT p.sha,p.pagina,p.folio,p.nombre,p.estado,p.hoja_id,
                   d.ruta,d.paginas AS paginas_fuente
            FROM documento_paginas p
            JOIN documentos_recibidos d ON d.sha=p.sha
            WHERE p.sesion_id=?
            ORDER BY p.nombre,p.folio,d.recibido,p.pagina
        """,(sid,))]
    with tempfile.TemporaryDirectory(prefix="omr_exp_") as directory:
        tmp=Path(directory)
        exported=[]
        xlsx=tmp/"Resultados.xlsx"
        export_report(store,sid,xlsx,internal=internal)
        exported.append((xlsx,"Resultados.xlsx"))
        if records:
            pages_writer=PdfWriter()
            source_cache={}
            for row in records:
                sha=row["sha"]
                reader=source_cache.get(sha)
                if reader is None:
                    reader=PdfReader(row["ruta"],strict=False)
                    if reader.is_encrypted:
                        raise ValueError("Original cifrado: no se puede exportar.")
                    source_cache[sha]=reader
                pages_writer.add_page(reader.pages[row["pagina"]-1])
            combined=tmp/"Evidencias_ordenadas.pdf"
            with combined.open("wb") as handle:
                pages_writer.write(handle)
            exported.append((combined,combined.name))

        # No sacar originales con otras sesiones/personas al expediente de una
        # sola evaluación. Preservar referencias SHA para verificarlos localmente.
        omitted=[]
        if internal:
            grouped={}
            for row in records:
                grouped.setdefault(row["sha"],[]).append(row)
            for sha,rows in grouped.items():
                original=Path(rows[0]["ruta"])
                source_name=f"PDF_originales/{sha[:16]}.pdf"
                if len({r["pagina"] for r in rows})==rows[0]["paginas_fuente"]:
                    exported.append((original,source_name))
                else:
                    filtered=tmp/(sha[:16]+"_filtrado.pdf")
                    create_organized_pdf(original,filtered,
                                         [r["pagina"]-1 for r in rows])
                    exported.append((filtered,
                                     "PDF_originales_filtrados/"+filtered.name))
                    omitted.append(
                        {"sha256":sha,"motivo":"Documento mixto o con hojas "
                         "sin identificar; no se incluye original íntegro"})
            notes=tmp/"Bitacora.json"
            notes.write_text(json.dumps({
                "revisiones_omr":store.revisions(sid),
                "eventos_documentales":evidence.audit(sid=sid),
                "vinculos":records,
            },ensure_ascii=False,indent=2),encoding="utf-8")
            exported.append((notes,notes.name))

        manifest={
            "formato":"EXPEDIENTE_OMR_V1",
            "tipo":"interno" if internal else "entrega",
            "sesion_id":sid,
            "evaluacion":session.get("nombre_evaluacion") or session["titulo"],
            "revision_biblioteca":session.get("revision_biblioteca"),
            "fecha":_utc(),
            "provisional":not store.results(sid)["definitivo"],
            "paginas_asociadas":[
                {"sha256_origen":row["sha"],"pagina":row["pagina"],
                 "folio":row["folio"],"estado":row["estado"]}
                for row in records
            ],
            "originales_no_incluidos":omitted,
            "archivos":[
                {"nombre":name,"sha256":_sha256(path),"bytes":path.stat().st_size}
                for path,name in exported
            ],
        }
        target.parent.mkdir(parents=True,exist_ok=True)
        pending=target.with_name("."+target.name+"."+uuid4().hex+".tmp")
        try:
            with ZipFile(pending,"w",compression=ZIP_DEFLATED) as bundle:
                for path,name in exported:
                    bundle.write(path,name)
                bundle.writestr("Manifiesto.json",json.dumps(
                    manifest,ensure_ascii=False,indent=2))
            os.replace(pending,target)
        finally:
            pending.unlink(missing_ok=True)
    return target
