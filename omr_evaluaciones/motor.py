"""Motor OMR local independiente de Tkinter, de los PDF privados y de servicios web.

Contratos principales:
- Cuatro marcas negras de registro; QR con token opaco y HMAC por sesión.
- La hoja impresa y el lector comparten exactamente la función bubble_positions.
- Ninguna lectura ambigua ni persona sin identificación se da por calificada.
- Los originales se preservan y cada corrección queda registrada en una bitácora.
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, BadZipFile

import cv2
import numpy as np
import pypdfium2 as pdfium
import qrcode
from PIL import Image
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader

PAPERS={'A4':A4,'Carta':letter,'Oficio':(612.0,936.0)}
SID_RE=re.compile(r'^[a-f0-9]{12}$')
IDS_RE=re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
ANSWER_CHOICES=('A','B','C','D')
MAX_PARTICIPANTS=500
MAX_QUESTIONS=100
MAX_PDF_SIZE=100*1024*1024
RENDER_DPI=200
RADIUS=7.7
QR_RE=re.compile(r'^OMR1\|([0-9a-f]{12})\|([0-9a-f]{24})\|([0-9]+)\|([0-9a-f]{16})$')

def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def compact_json(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))

def validate_questions(questions):
    if not isinstance(questions,list) or not 1<=len(questions)<=MAX_QUESTIONS:
        raise ValueError('Se requieren entre 1 y 100 preguntas.')
    for i,q in enumerate(questions,1):
        if not isinstance(q,dict) or not str(q.get('tema','')).strip() or q.get('correcta') not in ANSWER_CHOICES:
            raise ValueError(f'Pregunta {i}: requiere tema y respuesta A/B/C/D.')
        if not isinstance(q.get('pregunta'),str) or not q['pregunta'].strip():
            raise ValueError(f'Pregunta {i}: falta el enunciado.')

def read_roster(path:Path):
    """Lee CSV o Excel con ID de personal textual, nombre y adscripción; no altera fuentes."""
    path=Path(path)
    if path.stat().st_size>8*1024*1024:raise ValueError('La lista excede 8 MB.')
    if path.suffix.lower()=='.csv':
        with path.open('r',encoding='utf-8-sig',newline='') as h:
            content=list(csv.DictReader(h))
    elif path.suffix.lower()=='.xlsx':
        # El XLSX es un ZIP: limitar cantidad y expansión antes de abrirlo.
        try:
            with ZipFile(path) as archive:
                members=archive.infolist()
                if len(members)>180 or sum(v.file_size for v in members)>20*1024*1024:
                    raise ValueError('La lista XLSX contiene demasiados elementos.')
                if any('externalLink' in v.filename for v in members):
                    raise ValueError('No se admiten vínculos externos en el Excel de personal.')
        except BadZipFile as exc:
            raise ValueError('La lista XLSX no es válida.') from exc
        from openpyxl import load_workbook
        book=load_workbook(path,read_only=True,data_only=True)
        try:
            rows=list(book.active.iter_rows(values_only=True))
        finally:book.close()
        if not rows:raise ValueError('La hoja está vacía.')
        keys=[str(v or '').strip() for v in rows[0]]
        content=[dict(zip(keys,r)) for r in rows[1:] if any(x is not None for x in r)]
    else:raise ValueError('El archivo debe ser CSV o XLSX.')
    result=[]
    ids=set()
    for index,entry in enumerate(content,2):
        normalized={str(k).strip().casefold():v for k,v in entry.items() if k is not None}
        identifier=normalized.get('id_personal',normalized.get('id',''))
        if isinstance(identifier,float) and identifier.is_integer():identifier=int(identifier)
        identifier=str(identifier or '').strip()
        name=str(normalized.get('nombre') or '').strip()
        if not IDS_RE.fullmatch(identifier) or not name or len(name)>130:
            raise ValueError(f'Fila {index}: ID o nombre inválido; el ID debe ser texto y único.')
        if identifier in ids:raise ValueError(f'ID duplicado en fila {index}: {identifier}')
        ids.add(identifier)
        result.append({'id':identifier,'nombre':name,
            'area':str(normalized.get('area_adscripcion',normalized.get('area','')) or '').strip()[:90],
            'grupo':str(normalized.get('grupo') or '').strip()[:80],
            'turno':str(normalized.get('turno') or '').strip()[:60]})
        if len(result)>MAX_PARTICIPANTS:raise ValueError('Máximo 500 participantes por sesión.')
    if not result:raise ValueError('No hay participantes válidos.')
    return result

def bubble_positions(paper:str,n:int):
    """Centro (puntos PDF) de cada opción; esta geometría gobierna impresión y detección."""
    if paper not in PAPERS:raise ValueError('Formato de papel inválido.')
    if not 1<=n<=MAX_QUESTIONS:raise ValueError('Número de preguntas inválido.')
    w,h=PAPERS[paper]
    cols=1 if n<=25 else 2 if n<=50 else 4
    columns_width=(w-56)/cols
    pts=[]
    for idx in range(n):
        col,row=divmod(idx,25)
        base=28+columns_width*col
        y=h-227-row*19.3
        pts.append(tuple((base+45+23*k,y) for k in range(4)))
    return pts

def corner_centers(paper):
    w,h=PAPERS[paper]
    return [(32,h-32),(w-32,h-32),(w-32,32),(32,32)]

def _make_qr(text):
    obj=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=8,border=3)
    obj.add_data(text);obj.make(fit=True)
    return obj.make_image(fill_color='black',back_color='white').convert('RGB')

def _qr_data(sid,token,page,key):
    v=f'{sid}|{token}|{page}'
    tag=hmac.new(bytes.fromhex(key),v.encode(),hashlib.sha256).hexdigest()[:16]
    return f'OMR1|{v}|{tag}'

class OMRStore:
    """Persistencia transaccional local; cada instancia abre/cierra sus conexiones."""
    def __init__(self,root:Path):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.database=self.root/'sesiones.sqlite3'
        self._init()
    def connect(self):
        db=sqlite3.connect(self.database,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=15000')
        return db
    def _init(self):
        with self.connect() as db:
            db.executescript('''
             CREATE TABLE IF NOT EXISTS sesiones(
               id TEXT PRIMARY KEY, titulo TEXT NOT NULL, modo TEXT NOT NULL,
               papel TEXT NOT NULL, preguntas_json TEXT NOT NULL, version_sha TEXT NOT NULL,
               clave_hmac TEXT NOT NULL, creada TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'abierta');
             CREATE TABLE IF NOT EXISTS participantes(
               sesion_id TEXT NOT NULL, id TEXT NOT NULL,nombre TEXT NOT NULL,
               area TEXT, grupo TEXT,turno TEXT,token TEXT NOT NULL UNIQUE,
               folio TEXT NOT NULL UNIQUE,PRIMARY KEY(sesion_id,id),
               FOREIGN KEY(sesion_id) REFERENCES sesiones(id));
             CREATE TABLE IF NOT EXISTS hojas(
               id TEXT PRIMARY KEY,sesion_id TEXT NOT NULL,token TEXT,
               archivo_sha TEXT NOT NULL,pagina INTEGER NOT NULL,
               imagen TEXT NOT NULL, respuestas_json TEXT NOT NULL,
               dudas_json TEXT NOT NULL,estado TEXT NOT NULL,creada TEXT NOT NULL,
               FOREIGN KEY(sesion_id) REFERENCES sesiones(id));
             CREATE UNIQUE INDEX IF NOT EXISTS idx_ses_pdf_page ON hojas(sesion_id,archivo_sha,pagina);
             CREATE TABLE IF NOT EXISTS revisiones(
               id INTEGER PRIMARY KEY AUTOINCREMENT,hoja_id TEXT NOT NULL,pregunta INTEGER,
               decision TEXT NOT NULL,motivo TEXT NOT NULL,revisor TEXT NOT NULL,
               fecha TEXT NOT NULL,FOREIGN KEY(hoja_id) REFERENCES hojas(id));
            ''')
            # Bitácora de cada lote importado: subir páginas en varias fechas
            # no debe crear otro registro por persona ni perder el PDF original.
            db.execute("""
                CREATE TABLE IF NOT EXISTS importaciones_paginas(
                    sesion_id TEXT NOT NULL, archivo_sha TEXT NOT NULL,
                    pagina INTEGER NOT NULL, hoja_id TEXT NOT NULL,
                    accion TEXT NOT NULL, fecha TEXT NOT NULL,
                    PRIMARY KEY(sesion_id,archivo_sha,pagina),
                    FOREIGN KEY(sesion_id) REFERENCES sesiones(id)
                )
            """)
            # Migración aditiva: sesiones antiguas, escaneos y claves HMAC
            # continúan íntegros. No se fusionan dos bases de datos.
            fields={r['name'] for r in db.execute('PRAGMA table_info(sesiones)')}
            additions={
                'nombre_evaluacion':'TEXT',
                'cuestionario_id':'TEXT',
                'revision_biblioteca':'INTEGER',
                'lote_path':'TEXT',
            }
            for field,sqltype in additions.items():
                if field not in fields:
                    db.execute(f'ALTER TABLE sesiones ADD COLUMN {field} {sqltype}')
    def create_session(self,title,questions,people,paper='Carta',modo='personalizado',
                       *,nombre_evaluacion=None,cuestionario_id=None,
                       revision_biblioteca=None):
        validate_questions(questions)
        if modo not in ('normal','tradicional','ecologico','personalizado'):
            raise ValueError('Modalidad de sesión inválida.')
        if paper not in PAPERS:raise ValueError('Formato inválido.')
        if len(people)>MAX_PARTICIPANTS:raise ValueError('Demasiadas personas.')
        sid=uuid4().hex[:12];secret=secrets.token_hex(32)
        src=compact_json(questions)
        digest=hashlib.sha256(src.encode()).hexdigest()
        with self.connect() as db:
            db.execute('INSERT INTO sesiones(id,titulo,modo,papel,preguntas_json,version_sha,clave_hmac,creada) VALUES(?,?,?,?,?,?,?,?)',
                (sid,title[:100],modo,paper,src,digest,secret,utcnow()))
            if nombre_evaluacion or cuestionario_id or revision_biblioteca is not None:
                db.execute("""
                    UPDATE sesiones SET nombre_evaluacion=?,cuestionario_id=?,
                        revision_biblioteca=? WHERE id=?
                """,((nombre_evaluacion or title).strip()[:120],
                     cuestionario_id,revision_biblioteca,sid))
            for p in people:
                if not IDS_RE.fullmatch(str(p.get('id',''))):raise ValueError('ID del participante inválido.')
                if not str(p.get('nombre','')).strip():raise ValueError('Falta nombre del participante.')
                tok=secrets.token_hex(12)
                # El folio no contiene el ID de empleado y no se repite entre sesiones.
                folio='EX-'+secrets.token_hex(5).upper()
                db.execute('INSERT INTO participantes VALUES(?,?,?,?,?,?,?,?)',
                    (sid,p['id'],p['nombre'],p.get('area',''),p.get('grupo',''),p.get('turno',''),tok,folio))
        return sid
    def update_lote(self,sid,path):
        """Vincula sin alterar la clave OMR la carpeta de impresión del lote."""
        with self.connect() as db:
            db.execute('UPDATE sesiones SET lote_path=? WHERE id=?',
                       (str(Path(path).resolve()),sid))

    def link_legacy_library_by_exact_key(self,library_path):
        """Vincula aplicaciones antiguas SOLO ante coincidencia única verificable.

        Para sesiones impresas antes de guardar el UUID de biblioteca, se
        compara hash de reactivos, opciones correctas y tamaño de papel.
        Si hay 0 o múltiples cuestionarios equivalentes, no se supone nombre.
        La calificación, HMAC y revisión histórica no cambian.
        """
        library=Path(library_path)
        if not library.is_file():
            return 0
        from biblioteca import db_connect
        by_fingerprint={}
        with db_connect(library) as conn:
            rows=conn.execute("""
                SELECT id,nombre,preguntas_json,tamano_papel
                FROM cuestionarios WHERE eliminado_en IS NULL
            """).fetchall()
        for row in rows:
            try:
                questions=json.loads(row['preguntas_json'])
                reduced=[{
                    'tema':q['tema'],'pregunta':q['pregunta'],
                    'correcta':q['correcta'],
                } for q in questions]
                fingerprint=hashlib.sha256(
                    compact_json(reduced).encode()).hexdigest()
                key=(fingerprint,row['tamano_papel'])
            except (KeyError,ValueError,TypeError):
                continue
            by_fingerprint.setdefault(key,[]).append(
                (row['id'],row['nombre']))
        linked=0
        with self.connect() as db:
            old=db.execute("""
                SELECT id,version_sha,papel FROM sesiones
                WHERE cuestionario_id IS NULL AND nombre_evaluacion IS NULL
            """).fetchall()
            for row in old:
                matches=by_fingerprint.get((row['version_sha'],row['papel']),[])
                if len(matches)!=1:
                    continue
                ident,name=matches[0]
                db.execute("""
                    UPDATE sesiones SET cuestionario_id=?,nombre_evaluacion=?
                    WHERE id=? AND cuestionario_id IS NULL
                """,(ident,name,row['id']))
                linked+=1
        return linked

    def rename_session(self,sid,name):
        """Permite recuperar nombres de sesiones anteriores sin cambiar folios."""
        name=str(name).strip()
        if not name or len(name)>120:
            raise ValueError('Escribe un nombre de 1 a 120 caracteres.')
        if not SID_RE.fullmatch(str(sid)):
            raise ValueError('Identificador de sesión inválido.')
        with self.connect() as db:
            if db.execute('UPDATE sesiones SET nombre_evaluacion=? WHERE id=?',
                          (name,sid)).rowcount!=1:
                raise ValueError('Sesión inexistente.')

    def discard_empty_session(self,sid):
        """Limpia únicamente un intento fallido propio SIN hojas escaneadas."""
        with self.connect() as db:
            if db.execute('SELECT COUNT(*) FROM hojas WHERE sesion_id=?',(sid,)).fetchone()[0]:
                return False
            db.execute('DELETE FROM participantes WHERE sesion_id=?',(sid,))
            db.execute('DELETE FROM sesiones WHERE id=?',(sid,))
        return True

    def session(self,sid):
        if not SID_RE.fullmatch(sid):raise ValueError('Sesión inválida.')
        with self.connect() as db:
            s=db.execute('SELECT * FROM sesiones WHERE id=?',(sid,)).fetchone()
            if s is None:raise ValueError('Sesión inexistente.')
            participants=[dict(r) for r in db.execute('SELECT * FROM participantes WHERE sesion_id=? ORDER BY nombre,id',(sid,))]
        return dict(s)|{'preguntas':json.loads(s['preguntas_json']),'personal':participants}
    def sessions(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""
                SELECT s.id,s.titulo,s.nombre_evaluacion,s.cuestionario_id,
                       s.revision_biblioteca,s.lote_path,s.modo,s.papel,s.creada,
                       s.estado,
                       (SELECT COUNT(*) FROM participantes p
                        WHERE p.sesion_id=s.id) AS cantidad_participantes,
                       (SELECT COUNT(*) FROM hojas h
                        WHERE h.sesion_id=s.id) AS hojas_escaneadas,
                       (SELECT COUNT(*) FROM hojas h
                        WHERE h.sesion_id=s.id AND h.estado IN
                        ('sin_identificar','revisar','duplicado')) AS hojas_pendientes
                FROM sesiones s ORDER BY s.creada DESC
            """)]
    def register_page(self,sid,source_sha,page_idx,image,token,answers,uncertain,state):
        """Ingesta incremental: idempotente por PDF/página y folio.

        - Mismo PDF/página: repetida, salvo mejora automática de pendientes
          SIN decisiones humanas, entonces reprocesa en el registro anterior.
        - Otro PDF con el mismo folio y respuestas/dudas equivalentes: ya
          registrada, no duplica examen, participante ni trabajo.
        - Folio idéntico pero respuestas distintas: conflicto duplicado para
          revisión humana; nunca se reemplaza la calificación anterior.
        """
        if image is None or image.ndim!=3:
            raise ValueError('Imagen de página inválida.')
        entry_id=uuid4().hex
        folder=self.root/'escaneos'/sid
        folder.mkdir(parents=True,exist_ok=True)
        target=folder/(entry_id+'.png')

        def archive():
            if not cv2.imwrite(str(target),image):
                raise OSError('No fue posible archivar el escaneo.')

        with self.connect() as db:
            original=db.execute("""
                SELECT * FROM hojas WHERE sesion_id=? AND archivo_sha=? AND pagina=?
            """,(sid,source_sha,page_idx)).fetchone()
            if original:
                human=db.execute("""
                    SELECT COUNT(*) FROM revisiones
                    WHERE hoja_id=? AND revisor!='Motor OMR'
                """,(original['id'],)).fetchone()[0]
                prev_doubts=json.loads(original['dudas_json'])
                better=(
                    human==0 and token is not None and
                    state in ('validada','revisar') and
                    (original['token'] is None or original['token']==token) and
                    (original['estado']=='sin_identificar' or
                     (original['estado']=='revisar' and
                      len(uncertain)<len(prev_doubts)))
                )
                if better:
                    other=db.execute("""
                        SELECT COUNT(*) FROM hojas
                        WHERE sesion_id=? AND token=? AND id<>?
                        AND estado NOT IN ('descartada','duplicado')
                    """,(sid,token,original['id'])).fetchone()[0]
                    result='duplicado' if other else state
                    archive()
                    db.execute("""
                        UPDATE hojas SET token=?,imagen=?,respuestas_json=?,
                        dudas_json=?,estado=? WHERE id=?
                    """,(token,str(target),compact_json(answers),
                         compact_json(uncertain),result,original['id']))
                    db.execute("""
                        INSERT INTO revisiones(
                            hoja_id,pregunta,decision,motivo,revisor,fecha)
                        VALUES(?,?,?,?,?,?)
                    """,(original['id'],None,'RELECTURA_AUTOMATICA',
                         'Mejora del lector sobre PDF ya importado; '
                         'se conserva la evidencia anterior',
                         'Motor OMR',utcnow()))
                    return original['id'],'reprocesada_'+result
                return original['id'],'repetida'
            if token:
                previous=db.execute("""
                    SELECT * FROM hojas WHERE sesion_id=? AND token=?
                    AND estado NOT IN ('duplicado','descartada')
                    ORDER BY creada,id LIMIT 1
                """,(sid,token)).fetchone()
                if previous:
                    old_answers=json.loads(previous['respuestas_json'])
                    old_doubts=json.loads(previous['dudas_json'])
                    equivalent=(
                        list(answers)==old_answers and
                        {v.get('pregunta') for v in uncertain}==
                        {v.get('pregunta') for v in old_doubts}
                    )
                    if equivalent:
                        # PDF distinto, pero el MISMO folio/respuestas. El PDF
                        # fuente está archivado por scan_document; no repetir
                        # PNG ni crear una segunda hoja en la evaluación.
                        db.execute("""
                            INSERT OR IGNORE INTO importaciones_paginas
                            (sesion_id,archivo_sha,pagina,hoja_id,accion,fecha)
                            VALUES(?,?,?,?,?,?)
                        """,(sid,source_sha,page_idx,previous['id'],
                             'reimportada_sin_cambios',utcnow()))
                        return previous['id'],'repetida'
                    state='duplicado'
            archive()
            db.execute("""
                INSERT INTO hojas(
                    id,sesion_id,token,archivo_sha,pagina,imagen,
                    respuestas_json,dudas_json,estado,creada)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """,(entry_id,sid,token,source_sha,page_idx,str(target),
                 compact_json(answers),compact_json(uncertain),state,utcnow()))
            db.execute("""
                INSERT OR IGNORE INTO importaciones_paginas
                (sesion_id,archivo_sha,pagina,hoja_id,accion,fecha)
                VALUES(?,?,?,?,?,?)
            """,(sid,source_sha,page_idx,entry_id,
                 'duplicado_conflictivo' if state=='duplicado' else 'nuevo',
                 utcnow()))
        return entry_id,state

    def pages(self,sid):
        with self.connect() as db:
            rows=db.execute('SELECT * FROM hojas WHERE sesion_id=? ORDER BY creada,id',(sid,)).fetchall()
        return [dict(x)|{'respuestas':json.loads(x['respuestas_json']),'dudas':json.loads(x['dudas_json'])} for x in rows]
    def review(self,page_id,question,decision,reason,reviewer='Evaluador'):
        if not str(reason).strip() or not str(reviewer).strip():raise ValueError('La corrección requiere motivo y revisor.')
        if decision not in ('A','B','C','D','BLANCO','DESCARTAR'):
            raise ValueError('Decisión inválida.')
        with self.connect() as db:
            p=db.execute('SELECT * FROM hojas WHERE id=?',(page_id,)).fetchone()
            if not p:raise ValueError('Hoja inexistente.')
            answers=json.loads(p['respuestas_json']);issues=json.loads(p['dudas_json'])
            if decision=='DESCARTAR':
                if question not in (None,0):raise ValueError('Descartar se aplica a la hoja.')
                status='descartada'
            else:
                if not isinstance(question,int) or not 1<=question<=len(answers):raise ValueError('Pregunta inválida.')
                answers[question-1]=None if decision=='BLANCO' else decision
                issues=[x for x in issues if x.get('pregunta')!=question]
                status='revisar' if issues else 'validada'
                if p['token'] is None:status='sin_identificar'
                if p['estado']=='duplicado':status='duplicado'
            db.execute('UPDATE hojas SET respuestas_json=?,dudas_json=?,estado=? WHERE id=?',
                (compact_json(answers),compact_json(issues),status,page_id))
            db.execute('INSERT INTO revisiones(hoja_id,pregunta,decision,motivo,revisor,fecha) VALUES(?,?,?,?,?,?)',
                (page_id,question,decision,reason.strip()[:600],reviewer.strip()[:90],utcnow()))
    def capture_manual_sheet(self,page_id,decisions,reason,reviewer='Evaluador'):
        """Captura completa y auditada para una hoja identificada, sin OCR ni suposiciones.

        Las hojas sin QR requieren identify_page() (ID + folio exactos)
        ANTES de guardar respuestas. Ninguna casilla 'sin revisar' se admite.
        """
        if not str(reason).strip() or not str(reviewer).strip():
            raise ValueError('Indica justificación y nombre del evaluador.')
        if not isinstance(decisions,(list,tuple)):
            raise ValueError('Especifica todas las respuestas de la hoja.')
        valid={'A','B','C','D','BLANCO'}
        if any(choice not in valid for choice in decisions):
            raise ValueError('Revisa todos los reactivos; usa BLANCO si no contestó.')
        with self.connect() as db:
            page=db.execute('SELECT * FROM hojas WHERE id=?',(page_id,)).fetchone()
            if page is None:
                raise ValueError('No existe la hoja seleccionada.')
            if page['token'] is None:
                raise ValueError('Primero identifica por ID y folio; no se asignan '
                                 'respuestas a personas desconocidas.')
            if page['estado'] in ('duplicado','descartada'):
                raise ValueError('Resuelve antes la hoja duplicada o descartada.')
            row=db.execute('SELECT preguntas_json FROM sesiones WHERE id=?',
                           (page['sesion_id'],)).fetchone()
            n=len(json.loads(row['preguntas_json']))
            if len(decisions)!=n:
                raise ValueError(f'Se requieren {n} respuestas verificadas.')
            values=[None if choice=='BLANCO' else choice for choice in decisions]
            db.execute('UPDATE hojas SET respuestas_json=?,dudas_json=?,estado=? WHERE id=?',
                       (compact_json(values),'[]','validada',page_id))
            db.executemany('''
                INSERT INTO revisiones(hoja_id,pregunta,decision,motivo,revisor,fecha)
                VALUES(?,?,?,?,?,?)
            ''',[(page_id,k,decision,
                  reason.strip()[:600],reviewer.strip()[:90],utcnow())
                 for k,decision in enumerate(decisions,1)])
        return n

    def identify_page(self,page_id,person_id,printed_folio,reason,reviewer='Evaluador'):
        '''Asocia una hoja sin QR solo tras verificar físicamente ID y folio.

        En ausencia de QR no se confía en marcas detectadas: se exige revisar
        cada reactivo manualmente o repetir el escaneo. Nunca asigna nota sola.
        '''
        if not str(reason).strip() or not str(reviewer).strip():
            raise ValueError('Se requiere justificación y revisor.')
        with self.connect() as db:
            page=db.execute('SELECT * FROM hojas WHERE id=?',(page_id,)).fetchone()
            if page is None or page['estado']!='sin_identificar':
                raise ValueError('La hoja no está pendiente de identificación.')
            person=db.execute('SELECT * FROM participantes WHERE sesion_id=? AND id=? AND folio=?',
                    (page['sesion_id'],str(person_id),str(printed_folio))).fetchone()
            if person is None:raise ValueError('ID personal y folio no coinciden con esta sesión.')
            existing=db.execute('SELECT COUNT(*) FROM hojas WHERE sesion_id=? AND token=? AND estado NOT IN ("descartada","duplicado")',
                (page['sesion_id'],person['token'])).fetchone()[0]
            if existing:raise ValueError('Ya hay una hoja vinculada a ese folio; resuelve la duplicada.')
            s=db.execute('SELECT preguntas_json FROM sesiones WHERE id=?',(page['sesion_id'],)).fetchone()
            count=len(json.loads(s['preguntas_json']))
            issues=[{'pregunta':i,'razon':'Revisión completa: QR original ilegible'} for i in range(1,count+1)]
            db.execute('UPDATE hojas SET token=?,estado=?,respuestas_json=?,dudas_json=? WHERE id=?',
                (person['token'],'revisar',compact_json([None]*count),compact_json(issues),page_id))
            db.execute('INSERT INTO revisiones(hoja_id,pregunta,decision,motivo,revisor,fecha) VALUES(?,?,?,?,?,?)',
                (page_id,None,'IDENTIFICAR '+person['folio'],reason.strip()[:600],reviewer.strip()[:90],utcnow()))

    def results(self,sid):
        s=self.session(sid);pages=self.pages(sid)
        own={}
        for page in pages:
            if page['token'] and page['estado']=='validada':
                own.setdefault(page['token'],[]).append(page)
        n=len(s['preguntas'])
        records=[]
        for p in s['personal']:
            valid=own.get(p['token'],[])
            anyscan=[j for j in pages if j['token']==p['token'] and j['estado']!='descartada']
            if len(valid)==1 and not any(j['estado']=='duplicado' for j in anyscan):
                answers=valid[0]['respuestas']
                good=sum(x==q['correcta'] for x,q in zip(answers,s['preguntas']))
                blanks=sum(x is None for x in answers)
                topics={}
                for t in sorted({q['tema'] for q in s['preguntas']}):
                    indexes=[i for i,q in enumerate(s['preguntas']) if q['tema']==t]
                    hits=sum(answers[i]==s['preguntas'][i]['correcta'] for i in indexes)
                    topics[t]={'aciertos':hits,'preguntas':len(indexes),'porcentaje':round(100*hits/len(indexes),2)}
                status='validado'
            else:
                answers=None;good=None;blanks=None;topics={}
                status='pendiente' if anyscan else 'ausente'
            records.append({**p,'estado':status,'aciertos':good,'preguntas':n,
               'porcentaje':round(good/n*100,2) if good is not None else None,
               'blancos':blanks,'temas':topics})
        graded=[v for v in records if v['aciertos'] is not None]
        # Promedio por persona validada; no bajar por ausencias ni formularios dudosos.
        mean=round(sum(x['porcentaje'] for x in graded)/len(graded),2) if graded else None
        totals={}
        for q in s['preguntas']:
            totals.setdefault(q['tema'],{'preguntas':0,'aciertos':0})['preguntas']+=1
        for p in graded:
            for t,v in p['temas'].items():totals[t]['aciertos']+=v['aciertos']
        for t,v in totals.items():
            v['respuestas_posibles']=v['preguntas']*len(graded)
            v['porcentaje']=round(v['aciertos']/v['respuestas_posibles']*100,2) if v['respuestas_posibles'] else None
        return {'sesion':s,'participantes':records,'promedio':mean,'temas':totals,
           'validados':len(graded),'pendientes':sum(v['estado']=='pendiente' for v in records),
           'ausentes':sum(v['estado']=='ausente' for v in records),
           'hojas':pages,'definitivo':bool(graded) and not any(x['estado']=='pendiente' for x in records) and all(x['estado'] in ('validada','descartada') for x in pages)}
    def revisions(self,sid):
        with self.connect() as db:
            return [dict(x) for x in db.execute('''SELECT r.* FROM revisiones r JOIN hojas h ON h.id=r.hoja_id
                                                WHERE h.sesion_id=? ORDER BY r.id''',(sid,))]


