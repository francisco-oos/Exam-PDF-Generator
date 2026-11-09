"""Bandeja PDF y expedientes: pruebas con documentos sintéticos, sin datos reales."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader, PdfWriter

from omr_evaluaciones.expedientes import (
    EvidenceStore,create_organized_pdf,export_expediente,
)
from omr_evaluaciones.motor import (
    OMRStore,create_forms_pdf,create_generic_forms_pdf,inspect_pdf_sessions,
    scan_document,
)


def questions(n=3):
    return [
        {"tema":"Seguridad","pregunta":f"Pregunta ficticia {i+1}",
         "correcta":"ABCD"[i%4]}
        for i in range(n)
    ]


def persons(*names):
    return [
        {"id":f"{i+1:05d}","nombre":name,"grupo":"Prueba"}
        for i,name in enumerate(names)
    ]


def merge(destination, sources):
    writer=PdfWriter()
    for file in sources:
        reader=PdfReader(str(file))
        for page in reader.pages:
            writer.add_page(page)
    with Path(destination).open("wb") as out:
        writer.write(out)
    return Path(destination)


def fixture_two_sessions(tmp_path):
    store=OMRStore(tmp_path/"omr")
    sid_a=store.create_session(
        "Evaluación de Cabos",questions(),persons("Cabo Uno","Cabo Dos"),
        "Carta","ecologico",nombre_evaluacion="Cabos")
    sid_b=store.create_session(
        "Evaluación de Checadores",questions(),persons("Checador Uno"),
        "Carta","normal",nombre_evaluacion="Checadores")
    form_a=create_forms_pdf(store,sid_a,tmp_path/"cabos.pdf")
    form_b=create_forms_pdf(store,sid_b,tmp_path/"checadores.pdf")
    blank=create_generic_forms_pdf(
        questions(),"Sin QR","Carta",tmp_path/"desconocido.pdf")
    return store,sid_a,sid_b,form_a,form_b,blank


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_bandeja_conserva_todas_las_paginas_mixtas_y_reinicio(tmp_path):
    store,sid_a,sid_b,form_a,form_b,blank=fixture_two_sessions(tmp_path)
    mixed=merge(tmp_path/"mezclado.pdf",[form_a,blank,form_b])
    before=sha(mixed)
    evidence=EvidenceStore(store)
    doc,repeated=evidence.ingest(mixed)
    assert repeated is False
    assert doc["paginas"]==4
    assert Path(doc["ruta"]).is_file()
    assert sha(doc["ruta"])==before
    # Si el programa se cierra aquí, se han preservado las 4 páginas.
    reopened=EvidenceStore(OMRStore(tmp_path/"omr"))
    assert len(reopened.documents())==1
    assert len(reopened.pages(doc["sha"]))==4
    assert all(p["estado"]=="pendiente" for p in reopened.pages(doc["sha"]))
    detected=inspect_pdf_sessions(store,Path(doc["ruta"]))
    assert detected["mezclado"] is True
    assert [p["pagina"] for p in detected["no_identificadas"]]==[3]
    reopened.inspect(doc["sha"],detected)
    pages=reopened.pages(doc["sha"])
    assert [p["sesion_id"] for p in pages]==[sid_a,sid_a,None,sid_b]
    assert pages[2]["estado"]=="sin_identificar"
    assert sha(doc["ruta"])==before
    doc2,repeated2=reopened.ingest(mixed)
    assert repeated2 and doc2["sha"]==doc["sha"]
    reopened.inspect(doc["sha"],detected)
    assert len(reopened.documents())==1
    assert len(reopened.pages(doc["sha"]))==4
    assert sum(x["accion"]=="ARCHIVADO" for x in reopened.audit(doc["sha"]))==1


def test_lote_parcial_y_rescan_se_unen_a_la_aplicacion_existente(tmp_path):
    store,sid_a,sid_b,form_a,form_b,blank=fixture_two_sessions(tmp_path)
    evidence=EvidenceStore(store)
    first=merge(tmp_path/"lunes.pdf",[form_a])
    monday,_=evidence.ingest(first)
    preflight=inspect_pdf_sessions(store,Path(monday["ruta"]))
    evidence.inspect(monday["sha"],preflight)
    report=scan_document(store,sid_a,Path(monday["ruta"]),
                         page_indices=[0,1])
    evidence.record_report(monday["sha"],sid_a,report)
    assert len(store.pages(sid_a))==2
    assert all(p["hoja_id"] for p in evidence.pages(monday["sha"]))
    # Reimportar el mismo PDF no crea una segunda calificación.
    again=scan_document(store,sid_a,Path(monday["ruta"]),
                        page_indices=[0,1])
    evidence.record_report(monday["sha"],sid_a,again)
    assert again["repetidas"]==2
    assert len(store.pages(sid_a))==2
    # También se conserva la aplicación de Checadores en otra jornada.
    tuesday,_=evidence.ingest(form_b)
    evidence.inspect(tuesday["sha"],inspect_pdf_sessions(
        store,Path(tuesday["ruta"])))
    result=scan_document(store,sid_b,Path(tuesday["ruta"]),
                         page_indices=[0])
    evidence.record_report(tuesday["sha"],sid_b,result)
    assert len(store.sessions())==2
    assert len(store.pages(sid_b))==1
    assert len(evidence.documents())==2


def test_organizar_girar_extraer_sin_tocar_original(tmp_path):
    store,sid_a,sid_b,form_a,form_b,blank=fixture_two_sessions(tmp_path)
    mixed=merge(tmp_path/"lote.pdf",[form_a,form_b])
    initial=sha(mixed)
    copy=tmp_path/"organizado.pdf"
    create_organized_pdf(mixed,copy,[2,0,1],{2:90,0:180})
    reader=PdfReader(str(copy))
    assert len(reader.pages)==3
    assert int(reader.pages[0].get("/Rotate",0))%360==90
    assert int(reader.pages[1].get("/Rotate",0))%360==180
    assert sha(mixed)==initial
    single=tmp_path/"extraido.pdf"
    create_organized_pdf(mixed,single,[1])
    assert len(PdfReader(str(single)).pages)==1
    with pytest.raises(ValueError,match="otro nombre"):
        create_organized_pdf(mixed,mixed,[0])
    with pytest.raises(ValueError,match="fuera|existentes"):
        create_organized_pdf(mixed,tmp_path/"bad.pdf",[999])
    with pytest.raises(ValueError,match="90"):
        create_organized_pdf(mixed,tmp_path/"bad.pdf",[0],{0:45})


def test_exportacion_respeta_privacidad_de_otros_examenes(tmp_path):
    store,sid_a,sid_b,form_a,form_b,blank=fixture_two_sessions(tmp_path)
    mixed=merge(tmp_path/"mezclado.pdf",[form_a,form_b,blank])
    evidence=EvidenceStore(store)
    doc,_=evidence.ingest(mixed)
    pre=inspect_pdf_sessions(store,Path(doc["ruta"]))
    evidence.inspect(doc["sha"],pre)
    a=scan_document(store,sid_a,Path(doc["ruta"]),page_indices=[0,1])
    evidence.record_report(doc["sha"],sid_a,a)
    b=scan_document(store,sid_b,Path(doc["ruta"]),page_indices=[2])
    evidence.record_report(doc["sha"],sid_b,b)
    official=export_expediente(
        store,evidence,sid_a,tmp_path/"entrega.zip",internal=False)
    internal=export_expediente(
        store,evidence,sid_a,tmp_path/"interno.zip",internal=True)
    assert sha(mixed)==doc["sha"]
    with ZipFile(official) as bundle:
        assert "Resultados.xlsx" in bundle.namelist()
        assert "Evidencias_ordenadas.pdf" in bundle.namelist()
        assert "Bitacora.json" not in bundle.namelist()
        assert not any("PDF_originales/" in n for n in bundle.namelist())
        manifest=json.loads(bundle.read("Manifiesto.json"))
        assert manifest["sesion_id"]==sid_a
        assert len(manifest["paginas_asociadas"])==2
        for file in manifest["archivos"]:
            assert hashlib.sha256(bundle.read(file["nombre"])).hexdigest()==file["sha256"]
        extracted=tmp_path/"evidence.pdf"
        extracted.write_bytes(bundle.read("Evidencias_ordenadas.pdf"))
        assert len(PdfReader(str(extracted)).pages)==2
    with ZipFile(internal) as bundle:
        names=bundle.namelist()
        assert "Bitacora.json" in names
        assert len([n for n in names if n.startswith("PDF_originales_filtrados/")])==1
        assert not any(n.startswith("PDF_originales/") for n in names)
        filtered=tmp_path/"filtrado.pdf"
        filtered.write_bytes(bundle.read(next(n for n in names
                                            if n.startswith("PDF_originales_filtrados/"))))
        assert len(PdfReader(str(filtered)).pages)==2
        audit=json.loads(bundle.read("Bitacora.json"))
        assert audit["eventos_documentales"]


def test_identificacion_manual_exige_folio_y_no_califica(tmp_path):
    store,sid_a,sid_b,form_a,form_b,blank=fixture_two_sessions(tmp_path)
    evidence=EvidenceStore(store)
    doc,_=evidence.ingest(blank)
    inspection=inspect_pdf_sessions(store,Path(doc["ruta"]))
    evidence.inspect(doc["sha"],inspection)
    person=store.session(sid_b)["personal"][0]
    with pytest.raises(ValueError,match="ID y folio"):
        evidence.link_manual(doc["sha"],1,sid_b,person["id"],"FOLIO_FALSO",
                             "Operador","Comparé contra original")
    sheet=evidence.link_manual(
        doc["sha"],1,sid_b,person["id"],person["folio"],
        "Operador","Leí ID y folio en papel")
    assert sheet
    assert evidence.pages(doc["sha"])[0]["estado"]=="identificada_manual"
    assert evidence.pages(doc["sha"])[0]["sesion_id"]==sid_b
    assert store.results(sid_b)["validados"]==0
    assert len(store.pages(sid_b))==1
    assert any("IDENTIFICADA_MANUAL"==r["accion"]
               for r in evidence.audit(doc["sha"]))
    with pytest.raises(ValueError,match="ya tiene"):
        evidence.link_manual(doc["sha"],1,sid_a,"00001",
                             store.session(sid_a)["personal"][0]["folio"],
                             "Operador","Intento cruzado")


def test_documento_invalido_no_contamina_bandeja(tmp_path):
    store=OMRStore(tmp_path/"omr")
    evidence=EvidenceStore(store)
    invalid=tmp_path/"falso.pdf"
    invalid.write_bytes(b"NO-ES-PDF")
    with pytest.raises(ValueError,match="cabecera"):
        evidence.ingest(invalid)
    assert evidence.documents()==[]


def test_sesion_y_codigo_no_se_exponen_en_zip(tmp_path):
    store=OMRStore(tmp_path/"omr")
    sid=store.create_session("Capacitación",questions(1),
                             persons("Persona prueba"),"Carta")
    evidence=EvidenceStore(store)
    export=export_expediente(
        store,evidence,sid,tmp_path/"expediente.zip",internal=False)
    with ZipFile(export) as bundle:
        assert bundle.namelist()==["Resultados.xlsx","Manifiesto.json"]
        manifest=bundle.read("Manifiesto.json").decode("utf-8")
        assert store.session(sid)["clave_hmac"] not in manifest
        assert "provisional" in manifest
