"""Aceptación de archivo global, hojas mezcladas y expedientes OMR.

Datos y nombres ficticios. No utiliza PDF reales del usuario.
"""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json

import pytest
from pypdf import PdfReader,PdfWriter
import pypdfium2 as pdfium

from omr_evaluaciones.motor import (
    OMRStore, create_forms_pdf, create_generic_forms_pdf,
    inspect_pdf_sessions, scan_document,
)
from omr_evaluaciones.documentos import DocumentInbox, sha_file
from omr_evaluaciones.expedientes import (
    export_session_bundle, participant_receipt,
)


def qs(n=4):
    return [
        {'tema':'Tema de prueba','pregunta':f'Pregunta sintética {i+1}',
         'correcta':'ABCD'[i%4]}
        for i in range(n)
    ]


def people(prefix, n):
    return [
        {'id':f'{prefix}{i:03d}',
         'nombre':f'Persona sintética {prefix}{i+1}'}
        for i in range(1,n+1)
    ]


def combined(dst,*sources):
    writer=PdfWriter()
    for source in sources:
        reader=PdfReader(str(source))
        writer.append(reader)
    with Path(dst).open('wb') as out:
        writer.write(out)
    return Path(dst)


def fixture_mixed(tmp_path):
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    cabos=store.create_session(
        'Conocimientos',qs(),people('C',1),'Carta','normal',
        nombre_evaluacion='Evaluación de Cabos')
    chec=store.create_session(
        'Conocimientos',qs(),people('H',1),'Carta','ecologico',
        nombre_evaluacion='Evaluación de Checadores')
    pdf1=create_forms_pdf(store,cabos,tmp_path/'cabos.pdf')
    pdf2=create_forms_pdf(store,chec,tmp_path/'checadores.pdf')
    anon=create_generic_forms_pdf(qs(),'Hoja sin QR','Carta',
                                   tmp_path/'anonima.pdf')
    mixed=combined(tmp_path/'lote_mezclado.pdf',pdf1,pdf2,anon)
    return store,inbox,cabos,chec,mixed


def _ingest_and_grade(store,inbox,pdf):
    inspected=inspect_pdf_sessions(store,pdf)
    digest,archive=inbox.archive(pdf,inspected,operator='Técnico ficticio')
    for group in inspected['grupos']:
        report=scan_document(
            store,group['sesion_id'],archive,
            page_indices=[p-1 for p in group['paginas']])
        inbox.mark_processed(digest,group['sesion_id'],report)
    return inspected,digest,archive


def test_conservar_todas_las_paginas_y_clasificar_lote_mixto(tmp_path):
    store,inbox,cabos,chec,pdf=fixture_mixed(tmp_path)
    original=sha_file(pdf)
    inspected,digest,archive=_ingest_and_grade(store,inbox,pdf)
    assert digest==original and sha_file(archive)==original
    assert inspected['total_paginas']==3
    assert inspected['mezclado']
    assert [p['sesion_id'] for p in inspected['paginas']]==[
        cabos,chec,None]
    pages=inbox.pages(digest)
    assert [p['estado'] for p in pages]==[
        'procesada','procesada','pendiente']
    assert [p['sesion_id'] for p in pages]==[cabos,chec,None]
    assert len(store.pages(cabos))==1
    assert len(store.pages(chec))==1
    assert len(inbox.documents())==1
    assert inbox.documents()[0]['pendientes']==1

    # Otro día: el mismo PDF no ocupa otro espacio ni pisa los resultados.
    _ingest_and_grade(store,inbox,pdf)
    assert len(inbox.documents())==1
    assert inbox.documents()[0]['veces_recibido']==2
    assert len(store.pages(cabos))==1
    assert len(store.pages(chec))==1
    assert inbox.pages(digest)[2]['estado']=='pendiente'
    assert sha_file(archive)==original
    assert len([e for e in inbox.events(digest) if e['accion']=='ingreso'])==2