def _draw_formulario_omr(cnv, session: dict, persona: dict | None, *,
                        empresa='', grupo='', subtitulo='',
                        color_titulo='#213A4C', color_respuestas='#213A4C',
                        preview=False):
    """Hoja institucional: una sola geometría para PDF, QR y lectura de escáner.

    Usa bubble_positions y corner_centers sin alteraciones. El aspecto adopta
    el encabezado/colores de la hoja convencional y mantiene espacio libre
    alrededor del QR. La vista previa usa un token no perteneciente a sesiones.
    """
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from src.evaluaciones.core import _font
    normal, bold = _font()
    paper = session['papel']
    w, h = PAPERS[paper]
    tint = colors.HexColor(color_respuestas)
    title_ink = colors.HexColor(color_titulo)
    pts = bubble_positions(paper, len(session['preguntas']))
    cnv.setFillColorRGB(1, 1, 1)
    cnv.rect(0, 0, w, h, fill=1, stroke=0)
    # Cuatro cuadrados sólidos: el lector debe rectificar en las mismas
    # posiciones, con independencia del color o texto institucional.
    for x, y in corner_centers(paper):
        cnv.setFillColorRGB(0, 0, 0)
        cnv.rect(x-6, y-6, 12, 12, stroke=0, fill=1)

    def clip_text(text, font, size, maximum):
        txt = ' '.join(str(text or '').split())
        while txt and pdfmetrics.stringWidth(txt, font, size) > maximum:
            txt = txt[:-1]
        return txt

    cnv.setFillColor(tint)
    cnv.setFont(bold, 13)
    cnv.drawString(44, h-68, 'HOJA DE RESPUESTAS')
    cnv.setFont(bold, 9)
    cnv.setFillColor(title_ink)
    cnv.drawString(44, h-87, clip_text(session['titulo'], bold, 9, w-205))
    if subtitulo:
        cnv.setFont(normal, 8)
        cnv.drawString(44, h-101, clip_text(subtitulo, normal, 8, w-205))
    if empresa:
        cnv.setFillColor(tint)
        cnv.setFont(normal, 8)
        cnv.drawString(44, h-114, clip_text(empresa, normal, 8, w-205))
    cnv.setFillColor(tint)
    cnv.setFont(normal, 9)
    if persona is None:
        # Misma hoja, mismas posiciones y mismas marcas: solamente faltan
        # datos/QR. La persona rellena su nombre y se corrige con acetato.
        cnv.drawString(44,h-129,'Folio: ________________________')
        cnv.drawString(44,h-145,'ID: __________________________')
        cnv.drawString(44,h-161,'Nombre: _________________________________')
        cnv.setFont(normal,7.5)
        cnv.drawString(44,h-179,'Grupo / fecha: ___________________________')
    else:
        cnv.drawString(44,h-129,'Folio: '+persona['folio'])
        cnv.drawString(44,h-145,'ID: '+clip_text(persona['id'],normal,9,w-205))
        cnv.drawString(44,h-161,'Nombre: '+clip_text(persona['nombre'],normal,9,w-205))
        cnv.setFont(normal,7.5)
        label = grupo or persona.get('grupo','')
        if label:
            cnv.drawString(44,h-179,clip_text('Grupo: '+label,normal,7.5,w-205))
        qr_data = _qr_data(session['id'], persona['token'], 1, session['clave_hmac'])
        cnv.drawImage(ImageReader(_make_qr(qr_data)),w-158,h-178,
                      width=113,height=113,mask='auto')
    cnv.setStrokeColor(tint)
    cnv.setLineWidth(.9)
    cnv.line(44,h-190,w-44,h-190)
    n = len(pts)
    cols = 1 if n<=25 else 2 if n<=50 else 4
    cw = (w-56)/cols
    for col in range(cols):
        x=28+col*cw
        cnv.setFillColor(tint)
        cnv.setFont(bold, 7.2)
        for j,letter in enumerate(ANSWER_CHOICES):
            cnv.drawCentredString(x+45+23*j,h-215,letter)
    for i,bubbles in enumerate(pts):
        col,row=divmod(i,25)
        base=28+cw*col
        cnv.setFont(normal,8)
        cnv.setFillColor(tint)
        cnv.drawString(base,bubbles[0][1]-3,f'{i+1:02d}')
        for x,y in bubbles:
            cnv.setLineWidth(.85)
            cnv.setStrokeColor(tint)
            cnv.circle(x,y,RADIUS,fill=0,stroke=1)
    cnv.setFont(normal,7)
    cnv.drawString(44,56,clip_text(
        'Rellena completamente un círculo. Imprimir al 100 % y escanear la hoja completa.',
        normal,7,w-90))
    if preview:
        cnv.setFont(bold,7)
        cnv.drawRightString(w-43,46,
            'VISTA PREVIA · QR SIN SESIÓN VÁLIDA' if persona else
            'VISTA PREVIA · SIN QR')
    cnv.showPage()


