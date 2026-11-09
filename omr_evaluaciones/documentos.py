"""Bandeja documental local de OMR: conserva originales y páginas vinculadas.

Las páginas se clasifican por QR/HMAC en motor.inspect_pdf_sessions. La bandeja
NUNCA decide una nota. Sus estados y exportaciones son independientes del
estado pedagógico de la hoja; los originales son inmutables y direccionados por
SHA-256. No se usa OCR para asociar identidad o calificación.
"""
from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
import json
import os
import shutil

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter

from .motor import MAX_PDF_SIZE, OMRStore, SID_RE, utcnow


def sha_file(path: Path) -> str:
    digest = sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class DocumentInbox:
    """Catálogo compartido con OMRStore, migración aditiva e idempotente.

    document_pages es una tabla de ENLACES, no de calificaciones. Cada página
    se conserva aunque su QR no exista, pertenezca a otra aplicación o falle
    su lectura. En ninguna circunstancia se sobrescribe un PDF original.
    """
    def __init__(self, store: OMRStore):
        self.store = store
        self.root = store.root / 'documentos'
        self.originals = self.root / 'originales'
        self.originals.mkdir(parents=True, exist_ok=True)
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documentos_omr(
                    sha TEXT PRIMARY KEY,
                    ruta TEXT NOT NULL,
                    tamano INTEGER NOT NULL,
                    paginas INTEGER NOT NULL,
                    recibido TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ingresos_documentos_omr(
                    id TEXT PRIMARY KEY,
                    sha TEXT NOT NULL REFERENCES documentos_omr(sha),
                    fecha TEXT NOT NULL,
                    operador TEXT NOT NULL,
                    nombre_original TEXT NOT NULL,
                    nota TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ingresos_sha
                    ON ingresos_documentos_omr(sha,fecha);
                CREATE TABLE IF NOT EXISTS paginas_documentos_omr(
                    sha TEXT NOT NULL REFERENCES documentos_omr(sha),
                    pagina INTEGER NOT NULL,
                    sesion_id TEXT,
                    folio TEXT,
                    persona TEXT,
                    hoja_id TEXT,
                    estado TEXT NOT NULL,
                    diagnostico TEXT NOT NULL DEFAULT '',
                    revisada TEXT,
                    PRIMARY KEY(sha,pagina)
                );
                CREATE INDEX IF NOT EXISTS idx_paginas_sesion
                    ON paginas_documentos_omr(sesion_id,estado);
                CREATE INDEX IF NOT EXISTS idx_paginas_hoja
                    ON paginas_documentos_omr(hoja_id);
                CREATE TABLE IF NOT EXISTS eventos_documentos_omr(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sha TEXT NOT NULL,
                    pagina INTEGER,
                    accion TEXT NOT NULL,
                    fecha TEXT NOT NULL,
                    operador TEXT NOT NULL,
                    detalle TEXT NOT NULL
                );
            """)

    def _event(self, db, sha, page, action, operator, detail):
        db.execute("""
            INSERT INTO eventos_documentos_omr
            (sha,pagina,accion,fecha,operador,detalle)
            VALUES(?,?,?,?,?,?)
        """, (sha,page,action,utcnow(),operator[:90],detail[:800]))

    def _validate_file(self, source):
        path=Path(source)
        if not path.is_file() or path.suffix.lower()!='.pdf':
            raise ValueError('Selecciona un PDF existente.')
        if not 0<path.stat().st_size<=MAX_PDF_SIZE:
            raise ValueError('PDF vacío o mayor que 100 MB.')
        with path.open('rb') as src:
            if src.read(5)!=b'%PDF-':
                raise ValueError('El archivo no tiene cabecera PDF.')
        return path

    def archive(self, source, inspection, *, operator='Operador'):
        """Copia una vez y registra TODAS las páginas, verificadas o pendientes.

        Esta operación ocurre DESPUÉS de la confirmación del operador. Si
        inspection corresponde a otra versión del archivo, se rechaza antes
        de asociar sesiones para evitar una carrera de contenido.
        """
        source=self._validate_file(source)
        digest=sha_file(source)
        if digest!=inspection.get('pdf_sha256'):
            raise ValueError('El PDF cambió desde la identificación QR. '
                             'Vuelve a cargarlo antes de calificar.')
        n=inspection.get('total_paginas')
        items=inspection.get('paginas',[])
        if not isinstance(n,int) or n<1 or n>1500 or len(items)!=n:
            raise ValueError('Inspección incompleta: faltan páginas.')
        if [p.get('pagina') for p in items]!=list(range(1,n+1)):
            raise ValueError('El orden de páginas inspeccionado no coincide.')
        dst=self.originals/(digest+'.pdf')
        if dst.exists():
            if sha_file(dst)!=digest:
                raise ValueError('El PDF archivado ha cambiado: '
                                 'restaura la copia desde un respaldo.')
        else:
            with NamedTemporaryFile(dir=self.originals,suffix='.part',
                                    delete=False) as temp:
                temporary=Path(temp.name)
            try:
                shutil.copyfile(source,temporary)
                if sha_file(temporary)!=digest:
                    raise ValueError('Falló la verificación SHA-256 del PDF.')
                os.replace(temporary,dst)
            finally:
                temporary.unlink(missing_ok=True)
        # PDF archivado siempre completo. La BD se actualiza en una
        # transacción y nunca disminuye un estado ya procesado.
        with self.store.connect() as db:
            db.execute("""
                INSERT OR IGNORE INTO documentos_omr(sha,ruta,tamano,paginas,recibido)
                VALUES(?,?,?,?,?)
            """,(digest,str(dst),dst.stat().st_size,n,utcnow()))
            db.execute("""
                INSERT INTO ingresos_documentos_omr(
                    id,sha,fecha,operador,nombre_original,nota)
                VALUES(?,?,?,?,?,?)
            """,(uuid4().hex,digest,utcnow(),operator[:90],
                 source.name[:255],'PDF recibido y conservado'))
            for item in items:
                index=item['pagina']-1
                sid=item.get('sesion_id')
                folio=item.get('folio') if sid else None
                person=item.get('nombre') if sid else None
                if sid and (not SID_RE.fullmatch(sid) or not folio):
                    raise ValueError('La identificación QR contiene datos inválidos.')
                old=db.execute("""
                    SELECT * FROM paginas_documentos_omr
                    WHERE sha=? AND pagina=?
                """,(digest,index)).fetchone()
                if old:
                    if (sid and old['sesion_id'] and
                            (old['sesion_id']!=sid or old['folio']!=folio)):
                        # El archivo no ha cambiado. Una clasificación nueva
                        # contradictoria requiere revisión humana y no se
                        # reemplaza silenciosamente.
                        db.execute("""
                            UPDATE paginas_documentos_omr
                            SET estado='conflicto_identidad',
                                diagnostico='La identificación cambió entre importaciones'
                            WHERE sha=? AND pagina=?
                        """,(digest,index))
                        self._event(db,digest,index,'conflicto_identidad',operator,
                                    'Dos identificaciones diferentes del mismo PDF')
                    elif sid and old['sesion_id'] is None and not old['hoja_id']:
                        db.execute("""
                            UPDATE paginas_documentos_omr
                            SET sesion_id=?,folio=?,persona=?,estado='identificada',
                                diagnostico='',revisada=?
                            WHERE sha=? AND pagina=?
                        """,(sid,folio,person,utcnow(),digest,index))
                    continue
                db.execute("""
                    INSERT INTO paginas_documentos_omr(
                        sha,pagina,sesion_id,folio,persona,hoja_id,
                        estado,diagnostico,revisada)
                    VALUES(?,?,?,?,?,?,?,?,?)
                """,(digest,index,sid,folio,person,None,
                     'identificada' if sid else 'pendiente',
                     item.get('diagnostico','')[:500],utcnow()))
            self._event(db,digest,None,'ingreso',operator,
                        f'{source.name} · {n} páginas · QR firmado verificado')
        return digest, dst

    def mark_processed(self, digest, sid, report, *, operator='Lector OMR'):
        """Relaciona las páginas archivadas con el ID real devuelto por OMR."""
        if not SID_RE.fullmatch(sid):
            raise ValueError('Aplicación inválida.')
        with self.store.connect() as db:
            for detail in report.get('detalles',[]):
                page=int(detail['pagina'])-1
                row=db.execute("""
                    SELECT * FROM paginas_documentos_omr
                    WHERE sha=? AND pagina=?
                """,(digest,page)).fetchone()
                if not row or row['sesion_id']!=sid:
                    raise ValueError('No se puede asociar una hoja a otra aplicación.')
                if row['estado']=='conflicto_identidad':
                    continue
                action=detail['estado']
                state=('conflicto_duplicado' if action=='duplicado' else
                       'procesada' if action in ('validada','revisar') or
                       action.startswith('reprocesada_') else
                       'reimportada' if action=='repetida' else
                       'pendiente')
                if row['estado']=='procesada' and state=='reimportada':
                    # La nueva importación no disminuye un estado terminado.
                    continue
                db.execute("""
                    UPDATE paginas_documentos_omr
                    SET hoja_id=?,estado=?,diagnostico=?,revisada=?
                    WHERE sha=? AND pagina=?
                """,(detail.get('id'),state,
                     detail.get('diagnostico','')[:500],utcnow(),
                     digest,page))
                self._event(db,digest,page,'lectura_'+action,operator,sid)

    def documents(self):
        with self.store.connect() as db:
            return [dict(x) for x in db.execute("""
                SELECT d.sha,d.tamano,d.paginas,d.recibido,d.ruta,
                    (SELECT nombre_original FROM ingresos_documentos_omr i
                     WHERE i.sha=d.sha ORDER BY fecha DESC LIMIT 1) AS nombre,
                    (SELECT COUNT(*) FROM paginas_documentos_omr p
                     WHERE p.sha=d.sha AND p.estado IN
                     ('pendiente','conflicto_identidad','conflicto_duplicado')
                    ) AS pendientes,
                    (SELECT COUNT(*) FROM ingresos_documentos_omr i
                     WHERE i.sha=d.sha) AS veces_recibido
                FROM documentos_omr d ORDER BY d.recibido DESC,d.sha
            """)]

    def pages(self, digest):
        with self.store.connect() as db:
            return [dict(x) for x in db.execute("""
                SELECT * FROM paginas_documentos_omr
                WHERE sha=? ORDER BY pagina
            """,(digest,))]

    def original(self, digest):
        if not isinstance(digest,str) or len(digest)!=64 or any(
            ch not in '0123456789abcdef' for ch in digest):
            raise ValueError('Huella documental inválida.')
        source=self.originals/(digest+'.pdf')
        if not source.is_file() or sha_file(source)!=digest:
            raise ValueError('Documento original ausente o alterado.')
        return source

    def events(self, digest=None):
        with self.store.connect() as db:
            sql='SELECT * FROM eventos_documentos_omr'
            params=()
            if digest:
                sql+=' WHERE sha=?'
                params=(digest,)
            sql+=' ORDER BY id'
            return [dict(x) for x in db.execute(sql,params)]

    def bind_manual_pending(self, digest, page, sid, personal_id, folio,
                            reviewer, reason):
        """Asocia un QR ilegible a una aplicación SOLO como pendiente.

        Nunca se adjudica una nota. Se exige cotejo visual de ID+folio
        contra participantes de la sesión. La lectura de la hoja para
        calificarla sigue requiriendo revisión humana en OMRStore.
        """
        if not str(reviewer).strip() or not str(reason).strip():
            raise ValueError('Es necesario revisor y motivo.')
        person=next((x for x in self.store.session(sid)['personal']
                     if x['id']==personal_id and x['folio']==folio),None)
        if person is None:
            raise ValueError('ID y folio no corresponden a esa aplicación.')
        with self.store.connect() as db:
            row=db.execute("""
                SELECT * FROM paginas_documentos_omr WHERE sha=? AND pagina=?
            """,(digest,page)).fetchone()
            if row is None or row['estado'] not in ('pendiente','identificada'):
                raise ValueError('Solo pueden asociarse hojas pendientes.')
            if row['sesion_id'] and row['sesion_id']!=sid:
                raise ValueError('La hoja ya pertenece a otra evaluación.')
            db.execute("""
                UPDATE paginas_documentos_omr SET sesion_id=?,folio=?,persona=?,
                    estado='manual_pendiente',diagnostico=?,revisada=?
                WHERE sha=? AND pagina=?
            """,(sid,folio,person['nombre'],
                 'Vinculación de folio sin QR: requiere captura manual',
                 utcnow(),digest,page))
            self._event(db,digest,page,'vinculacion_manual',reviewer,
                        reason.strip()[:600])
        return person['nombre']

    def assemble(self, selections, target):
        """Compone PDF nuevo: [(sha, índice 0-based, rotación °)].

        Permite reordenar, girar, extraer y combinar sin editar originales.
        No asocia identidades ni altera el resultado de una aplicación.
        """
        entries=list(selections)
        if not entries or len(entries)>1500:
            raise ValueError('Selecciona entre 1 y 1500 páginas.')
        output=Path(target)
        if output.suffix.lower()!='.pdf':
            raise ValueError('La salida debe ser un PDF.')
        if output.resolve().is_relative_to(self.originals.resolve()):
            raise ValueError('No sobrescribas el archivo de originales.')
        output.parent.mkdir(parents=True,exist_ok=True)
        writer=PdfWriter()
        with ExitStack() as stack:
            readers={}
            for digest,index,rotation in entries:
                if rotation not in (0,90,180,270):
                    raise ValueError('Rotación permitida: 0, 90, 180 o 270.')
                if type(index) is not int or index<0:
                    raise ValueError('Número de página inválido.')
                if digest not in readers:
                    handle=stack.enter_context(self.original(digest).open('rb'))
                    readers[digest]=PdfReader(handle,strict=False)
                reader=readers[digest]
                if index>=len(reader.pages):
                    raise ValueError('La página indicada no existe.')
                writer.add_page(reader.pages[index])
                if rotation:
                    writer.pages[-1].rotate(rotation)
            with NamedTemporaryFile(dir=output.parent,suffix='.part',
                                    delete=False) as f:
                tmp=Path(f.name)
            try:
                with tmp.open('wb') as out:
                    writer.write(out)
                os.replace(tmp,output)
            finally:
                tmp.unlink(missing_ok=True)
        return output

    def render_page(self, digest, index, *, scale=0.9, rotate=0):
        """Vista previa ligera; solamente se dibuja la página seleccionada."""
        if rotate not in (0,90,180,270) or not .2<=scale<=1.5:
            raise ValueError('Vista previa fuera de rango.')
        original=self.original(digest)
        doc=pdfium.PdfDocument(str(original))
        try:
            if not 0<=index<len(doc):
                raise ValueError('Página fuera de rango.')
            page=doc[index]
            try:
                img=page.render(scale=scale).to_pil().convert('RGB')
            finally:
                page.close()
        finally:
            doc.close()
        if rotate:
            img=img.rotate(-rotate,expand=True)
        return img
