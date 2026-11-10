"""Servicios multiusuario OMR, sin importar Tkinter.

El servidor es la única autoridad para usuarios, asignaciones y decisiones.
Los escaneos, claves HMAC y folios siguen perteneciendo al motor OMR original.
No hay sincronización de SQLite a través de red ni segunda base de resultados.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from biblioteca import list_exams, load_exam
from generacion_integrada import preparar_examen
from omr_evaluaciones.documentos import DocumentInbox
from omr_evaluaciones.expedientes import export_session_bundle, participant_receipt
from omr_evaluaciones.motor import (
    OMRStore, compact_json, inspect_pdf_sessions, scan_document, utcnow,
)

VALID_ROLES = {"admin", "coordinador", "capturista", "auditor"}
IDENTITY = re.compile(r"^[A-Za-z0-9_.-]{3,40}$")


class WebError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def password_hash(password: str, salt: bytes | None = None) -> str:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 160:
        raise WebError("La contraseña requiere al menos 12 caracteres.")
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 320_000)
    return salt.hex() + ":" + derived.hex()


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt, digest = encoded.split(":", 1)
        expected = bytes.fromhex(digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                    bytes.fromhex(salt), 320_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def checksum(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class WebService:
    def __init__(self, root: Path, *, start_workers: bool = True):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = OMRStore(self.root / "omr")
        self.inbox = DocumentInbox(self.store)
        self.library = self.root / "biblioteca.sqlite3"
        self.incoming = self.root / "omr" / "web_ingresos"
        self.incoming.mkdir(parents=True, exist_ok=True)
        self.outputs = self.root / "omr" / "web_exportaciones"
        self.outputs.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=1) if start_workers else None
        self._wake_lock = threading.Lock()
        self._setup_token = os.getenv("OMR_WEB_SETUP_TOKEN") or secrets.token_urlsafe(25)
        with self.store.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS web_usuarios(
                  id TEXT PRIMARY KEY,usuario TEXT NOT NULL UNIQUE,
                  nombre TEXT NOT NULL,rol TEXT NOT NULL,
                  password_hash TEXT NOT NULL,activo INTEGER NOT NULL DEFAULT 1,
                  cambiar_clave INTEGER NOT NULL DEFAULT 0,creado TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS web_sesiones(
                  token_hash TEXT PRIMARY KEY,usuario_id TEXT NOT NULL,
                  csrf_hash TEXT NOT NULL,vence INTEGER NOT NULL,
                  FOREIGN KEY(usuario_id) REFERENCES web_usuarios(id));
                CREATE TABLE IF NOT EXISTS web_asignaciones(
                  usuario_id TEXT NOT NULL,sesion_id TEXT NOT NULL,
                  PRIMARY KEY(usuario_id,sesion_id));
                CREATE TABLE IF NOT EXISTS web_reclamos(
                  hoja_id TEXT PRIMARY KEY,usuario_id TEXT NOT NULL,
                  token_hash TEXT NOT NULL,vence INTEGER NOT NULL,
                  revision INTEGER NOT NULL DEFAULT 0,
                  FOREIGN KEY(hoja_id) REFERENCES hojas(id));
                CREATE TABLE IF NOT EXISTS web_eventos(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  usuario_id TEXT NOT NULL,hoja_id TEXT,accion TEXT NOT NULL,
                  detalle TEXT NOT NULL,fecha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS web_trabajos(
                  id TEXT PRIMARY KEY,operador_id TEXT NOT NULL,
                  ruta TEXT NOT NULL,estado TEXT NOT NULL,
                  resultado TEXT NOT NULL DEFAULT '{}',
                  error TEXT NOT NULL DEFAULT '',
                  creado TEXT NOT NULL,actualizado TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS web_aprobaciones(
                  hoja_id TEXT PRIMARY KEY,usuario_id TEXT NOT NULL,
                  fecha TEXT NOT NULL,revision INTEGER NOT NULL);
            """)
            # Reiniciar trabajos interrumpidos sin perder sus originales
            # (la importación OMR ya es idempotente).
            db.execute("UPDATE web_trabajos SET estado='pendiente' "
                       "WHERE estado='procesando'")
        if self._executor:
            self.wake()

    def close(self):
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=False)

    @property
    def needs_setup(self) -> bool:
        with self.store.connect() as db:
            return db.execute("SELECT COUNT(*) FROM web_usuarios").fetchone()[0] == 0

    def setup(self, token: str, username: str, name: str, password: str):
        if not hmac.compare_digest(str(token), self._setup_token):
            raise WebError("Código de instalación incorrecto.", 403)
        if not IDENTITY.fullmatch(username):
            raise WebError("Usuario inválido.")
        hashed = password_hash(password)
        uid = uuid4().hex
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM web_usuarios LIMIT 1").fetchone():
                raise WebError("La instalación ya tiene administrador.", 409)
            db.execute("""INSERT INTO web_usuarios VALUES(?,?,?,?,?,?,?,?)""",
                       (uid, username, name.strip()[:100] or "Administrador",
                        "admin", hashed, 1, 0, utcnow()))
        return {"id": uid, "usuario": username}

    def login(self, username: str, password: str):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM web_usuarios WHERE usuario=? AND activo=1",
                             (username,)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise WebError("Credenciales incorrectas.", 401)
            token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
            db.execute("""INSERT INTO web_sesiones
                (token_hash,usuario_id,csrf_hash,vence) VALUES(?,?,?,?)""",
                (checksum(token), row["id"], checksum(csrf), int(time.time()) + 10*3600))
        return token, csrf, self._public_user(row)

    @staticmethod
    def _public_user(row):
        return {"id": row["id"], "usuario": row["usuario"],
                "nombre": row["nombre"], "rol": row["rol"],
                "cambiar_clave": bool(row["cambiar_clave"])}

    def authenticate(self, token: str | None, csrf: str | None = None,
                     *, write=False):
        if not token:
            raise WebError("Inicia sesión.", 401)
        with self.store.connect() as db:
            row = db.execute("""SELECT u.*,s.csrf_hash,s.vence
                FROM web_sesiones s JOIN web_usuarios u ON u.id=s.usuario_id
                WHERE s.token_hash=?""", (checksum(token),)).fetchone()
            if not row or not row["activo"] or row["vence"] <= time.time():
                raise WebError("La sesión terminó.", 401)
            if write and (not csrf or not hmac.compare_digest(
                    row["csrf_hash"], checksum(csrf))):
                raise WebError("Token de protección inválido.", 403)
        return dict(row)

    def logout(self, token):
        if token:
            with self.store.connect() as db:
                db.execute("DELETE FROM web_sesiones WHERE token_hash=?",
                           (checksum(token),))

    def change_password(self, user, old, new):
        if not verify_password(old, user["password_hash"]):
            raise WebError("La contraseña anterior no coincide.", 403)
        encoded = password_hash(new)
        with self.store.connect() as db:
            db.execute("UPDATE web_usuarios SET password_hash=?,cambiar_clave=0 "
                       "WHERE id=?", (encoded, user["id"]))
            db.execute("DELETE FROM web_sesiones WHERE usuario_id=?", (user["id"],))

    def require(self, user, *, roles=None, sid=None):
        if user["cambiar_clave"]:
            raise WebError("Debes cambiar tu contraseña temporal.", 403)
        if roles and user["rol"] not in roles:
            raise WebError("No tienes permiso para esta operación.", 403)
        if sid and user["rol"] != "admin":
            with self.store.connect() as db:
                found = db.execute("""SELECT 1 FROM web_asignaciones
                    WHERE usuario_id=? AND sesion_id=?""",
                    (user["id"], sid)).fetchone()
            if not found:
                raise WebError("Evaluación no asignada.", 403)

    def list_users(self, user):
        self.require(user, roles={"admin"})
        with self.store.connect() as db:
            return [self._public_user(r) | {"activo": bool(r["activo"])}
                    for r in db.execute("SELECT * FROM web_usuarios ORDER BY nombre")]

    def add_user(self, admin, username, name, password, role):
        self.require(admin, roles={"admin"})
        if role not in VALID_ROLES or not IDENTITY.fullmatch(username):
            raise WebError("Rol o usuario inválido.")
        uid = uuid4().hex
        try:
            with self.store.connect() as db:
                db.execute("""INSERT INTO web_usuarios VALUES(?,?,?,?,?,?,?,?)""",
                           (uid,username,name.strip()[:100],role,
                            password_hash(password),1,1,utcnow()))
        except sqlite3.IntegrityError as exc:
            raise WebError("Ya existe ese usuario.", 409) from exc
        return uid

    def assign(self, admin, uid, sid):
        self.require(admin, roles={"admin"})
        self.store.session(sid)
        with self.store.connect() as db:
            if not db.execute("SELECT 1 FROM web_usuarios WHERE id=?",
                              (uid,)).fetchone():
                raise WebError("Usuario inexistente.", 404)
            db.execute("INSERT OR IGNORE INTO web_asignaciones VALUES(?,?)",
                       (uid,sid))

    def visible_sessions(self, user):
        self.require(user)
        # La ubicación local de salida no forma parte del contrato de la API.
        # Evitar exponer rutas absolutas del equipo servidor a navegadores.
        sessions=[{k:v for k,v in row.items() if k!="lote_path"}
                  for row in self.store.sessions()]
        if user["rol"] == "admin":
            return sessions
        with self.store.connect() as db:
            allowed={x[0] for x in db.execute(
                "SELECT sesion_id FROM web_asignaciones WHERE usuario_id=?",
                (user["id"],))}
        return [x for x in sessions if x["id"] in allowed]

    def questions(self, user, sid):
        self.require(user, sid=sid)
        sess=self.store.session(sid)
        return [{"numero":i,"tema":x["tema"],"pregunta":x["pregunta"]}
                for i,x in enumerate(sess["preguntas"],1)]

    def list_sheets(self, user, sid, *, include_done=False):
        self.require(user, sid=sid)
        data=self.store.pages(sid)
        persons={p["token"]:p for p in self.store.session(sid)["personal"]}
        now=int(time.time())
        with self.store.connect() as db:
            leases={r["hoja_id"]:dict(r) for r in db.execute(
                "SELECT hoja_id,usuario_id,vence FROM web_reclamos")}
        result=[]
        for page in data:
            if not include_done and page["estado"] not in ("revisar","duplicado"):
                continue
            person=persons.get(page["token"])
            lease=leases.get(page["id"])
            result.append({
                "id":page["id"],"sesion_id":sid,"estado":page["estado"],
                "pagina":page["pagina"]+1,
                "folio":person["folio"] if person else None,
                "nombre":person["nombre"] if person else "Sin identificar",
                "dudas":len(page["dudas"]),
                "ocupada_por_otro":bool(lease and lease["vence"]>now and
                                      lease["usuario_id"]!=user["id"]),
                "ocupada_por_mi":bool(lease and lease["vence"]>now and
                                    lease["usuario_id"]==user["id"]),
            })
        return result

    def get_sheet(self, user, sheet_id):
        self.require(user)
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM hojas WHERE id=?", (sheet_id,)).fetchone()
            if not row:
                raise WebError("Hoja inexistente.", 404)
            self.require(user, sid=row["sesion_id"])
            lease=db.execute("SELECT revision,usuario_id,vence FROM web_reclamos "
                             "WHERE hoja_id=?", (sheet_id,)).fetchone()
        sess=self.store.session(row["sesion_id"])
        return {
            "id":sheet_id,"sesion_id":row["sesion_id"],
            "estado":row["estado"],"pagina":row["pagina"]+1,
            "respuestas":json.loads(row["respuestas_json"]),
            "dudas":json.loads(row["dudas_json"]),
            "preguntas":[{"numero":i,"tema":q["tema"],"pregunta":q["pregunta"]}
                         for i,q in enumerate(sess["preguntas"],1)],
            "revision":int(lease["revision"]) if lease else 0,
            "ocupada_por_otro":bool(lease and lease["vence"]>time.time() and
                                  lease["usuario_id"]!=user["id"]),
        }

    def claim(self, user, sheet_id, *, ttl=300):
        self.require(user, roles={"admin","coordinador","capturista"})
        now=int(time.time())
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            page=db.execute("SELECT sesion_id,estado,token FROM hojas WHERE id=?",
                            (sheet_id,)).fetchone()
            if not page:
                raise WebError("Hoja inexistente.", 404)
            self.require(user,sid=page["sesion_id"])
            if not page["token"] or page["estado"] in ("duplicado","descartada","sin_identificar"):
                raise WebError("Hoja sin identidad válida o en conflicto.", 409)
            if page["estado"]=="validada" and user["rol"]=="capturista":
                raise WebError("Una hoja validada requiere revisión del coordinador.",409)
            old=db.execute("SELECT * FROM web_reclamos WHERE hoja_id=?",
                           (sheet_id,)).fetchone()
            if old and old["vence"]>now and old["usuario_id"]!=user["id"]:
                raise WebError("Otro capturista está revisando esta hoja.", 409)
            token=secrets.token_urlsafe(32)
            rev=int(old["revision"]) if old else 0
            db.execute("""INSERT INTO web_reclamos
                (hoja_id,usuario_id,token_hash,vence,revision)
                VALUES(?,?,?,?,?) ON CONFLICT(hoja_id) DO UPDATE SET
                usuario_id=excluded.usuario_id,token_hash=excluded.token_hash,
                vence=excluded.vence""",
                (sheet_id,user["id"],checksum(token),now+ttl,rev))
            self._event(db,user["id"],sheet_id,"RECLAMAR","Revisión temporal")
        return {"lease":token,"revision":rev,"vence_en_segundos":ttl}

    def claim_next(self,user,sid):
        """Repartir trabajo sin que dos personas reciban la misma hoja.

        Los candidatos se consultan por evaluación autorizada y cada
        reclamación se efectúa en BEGIN IMMEDIATE en claim(). Si otro
        capturista gana la carrera, se intenta el siguiente.
        """
        self.require(user,roles={"admin","coordinador","capturista"},sid=sid)
        candidates=self.list_sheets(user,sid)
        for item in candidates:
            if item["estado"]!="revisar" or item["ocupada_por_otro"]:
                continue
            try:
                result=self.claim(user,item["id"])
                return {"hoja_id":item["id"],**result}
            except WebError as exc:
                if exc.status != 409:
                    raise
        raise WebError("No hay hojas disponibles para reclamar.",404)

    def _event(self,db,uid,sheet,action,detail):
        db.execute("""INSERT INTO web_eventos
            (usuario_id,hoja_id,accion,detalle,fecha)
            VALUES(?,?,?,?,?)""",(uid,sheet,action,detail[:650],utcnow()))

    def release(self,user,sheet_id,lease_token):
        self.require(user,roles={"admin","coordinador","capturista"})
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT * FROM web_reclamos WHERE hoja_id=?",
                           (sheet_id,)).fetchone()
            if not old or old["usuario_id"]!=user["id"] or not hmac.compare_digest(
                    old["token_hash"],checksum(lease_token)):
                raise WebError("Reserva inválida.",409)
            db.execute("UPDATE web_reclamos SET vence=0 WHERE hoja_id=?",
                       (sheet_id,))
            self._event(db,user["id"],sheet_id,"LIBERAR","Fin de reserva")

    def save_decisions(self,user,sheet_id,lease_token,expected_revision,
                       changes,reason):
        """Una transacción garantiza revisión optimista + bitácora + notas."""
        self.require(user,roles={"admin","coordinador","capturista"})
        if not str(reason).strip():
            raise WebError("Escribe una justificación.")
        if not isinstance(changes,list) or not changes:
            raise WebError("Selecciona las decisiones.")
        now=int(time.time())
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            page=db.execute("SELECT * FROM hojas WHERE id=?",
                            (sheet_id,)).fetchone()
            if not page:
                raise WebError("Hoja inexistente.",404)
            self.require(user,sid=page["sesion_id"])
            lease=db.execute("SELECT * FROM web_reclamos WHERE hoja_id=?",
                             (sheet_id,)).fetchone()
            if (not lease or lease["usuario_id"]!=user["id"] or
                    lease["vence"]<=now or not hmac.compare_digest(
                    lease["token_hash"],checksum(lease_token))):
                raise WebError("La reserva expiró o pertenece a otro usuario.",409)
            if lease["revision"]!=expected_revision:
                raise WebError("La hoja cambió. Actualízala antes de guardar.",409)
            if not page["token"] or page["estado"] in ("duplicado","descartada","sin_identificar"):
                raise WebError("Identifica o resuelve antes esta hoja.",409)
            if page["estado"]=="validada" and user["rol"]=="capturista":
                raise WebError("Una hoja validada requiere revisión del coordinador.",409)
            answers=json.loads(page["respuestas_json"])
            issues=json.loads(page["dudas_json"])
            taken=set()
            for change in changes:
                q=change.get("pregunta")
                decision=change.get("decision")
                if type(q) is not int or not 1<=q<=len(answers) or q in taken:
                    raise WebError("Reactivo repetido o inexistente.")
                if decision not in ("A","B","C","D","BLANCO"):
                    raise WebError("Decisión inválida.")
                taken.add(q)
                answers[q-1]=None if decision=="BLANCO" else decision
                issues=[i for i in issues if i.get("pregunta")!=q]
                db.execute("""INSERT INTO revisiones
                    (hoja_id,pregunta,decision,motivo,revisor,fecha)
                    VALUES(?,?,?,?,?,?)""",
                    (sheet_id,q,decision,reason[:600],user["nombre"],utcnow()))
            status="revisar" if issues else "validada"
            db.execute("""UPDATE hojas SET respuestas_json=?,
                dudas_json=?,estado=? WHERE id=?""",
                (compact_json(answers),compact_json(issues),status,sheet_id))
            new_revision=lease["revision"]+1
            db.execute("""UPDATE web_reclamos SET revision=?,vence=?
                WHERE hoja_id=?""",(new_revision,now+300,sheet_id))
            db.execute("DELETE FROM web_aprobaciones WHERE hoja_id=?", (sheet_id,))
            self._event(db,user["id"],sheet_id,"CORRECCION",
                        f"{len(changes)} reactivos; motivo: {reason}")
        return {"revision":new_revision,"estado":status,"pendientes":len(issues)}

    def approve(self,user,sheet_id):
        self.require(user,roles={"admin","coordinador"})
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            page=db.execute("SELECT sesion_id,estado FROM hojas WHERE id=?",
                            (sheet_id,)).fetchone()
            if not page:
                raise WebError("Hoja inexistente.",404)
            self.require(user,sid=page["sesion_id"])
            if page["estado"]!="validada":
                raise WebError("Solo se aprueban hojas validadas.",409)
            lease=db.execute("SELECT * FROM web_reclamos WHERE hoja_id=?",
                             (sheet_id,)).fetchone()
            if lease and lease["vence"]>time.time() and lease["usuario_id"]!=user["id"]:
                raise WebError("La hoja sigue en revisión por otro operador.",409)
            revision=int(lease["revision"]) if lease else 0
            db.execute("""INSERT OR REPLACE INTO web_aprobaciones VALUES(?,?,?,?)""",
                       (sheet_id,user["id"],utcnow(),revision))
            self._event(db,user["id"],sheet_id,"APROBAR","Validación del coordinador")

    def list_events(self,user,sid):
        self.require(user,sid=sid)
        with self.store.connect() as db:
            return [dict(x) for x in db.execute("""
                SELECT e.accion,e.detalle,e.fecha,u.nombre AS operador,
                       h.id AS hoja_id
                FROM web_eventos e JOIN web_usuarios u ON u.id=e.usuario_id
                JOIN hojas h ON h.id=e.hoja_id
                WHERE h.sesion_id=? ORDER BY e.id DESC LIMIT 400
            """,(sid,))]

    def create_application(self,user,questionnaire_id,name,mode,paper,participants):
        self.require(user,roles={"admin"})
        if mode not in ("normal","ecologico") or paper not in ("A4","Carta","Oficio"):
            raise WebError("Modalidad o papel inválidos.")
        if not isinstance(participants,list) or not 1<=len(participants)<=500:
            raise WebError("Se requiere una lista de 1 a 500 participantes.")
        with TemporaryDirectory(prefix="omr_biblioteca_") as tmp:
            exam=load_exam(self.library,questionnaire_id,Path(tmp))
            if not exam.questions:
                raise WebError("El cuestionario no tiene preguntas.")
            source=Path(tmp)/"Preguntas.xlsx"
            from biblioteca import export_workbook
            export_workbook(exam.questions,source)
            import csv
            roster=Path(tmp)/"personal.csv"
            with roster.open("w",newline="",encoding="utf-8-sig") as f:
                writer=csv.DictWriter(f,fieldnames=["id","nombre","area","grupo","turno"])
                writer.writeheader()
                for p in participants:
                    writer.writerow({k:p.get(k,"") for k in writer.fieldnames})
            folder=preparar_examen(
                source,self.root/"salidas",exam.titulo,exam.subtitulo,
                modo_examen=mode,lista_personal=roster,
                omr_root=self.store.root,nombre_evaluacion=name or exam.nombre,
                cuestionario_id=exam.id,revision_biblioteca=exam.revision,
                empresa=exam.empresa,puesto=exam.grupo,
                instrucciones=exam.instrucciones,logo=exam.logo,
                tamano_papel=paper,letra=exam.letra,
                color_titulo=exam.color_titulo,
                color_subtitulo=exam.color_subtitulo,
                color_respuestas=exam.color_respuestas,
                color_acetato=exam.color_acetato,
            )
        import re
        text=(folder/"Sesion_OMR.txt").read_text(encoding="utf-8")
        match=re.search(r"\b[0-9a-f]{12}\b",text)
        if not match:
            raise WebError("No se pudo verificar la aplicación generada.",500)
        return {"sid":match.group(0),"ruta":str(folder.relative_to(self.root)),
                "archivos":["Cuadernillo.pdf","Hoja_respuestas.pdf","Acetato_clave.pdf"]}

    def add_job(self,user,source):
        self.require(user,roles={"admin","coordinador"})
        jid=uuid4().hex
        with self.store.connect() as db:
            db.execute("""INSERT INTO web_trabajos VALUES(?,?,?,?,?,?,?,?)""",
                       (jid,user["id"],str(source),"pendiente","{}","",
                        utcnow(),utcnow()))
        self.wake()
        return jid

    def job(self,user,jid):
        self.require(user)
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM web_trabajos WHERE id=?",
                           (jid,)).fetchone()
            if not row:
                raise WebError("Trabajo inexistente.",404)
            if user["rol"]!="admin" and row["operador_id"]!=user["id"]:
                raise WebError("Trabajo ajeno.",403)
        return {"id":jid,"estado":row["estado"],"error":row["error"],
                "resultado":json.loads(row["resultado"]),
                "creado":row["creado"]}

    def wake(self):
        if self._executor and self._wake_lock.acquire(blocking=False):
            self._executor.submit(self._process_pending)

    def _process_pending(self):
        try:
            while True:
                with self.store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    row=db.execute("""SELECT * FROM web_trabajos
                        WHERE estado='pendiente' ORDER BY creado,id LIMIT 1""").fetchone()
                    if not row:
                        break
                    db.execute("UPDATE web_trabajos SET estado='procesando', "
                               "actualizado=? WHERE id=?",(utcnow(),row["id"]))
                try:
                    result=self._process_file(row)
                    with self.store.connect() as db:
                        db.execute("""UPDATE web_trabajos SET estado='terminado',
                            resultado=?,error='',actualizado=? WHERE id=?""",
                            (compact_json(result),utcnow(),row["id"]))
                except Exception as exc:
                    with self.store.connect() as db:
                        db.execute("""UPDATE web_trabajos SET estado='error',
                            error=?,actualizado=? WHERE id=?""",
                            (str(exc)[:550],utcnow(),row["id"]))
        finally:
            # En operación normal wake() adquirió el lock. Las pruebas y
            # recuperación explícita permiten ejecutar la cola sin executor.
            if self._wake_lock.locked():
                self._wake_lock.release()
            # Si llegó un trabajo justo después de comprobar la cola vacía,
            # su add_job no pudo adquirir el candado. Volver a despertarla.
            if self._executor:
                with self.store.connect() as db:
                    pending=db.execute("SELECT 1 FROM web_trabajos "
                                       "WHERE estado='pendiente' LIMIT 1").fetchone()
                if pending:
                    self.wake()

    def _process_file(self,row):
        source=Path(row["ruta"])
        if not source.is_file():
            raise WebError("No está disponible el PDF original.")
        inspection=inspect_pdf_sessions(self.store,source)
        with self.store.connect() as db:
            user=db.execute("SELECT * FROM web_usuarios WHERE id=?",
                            (row["operador_id"],)).fetchone()
        if not user or not user["activo"]:
            raise WebError("El operador fue desactivado.")
        sha,archived=self.inbox.archive(source,inspection,operator=user["nombre"])
        imported=[]
        withheld=0
        for group in inspection["grupos"]:
            try:
                self.require(user,sid=group["sesion_id"])
            except WebError:
                withheld+=len(group["paginas"])
                continue
            report=scan_document(
                self.store,group["sesion_id"],archived,
                page_indices=[i-1 for i in group["paginas"]])
            self.inbox.mark_processed(sha,group["sesion_id"],report,
                                      operator=user["nombre"])
            imported.append({"sesion_id":group["sesion_id"],
                             "paginas":len(group["paginas"]),
                             "validadas":report["validadas"],
                             "revisar":report["revisar"],
                             "repetidas":report["repetidas"]})
        return {"sha":sha,"total":inspection["total_paginas"],
                "sin_identificar":len(inspection["no_identificadas"]),
                "no_autorizadas":withheld,"aplicaciones":imported}

    def retry_job(self,user,jid):
        self.require(user,roles={"admin","coordinador"})
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM web_trabajos WHERE id=?",(jid,)).fetchone()
            if not row or row["estado"]!="error" or (user["rol"]!="admin" and
                    row["operador_id"]!=user["id"]):
                raise WebError("Solo se reintentan trabajos fallidos propios.",409)
            db.execute("UPDATE web_trabajos SET estado='pendiente',error='' "
                       "WHERE id=?",(jid,))
        self.wake()