def create_forms_pdf(store:OMRStore,sid:str,target:Path, *,
                     empresa='',grupo='',subtitulo='',
                     color_titulo='#213A4C',color_respuestas='#213A4C',
                     person_ids=None):
    """Imprime las hojas QR desde el diseño único; no genera otro examen.

    Cada código tiene HMAC de la misma sesión persistida que utilizará el lector.
    Los marcadores cuadrados y las burbujas proceden del motor OMR existente.
    """
    s=store.session(sid)
    if not s['personal']:
        raise ValueError('Carga participantes antes de generar hojas con folio y QR.')
    path=Path(target)
    path.parent.mkdir(parents=True,exist_ok=True)
    cnv=Canvas(str(path),pagesize=PAPERS[s['papel']],pageCompression=1)
    selected=set(person_ids) if person_ids is not None else None
    if selected is not None:
        actual={p['id'] for p in s['personal']}
        if not selected or not selected.issubset(actual):
            raise ValueError('Participantes solicitados fuera de la sesión OMR.')
    for p in s['personal']:
        if selected is not None and p['id'] not in selected:
            continue
        _draw_formulario_omr(cnv,s,p,empresa=empresa,grupo=grupo,subtitulo=subtitulo,
                            color_titulo=color_titulo,color_respuestas=color_respuestas)
    cnv.save()
    return path