def test_no_perder_archivo_sin_qr_y_detectar_cambio_entre_inspeccion_y_archivo(
        tmp_path):
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    anon=create_generic_forms_pdf(qs(),'Anónimo','Carta',
                                   tmp_path/'generico.pdf')
    checked=inspect_pdf_sessions(store,anon)
    assert not checked['grupos']
    assert checked['no_identificadas'][0]['pagina']==1
    digest,_=inbox.archive(anon,checked)
    assert inbox.pages(digest)[0]['estado']=='pendiente'
    assert len(store.sessions())==0
    checked['pdf_sha256']='0'*64
    with pytest.raises(ValueError,match='cambió'):
        inbox.archive(anon,checked)
    assert inbox.original(digest).exists()


def test_organizar_extraer_girar_sin_tocar_el_pdf_original(tmp_path):
    store,inbox,cabos,chec,pdf=fixture_mixed(tmp_path)
    inspected,digest,archive=_ingest_and_grade(store,inbox,pdf)
    before=archive.read_bytes()
    derivative=inbox.assemble([
        (digest,1,90),(digest,0,0),(digest,2,180)],
        tmp_path/'organizado.pdf')
    reader=PdfReader(str(derivative))
    assert len(reader.pages)==3
    assert int(reader.pages[0].get('/Rotate',0))%360==90
    assert int(reader.pages[2].get('/Rotate',0))%360==180
    source=PdfReader(str(archive))
    assert [page.extract_text() for page in reader.pages]==[
        source.pages[i].extract_text() for i in (1,0,2)]
    assert archive.read_bytes()==before
    assert sha_file(archive)==digest
    extracted=inbox.assemble([(digest,1,0)],tmp_path/'extraido.pdf')
    assert len(PdfReader(str(extracted)).pages)==1
    image=inbox.render_page(digest,0,scale=.5,rotate=90)
    assert image.width>50 and image.height>50
    with pytest.raises(ValueError,match='Rotación'):
        inbox.assemble([(digest,0,45)],tmp_path/'no.pdf')
    with pytest.raises(ValueError,match='original'):
        inbox.assemble([(digest,0,0)],archive)


def test_expediente_no_filtra_archivo_mixto_entre_evaluaciones(tmp_path):
    store,inbox,cabos,chec,pdf=fixture_mixed(tmp_path)
    inspected,digest,archive=_ingest_and_grade(store,inbox,pdf)
    result=export_session_bundle(
        store,inbox,cabos,tmp_path/'expediente.zip',internal=True)
    with ZipFile(result) as zipfile:
        names=zipfile.namelist()
        assert 'Resultados_Internos.xlsx' in names
        assert 'Bitacora.pdf' in names
        assert 'Evidencias_Ordenadas.pdf' in names
        assert 'Manifiesto.json' in names
        assert not any(name.startswith('PDF_originales/') for name in names)
        data=json.loads(zipfile.read('Manifiesto.json'))
        assert digest in data['originales_no_incluidos_por_mezcla']
        for filename,digest_expected in data['archivos_sha256'].items():
            assert sha256(zipfile.read(filename)).hexdigest()==digest_expected
        evidence=pdfium.PdfDocument(zipfile.read('Evidencias_Ordenadas.pdf'))
        assert len(evidence)==1
        evidence.close()
    official=export_session_bundle(
        store,inbox,cabos,tmp_path/'oficial.zip',internal=False)
    with ZipFile(official) as z:
        assert 'Resultados_Oficiales.xlsx' in z.namelist()
        assert not any('Evidencia' in x or 'Bitacora' in x or
                       'Original' in x for x in z.namelist())
    person=store.session(cabos)['personal'][0]
    receipt=participant_receipt(
        store,cabos,person['id'],tmp_path/'resultado_personal.pdf')
    content=PdfReader(str(receipt)).pages[0].extract_text()
    assert person['id'] in content
    assert store.session(chec)['personal'][0]['id'] not in content
    assert 'Preguntas correctas' not in content


