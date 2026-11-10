"""Simulaciones multiusuario sin Xerox real, identidades ficticias."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib

import numpy as np
import pytest
from omr_web.service import WebService, WebError


QUESTIONS=[
    {"tema":"Seguridad","pregunta":"Primero","correcta":"A"},
    {"tema":"Operación","pregunta":"Segundo","correcta":"C"},
    {"tema":"Mantenimiento","pregunta":"Tercero","correcta":"D"},
]


def second_user(svc,admin,name,role="capturista",sid=None):
    start="TemporalDePrueba2026!"
    end="DefinitivaDePrueba2026!"
    uid=svc.add_user(admin,name,name,start,role)
    if sid: svc.assign(admin,uid,sid)
    token,_,_=svc.login(name,start)
    svc.change_password(svc.authenticate(token),start,end)
    token,_,_=svc.login(name,end)
    return svc.authenticate(token)


@pytest.fixture()
def sample(tmp_path):
    svc=WebService(tmp_path,start_workers=False)
    svc.setup(svc._setup_token,"adminprueba","Admin","ClaveDefinitivaAdmin2026!")
    token,_,_=svc.login("adminprueba","ClaveDefinitivaAdmin2026!")
    admin=svc.authenticate(token)
    sid=svc.store.create_session("Simulacro de Cabos",QUESTIONS,[
        {"id":"ID001","nombre":"Persona ficticia 1"},
        {"id":"ID002","nombre":"Persona ficticia 2"}],"Carta")
    people=svc.store.session(sid)["personal"]
    yield svc,admin,sid,people
    svc.close()


def register(svc,sid,person,index,answers,issues=None,status="validada"):
    image=np.full((240,190,3),255,dtype=np.uint8)
    return svc.store.register_page(sid,f"{index:064x}",0,image,
        person["token"],answers,issues or [],status)[0]


def test_ausente_y_lapiz_dudoso_no_generan_nota_definitiva(sample):
    svc,admin,sid,people=sample
    sheet=register(svc,sid,people[0],21,[None,None,"D"],[
        {"pregunta":1,"razon":"Grafito tenue"},
        {"pregunta":2,"razon":"Doble marca"}],"revisar")
    report=svc.results_with_evidence(admin,sid)
    assert report["ausentes"]==1
    assert report["participantes"][0]["aciertos"] is None
    assert report["participantes"][1]["estado"]=="ausente"
    assert {p["motivo"] for p in svc.closure_summary(admin,sid)["faltantes"]}=={
        "REVISION_PENDIENTE","SIN_ESCANEO"}
    with pytest.raises(WebError,match="Cierre bloqueado"):
        svc.close_application(admin,sid)
    assert svc.get_sheet(admin,sheet)["dudas"][0]["razon"]=="Grafito tenue"


def test_dos_auxiliares_revision_parcial_version_y_lease(sample):
    svc,admin,sid,people=sample
    sheet=register(svc,sid,people[0],22,[None,None,"D"],[
        {"pregunta":1,"razon":"Lápiz tenue"},
        {"pregunta":2,"razon":"Doble marca"}],"revisar")
    first=second_user(svc,admin,"auxiliar1",sid=sid)
    other=second_user(svc,admin,"auxiliar2",sid=sid)
    lease=svc.claim(first,sheet)
    with pytest.raises(WebError) as locked: svc.claim(other,sheet)
    assert locked.value.status==409
    partial=svc.save_decisions(first,sheet,lease["lease"],lease["revision"],
        [{"pregunta":1,"decision":"A"}],"Cotejo de papel y grafito")
    assert partial["estado"]=="revisar" and partial["pendientes"]==1
    with pytest.raises(WebError) as stale:
        svc.save_decisions(first,sheet,lease["lease"],lease["revision"],
            [{"pregunta":2,"decision":"BLANCO"}],"Pestaña vieja")
    assert stale.value.status==409
    finished=svc.save_decisions(first,sheet,lease["lease"],partial["revision"],
        [{"pregunta":2,"decision":"BLANCO"}],"Doble marca anulada en papel")
    assert finished["reserva_liberada"]
    with pytest.raises(WebError) as blocked:
        svc.save_decisions(first,sheet,lease["lease"],finished["revision"],
            [{"pregunta":2,"decision":"C"}],"Guardado tardío")
    assert blocked.value.status==409
    assert svc.store.results(sid)["participantes"][0]["aciertos"]==2
    svc.approve(admin,sheet)


def test_rectificacion_suspende_nota_y_exige_firma_de_otro_operador(sample):
    svc,admin,sid,people=sample
    first=register(svc,sid,people[0],23,["A","C","D"])
    second=register(svc,sid,people[1],24,["A","C","D"])
    svc.approve(admin,first)
    svc.approve(admin,second)
    before=hashlib.sha256(Path(svc.store.pages(sid)[0]["imagen"]).read_bytes()).hexdigest()
    opened=svc.reopen_validated(admin,first,2,
        "Solicitud documentada para cotejar de nuevo la hoja")
    assert opened["aciertos_anteriores"]==3
    assert svc.results_with_evidence(admin,sid)["participantes"][0]["aciertos"] is None
    assert svc.closure_summary(admin,sid)["faltantes"][0]["motivo"]=="REVISION_PENDIENTE"
    with pytest.raises(WebError): svc.approve(admin,first)
    lease=svc.claim(admin,first)
    finished=svc.save_decisions(admin,first,lease["lease"],lease["revision"],
        [{"pregunta":2,"decision":"BLANCO"}],"Rectificación documentada en papel")
    assert finished["estado"]=="validada"
    assert svc.store.results(sid)["participantes"][0]["aciertos"]==2
    assert svc.results_with_evidence(admin,sid)["participantes"][0]["requiere_otro_aprobador"]
    with pytest.raises(WebError,match="OTRO administrador"):
        svc.approve(admin,first)
    supervisor=second_user(svc,admin,"supervisor",role="admin")
    assert not svc.results_with_evidence(supervisor,sid)["participantes"][0]["requiere_otro_aprobador"]
    svc.approve(supervisor,first)
    with pytest.raises(WebError,match="ya cuenta con aprobación"):
        svc.approve(admin,first)
    assert svc.closure_summary(admin,sid)["listo"]
    assert svc.close_application(admin,sid)["estado"]=="cerrada"
    after=hashlib.sha256(Path(svc.store.pages(sid)[0]["imagen"]).read_bytes()).hexdigest()
    assert before==after
    with pytest.raises(WebError):
        svc.reopen_validated(admin,first,2,"No se modifica una evaluación cerrada")


def test_dos_administradores_no_pueden_reemplazar_aprobacion(sample):
    svc,admin,sid,people=sample
    sheet=register(svc,sid,people[0],25,["A","C","D"])
    other=second_user(svc,admin,"adminparalelo",role="admin")
    def attempt(user):
        try:
            svc.approve(user,sheet)
            return "ok"
        except WebError as exc:
            return str(exc.status)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(attempt,[admin,other]))
    assert sorted(outcomes)==["409","ok"]
    with svc.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM web_aprobaciones WHERE hoja_id=?",
                          (sheet,)).fetchone()[0]==1


def test_hojas_sin_identificar_bloquean_cierre_aun_con_lista_aprobada(sample):
    svc,admin,sid,people=sample
    for index,person in enumerate(people):
        sheet=register(svc,sid,person,30+index,["A","C","D"])
        svc.approve(admin,sheet)
    image=np.full((240,190,3),255,dtype=np.uint8)
    svc.store.register_page(sid,"a"*64,0,image,None,[None]*3,[
        {"pregunta":1,"razon":"QR ilegible"}],"sin_identificar")
    summary=svc.closure_summary(admin,sid)
    assert summary["cantidad_pendientes"]==0
    assert summary["sin_identificar"]==1 and not summary["listo"]
    with pytest.raises(WebError,match="Cierre bloqueado"):
        svc.close_application(admin,sid)