def _draw_acetato_omr(cnv, session: dict, *, color='#167341'):
    from reportlab.lib import colors
    from src.evaluaciones.core import _font
    s=session
    w,h=PAPERS[s['papel']]
    normal,bold=_font()
    cnv.setFont(bold,12)
    cnv.setFillColor(colors.HexColor('#213A4C'))
    cnv.drawString(44,h-68,'ACETATO · HOJA DE RESPUESTAS')
    cnv.setFont(normal,8)
    cnv.drawString(44,h-88,'Misma posición de círculos con o sin QR. Imprimir al 100 %.')
    for x,y in corner_centers(s['papel']):
        cnv.setStrokeColorRGB(0,0,0)
        cnv.setLineWidth(.7)
        cnv.rect(x-6,y-6,12,12,fill=0,stroke=1)
    for idx,points in enumerate(bubble_positions(s['papel'],len(s['preguntas']))):
        x,y=points[ANSWER_CHOICES.index(s['preguntas'][idx]['correcta'])]
        cnv.saveState()
        cnv.setStrokeColor(colors.HexColor(color))
        cnv.setFillColor(colors.HexColor(color))
        cnv.setFillAlpha(.26)
        cnv.setLineWidth(2.2)
        cnv.circle(x,y,RADIUS+3.5,stroke=1,fill=1)
        cnv.restoreState()
    cnv.setFont(normal,7)
    cnv.setFillColor(colors.HexColor('#213A4C'))
    cnv.drawCentredString(w/2,22,'ACETATO DE EVALUACIÓN · IMPRIMIR AL 100 %')
    cnv.showPage()