def test_pdf_exclusivo_se_incluye_en_expediente_interno(tmp_path):
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    sid=store.create_session('Evaluación A',qs(),people('A',1),'Carta')
    paper=create_forms_pdf(store,sid,tmp_path/'solo_a.pdf')
    _,digest,_=_ingest_and_grade(store,inbox,paper)
    with ZipFile(export_session_bundle(
        store,inbox,sid,tmp_path/'interno.zip')) as z:
        assert 'PDF_originales/'+digest+'.pdf' in z.namelist()
        assert z.read('PDF_originales/'+digest+'.pdf')==paper.read_bytes()


def test_vincular_sin_qr_a_una_sesion_no_califica_automaticamente(tmp_path):
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    sid=store.create_session('Ejemplo',qs(),people('A',1),'Carta')
    anon=create_generic_forms_pdf(qs(),'Anónimo','Carta',
                                   tmp_path/'anon.pdf')
    inspection=inspect_pdf_sessions(store,anon)
    digest,_=inbox.archive(anon,inspection)
    person=store.session(sid)['personal'][0]
    with pytest.raises(ValueError,match='no corresponden'):
        inbox.bind_manual_pending(digest,0,sid,'NO_EXISTE',person['folio'],
                                  'Inspector','Revisión de papel')
    inbox.bind_manual_pending(
        digest,0,sid,person['id'],person['folio'],
        'Inspector','Verifiqué físicamente ID y folio')
    assert inbox.pages(digest)[0]['estado']=='manual_pendiente'
    rows=store.pages(sid)
    assert len(rows)==1 and rows[0]['estado']=='revisar'
    assert all(x is None for x in rows[0]['respuestas'])
    assert store.results(sid)['validados']==0
    store.capture_manual_sheet(rows[0]['id'],list('ABCD'),
                               'Respuesta cotejada','Inspector')
    assert store.results(sid)['validados']==1
    assert inbox.pages(digest)[0]['estado']=='procesada_manual'
    assert inbox.documents()[0]['pendientes']==0
    assert len(store.revisions(sid))==5


def test_importaciones_de_varios_dias_no_crean_segundas_sesiones(tmp_path):
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    sid=store.create_session('Curso de seguridad',qs(),people('A',2),
                             'Carta','ecologico')
    total=create_forms_pdf(store,sid,tmp_path/'total.pdf')
    source=PdfReader(str(total))
    for index in (0,1):
        path=tmp_path/f'dia_{index+1}.pdf'
        writer=PdfWriter()
        writer.add_page(source.pages[index])
        with path.open('wb') as f:
            writer.write(f)
        _ingest_and_grade(store,inbox,path)
    assert len(store.sessions())==1
    assert len(inbox.documents())==2
    assert len(inbox.pages_for_session(sid))==2
    assert len(store.pages(sid))==2
    assert store.results(sid)['validados']==2
    _ingest_and_grade(store,inbox,tmp_path/'dia_1.pdf')
    assert len(store.pages(sid))==2
    assert inbox.documents()[0]['veces_recibido'] in (1,2)


def test_no_exponer_rutas_ni_hmac_en_manifiestos(tmp_path):
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    sid=store.create_session('Curso',qs(),people('A',1),'Carta')
    pdf=create_forms_pdf(store,sid,tmp_path/'sheet.pdf')
    _ingest_and_grade(store,inbox,pdf)
    target=export_session_bundle(
        store,inbox,sid,tmp_path/'audit.zip')
    with ZipFile(target) as z:
        manifest=z.read('Manifiesto.json').decode()
        assert str(tmp_path) not in manifest
        assert store.session(sid)['clave_hmac'] not in manifest



def test_migracion_de_bandeja_no_modifica_sesiones_anteriores(tmp_path):
    store=OMRStore(tmp_path/'omr')
    sid=store.create_session('Evaluación anterior',qs(),people('H',1),
                             'Carta')
    old=store.session(sid)
    inbox=DocumentInbox(store)
    inbox2=DocumentInbox(store)
    new=store.session(sid)
    assert old['clave_hmac']==new['clave_hmac']
    assert old['version_sha']==new['version_sha']
    assert len(store.sessions())==1
    assert inbox.documents()==inbox2.documents()==[]


