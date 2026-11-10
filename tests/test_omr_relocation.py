"""Copia piloto entre dos ubicaciones y restitución verificable de evidencias."""
from __future__ import annotations

import hashlib
import shutil

import numpy as np

from omr_web.relocate import repair_paths
from omr_web.service import WebService


def test_mover_copia_conserva_pdf_imagen_usuarios_y_respuestas(tmp_path):
    source = tmp_path / "laptop"
    service = WebService(source, start_workers=False)
    service.setup(service._setup_token, "admin", "Administrador", "Segura123456789!")
    token, _, _ = service.login("admin", "Segura123456789!")
    admin = service.authenticate(token)
    sid = service.store.create_session(
        "Piloto",
        [{"tema": "Material", "pregunta": "Prueba", "correcta": "A"}],
        [{"id": "P01", "nombre": "Persona de prueba"}], "Carta")
    participant = service.store.session(sid)["personal"][0]
    sheet, _ = service.store.register_page(
        sid, "a" * 64, 0, np.full((160, 120, 3), 255, dtype=np.uint8),
        participant["token"], [None],
        [{"pregunta": 1, "razon": "Marca ambigua"}], "revisar")
    claim = service.claim(admin, sheet)
    service.save_decisions(admin, sheet, claim["lease"], claim["revision"],
                           [{"pregunta": 1, "decision": "A"}],
                           "Prueba de restauración")
    service.release(admin, sheet, claim["lease"])
    folder = source / "salidas" / "paquete"
    folder.mkdir(parents=True)
    (folder / "Sesion_OMR.txt").write_text(f"Sesión {sid}\n", encoding="utf-8")
    service.store.update_lote(sid, folder)
    original = b"%PDF-1.4\n%archivo sintetico\n%%EOF\n"
    digest = hashlib.sha256(original).hexdigest()
    pdf = service.inbox.originals / (digest + ".pdf")
    pdf.write_bytes(original)
    with service.store.connect() as db:
        db.execute(
            "INSERT INTO documentos_omr(sha,ruta,tamano,paginas,recibido)"
            " VALUES(?,?,?,?,?)",
            (digest, str(pdf), len(original), 1, "2026-11-09T00:00:00"))
    source_image = source / "omr" / "escaneos" / sid / (sheet + ".png")
    assert source_image.is_file()
    initial = service.store.results(sid)
    initial_revisions = len(service.store.revisions(sid))
    service.close()

    dest = tmp_path / "tablet"
    shutil.copytree(source, dest)
    preview = repair_paths(dest)
    assert preview["apto"] and not preview["aplicado"]
    assert preview["contadores"] == {
        "hojas": 1, "documentos_omr": 1, "sesiones": 1, "web_trabajos": 0}
    assert repair_paths(dest, apply=True)["aplicado"] is True
    assert repair_paths(dest, apply=True)["contadores"]["hojas"] == 0
    restored = WebService(dest, start_workers=False)
    assert restored.store.results(sid)["participantes"] == initial["participantes"]
    assert len(restored.store.revisions(sid)) == initial_revisions
    assert restored.inbox.original(digest).read_bytes() == original
    with restored.store.connect() as db:
        image_path = db.execute("SELECT imagen FROM hojas WHERE id=?", (sheet,)).fetchone()[0]
        assert image_path == str(dest / "omr" / "escaneos" / sid / (sheet + ".png"))
        assert db.execute("SELECT lote_path FROM sesiones WHERE id=?", (sid,)).fetchone()[0] == str(dest / "salidas" / "paquete")
        assert db.execute("SELECT ruta FROM documentos_omr WHERE sha=?", (digest,)).fetchone()[0] == str(dest / "omr" / "documentos" / "originales" / (digest + ".pdf"))
    restored.close()


def test_reubicacion_no_modifica_base_si_falta_evidencia(tmp_path):
    service = WebService(tmp_path / "original", start_workers=False)
    service.setup(service._setup_token, "admin", "Administrador", "Segura123456789!")
    sid = service.store.create_session(
        "Prueba", [{"tema": "T", "pregunta": "P", "correcta": "B"}],
        [{"id": "P01", "nombre": "Persona"}])
    participant = service.store.session(sid)["personal"][0]
    sheet, _ = service.store.register_page(
        sid, "b" * 64, 0, np.full((80, 120, 3), 255, dtype=np.uint8),
        participant["token"], [None], [{"pregunta": 1, "razon": "Dudosa"}], "revisar")
    service.close()
    dest = tmp_path / "copia_incompleta"
    shutil.copytree(tmp_path / "original", dest)
    missing = dest / "omr" / "escaneos" / sid / (sheet + ".png")
    missing.unlink()
    report = repair_paths(dest, apply=True)
    assert not report["apto"] and not report["aplicado"]
    assert report["problemas"][0]["tipo"] == "hojas"
    other = WebService(dest, start_workers=False)
    with other.store.connect() as db:
        stored = db.execute("SELECT imagen FROM hojas WHERE id=?", (sheet,)).fetchone()[0]
        assert stored != str(missing)
    other.close()