def create_acetato_omr(store:OMRStore,sid:str,target:Path, *, color='#167341'):
    """Acetato compatible con las hojas QR generadas para ESTA sesión."""
    s=store.session(sid)
    cnv=Canvas(str(target),pagesize=PAPERS[s['papel']],pageCompression=1)
    _draw_acetato_omr(cnv,s,color=color)
    cnv.save()
    return Path(target)


def preview_acetato_omr(questions, paper, *, color='#167341'):
    """La vista previa del acetato usa las mismas coordenadas de la hoja QR."""
    from io import BytesIO
    validate_questions(questions)
    data=BytesIO()
    cnv=Canvas(data,pagesize=PAPERS[paper],pageCompression=1)
    _draw_acetato_omr(cnv,{'papel':paper,'preguntas':questions},color=color)
    cnv.save()
    return data.getvalue()


def preview_formulario_omr(questions, title, paper, *,
                          empresa='',grupo='',subtitulo='',
                          color_titulo='#213A4C',color_respuestas='#213A4C',
                          nombre='Ejemplo de participante',identifier='000001',
                          con_personal=True):
    """Muestra el aspecto exacto sin crear folios utilizables ni escribir disco."""
    from io import BytesIO
    validate_questions(questions)
    sample={'id':identifier,'nombre':nombre,'folio':'EX-VISTA-PREVIA',
            'token':'0'*24,'grupo':grupo}
    session={'id':'0'*12,'titulo':title,'papel':paper,'preguntas':questions,
             'clave_hmac':'0'*64}
    data=BytesIO()
    cnv=Canvas(data,pagesize=PAPERS[paper],pageCompression=1)
    _draw_formulario_omr(cnv,session,sample if con_personal else None,
                        empresa=empresa,grupo=grupo,subtitulo=subtitulo,
                        color_titulo=color_titulo,
                        color_respuestas=color_respuestas,preview=True)
    cnv.save()
    return data.getvalue()



def create_generic_forms_pdf(questions, title, paper, target, *,
                             empresa='',grupo='',subtitulo='',
                             color_titulo='#213A4C',color_respuestas='#213A4C'):
    """Hoja anónima con EXACTA geometría OMR y espacios manuscritos, sin QR.

    El diseño no cambia al cargar personal: solo se rellenan datos y QR.
    El motor de calificación automática exige una sesión y un QR válido.
    """
    validate_questions(questions)
    path=Path(target)
    path.parent.mkdir(parents=True,exist_ok=True)
    cnv=Canvas(str(path),pagesize=PAPERS[paper],pageCompression=1)
    session={'titulo':title,'papel':paper,'preguntas':questions}
    _draw_formulario_omr(cnv,session,None,empresa=empresa,grupo=grupo,
                         subtitulo=subtitulo,color_titulo=color_titulo,
                         color_respuestas=color_respuestas)
    cnv.save()
    return path


def create_generic_acetato_pdf(questions, paper, target, *, color='#167341'):
    """Acetato universal, tanto de la hoja genérica como de las hojas QR."""
    validate_questions(questions)
    path=Path(target)
    path.parent.mkdir(parents=True,exist_ok=True)
    cnv=Canvas(str(path),pagesize=PAPERS[paper],pageCompression=1)
    _draw_acetato_omr(cnv,{'papel':paper,'preguntas':questions},color=color)
    cnv.save()
    return path