def test_original_alterado_bloqueado_para_todas_las_exportaciones(tmp_path):
    store,inbox,cabos,chec,pdf=fixture_mixed(tmp_path)
    inspected,digest,archived=_ingest_and_grade(store,inbox,pdf)
    with archived.open('ab') as out:
        out.write(b'alterado')
    with pytest.raises(ValueError,match='alterado'):
        inbox.original(digest)
    with pytest.raises(ValueError,match='alterado'):
        inbox.assemble([(digest,0,0)],tmp_path/'derivado.pdf')
    with pytest.raises(ValueError,match='alterado'):
        export_session_bundle(store,inbox,cabos,tmp_path/'expediente.zip')


def test_no_incluir_datos_de_otra_evaluacion_en_historial_pdf(tmp_path):
    store,inbox,cabos,chec,pdf=fixture_mixed(tmp_path)
    _ingest_and_grade(store,inbox,pdf)
    result=export_session_bundle(store,inbox,cabos,
                                 tmp_path/'solo_cabos.zip',internal=True)
    with ZipFile(result) as z:
        assert 'Historial_Documental.pdf' in z.namelist()
        import io
        reader=PdfReader(io.BytesIO(z.read('Historial_Documental.pdf')))
        text='\n'.join(page.extract_text() or '' for page in reader.pages)
        # Los eventos de página de Checadores no deben salir en Cabos.
        assert store.session(chec)['personal'][0]['folio'] not in text



def test_combinar_paginas_de_dos_documentos_sin_editar_fuentes(tmp_path):
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    sessions=[]
    archived=[]
    for code in ('A','B'):
        sid=store.create_session(
            'Cuestionario '+code,qs(),people(code,1),'Carta')
        paper=create_forms_pdf(store,sid,tmp_path/(code+'.pdf'))
        preflight=inspect_pdf_sessions(store,paper)
        digest,path=inbox.archive(paper,preflight)
        sessions.append(sid)
        archived.append((digest,path,sha_file(path)))
    output=inbox.assemble([
        (archived[1][0],0,270),
        (archived[0][0],0,0),
    ],tmp_path/'combinado.pdf')
    pages=PdfReader(str(output)).pages
    assert len(pages)==2
    assert int(pages[0].get('/Rotate',0))%360==270
    assert all(sha_file(source)==old_hash
               for _,source,old_hash in archived)
    assert len([e for e in inbox.events()
                if e['accion']=='pdf_organizado'])==2


@pytest.mark.parametrize('location', ['bandeja', 'originales', 'escaneos'])
def test_resultado_individual_no_sobrescribe_evidencia(tmp_path, location):
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    sid=store.create_session('Prueba',qs(),people('A',1),'Carta')
    paper=create_forms_pdf(store,sid,tmp_path/'hoja.pdf')
    _,digest,archived=_ingest_and_grade(store,inbox,paper)
    target=archived if location=='bandeja' else store.root/location/'fuente.pdf'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target!=archived:
        target.write_bytes(paper.read_bytes())
    before=target.read_bytes()
    person=store.session(sid)['personal'][0]
    with pytest.raises(ValueError,match='original|escaneo'):
        participant_receipt(store,sid,person['id'],target)
    assert target.read_bytes()==before
    assert sha_file(archived)==digest


