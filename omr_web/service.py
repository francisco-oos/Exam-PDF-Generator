"""Servicios multiusuario OMR, sin importar Tkinter.

El servidor es la única autoridad para usuarios, asignaciones y decisiones.
Los escaneos, claves HMAC y folios siguen perteneciendo al motor OMR original.
No hay sincronización de SQLite a través de red ni segunda base de resultados.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
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


@contextmanager
def exclusive_scan_queue(lockfile: Path):
    """Candado de proceso para una cola SQLite compartida, Linux y Windows.

    El lock del SO se libera también si el proceso termina abruptamente.
    Un segundo worker espera sin bloquear el servidor web ni las revisiones.
    """
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    with lockfile.open("a+b") as handle:
        if os.name=="nt":
            import msvcrt
            # Windows exige locks obligatorios: leer el byte reservado
            # por otro worker lanza PermissionError. Sólo consultar tamaño.
            handle.seek(0,os.SEEK_END)
            if handle.tell()==0:
                handle.write(b"0")
                handle.flush()
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                    break
                except OSError:
                    time.sleep(0.2)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


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
                -- Sin personal NO se inventa una sesión OMR: los PDF
                -- se conservan como lote genérico para acetato manual.
                CREATE TABLE IF NOT EXISTS web_lotes_impresion(
                  id TEXT PRIMARY KEY, nombre TEXT NOT NULL,
                  ruta TEXT NOT NULL, modo TEXT NOT NULL,
                  papel TEXT NOT NULL, creado TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS web_auditoria_revision(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  hoja_id TEXT NOT NULL, tipo TEXT NOT NULL,
                  pregunta INTEGER, anterior TEXT, nueva TEXT,
                  aciertos_antes INTEGER, aciertos_despues INTEGER,
                  motivo TEXT NOT NULL, usuario_id TEXT NOT NULL,
                  fecha TEXT NOT NULL,
                  FOREIGN KEY(hoja_id) REFERENCES hojas(id),
                  FOREIGN KEY(usuario_id) REFERENCES web_usuarios(id));
                CREATE INDEX IF NOT EXISTS idx_auditoria_hoja
                  ON web_auditoria_revision(hoja_id,id);
            """)
            # Sólo el worker que tenga el candado global puede recuperar
            # trabajos interrumpidos: otra instancia podría estar procesando.
            columns={r["name"] for r in db.execute("PRAGMA table_info(web_trabajos)")}
            if "archivo_sha" not in columns:
                db.execute("ALTER TABLE web_trabajos ADD COLUMN archivo_sha TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS idx_web_trabajos_sha "
                       "ON web_trabajos(archivo_sha,estado)")
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
        # "auxiliar" es el perfil sencillo del usuario. Internamente se
        # conserva "capturista" para no romper cuentas ni permisos históricos.
        role = "capturista" if role == "auxiliar" else role
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
        sessions=[
            {k:v for k,v in row.items() if k!="lote_path"}|
            {"calificacion_manual":bool(
                (row.get("nombre_evaluacion") or "").startswith("MANUAL ·")
                and row["modo"]=="personalizado")}
            for row in self.store.sessions()]
        if user["rol"] == "admin":
            return sessions
        with self.store.connect() as db:
            allowed={x[0] for x in db.execute(
                "SELECT sesion_id FROM web_asignaciones WHERE usuario_id=?",
                (user["id"],))}
        return [x for x in sessions if x["id"] in allowed]

    @staticmethod
    def _assert_open(db, sid):
        session=db.execute("SELECT estado FROM sesiones WHERE id=?",(sid,)).fetchone()
        if not session or session["estado"]!="abierta":
            raise WebError("La evaluación está cerrada; requiere una nueva autorización.",409)

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
        person=next((p for p in sess["personal"] if p["token"]==row["token"]),None)
        source=None
        if sess.get("cuestionario_id") and self.library.is_file():
            # Solo metadatos no confidenciales: nunca devolver preguntas,
            # respuestas correctas ni acetato a capturistas.
            from biblioteca import db_connect
            with db_connect(self.library) as conn:
                lib=conn.execute("SELECT nombre FROM cuestionarios WHERE id=?",
                    (sess["cuestionario_id"],)).fetchone()
                source=lib["nombre"] if lib else None
        return {
            "id":sheet_id,"sesion_id":row["sesion_id"],
            "evaluacion":sess.get("nombre_evaluacion") or sess["titulo"],
            "calificacion_manual":bool(
                (sess.get("nombre_evaluacion") or "").startswith("MANUAL ·")
                and sess["modo"]=="personalizado"),
            "biblioteca":source or "Cuestionario histórico sin vínculo",
            "revision_biblioteca":sess.get("revision_biblioteca"),
            "participante":person["nombre"] if person else "Sin identificar",
            "folio":person["folio"] if person else None,
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
            self._assert_open(db,page["sesion_id"])
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
            self._assert_open(db,page["sesion_id"])
            # Una hoja ya validada es inmutable salvo reapertura formal,
            # incluso si su antiguo lease fue liberado tras guardar.
            if page["estado"]=="validada":
                if user["rol"]=="capturista":
                    raise WebError("Una hoja validada requiere revisión del coordinador.",409)
                raise WebError("Reabre una corrección autorizada desde Resultados.",409)
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
            answers=json.loads(page["respuestas_json"])
            issues=json.loads(page["dudas_json"])
            original=list(answers)
            questions=json.loads(db.execute(
                "SELECT preguntas_json FROM sesiones WHERE id=?",
                (page["sesion_id"],)).fetchone()["preguntas_json"])
            before_score=sum(a==q["correcta"] for a,q in zip(original,questions))
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
            after_score=sum(a==q["correcta"] for a,q in zip(answers,questions))
            for change in changes:
                index=change["pregunta"]-1
                db.execute("""INSERT INTO web_auditoria_revision(
                    hoja_id,tipo,pregunta,anterior,nueva,aciertos_antes,
                    aciertos_despues,motivo,usuario_id,fecha)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (sheet_id,"CORRECCION",index+1,
                     original[index] or "BLANCO",change["decision"],
                     before_score,after_score,reason.strip()[:600],
                     user["id"],utcnow()))
            status="revisar" if issues else "validada"
            db.execute("""UPDATE hojas SET respuestas_json=?,
                dudas_json=?,estado=? WHERE id=?""",
                (compact_json(answers),compact_json(issues),status,sheet_id))
            new_revision=lease["revision"]+1
            # La reserva sólo se mantiene durante correcciones parciales.
            # Al guardar la última duda, liberar atómicamente: no retener
            # otra tableta cinco minutos ni impedir la aprobación 2/2.
            new_expiry=now+300 if status=="revisar" else 0
            db.execute("""UPDATE web_reclamos SET revision=?,vence=?
                WHERE hoja_id=?""",(new_revision,new_expiry,sheet_id))
            db.execute("DELETE FROM web_aprobaciones WHERE hoja_id=?", (sheet_id,))
            self._event(db,user["id"],sheet_id,"CORRECCION",
                        f"{len(changes)} reactivos; motivo: {reason}")
        return {"revision":new_revision,"estado":status,"pendientes":len(issues),
                "reserva_liberada":status=="validada"}

    def approve(self,user,sheet_id):
        self.require(user,roles={"admin","coordinador"})
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            page=db.execute("SELECT sesion_id,estado FROM hojas WHERE id=?",
                            (sheet_id,)).fetchone()
            if not page:
                raise WebError("Hoja inexistente.",404)
            self.require(user,sid=page["sesion_id"])
            self._assert_open(db,page["sesion_id"])
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

    def reopen_validated(self,user,sheet_id,question,reason):
        """Reabrir un reactivo sin destruir la nota, el original ni la bitácora."""
        self.require(user,roles={"admin","coordinador"})
        reason=str(reason or "").strip()
        if len(reason)<10:
            raise WebError("Motivo obligatorio (mínimo 10 caracteres).",422)
        if type(question) is not int:
            raise WebError("Reactivo inválido.",422)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            page=db.execute("SELECT * FROM hojas WHERE id=?",(sheet_id,)).fetchone()
            if not page:
                raise WebError("Hoja inexistente.",404)
            self.require(user,sid=page["sesion_id"])
            self._assert_open(db,page["sesion_id"])
            if page["estado"]!="validada" or not page["token"]:
                raise WebError("Sólo se reabren hojas identificadas y validadas.",409)
            answers=json.loads(page["respuestas_json"])
            if not 1<=question<=len(answers):
                raise WebError("Reactivo fuera de rango.",422)
            lease=db.execute("SELECT * FROM web_reclamos WHERE hoja_id=?",
                             (sheet_id,)).fetchone()
            if (lease and lease["vence"]>int(time.time()) and
                    lease["usuario_id"]!=user["id"]):
                raise WebError("Otra persona está revisando esta hoja.",409)
            # Reabrir invalida también la reserva anterior del mismo usuario:
            # cualquier pestaña vieja perderá su token antes de poder guardar.
            questions=json.loads(db.execute(
                "SELECT preguntas_json FROM sesiones WHERE id=?",
                (page["sesion_id"],)).fetchone()["preguntas_json"])
            correct=sum(a==q["correcta"] for a,q in zip(answers,questions))
            previous=answers[question-1] or "BLANCO"
            issues=[{"pregunta":question,
                     "razon":"Aclaración abierta: requiere cotejo humano."}]
            db.execute("UPDATE hojas SET estado='revisar',dudas_json=? WHERE id=?",
                       (compact_json(issues),sheet_id))
            db.execute("DELETE FROM web_reclamos WHERE hoja_id=?",(sheet_id,))
            db.execute("DELETE FROM web_aprobaciones WHERE hoja_id=?",(sheet_id,))
            db.execute("""INSERT INTO web_auditoria_revision(
                hoja_id,tipo,pregunta,anterior,nueva,aciertos_antes,
                aciertos_despues,motivo,usuario_id,fecha)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (sheet_id,"REAPERTURA",question,previous,None,correct,None,
                 reason[:600],user["id"],utcnow()))
            db.execute("""INSERT INTO revisiones(
                hoja_id,pregunta,decision,motivo,revisor,fecha)
                VALUES(?,?,?,?,?,?)""",
                (sheet_id,question,"REAPERTURA",reason[:600],
                 user["nombre"],utcnow()))
            self._event(db,user["id"],sheet_id,"REAPERTURA",
                        f"Pregunta {question}; nota previa {correct}/{len(questions)}; "
                        f"motivo: {reason}")
        return {"hoja_id":sheet_id,"sesion_id":page["sesion_id"],
                "pregunta":question,"estado":"revisar",
                "aciertos_anteriores":correct,
                "mensaje":"Resultado suspendido hasta guardar una nueva decisión."}

    def sheet_history(self,user,sheet_id):
        """Bitácora anterior y actual por hoja, nunca expone claves."""
        self.require(user,roles={"admin","coordinador","auditor"})
        with self.store.connect() as db:
            page=db.execute("SELECT sesion_id FROM hojas WHERE id=?",
                            (sheet_id,)).fetchone()
            if not page:
                raise WebError("Hoja inexistente.",404)
            self.require(user,sid=page["sesion_id"])
            detailed=[dict(x) for x in db.execute("""
                SELECT h.id,h.tipo,h.pregunta,h.anterior,h.nueva,
                       h.aciertos_antes,h.aciertos_despues,h.motivo,h.fecha,
                       u.nombre AS operador,u.usuario AS cuenta
                FROM web_auditoria_revision h
                JOIN web_usuarios u ON u.id=h.usuario_id
                WHERE h.hoja_id=? ORDER BY h.id
            """,(sheet_id,))]
            legacy=[dict(x) for x in db.execute("""
                SELECT id,pregunta,decision,motivo,revisor,fecha
                FROM revisiones WHERE hoja_id=? ORDER BY id
            """,(sheet_id,))]
            approval=db.execute("""
                SELECT a.fecha,a.revision,u.nombre AS operador
                FROM web_aprobaciones a JOIN web_usuarios u
                  ON u.id=a.usuario_id WHERE a.hoja_id=?
            """,(sheet_id,)).fetchone()
        return {"hoja_id":sheet_id,"cambios":detailed,
                "registros_historicos":legacy,
                "aprobacion":dict(approval) if approval else None}

    def results_with_evidence(self,user,sid):
        self.require(user,roles={"admin","coordinador","auditor"},sid=sid)
        report=self.store.results(sid)
        pages=self.store.pages(sid)
        session=report["sesion"]
        by_person={}
        for person in session["personal"]:
            scanned=[page for page in pages
                     if page["token"]==person["token"] and
                     page["estado"] not in ("descartada","duplicado")]
            by_person[person["id"]]=scanned[0]["id"] if len(scanned)==1 else None
        with self.store.connect() as db:
            approvals={x["hoja_id"]:dict(x) for x in db.execute(
                "SELECT hoja_id,fecha,revision FROM web_aprobaciones")}
        return {"sesion_id":sid,"promedio":report["promedio"],
                "estado_cierre":report["sesion"]["estado"],
                "validados":report["validados"],"pendientes":report["pendientes"],
                "ausentes":report["ausentes"],
                "participantes":[{
                    "id":p["id"],"folio":p["folio"],"nombre":p["nombre"],
                    "estado":p["estado"],"aciertos":p["aciertos"],
                    "porcentaje":p["porcentaje"],"preguntas":p["preguntas"],
                    "temas":p["temas"],"areas_mejora":p["areas_mejora"],
                    "hoja_id":by_person.get(p["id"]),
                    "aprobacion":approvals.get(by_person.get(p["id"])),
                } for p in report["participantes"]]}

    def resolve_duplicate(self,user,sheet_id,reason):
        """Descarta exclusivamente el reescaneo conflictivo, nunca la nota anterior.

        Requiere una hoja primaria validada y un motivo explícito. La evidencia
        y el PDF original del duplicado siguen archivados, con auditoría.
        """
        self.require(user,roles={"admin","coordinador"})
        reason=str(reason or "").strip()
        if len(reason)<10:
            raise WebError("Indica el motivo de descarte (mínimo 10 caracteres).",422)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            page=db.execute("SELECT * FROM hojas WHERE id=?",(sheet_id,)).fetchone()
            if not page:
                raise WebError("Hoja inexistente.",404)
            self.require(user,sid=page["sesion_id"])
            self._assert_open(db,page["sesion_id"])
            if page["estado"]!="duplicado" or not page["token"]:
                raise WebError("Sólo se puede descartar un reescaneo duplicado.",409)
            primary=db.execute("""SELECT id FROM hojas
                WHERE sesion_id=? AND token=? AND id<>?
                  AND estado='validada' ORDER BY creada,id LIMIT 1""",
                (page["sesion_id"],page["token"],sheet_id)).fetchone()
            if not primary:
                raise WebError("Primero se debe validar la hoja original del folio.",409)
            db.execute("UPDATE hojas SET estado='descartada' WHERE id=?",(sheet_id,))
            db.execute("""INSERT INTO web_auditoria_revision(
                hoja_id,tipo,pregunta,anterior,nueva,aciertos_antes,
                aciertos_despues,motivo,usuario_id,fecha)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (sheet_id,"DESCARTAR_REESCANEO",None,"duplicado","descartada",
                 None,None,reason[:600],user["id"],utcnow()))
            self._event(db,user["id"],sheet_id,"DESCARTAR_REESCANEO",
                        "Original protegido: "+primary["id"]+"; "+reason)
        return {"hoja_id":sheet_id,"estado":"descartada",
                "original_conservado":primary["id"]}

    def closure_summary(self,user,sid):
        """Pre-cierre: ningún ausente se disfraza de calificado."""
        self.require(user,roles={"admin","coordinador"},sid=sid)
        report=self.store.results(sid)
        pages=report["hojas"]
        with self.store.connect() as db:
            approval={row["hoja_id"] for row in db.execute(
                "SELECT hoja_id FROM web_aprobaciones")}
            active=db.execute("""SELECT COUNT(*) FROM web_reclamos wr
                JOIN hojas h ON h.id=wr.hoja_id
                WHERE h.sesion_id=? AND wr.vence>?""",
                (sid,int(time.time()))).fetchone()[0]
            processing=db.execute("""SELECT COUNT(*) FROM web_trabajos
                WHERE estado IN ('pendiente','procesando')""").fetchone()[0]
        missing=[]
        for person in report["participantes"]:
            matched=[p for p in pages if p["token"]==person["token"]
                     and p["estado"]!="descartada"]
            valid=[p for p in matched if p["estado"]=="validada"]
            if not matched:
                reason="SIN_ESCANEO"
            elif any(p["estado"]=="duplicado" for p in matched) or len(valid)>1:
                reason="DUPLICADO_POR_RESOLVER"
            elif len(valid)!=1:
                reason="REVISION_PENDIENTE"
            elif valid[0]["id"] not in approval:
                reason="APROBACION_PENDIENTE"
            else:
                continue
            missing.append({"id":person["id"],"folio":person["folio"],
                            "nombre":person["nombre"],"motivo":reason,
                            "estado":"pendiente"})
        unidentified=sum(p["estado"]=="sin_identificar" for p in pages)
        return {"sesion_id":sid,"estado":report["sesion"]["estado"],
                "total_lista":len(report["participantes"]),
                "validados":report["validados"],"faltantes":missing,
                "cantidad_pendientes":len(missing),
                "sin_identificar":unidentified,
                "revisiones_activas":active,"trabajos_en_cola":processing,
                "listo":not (missing or unidentified or active or processing)}

    def close_application(self,user,sid):
        """Cierre irreversible del piloto, solamente con lista conciliada."""
        self.require(user,roles={"admin","coordinador"},sid=sid)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_open(db,sid)
            summary=self.closure_summary(user,sid)
            if not summary["listo"]:
                raise WebError("Cierre bloqueado: hay folios sin escaneo, "
                               "correcciones, aprobaciones o tareas pendientes. "
                               "Consulta la conciliación antes de entregar.",409)
            db.execute("UPDATE sesiones SET estado='cerrada' WHERE id=?",(sid,))
            self._event(db,user["id"],None,"CIERRE_EVALUACION",
                        "Lista conciliada: "+str(summary["total_lista"])+" personas")
        return {**summary,"estado":"cerrada","listo":True}

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
        """Dos modos aprobados; QR solamente al cargar lista de personas.

        Normal + lista: paquetes por participante; Ecológico + lista:
        cuadernillo reutilizable. SIN lista en cualquiera de los dos
        casos: hoja genérica sin QR y acetato físico; no crear calificaciones.
        """
        self.require(user,roles={"admin"})
        if mode not in ("normal","ecologico") or paper not in ("A4","Carta","Oficio"):
            raise WebError("Modalidad o papel inválidos.")
        if not isinstance(participants,list) or len(participants)>500:
            raise WebError("Lista inválida; máximo 500 participantes.")
        with TemporaryDirectory(prefix="omr_biblioteca_") as tmp:
            exam=load_exam(self.library,questionnaire_id,Path(tmp))
            if not exam.questions:
                raise WebError("El cuestionario no tiene preguntas.")
            source=Path(tmp)/"Preguntas.xlsx"
            from biblioteca import export_workbook
            export_workbook(exam.questions,source)
            roster=None
            if participants:
                # Reutilizar read_roster: las mismas validaciones se aplican
                # a los datos pegados y a los importados desde XLSX/CSV.
                import csv
                roster=Path(tmp)/"personal.csv"
                with roster.open("w",newline="",encoding="utf-8-sig") as stream:
                    writer=csv.DictWriter(stream,
                        fieldnames=["id","nombre","area","grupo","turno"])
                    writer.writeheader()
                    for person in participants:
                        if not isinstance(person,dict):
                            raise WebError("Participante inválido.")
                        writer.writerow({key:person.get(key,"") for key
                                         in writer.fieldnames})
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
                logo_ancho_mm=exam.logo_ancho_mm,
                question_layouts=[{
                    "ancho_imagen_mm":q.image_width_mm,
                    "alto_imagen_mm":q.image_height_mm,
                    "alineacion_imagen":q.image_align}
                    for q in exam.questions],
            )
        files=[f for f in ("Cuadernillo.pdf","Hoja_respuestas.pdf",
               "Acetato_clave.pdf","Clave_docente.pdf",
               "Paquetes_individuales.zip","manifest.json")
               if (folder/f).is_file()]
        session_file=folder/"Sesion_OMR.txt"
        if session_file.is_file():
            match=re.search(r"\b[0-9a-f]{12}\b",
                            session_file.read_text(encoding="utf-8"))
            if not match:
                raise WebError("La aplicación generada no tiene sesión válida.",500)
            return {"tipo":"omr","sid":match.group(0),"lote_id":None,
                    "modalidad":mode,"con_personal":True,"archivos":files}
        if participants:
            raise WebError("No se generó la sesión OMR esperada.",500)
        lot_id=uuid4().hex
        relative=str(folder.relative_to(self.root))
        with self.store.connect() as db:
            db.execute("""INSERT INTO web_lotes_impresion
                (id,nombre,ruta,modo,papel,creado) VALUES(?,?,?,?,?,?)""",
                (lot_id,(name or exam.nombre)[:120],relative,mode,paper,utcnow()))
        return {"tipo":"manual","sid":None,"lote_id":lot_id,
                "modalidad":mode,"con_personal":False,"archivos":files,
                "aviso":"Sin lista: hoja sin QR, corrección manual con acetato."}

    def print_lots(self,user):
        self.require(user,roles={"admin"})
        with self.store.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,nombre,modo,papel,creado FROM web_lotes_impresion "
                "ORDER BY creado DESC LIMIT 100")]

    def print_lot_file(self,user,lot_id,filename):
        """Acceder solamente a archivos de lotes propios guardados en salidas."""
        self.require(user,roles={"admin"})
        if filename not in {"Cuadernillo.pdf","Hoja_respuestas.pdf",
                            "Acetato_clave.pdf","Clave_docente.pdf",
                            "manifest.json"}:
            raise WebError("Archivo no permitido.",404)
        with self.store.connect() as db:
            row=db.execute("SELECT ruta FROM web_lotes_impresion WHERE id=?",
                           (lot_id,)).fetchone()
        if row is None:
            raise WebError("Lote inexistente.",404)
        root=(self.root/"salidas").resolve()
        folder=(self.root/row["ruta"]).resolve()
        if not folder.is_relative_to(root) or not folder.is_dir():
            raise WebError("Carpeta del lote fuera del servidor.",403)
        target=(folder/filename).resolve()
        if target.parent!=folder or not target.is_file():
            raise WebError("Archivo del lote no disponible.",404)
        return target


    def bind_manual_from_library(
            self,user,digest,page,questionnaire_id,person_id,name,paper,
            reason,area="",group="",turno=""):
        """Segunda vía: identidad y biblioteca verificadas por humano, SIN QR.

        Solo se acepta una página PENDIENTE de la bandeja. Crea una
        aplicación aislada con clave versión vigente de biblioteca y folio
        interno nuevo, distinto del texto visible del PDF escaneado.
        Ninguna marca queda autocalificada: los N reactivos requieren
        captura manual completa con bitácora de revisiones.
        """
        from omr_evaluaciones.motor import IDS_RE, PAPERS
        self.require(user,roles={"admin"})
        if (paper not in PAPERS or not isinstance(person_id,str)
                or not IDS_RE.fullmatch(person_id)
                or not isinstance(name,str) or not name.strip()
                or len(name.strip())>130):
            raise WebError("Indica papel, ID y nombre válidos.",422)
        if not isinstance(reason,str) or len(reason.strip())<8:
            raise WebError("Describe el motivo de vinculación manual (8 caracteres mínimo).",422)
        if not isinstance(page,int) or page<0:
            raise WebError("Página inexistente.",422)
        if not isinstance(questionnaire_id,str) or not re.fullmatch(
                r"[0-9a-f]{32}",questionnaire_id):
            raise WebError("Selecciona un cuestionario válido.",422)
        info=next((x for x in self.inbox.pages(digest) if x["pagina"]==page),None)
        if not info or info["estado"]!="pendiente" or info["sesion_id"] or info["hoja_id"]:
            raise WebError("Solo se vinculan páginas sin sesión QR y pendientes.",409)
        with TemporaryDirectory(prefix="omr_manual_lib_") as temp:
            try:
                exam=load_exam(self.library,questionnaire_id,Path(temp))
            except ValueError as error:
                raise WebError(str(error),404) from error
            questions=[
                {"tema":q.section,"pregunta":q.prompt,
                 "correcta":"ABCD"[q.correct]} for q in exam.questions]
            sid=self.store.create_session(
                "MANUAL · "+exam.titulo[:90],questions,
                [{"id":person_id,"nombre":name.strip(),
                  "area":str(area)[:90],"grupo":str(group)[:80],
                  "turno":str(turno)[:60]}],paper,"personalizado",
                nombre_evaluacion="MANUAL · "+exam.nombre,
                cuestionario_id=exam.id,revision_biblioteca=exam.revision)
        person=self.store.session(sid)["personal"][0]
        try:
            self.inbox.bind_manual_pending(
                digest,page,sid,person_id,person["folio"],
                user["nombre"],reason)
        except Exception:
            # Nunca borrar una sesión con una hoja ya almacenada: conservar
            # evidencia íntegra ante interrupciones o carreras concurrentes.
            self.store.discard_empty_session(sid)
            raise
        bound=next((x for x in self.inbox.pages(digest) if x["pagina"]==page),None)
        if not bound or not bound["hoja_id"]:
            raise WebError("No se pudo comprobar la vinculación.",500)
        with self.store.connect() as db:
            self._event(db,user["id"],bound["hoja_id"],
                        "VINCULAR_MANUAL_BIBLIOTECA",
                        "Documento SHA-256: "+digest+"; página "+str(page+1)+
                        "; cuestionario "+exam.id+" rev "+str(exam.revision)+
                        "; folio interno "+person["folio"]+
                        "; motivo: "+reason.strip()[:300])
        return {"sesion_id":sid,"hoja_id":bound["hoja_id"],
                "folio":person["folio"],"participante":name.strip(),
                "biblioteca":exam.nombre,"revision":exam.revision,
                "modo":"manual","requiere_captura_completa":True}

    def add_job(self,user,source):
        self.require(user,roles={"admin","coordinador"})
        source=Path(source)
        if not source.is_file():
            raise WebError("El PDF de ingreso no está disponible.",404)
        digest=hashlib.sha256()
        with source.open("rb") as fp:
            for chunk in iter(lambda:fp.read(1024*1024),b""):
                digest.update(chunk)
        sha=digest.hexdigest()
        jid=uuid4().hex
        reused=False
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("""SELECT id,ruta,operador_id FROM web_trabajos
                WHERE archivo_sha=? AND estado IN ('pendiente','procesando')
                ORDER BY creado,id LIMIT 1""",(sha,)).fetchone()
            if old:
                if (user["rol"]!="admin" and old["operador_id"]!=user["id"]):
                    raise WebError("Este PDF ya está en cola por otro operador. "
                                   "Solicita al administrador revisar el trabajo.",409)
                jid=old["id"]
                reused=(source.resolve()!=Path(old["ruta"]).resolve())
            else:
                db.execute("""INSERT INTO web_trabajos
                    (id,operador_id,ruta,estado,resultado,error,creado,actualizado,archivo_sha)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (jid,user["id"],str(source),"pendiente","{}","",
                     utcnow(),utcnow(),sha))
        if reused and source.resolve().is_relative_to(self.incoming.resolve()):
            # No borrar el archivo usado por el trabajo vigente; sólo
            # descartar otra copia temporal de contenido idéntico.
            source.unlink(missing_ok=True)
        self.wake()
        return jid

    def reanalyze_archive(self,user,digest):
        """Reprocesa el PDF ya archivado, nunca el archivo local del usuario.

        Solo administradores. register_page conserva id/folio, evidencia y
        correcciones humanas; la lectura automática solo sustituye una
        pendiente cuando reduce el número de dudas. No aceptar un SHA sin
        comprobar que el PDF inmutable aún existe e integra su hash.
        """
        self.require(user,roles={"admin"})
        try:
            source=self.inbox.original(digest)
        except (ValueError,OSError) as exc:
            raise WebError(str(exc),422) from exc
        # Evitar doble envío si el administrador hace clic repetidamente.
        with self.store.connect() as db:
            current=db.execute("""
                SELECT id FROM web_trabajos
                WHERE ruta=? AND estado IN ('pendiente','procesando')
                ORDER BY creado DESC LIMIT 1
            """,(str(source),)).fetchone()
        if current:
            return {"trabajo_id":current["id"],"estado":"pendiente",
                    "reutilizado":True}
        jid=self.add_job(user,source)
        return {"trabajo_id":jid,"estado":"pendiente","reutilizado":False}

    def job(self,user,jid):
        self.require(user)
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM web_trabajos WHERE id=?",
                           (jid,)).fetchone()
            if not row:
                raise WebError("Trabajo inexistente.",404)
            if user["rol"]!="admin" and row["operador_id"]!=user["id"]:
                raise WebError("Trabajo ajeno.",403)
        with self.store.connect() as db:
            position=(1+db.execute("""SELECT COUNT(*) FROM web_trabajos
                WHERE estado='pendiente' AND
                      (creado < ? OR (creado=? AND id < ?))""",
                (row["creado"],row["creado"],jid)).fetchone()[0]
                if row["estado"]=="pendiente" else None)
        return {"id":jid,"estado":row["estado"],"error":row["error"],
                "resultado":json.loads(row["resultado"]),
                "posicion_cola":position,"creado":row["creado"]}

    def wake(self):
        if self._executor and self._wake_lock.acquire(blocking=False):
            self._executor.submit(self._process_pending)

    def _process_pending(self):
        try:
            # El ThreadPoolExecutor es por instancia; este candado protege
            # también contra dos procesos uvicorn o administradores simultáneos.
            with exclusive_scan_queue(self.root/"omr"/"web_cola.lock"):
                with self.store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    # Bajo lock global no existe otro worker vivo procesando.
                    # Solo aquí se recuperan tareas de un proceso caído.
                    db.execute("UPDATE web_trabajos SET estado='pendiente' "
                               "WHERE estado='procesando'")
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
            if self._wake_lock.locked():
                self._wake_lock.release()
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
        from_archive=source.resolve().is_relative_to(self.inbox.originals.resolve())
        sha,archived=self.inbox.archive(
            source,inspection,operator=user["nombre"],
            record_ingress=not from_archive)
        imported=[]
        withheld=0
        for group in inspection["grupos"]:
            try:
                self.require(user,sid=group["sesion_id"])
            except WebError:
                withheld+=len(group["paginas"])
                continue
            # Comparación de la misma página anterior y posterior.
            # La mejora del motor no debe atribuir cambios a otra sesión
            # de un PDF mezclado ni alterar las decisiones del personal.
            scoped=set(i-1 for i in group["paginas"])
            previous={
                page["pagina"]:page
                for page in self.store.pages(group["sesion_id"])
                if page["archivo_sha"]==sha and page["pagina"] in scoped
            }
            report=scan_document(
                self.store,group["sesion_id"],archived,
                page_indices=list(scoped))
            self.inbox.mark_processed(sha,group["sesion_id"],report,
                                      operator=user["nombre"])
            following={
                page["pagina"]:page
                for page in self.store.pages(group["sesion_id"])
                if page["archivo_sha"]==sha and page["pagina"] in scoped
            }
            comparison=[{
                "pagina":i+1,
                "antes":len(previous[i]["dudas"]) if i in previous else None,
                "despues":len(following[i]["dudas"]) if i in following else None,
                "estado":following[i]["estado"] if i in following else "no encontrada",
                "mejora_aplicada":any(d["pagina"]==i+1 and
                                     str(d["estado"]).startswith("reprocesada_")
                                     for d in report["detalles"]),
            } for i in sorted(scoped)]
            imported.append({"sesion_id":group["sesion_id"],
                             "paginas":len(group["paginas"]),
                             "validadas":report["validadas"],
                             "revisar":report["revisar"],
                             "repetidas":report["repetidas"],
                             "reprocesadas":report["reprocesadas"],
                             "comparacion":comparison})
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