def _find_four_markers(gray, paper, factor):
    """Localiza cuatro cuadrados incluso cuando un escáner los vuelve grises.

    La Xerox puede entregar marcas negras con gris ~110-130. El umbral
    histórico de 85 las descartaba, dejando las hojas SIN_IDENTIFICAR.
    Se prueban umbrales de forma ascendente y se valida la geometría.
    """
    h,w=gray.shape[:2]
    tw,th=PAPERS[paper]
    target_side=12*factor
    expected=np.float32([
        (32/tw*w,32/th*h),((tw-32)/tw*w,32/th*h),
        ((tw-32)/tw*w,(th-32)/th*h),(32/tw*w,(th-32)/th*h),
    ])
    for threshold in (85,120,150,185,220):
        _,mask=cv2.threshold(gray,threshold,255,cv2.THRESH_BINARY_INV)
        contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        candidates=[]
        for c in contours:
            x,y,bw,bh=cv2.boundingRect(c)
            if not .53*target_side<=bw<=2.2*target_side:continue
            if not .53*target_side<=bh<=2.2*target_side:continue
            if not .7<bw/max(bh,1)<1.3:continue
            if cv2.contourArea(c)<.42*bw*bh:continue
            candidates.append((x+bw/2,y+bh/2,bw*bh))
        if len(candidates)<4:continue
        points=[]
        for ex,ey in expected:
            nearest=min(candidates,key=lambda z:(z[0]-ex)**2+(z[1]-ey)**2)
            dx=(nearest[0]-ex)/w;dy=(nearest[1]-ey)/h
            if dx*dx+dy*dy>.017:
                break
            points.append(nearest[:2])
        if len(points)!=4 or len(set(points))!=4:continue
        points=np.float32(points)
        if (np.linalg.norm(points[0]-points[1])<.55*w or
                np.linalg.norm(points[0]-points[3])<.55*h):continue
        # Rechazar cuadrados mal ordenados o lados invertidos.
        if not (points[0,0]<points[1,0] and points[3,0]<points[2,0] and
                points[0,1]<points[3,1] and points[1,1]<points[2,1]):
            continue
        return points
    return None

def _rectify(gray,paper):
    scale=RENDER_DPI/72.0
    w,h=PAPERS[paper];tw,th=round(w*scale),round(h*scale)
    # Intentar portrait y rotaciones de 90 grados en un PDF sin orientación fiable.
    variants=[gray,cv2.rotate(gray,cv2.ROTATE_180),cv2.rotate(gray,cv2.ROTATE_90_CLOCKWISE),cv2.rotate(gray,cv2.ROTATE_90_COUNTERCLOCKWISE)]
    expected=np.float32([(32*scale,32*scale),(tw-32*scale,32*scale),
                         (tw-32*scale,th-32*scale),(32*scale,th-32*scale)])
    for img in variants:
        points=_find_four_markers(img,paper,scale)
        if points is None:continue
        warp=cv2.getPerspectiveTransform(points,expected)
        result=cv2.warpPerspective(img,warp,(tw,th),flags=cv2.INTER_LINEAR,borderValue=255)
        yield result

def _decode_qr(gray, *, allow_full=True):
    """Primero leer SOLO el encabezado: más veloz que buscar en toda la página.

    Los recortes y escalados no modifican la evidencia. Solo retorna texto:
    una lectura NO es válida hasta comprobar token, sesión y HMAC.
    """
    detector=cv2.QRCodeDetector()
    h,w=gray.shape[:2]
    x0,x1=int(.65*w),int(.985*w)
    y0,y1=int(.05*h),int(.315*h)
    roi=gray[y0:y1,x0:x1]
    if roi.size==0:
        return None
    for factor in (1.,1.5,2.):
        candidate=(roi if factor==1. else
                   cv2.resize(roi,None,fx=factor,fy=factor,
                              interpolation=cv2.INTER_CUBIC))
        text,points,_=detector.detectAndDecode(candidate)
        if text and points is not None:
            return text
    if allow_full:
        text,points,_=detector.detectAndDecode(gray)
        if text and points is not None:
            center=points.reshape(-1,2).mean(axis=0)
            if .64*w<center[0]<.99*w and .04*h<center[1]<.36*h:
                return text
    try:
        from pyzbar.pyzbar import decode
        for item in decode(Image.fromarray(roi)):
            if item.type=='QRCODE':
                return item.data.decode('utf-8','strict')
    except (ImportError,OSError,UnicodeDecodeError):
        pass
    return None


def render_review_with_acetato(original_bgr, paper, questions, *,
                              show_acetato=True, issue_numbers=()):
    """Renderiza evidencia ALINEADA y acetato digital transparente, nunca el original.

    La homografía usa las cuatro marcas, incluso cuando el QR falló.
    Si no hay cuatro marcas fiables NO superpone la clave sobre una posición
    estimada: exige revisión manual sin overlay. La clave jamás se escribe en
    el PDF escaneado que se conserva en disco.
    """
    from PIL import ImageDraw
    validate_questions(questions)
    if original_bgr is None or len(original_bgr.shape)!=3:
        raise ValueError('La imagen escaneada no es RGB/BGR.')
    gray=cv2.cvtColor(original_bgr,cv2.COLOR_BGR2GRAY)
    aligned=next(_rectify(gray,paper),None)
    if aligned is None:
        raise ValueError('No se pueden alinear cuatro marcas. '
                         'Captura manualmente sin acetato digital o vuelve a escanear.')
    background=Image.fromarray(aligned).convert('RGBA')
    overlay=Image.new('RGBA',background.size,(0,0,0,0))
    draw=ImageDraw.Draw(overlay,'RGBA')
    height=PAPERS[paper][1]
    factor=RENDER_DPI/72.0
    coordinates=bubble_positions(paper,len(questions))
    if show_acetato:
        for idx,(q,options) in enumerate(zip(questions,coordinates)):
            x,y=options[ANSWER_CHOICES.index(q['correcta'])]
            px,py=round(x*factor),round((height-y)*factor)
            r=round((RADIUS+3.5)*factor)
            draw.ellipse((px-r,py-r,px+r,py+r),
                         fill=(15,155,94,65),outline=(0,120,80,230),
                         width=max(3,round(1.3*factor)))
    for n in issue_numbers:
        if not isinstance(n,int) or not 1<=n<=len(coordinates):
            continue
        options=coordinates[n-1]
        coords=[(round(x*factor),round((height-y)*factor)) for x,y in options]
        left=min(x for x,y in coords)-35
        right=max(x for x,y in coords)+35
        top=min(y for x,y in coords)-27
        bottom=max(y for x,y in coords)+27
        draw.rectangle((left,top,right,bottom),outline=(242,147,23,255),
                       width=max(4,round(2*factor)))
    return Image.alpha_composite(background,overlay).convert('RGB')


def resolve_pdf_session(store:OMRStore,pdf_path:Path,*,max_pages=5):
    """Identifica la aplicación por QR firmado, sin confiar en títulos repetidos.

    Inspecciona algunas páginas, valida HMAC/token/ID contra la BD local.
    No vincula la sesión por nombre, posición en el historial ni por OCR.
    Si el PDF contiene folios válidos de dos sesiones, rechaza la atribución.
    """
    path=Path(pdf_path)
    if (not path.is_file() or path.suffix.lower()!='.pdf' or
            path.stat().st_size>MAX_PDF_SIZE):
        raise ValueError('Selecciona un PDF válido de hasta 100 MB.')
    pdf=pdfium.PdfDocument(str(path))
    found=set()
    try:
        for index in range(min(len(pdf),max_pages)):
            page=pdf[index]
            try:
                width,height=page.get_size()
                if not 100<=width<=1500 or not 100<=height<=2000:
                    raise ValueError('Dimensiones de escaneo fuera de rango.')
                rgb=np.asarray(
                    page.render(scale=RENDER_DPI/72).to_pil().convert('RGB'))
            finally:
                page.close()
            gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
            rotations=(gray,cv2.rotate(gray,cv2.ROTATE_180),
                       cv2.rotate(gray,cv2.ROTATE_90_CLOCKWISE),
                       cv2.rotate(gray,cv2.ROTATE_90_COUNTERCLOCKWISE))
            for rotated in rotations:
                decoded=_decode_qr(rotated)
                match=QR_RE.fullmatch(decoded or '')
                if match is None:
                    continue
                sid,token,page_number,tag=match.groups()
                if page_number!='1':continue
                try:
                    s=store.session(sid)
                except ValueError:
                    continue
                if token not in {p['token'] for p in s['personal']}:
                    continue
                if not hmac.compare_digest(
                    _qr_data(sid,token,1,s['clave_hmac']),decoded):
                    continue
                found.add(sid)
                break
            if len(found)>1:
                raise ValueError(
                    'El PDF mezcla QR válidos de evaluaciones diferentes; '
                    'separa los lotes antes de calificar.')
    finally:
        pdf.close()
    return next(iter(found)) if found else None


