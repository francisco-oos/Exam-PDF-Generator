"""Pruebas de integridad OMR: duplicados, cola global y cierre, sin Xerox."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import secrets
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from omr_web.app import create_app
from omr_web.service import WebError, WebService


def _admin(svc):
    if svc.needs_setup:
        svc.setup(svc._setup_token,"adminpiloto","Administrador","ClaveSeguraPrueba123!")
    token, _, _=svc.login("adminpiloto","ClaveSeguraPrueba123!")
    return svc.authenticate(token)


def _session(svc,number=1):
    people=[{"id":f"P{i:03d}","nombre":f"Persona {i}"}
            for i in range(1,number+1)]
    sid=svc.store.create_session(
        "Integridad de resultados",
        [{"tema":"Seguridad","pregunta":"¿Qué procede?","correcta":"A"}],
        people,"Carta")
    return sid,svc.store.session(sid)["personal"]


def _image():
    return np.full((120,100,3),255,dtype=np.uint8)


def test_escaneo_nuevo_con_respuesta_distinta_nunca_reemplaza_validada(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    user=_admin(svc)
    sid,people=_session(svc)
    token=people[0]["token"]
    original,first=svc.store.register_page(
        sid,"1"*64,0,_image(),token,["A"],[],"validada")
    assert first=="validada"
    svc.approve(user,original)
    before=Path(svc.store.pages(sid)[0]["imagen"]).read_bytes()
    duplicate,second=svc.store.register_page(
        sid,"2"*64,0,_image(),token,["B"],[],"validada")
    assert duplicate!=original and second=="duplicado"
    pages=svc.store.pages(sid)
    assert next(p for p in pages if p["id"]==original)["respuestas"]==["A"]
    assert Path(next(p for p in pages if p["id"]==original)["imagen"]).read_bytes()==before
    assert svc.store.results(sid)["participantes"][0]["estado"]=="pendiente"
    with pytest.raises(WebError,match="Cierre bloqueado"):
        svc.close_application(user,sid)
    assert svc.closure_summary(user,sid)["faltantes"][0]["motivo"]=="DUPLICADO_POR_RESOLVER"
    with pytest.raises(WebError):
        svc.resolve_duplicate(user,original,"No es un duplicado")
    result=svc.resolve_duplicate(user,duplicate,"Reescaneo accidental sin cambio autorizado")
    assert result["original_conservado"]==original
    assert svc.store.results(sid)["participantes"][0]["aciertos"]==1
    assert svc.closure_summary(user,sid)["listo"] is True
    assert svc.close_application(user,sid)["estado"]=="cerrada"
    with pytest.raises(ValueError,match="cerrada"):
        svc.store.register_page(sid,"3"*64,0,_image(),token,["B"],[],"validada")
    assert len(svc.store.pages(sid))==2
    svc.close()


def test_folio_atomicamente_protegido_con_dos_administradores(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    _admin(svc)
    sid,people=_session(svc)
    token=people[0]["token"]
    def attempt(pair):
        idx,answer=pair
        return svc.store.register_page(
            sid,str(idx)*64,0,_image(),token,[answer],[],"validada")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,[(1,"A"),(2,"B")]))
    assert {state for _,state in results}=={"validada","duplicado"}
    assert len(svc.store.pages(sid))==2
    assert len([p for p in svc.store.pages(sid) if p["estado"]=="validada"])==1
    svc.close()


def test_deduplica_trabajos_con_mismo_pdf_en_dos_instancias(tmp_path):
    first=WebService(tmp_path,start_workers=False)
    admin=_admin(first)
    second=WebService(tmp_path,start_workers=False)
    pdf=b"%PDF-1.4\n%%EOF\n"
    files=[]
    for index in range(2):
        target=first.incoming/f"archivo{index}.pdf"
        target.write_bytes(pdf)
        files.append(target)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(lambda args:args[0].add_job(admin,args[1]),
                          [(first,files[0]),(second,files[1])]))
    assert ids[0]==ids[1]
    with first.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM web_trabajos").fetchone()[0]==1
    assert first.job(admin,ids[0])["posicion_cola"]==1
    assert sum(p.exists() for p in files)==1
    first.close();second.close()


def test_cola_de_instancias_no_procesa_dos_pdf_en_paralelo(tmp_path):
    first=WebService(tmp_path,start_workers=False)
    admin=_admin(first)
    second=WebService(tmp_path,start_workers=False)
    active=0
    maximum=0
    order=[]
    lock=threading.Lock()
    def process(row):
        nonlocal active,maximum
        with lock:
            active+=1
            maximum=max(maximum,active)
        time.sleep(0.07)
        with lock:
            order.append(row["id"])
            active-=1
        return {"prueba":True}
    first._process_file=process
    second._process_file=process
    jobs=[]
    for i in range(3):
        path=first.incoming/f"{i}.pdf"
        path.write_bytes(("%PDF-1.4\n"+str(i)+"\n%%EOF\n").encode())
        jobs.append(first.add_job(admin,path))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda svc:svc._process_pending(),[first,second]))
    with first.store.connect() as db:
        statuses=[x["estado"] for x in db.execute(
            "SELECT estado FROM web_trabajos")]
    assert statuses==["terminado"]*3
    assert maximum==1 and len(order)==3
    first.close();second.close()


def test_cierre_bloqueado_por_ausentes_y_aprobacion_con_lista_integra(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    user=_admin(svc)
    sid,people=_session(svc,3)
    first=svc.closure_summary(user,sid)
    assert first["cantidad_pendientes"]==3
    assert {p["motivo"] for p in first["faltantes"]}=={"SIN_ESCANEO"}
    with pytest.raises(WebError) as exc:
        svc.close_application(user,sid)
    assert exc.value.status==409
    for index,person in enumerate(people):
        svc.store.register_page(
            sid,str(index+1)*64,0,_image(),person["token"],
            ["A"],[],"validada")
    summary=svc.closure_summary(user,sid)
    assert summary["cantidad_pendientes"]==3
    assert {p["motivo"] for p in summary["faltantes"]}=={"APROBACION_PENDIENTE"}
    for p in svc.store.pages(sid):
        svc.approve(user,p["id"])
    assert svc.closure_summary(user,sid)["listo"]
    final=svc.close_application(user,sid)
    assert final["estado"]=="cerrada"
    with pytest.raises(WebError) as exc:
        svc.claim(user,svc.store.pages(sid)[0]["id"])
    assert exc.value.status==409
    svc.close()


def test_api_conciliacion_presenta_faltantes_y_cierre_protegido(tmp_path):
    app=create_app(tmp_path,start_workers=False)
    svc=app.state.engine
    user=_admin(svc)
    sid,_=_session(svc,2)
    with TestClient(app) as client:
        response=client.post("/api/login",json={
            "usuario":"adminpiloto","password":"ClaveSeguraPrueba123!"})
        assert response.status_code==200
        headers={"X-CSRF-Token":client.cookies.get("omr_csrf")}
        pre=client.get(f"/api/applications/{sid}/closure")
        assert pre.status_code==200
        assert len(pre.json()["faltantes"])==2
        closed=client.post(f"/api/applications/{sid}/close",headers=headers)
        assert closed.status_code==409
    svc.close()


def test_guardar_ultima_decision_libera_reserva_atomica(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    admin=_admin(svc)
    sid,people=_session(svc)
    sheet,_=svc.store.register_page(
        sid,"9"*64,0,_image(),people[0]["token"],
        [None],[{"pregunta":1,"razon":"Grafito tenue"}],"revisar")
    claim=svc.claim(admin,sheet)
    saved=svc.save_decisions(admin,sheet,claim["lease"],claim["revision"],
                             [{"pregunta":1,"decision":"A"}],
                             "Comprobación física de marca")
    assert saved["estado"]=="validada" and saved["reserva_liberada"]
    assert svc.closure_summary(admin,sid)["revisiones_activas"]==0
    with pytest.raises(WebError) as exc:
        svc.save_decisions(admin,sheet,claim["lease"],saved["revision"],
                           [{"pregunta":1,"decision":"B"}],"Intento tardío")
    assert exc.value.status==409
    svc.approve(admin,sheet)
    assert svc.closure_summary(admin,sid)["listo"]
    svc.close()


def test_repetir_add_job_con_misma_ruta_no_borra_original_en_cola(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    admin=_admin(svc)
    source=svc.incoming/"mismo_archivo.pdf"
    source.write_bytes(b"%PDF-1.4\\n%%EOF\\n")
    first=svc.add_job(admin,source)
    second=svc.add_job(admin,source)
    assert first==second
    assert source.is_file()
    with svc.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM web_trabajos").fetchone()[0]==1
    svc.close()
