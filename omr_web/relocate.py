"""Auditoría y reparación EXPLÍCITA de rutas al mover una copia del piloto.

No altera folios, respuestas, revisiones ni claves HMAC. Sólo reubica
referencias a archivos que YA existen en la estructura copiada. Nunca
repara sobre el origen durante una migración: detener servidor, respaldar,
copiar y ejecutar en el destino con --apply --confirm-stopped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from .runtime import data_directory


def _name(path: str) -> str:
    # Un respaldo creado en Windows se puede restaurar en Linux y viceversa.
    return str(path).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def plan_relocation(root: Path):
    root = Path(root).resolve()
    database = root / "omr" / "sesiones.sqlite3"
    if not database.is_file():
        raise ValueError("No existe la base OMR en la copia de destino.")
    pending = []
    problems = []
    counts = {"hojas": 0, "documentos_omr": 0,
              "sesiones": 0, "web_trabajos": 0}
    with sqlite3.connect(database, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}

        def queue(table, column, key, old, target, exists, reason):
            if not old or str(old) == str(target):
                return
            if exists:
                pending.append((table, column, key, old, str(target)))
                counts[table] += 1
            else:
                problems.append({"tipo": table, "id": str(key), "detalle": reason})

        if "hojas" in tables:
            for row in connection.execute("SELECT id,sesion_id,imagen FROM hojas"):
                target = (root / "omr" / "escaneos" /
                          row["sesion_id"] / (row["id"] + ".png"))
                queue("hojas", "imagen", row["id"], row["imagen"], target,
                      target.is_file(), "Imagen de evidencia ausente")
        if "documentos_omr" in tables:
            for row in connection.execute("SELECT sha,ruta FROM documentos_omr"):
                target = root / "omr" / "documentos" / "originales" / (row["sha"] + ".pdf")
                authentic = target.is_file() and _checksum(target) == row["sha"]
                queue("documentos_omr", "ruta", row["sha"], row["ruta"], target,
                      authentic, "Falta PDF original o su SHA no coincide")
        if "sesiones" in tables and any(
            c[1] == "lote_path" for c in connection.execute("PRAGMA table_info(sesiones)")
        ):
            for row in connection.execute("SELECT id,lote_path FROM sesiones"):
                stored = row["lote_path"]
                if not stored:
                    continue
                target = root / "salidas" / _name(stored)
                summary = target / "Sesion_OMR.txt"
                correct = summary.is_file() and row["id"] in summary.read_text(
                    encoding="utf-8")
                queue("sesiones", "lote_path", row["id"], stored, target,
                      correct, "Carpeta de impresión incompleta o de otra aplicación")
        if "web_trabajos" in tables:
            for row in connection.execute("SELECT id,ruta,estado FROM web_trabajos"):
                stored = row["ruta"]
                target = root / "omr" / "web_ingresos" / _name(stored)
                # Los trabajos terminados no necesitan un PDF temporal para
                # procesarse; su original definitivo ya vive en documentos/.
                if row["estado"] == "terminado" and not target.is_file():
                    continue
                queue("web_trabajos", "ruta", row["id"], stored, target,
                      target.is_file(), "PDF de trabajo pendiente ausente")
    return {"base": str(database), "cambios": pending,
            "problemas": problems, "contadores": counts}


def repair_paths(root: Path, *, apply: bool = False):
    plan = plan_relocation(root)
    if plan["problemas"]:
        return {"apto": False, "aplicado": False,
                "contadores": plan["contadores"],
                "problemas": plan["problemas"]}
    if not apply:
        return {"apto": True, "aplicado": False,
                "contadores": plan["contadores"], "problemas": []}
    # Una transacción: o todas las rutas se verifican y cambian, o ninguna.
    with sqlite3.connect(plan["base"], timeout=5) as db:
        db.execute("BEGIN IMMEDIATE")
        for table, column, identifier, original, target in plan["cambios"]:
            pk = "sha" if table == "documentos_omr" else "id"
            # Tabla/columna son literales internos, no provienen del usuario.
            count = db.execute(
                f"UPDATE {table} SET {column}=? WHERE {pk}=? AND {column}=?",
                (target, identifier, original)).rowcount
            if count != 1:
                raise RuntimeError("La base cambió durante la reparación; no se aplicó.")
    return {"apto": True, "aplicado": True,
            "contadores": plan["contadores"], "problemas": []}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reparar rutas de una COPIA restaurada")
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios verificados")
    parser.add_argument("--confirm-stopped", action="store_true",
                        help="Confirma que ningún Tk/servidor usa esta copia")
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.apply and not args.confirm_stopped:
        parser.error("--apply exige --confirm-stopped y respaldo previo")
    try:
        result = repair_paths(args.data_dir or data_directory(), apply=args.apply)
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as exc:
        print("ERROR de reubicación:", exc, file=sys.stderr)
        return 1
    # No enviar rutas, nombres ni contenido personal a los diagnósticos.
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["apto"] else 1


if __name__ == "__main__":
    sys.exit(main())