def inspect_pdf_sessions(store: OMRStore, pdf_path: Path, *, progress=None):
    """Clasifica el lote completo en dos niveles sin modificar calificaciones.

    PREVISUALIZACIÓN RÁPIDA: render a 175 DPI y QR recortado. Solo cuando una
    hoja es difícil se renderiza a 200 DPI y se alinean marcas. No multiplica
    por 4 rotaciones x 3 papeles a menos que fallen las rutas rápidas.
    """
    path=Path(pdf_path)
    if (not path.is_file() or path.suffix.lower()!='.pdf' or
            path.stat().st_size>MAX_PDF_SIZE):
        raise ValueError('Selecciona un PDF válido de hasta 100 MB.')
    with path.open('rb') as source:
        if source.read(5)!=b'%PDF-':
            raise ValueError('Archivo PDF inválido.')
    doc=pdfium.PdfDocument(str(path))
    cache={}
    items=[]
    try:
        count=len(doc)
        if count>1500:
            raise ValueError('PDF con demasiadas páginas.')
        for idx in range(count):
            if progress:
                progress(idx+1,count)
            page=doc[idx]
            try:
                pw,ph=page.get_size()
                if not 100<=pw<=1500 or not 100<=ph<=2000:
                    raise ValueError(f'Página {idx+1}: dimensiones anormales.')
                raw=np.asarray(page.render(scale=175/72).to_pil().convert('RGB'))
            finally:
                page.close()
            gray=cv2.cvtColor(raw,cv2.COLOR_RGB2GRAY)
            seen=False

            def valid_qr(qr):
                nonlocal seen
                if not qr:
                    return None
                seen=True
                match=QR_RE.fullmatch(qr)
                if match is None:return None
                sid,token,page_num,_=match.groups()
                if page_num!='1':return None
                if sid not in cache:
                    try:
                        data=store.session(sid)
                        data['_tokens']={
                            person['token']:person for person in data['personal']
                        }
                        cache[sid]=data
                    except ValueError:
                        cache[sid]=None
                session=cache[sid]
                if session is None:return None
                person=session['_tokens'].get(token)
                if person is None:return None
                if not hmac.compare_digest(
                    _qr_data(sid,token,1,session['clave_hmac']),qr):
                    return None
                return {'pagina':idx+1,'sesion_id':sid,
                        'estado':'verificada',
                        'evaluacion':session.get('nombre_evaluacion')
                                     or session['titulo'],
                        'nombre':person['nombre'],'folio':person['folio']}

            verified=valid_qr(_decode_qr(gray,allow_full=False))
            if verified is None:
                verified=valid_qr(
                    _decode_qr(cv2.rotate(gray,cv2.ROTATE_180),
                               allow_full=False))
            if verified is None:
                # Las páginas complicadas conservan el reconocimiento
                # anterior a resolución completa y alineación por marcas.
                page=doc[idx]
                try:
                    full=np.asarray(page.render(scale=RENDER_DPI/72)
                                      .to_pil().convert('RGB'))
                finally:
                    page.close()
                full_gray=cv2.cvtColor(full,cv2.COLOR_RGB2GRAY)
                orientations=(
                    full_gray,cv2.rotate(full_gray,cv2.ROTATE_180),
                    cv2.rotate(full_gray,cv2.ROTATE_90_CLOCKWISE),
                    cv2.rotate(full_gray,cv2.ROTATE_90_COUNTERCLOCKWISE))
                for rotated in orientations:
                    verified=valid_qr(_decode_qr(rotated))
                    if verified:break
                if verified is None:
                    for paper in PAPERS:
                        for aligned in _rectify(full_gray,paper):
                            verified=valid_qr(_decode_qr(aligned))
                            if verified:break
                        if verified:break
            if verified:
                items.append(verified)
            else:
                items.append({
                    'pagina':idx+1,'sesion_id':None,'estado':'sin_identificar',
                    'diagnostico':(
                        'QR presente pero sin token o firma verificables.'
                        if seen else 'No se pudo leer un QR firmado.'),
                })
    finally:
        doc.close()
    groups={}
    for item in items:
        sid=item['sesion_id']
        if sid:
            if sid not in groups:
                groups[sid]={'sesion_id':sid,'evaluacion':item['evaluacion'],
                             'paginas':[]}
            groups[sid]['paginas'].append(item['pagina'])
    return {'total_paginas':len(items),'paginas':items,
            'grupos':list(groups.values()),
            'no_identificadas':[x for x in items if not x['sesion_id']],
            'mezclado':len(groups)>1}


def _recognize(gray,paper,questions_count):
    """Mide grafito por contraste del CENTRO, preservando dudas auténticas.

    El detector anterior convertía toda la página en dos máscaras binarias
    absolutas (148/215), por lo que un lápiz HB/#2 gris daba 15-20 dudas.
    Este mide intensidad y cobertura en el interior, lejos del contorno
    impreso, y compara la opción principal con las otras tres. Las marcas
    dobles, tenues o sucias NO se adjudican por aproximación.
    """
    scale=RENDER_DPI/72.0
    r=round(4.7*scale)
    yy,xx=np.ogrid[-r:r+1,-r:r+1]
    mask=(xx*xx+yy*yy)<r*r
    h,w=gray.shape[:2]
    answers=[];issues=[];levels=[]
    for index,positions in enumerate(bubble_positions(paper,questions_count),1):
        stats=[]
        for cx,cy in positions:
            x=round(cx*scale)
            y=round((PAPERS[paper][1]-cy)*scale)
            if x-r<0 or x+r>=w or y-r<0 or y+r>=h:
                stats.append((0.,0.,0.))
                continue
            pixels=gray[y-r:y+r+1,x-r:x+r+1][mask]
            ink=255.-pixels.astype(np.float32)
            stats.append((float(ink.mean()),
                          float(np.percentile(ink,70)),
                          float(np.mean(pixels<210))))
        ranking=sorted(enumerate(stats),key=lambda z:z[1][0],reverse=True)
        winner,(v,q,c)=ranking[0]
        other,(second,q2,c2)=ranking[1]
        levels.append([round(score[0]/255,3) for score in stats])
        if v<12 and max(item[2] for item in stats)<.11:
            answers.append(None)
            continue
        strong=(v>=73 and q>=75 and c>=.54)
        other_mark=(second>=31 and q2>=47 and c2>=.16)
        separated=(v-second>=47 and
                   (second<=12 or v>=2.15*second))
        if strong and separated and not other_mark:
            answers.append(ANSWER_CHOICES[winner])
        else:
            answers.append(None)
            reason=('Dos marcas o tachaduras posibles'
                    if other_mark else
                    'Lápiz demasiado tenue o marca poco diferenciada')
            issues.append({'pregunta':index,'razon':reason,
                           'niveles':levels[-1]})
    return answers,issues,levels