def test_recuperar_archivado_antes_de_calificar_tras_reabrir(tmp_path):
    store,inbox,cabos,chec,pdf=fixture_mixed(tmp_path)
    checked=inspect_pdf_sessions(store,pdf)
    digest,archive=inbox.archive(pdf,checked)
    assert store.pages(cabos)==store.pages(chec)==[]
    # Todas las conexiones son transaccionales; nuevas instancias leen solo
    # el estado persistido, sin conservar la inspección en memoria.
    reopened=OMRStore(tmp_path/'omr')
    recovered=DocumentInbox(reopened)
    assert recovered.documents()[0]['pendientes']==3
    assert len(recovered.pages(digest))==3
    inspected=inspect_pdf_sessions(reopened,recovered.original(digest))
    for group in inspected['grupos']:
        report=scan_document(reopened,group['sesion_id'],archive,
                             page_indices=[p-1 for p in group['paginas']])
        recovered.mark_processed(digest,group['sesion_id'],report)
    assert recovered.documents()[0]['pendientes']==1
    assert len(reopened.pages(cabos))==len(reopened.pages(chec))==1
    assert sha_file(archive)==digest


def test_duplicados_equivalentes_y_conflictivos_en_bandeja(tmp_path):
    from test_motor_omr import fake_scanned_pdf
    store=OMRStore(tmp_path/'omr')
    inbox=DocumentInbox(store)
    sid=store.create_session('Cabos',qs(),people('C',1),'Carta')
    forms=create_forms_pdf(store,sid,tmp_path/'forms.pdf')
    scan=tmp_path/'scan.pdf'
    fake_scanned_pdf(forms,scan,'Carta',[list('ABCD')])
    _ingest_and_grade(store,inbox,scan)
    original=store.pages(sid)[0]
    equivalent=combined(tmp_path/'equivalente.pdf',scan)
    assert sha_file(equivalent)!=sha_file(scan)
    _,digest,_=_ingest_and_grade(store,inbox,equivalent)
    assert inbox.pages(digest)[0]['estado']=='reimportada'
    assert len(store.pages(sid))==1
    changed=tmp_path/'conflictivo.pdf'
    fake_scanned_pdf(forms,changed,'Carta',[list('DBCD')])
    _,digest,_=_ingest_and_grade(store,inbox,changed)
    assert inbox.pages(digest)[0]['estado']=='conflicto_duplicado'
    assert next(p for p in store.pages(sid) if p['id']==original['id'])[
        'respuestas']==list('ABCD')
    assert len(store.pages(sid))==2
    with ZipFile(export_session_bundle(store,inbox,sid,tmp_path/'conflicto.zip')) as z:
        assert 'Evidencias_Ordenadas.pdf' not in z.namelist()
        assert json.loads(z.read('Manifiesto.json'))['folios_sin_evidencia_efectiva']


def test_contenido_completo_de_entregables_aislado_por_evaluacion(tmp_path):
    from io import BytesIO
    from openpyxl import load_workbook
    store,inbox,cabos,chec,pdf=fixture_mixed(tmp_path)
    _ingest_and_grade(store,inbox,pdf)
    other=store.session(chec)['personal'][0]
    forbidden=[other['id'],other['nombre'],other['folio'],chec]
    for internal in (True,False):
        bundle=export_session_bundle(store,inbox,cabos,
                                     tmp_path/f'{internal}.zip',internal=internal)
        with ZipFile(bundle) as z:
            for name in z.namelist():
                data=z.read(name)
                if name.endswith('.pdf'):
                    text='\n'.join(p.extract_text() or ''
                                   for p in PdfReader(BytesIO(data)).pages)
                elif name.endswith('.xlsx'):
                    book=load_workbook(BytesIO(data))
                    text='\n'.join(str(c.value) for sheet in book
                                   for row in sheet for c in row)
                    book.close()
                elif name.endswith('.json'):
                    text=data.decode('utf-8')
                else:
                    pytest.fail('Entregable no inspeccionado: '+name)
                assert not any(value in text for value in forbidden),name
                if name=='Evidencias_Ordenadas.pdf':
                    evidence=tmp_path/'evidencia.pdf'
                    evidence.write_bytes(data)
                    verified=inspect_pdf_sessions(store,evidence)
                    assert [g['sesion_id'] for g in verified['grupos']]==[cabos]
                    assert verified['total_paginas']==1