def scan_document(store:OMRStore,sid:str,pdf_path:Path, *, page_indices=None):
    """Lee PDF multipágina, valida QR+HMAC, archiva evidencias y devuelve resumen.

    No usa OCR de nombres ni cambia resultados anteriores ante duplicados.
    Un QR ilegible implica hoja sin identificar; nunca adjudica una identidad falsa.
    """
    path=Path(pdf_path)
    if not path.is_file() or path.suffix.lower()!='.pdf' or path.stat().st_size>MAX_PDF_SIZE:
        raise ValueError('Selecciona un PDF válido de hasta 100 MB.')
    with path.open('rb') as stream:
        if stream.read(5)!=b'%PDF-':raise ValueError('Archivo PDF inválido.')
    s=store.session(sid)
    fingerprint=hashlib.sha256(path.read_bytes()).hexdigest()
    folder=store.root/'originales'/sid;folder.mkdir(parents=True,exist_ok=True)
    archived=folder/(fingerprint+'.pdf')
    if not archived.exists():shutil.copy2(path,archived)
    by_token={p['token']:p for p in s['personal']}
    report={'leidas':0,'validadas':0,'revisar':0,'sin_identificar':0,
            'duplicadas':0,'repetidas':0,'reprocesadas':0,'detalles':[]}
    doc=pdfium.PdfDocument(str(archived))
    try:
        if len(doc)>MAX_PARTICIPANTS*3 or len(doc)>1500:
            raise ValueError('PDF con demasiadas páginas.')
        selected=None if page_indices is None else set(page_indices)
        if selected is not None and (
                not selected or any(type(i) is not int or i<0 or i>=len(doc)
                                    for i in selected)):
            raise ValueError('Las páginas solicitadas están fuera del PDF.')
        for idx in range(len(doc)):
            if selected is not None and idx not in selected:
                continue
            page=doc[idx]
            try:
                # Un PDF pequeño puede declarar páginas gigantes que saturan RAM
                # al renderizarse. Las medidas de Xerox quedan muy por debajo.
                page_w,page_h=page.get_size()
                if not 100<=page_w<=1500 or not 100<=page_h<=2000:
                    raise ValueError(f'Página {idx+1}: dimensiones anormales de PDF escaneado.')
                image=page.render(scale=RENDER_DPI/72).to_pil().convert('RGB')
            finally:page.close()
            original=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR)
            gray=cv2.cvtColor(original,cv2.COLOR_BGR2GRAY)
            best=None
            fallback=None
            scan_diagnosis='No se encontraron cuatro marcas de registro.'
            different_session=None
            for rectified in _rectify(gray,s['papel']):
                if fallback is None:
                    fallback=rectified
                    scan_diagnosis='Marcas alineadas, pero no se pudo validar QR.'
                qrtext=_decode_qr(rectified)
                if not qrtext:continue
                match=QR_RE.fullmatch(qrtext)
                if not match:
                    scan_diagnosis='QR detectado con formato incompatible.'
                    continue
                found_sid,token,page_num,mac=match.groups()
                if found_sid!=sid:
                    different_session=found_sid
                    scan_diagnosis='El QR pertenece a otra sesión de evaluación.'
                    continue
                if token not in by_token or page_num!='1':
                    scan_diagnosis='QR con token o número de página ajeno a esta sesión.'
                    continue
                if not hmac.compare_digest(_qr_data(sid,token,1,s['clave_hmac']),qrtext):
                    scan_diagnosis='Firma HMAC del QR no válida.'
                    continue
                best=(rectified,token)
                break
            if best is None:
                # Si hay marcas pero no QR, guardar la hoja RECTIFICADA para
                # poder sobreponer el acetato digital y capturarla manualmente.
                evidence=(cv2.cvtColor(fallback,cv2.COLOR_GRAY2BGR)
                          if fallback is not None else original)
                uid,st=store.register_page(
                    sid,fingerprint,idx,evidence,None,
                    [None]*len(s['preguntas']),
                    [{'pregunta':None,'razon':scan_diagnosis}],
                    'sin_identificar',
                )
            else:
                rectified,token=best
                answers,issues,levels=_recognize(
                    rectified,s['papel'],len(s['preguntas']))
                state='revisar' if issues else 'validada'
                uid,st=store.register_page(
                    sid,fingerprint,idx,cv2.cvtColor(rectified,cv2.COLOR_GRAY2BGR),
                    token,answers,issues,state)
            report['leidas']+=1
            key={'validada':'validadas','revisar':'revisar','sin_identificar':'sin_identificar',
                 'duplicado':'duplicadas','repetida':'repetidas'}.get(st,'revisar')
            if st.startswith('reprocesada_'):
                report['reprocesadas']+=1
                restored=st.removeprefix('reprocesada_')
                report[{'validada':'validadas','revisar':'revisar',
                        'duplicado':'duplicadas'}[restored]]+=1
            else:
                report[key]+=1
            report['detalles'].append({
                'pagina':idx+1,'id':uid,'estado':st,
                'diagnostico':scan_diagnosis if best is None else 'QR y alineación verificados',
                'sesion_detectada':different_session if best is None else None,
            })
    finally:doc.close()
    return report


def export_report(store:OMRStore,sid:str,output:Path,internal:bool=False):
    """XLSX de entrega sin clave correcta ni datos de marcas por defecto.

    La hoja confidencial Incidencias solo se añade al archivo interno.
    La exportación no cambia notas guardadas ni recalcula sesiones históricas.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
    from openpyxl.utils import get_column_letter
    results=store.results(sid);s=results['sesion'];people=results['participantes']
    def xl(value):
        # Evitar que nombres y comentarios importados se conviertan en fórmulas Excel.
        if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
            return "'"+value
        return value
    book=Workbook();book.remove(book.active)
    official=book.create_sheet('Resultados')
    headers=['Folio','ID personal','Nombre','Área de adscripción','Grupo','Turno',
             'Preguntas','Aciertos','Blancos','Porcentaje','Estado']
    official.append([f'Resultados · {s["titulo"]} · sesión {sid}'])
    official.append([f'Fecha: {s["creada"]} · Versión: {s["version_sha"][:12]} · '+
                     ('DEFINITIVO' if results['definitivo'] else 'PROVISIONAL')])
    official.append(headers)
    for row in people:
        official.append([row['folio'],xl(row['id']),xl(row['nombre']),xl(row['area']),xl(row['grupo']),xl(row['turno']),
             row['preguntas'],row['aciertos'],row['blancos'],row['porcentaje'],row['estado']])
    topic=book.create_sheet('Desempeño por tema')
    topic.append(['ID personal','Nombre','Tema','Aciertos','Preguntas','Porcentaje'])
    for p in people:
        for t,metric in p['temas'].items():topic.append([xl(p['id']),xl(p['nombre']),xl(t),metric['aciertos'],metric['preguntas'],metric['porcentaje']])
    summary=book.create_sheet('Resumen por grupo')
    summary.append(['Indicador','Valor','Definición'])
    for row in [ ('Convocados',len(people),'Participantes registrados'),
                 ('Validados',results['validados'],'Sin dudas ni duplicados'),
                 ('Pendientes',results['pendientes'],'Requieren revisión del evaluador'),
                 ('Ausentes',results['ausentes'],'Sin hoja atribuida'),
                 ('Promedio del grupo (%)',results['promedio'],'Media de porcentajes solo de validados')]:summary.append(row)
    summary.append([]);summary.append(['Tema','Aciertos','Respuestas posibles','Desempeño (%)'])
    for name,m in results['temas'].items():summary.append([xl(name),m['aciertos'],m['respuestas_posibles'],m['porcentaje']])
    control=book.create_sheet('Control de entrega')
    for row in [('Sesión',sid),('Evaluación',s['titulo']),('Fecha de creación',s['creada']),
                ('Formato',s['papel']),('Revisión de clave SHA-256',s['version_sha']),
                ('Estado','DEFINITIVO' if results['definitivo'] else 'PROVISIONAL'),
                ('Exportado UTC',utcnow()),('Responsable / firma','________________________')]:control.append(row)
    if internal:
        issues=book.create_sheet('Incidencias internas')
        issues.append(['Hoja','Folio','Página','Estado','Preguntas pendientes','Fuente PNG'])
        for p in results['hojas']:
            issues.append([p['id'],next((j['folio'] for j in people if j['token']==p['token']),''),
                           p['pagina']+1,p['estado'],','.join(str(x.get('pregunta')) for x in p['dudas']),p['imagen']])
        audit=book.create_sheet('Revisiones')
        audit.append(['Hoja','Pregunta','Decisión','Motivo','Revisor','Fecha'])
        for r in store.revisions(sid):audit.append([r['hoja_id'],r['pregunta'],r['decision'],r['motivo'],r['revisor'],r['fecha']])
    for sheet in book.worksheets:
        start=3 if sheet==official else 1
        sheet.freeze_panes=f'A{start+1}'
        sheet.auto_filter.ref=f'A{start}:{get_column_letter(sheet.max_column)}{sheet.max_row}' if sheet.max_row>start else None
        for cell in sheet[start]:
            cell.fill=PatternFill('solid',fgColor='142E40');cell.font=Font(color='FFFFFF',bold=True)
            cell.alignment=Alignment(vertical='center',wrap_text=True)
        sheet.row_dimensions[start].height=26
        for idx,col in enumerate(sheet.columns,1):
            size=min(46,max(12,max(len(str(c.value or '')) for c in list(col)[:60])+3))
            sheet.column_dimensions[get_column_letter(idx)].width=size
        for row in sheet.iter_rows(min_row=start+1):
            for cell in row:
                cell.alignment=Alignment(vertical='center')
                if cell.row%2==0:cell.fill=PatternFill('solid',fgColor='F2F6F7')
        sheet.sheet_view.showGridLines=False
        sheet.print_options.horizontalCentered=True
        sheet.sheet_properties.pageSetUpPr.fitToPage=True
        sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
    for col in official['B'][3:]:col.number_format='@'
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    book.save(output)
    return output
