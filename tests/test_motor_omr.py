"""Banco sintético reproducible: patrones conocidos sobre el PDF real que genera la app.

No constituye prueba de precisión de la Xerox física: falta calibración con muestras reales.
"""
import math
import shutil
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytest
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
from omr_evaluaciones.motor import (OMRStore,bubble_positions,create_forms_pdf,
    scan_document,export_report,PAPERS,RENDER_DPI,_recognize,read_roster)


def questions(n):
    return [{'tema':f'Tema {i%4+1}','pregunta':f'Pregunta {i+1}', 'correcta':'ABCD'[i%4]} for i in range(n)]


def people(n):
    return [{'id':f'{i+1:06d}','nombre':f'Personal sintético {i+1}','area':'Prueba', 'grupo':'A'} for i in range(n)]


def fake_scanned_pdf(src:Path,dst:Path,paper:str,answers,rotation=0,weak=None,double=None,blur=0):
    doc=pdfium.PdfDocument(str(src))
    w,h=PAPERS[paper]
    out=Canvas(str(dst),pagesize=(w,h),pageCompression=1)
    for idx in range(len(doc)):
        page=doc[idx]
        try:im=page.render(scale=RENDER_DPI/72).to_pil().convert('RGB')
        finally:page.close()
        frame=np.asarray(im).copy()
        for j,letter in enumerate(answers[idx]):
            if letter is None:continue
            pts=bubble_positions(paper,len(answers[idx]))[j]
            x,y=pts['ABCD'.index(letter)]
            xx,yy=int(x*RENDER_DPI/72),int((h-y)*RENDER_DPI/72)
            color=(140,140,140) if weak==(idx,j) else (25,25,25)
            cv2.circle(frame,(xx,yy),int(5.5*RENDER_DPI/72),color,-1,cv2.LINE_AA)
            if double==(idx,j):
                x2,y2=pts[('ABCD'.index(letter)+1)%4]
                cv2.circle(frame,(int(x2*RENDER_DPI/72),int((h-y2)*RENDER_DPI/72)),int(5.5*RENDER_DPI/72),(20,20,20),-1)
        if blur:
            frame=cv2.GaussianBlur(frame,(blur,blur),0)
        if rotation:
            center=(frame.shape[1]/2,frame.shape[0]/2)
            matrix=cv2.getRotationMatrix2D(center,rotation,1)
            frame=cv2.warpAffine(frame,matrix,(frame.shape[1],frame.shape[0]),borderValue=(255,255,255))
        img=Image.fromarray(frame)
        out.drawImage(ImageReader(img),0,0,width=w,height=h)
        out.showPage()
    doc.close();out.save()


def test_20_persons_qr_and_scoring(tmp_path):
    store=OMRStore(tmp_path/'store')
    sid=store.create_session('Examen sintético',questions(20),people(4),'Carta')
    paper=create_forms_pdf(store,sid,tmp_path/'answer_forms.pdf')
    true=['ABCD'[i%4] for i in range(20)]
    # Un participante comete tres errores, uno no contesta.
    marks=[true,true.copy(),true.copy(),true.copy()]
    marks[1][0]='B';marks[1][3]='B';marks[1][8]='D'
    marks[2][5]=None
    marks[3][12]='C'
    fake_scanned_pdf(paper,tmp_path/'scan.pdf','Carta',marks)
    got=scan_document(store,sid,tmp_path/'scan.pdf')
    assert got['leidas']==4 and got['validadas']==4 and got['revisar']==0,got
    results=store.results(sid)
    assert results['definitivo'] is True
    scores=sorted(p['aciertos'] for p in results['participantes'])
    assert scores==[17,19,19,20]
    assert results['promedio']==round((17+19+19+20)/80*100,2)
    # Mismo archivo otra vez: no se recalifica.
    rpt=scan_document(store,sid,tmp_path/'scan.pdf')
    assert rpt['repetidas']==4
    assert len(store.pages(sid))==4
    official=export_report(store,sid,tmp_path/'oficial.xlsx')
    assert official.is_file()


def test_ambiguous_never_auto_scored(tmp_path):
    store=OMRStore(tmp_path/'store');sid=store.create_session('Prueba',questions(20),people(1),'A4')
    pdf=create_forms_pdf(store,sid,tmp_path/'print.pdf')
    good=['ABCD'[i%4] for i in range(20)]
    fake_scanned_pdf(pdf,tmp_path/'scan.pdf','A4',[good],double=(0,5))
    reading=scan_document(store,sid,tmp_path/'scan.pdf')
    assert reading['revisar']==1,reading
    assert store.results(sid)['validados']==0
    sheet=store.pages(sid)[0]
    assert any(x['pregunta']==6 for x in sheet['dudas'])
    with pytest.raises(ValueError):store.review(sheet['id'],6,'B','')
    store.review(sheet['id'],6,good[5],'Se confirmó marca original','Inspector')
    assert store.results(sid)['validados']==1
    assert store.results(sid)['participantes'][0]['aciertos']==20


def test_unidentified_and_duplicate(tmp_path):
    store=OMRStore(tmp_path/'store');sid=store.create_session('Prueba',questions(1),people(1))
    pdf=create_forms_pdf(store,sid,tmp_path/'print.pdf')
    fake_scanned_pdf(pdf,tmp_path/'scan.pdf','Carta',[['A']])
    assert scan_document(store,sid,tmp_path/'scan.pdf')['validadas']==1
    shutil.copy(tmp_path/'scan.pdf',tmp_path/'copied.pdf')
    # Identical content hash is a reimport and not a second exam.
    assert scan_document(store,sid,tmp_path/'copied.pdf')['repetidas']==1


@pytest.mark.parametrize('n',[1,20,100])
@pytest.mark.parametrize('paper',['A4','Carta','Oficio'])
def test_positions_and_sizes(n,paper,tmp_path):
    s=OMRStore(tmp_path/'data');sid=s.create_session('Prueba',questions(n),people(1),paper)
    f=create_forms_pdf(s,sid,tmp_path/'page.pdf')
    doc=pdfium.PdfDocument(str(f))
    assert len(doc)==1
    pg=doc[0];width,height=pg.get_size()
    assert abs(width-PAPERS[paper][0])<1 and abs(height-PAPERS[paper][1])<1
    assert len(bubble_positions(paper,n))==n
    pg.close();doc.close()


def test_average_not_penalize_absences(tmp_path):
    store=OMRStore(tmp_path/'db');sid=store.create_session('Prueba',questions(1),people(3))
    result=store.results(sid)
    assert result['promedio'] is None
    assert result['ausentes']==3


def test_roster_csv_zero_ids(tmp_path):
    csv=tmp_path/'personas.csv'
    csv.write_text('ID_personal,Nombre,Area_adscripcion,Grupo\n00001,Ana,A,Uno\n00002,Luis,B,Dos\n',encoding='utf-8-sig')
    data=read_roster(csv)
    assert data[0]['id']=='00001'
    csv.write_text('ID_personal,Nombre\n00001,Ana\n00001,Luis\n',encoding='utf-8')
    with pytest.raises(ValueError,match='duplicado'):read_roster(csv)

@pytest.mark.parametrize('angle',[0,1.5,-1.5,180])
def test_rotation_registration_and_qr(angle,tmp_path):
    store=OMRStore(tmp_path/'store');sid=store.create_session('Prueba rotada',questions(20),people(1),'Carta')
    forms=create_forms_pdf(store,sid,tmp_path/'printed.pdf')
    known=[['ABCD'[j%4] for j in range(20)]]
    fake_scanned_pdf(forms,tmp_path/'scan.pdf','Carta',known,rotation=angle)
    report=scan_document(store,sid,tmp_path/'scan.pdf')
    assert report['validadas']==1,report
    assert store.results(sid)['participantes'][0]['aciertos']==20

@pytest.mark.parametrize('blur',[0,3,5])
def test_blur_simulated(blur,tmp_path):
    store=OMRStore(tmp_path/'db');sid=store.create_session('Prueba borrosa',questions(20),people(1))
    page=create_forms_pdf(store,sid,tmp_path/'pdf.pdf')
    fake_scanned_pdf(page,tmp_path/'scan.pdf','Carta',[['ABCD'[i%4] for i in range(20)]],blur=blur)
    result=scan_document(store,sid,tmp_path/'scan.pdf')
    assert result['validadas']==1,result


def test_duplicate_different_pdf_but_same_token_requires_decision(tmp_path):
    store=OMRStore(tmp_path/'db');sid=store.create_session('Prueba',questions(1),people(1))
    source=create_forms_pdf(store,sid,tmp_path/'printed.pdf')
    fake_scanned_pdf(source,tmp_path/'a.pdf','Carta',[['A']])
    fake_scanned_pdf(source,tmp_path/'b.pdf','Carta',[['B']])
    assert scan_document(store,sid,tmp_path/'a.pdf')['validadas']==1
    assert scan_document(store,sid,tmp_path/'b.pdf')['duplicadas']==1
    assert store.results(sid)['definitivo'] is False
    found=next(p for p in store.pages(sid) if p['estado']=='duplicado')
    store.review(found['id'],None,'DESCARTAR','Segundo intento duplicado','Supervisor')
    assert store.results(sid)['definitivo'] is True


def test_xlsx_is_structured_and_no_answer_key(tmp_path):
    from openpyxl import load_workbook
    store=OMRStore(tmp_path/'store');sid=store.create_session('Prueba',questions(1),people(1))
    sheet=export_report(store,sid,tmp_path/'reporte.xlsx')
    wb=load_workbook(sheet)
    assert {'Resultados','Desempeño por tema','Resumen por grupo','Control de entrega'}==set(wb.sheetnames)
    assert 'Incidencias internas' not in wb.sheetnames
    assert 'PROVISIONAL' in wb['Control de entrega']['B6'].value
    text=''.join(str(c.value or '') for row in wb['Resultados'] for c in row)
    assert 'correcta' not in text
    wb.close()

def test_absent_and_definitive_scanned_attendees_only(tmp_path):
    s=OMRStore(tmp_path/'local');sid=s.create_session('Ausentes',questions(1),people(2),'Carta')
    p=create_forms_pdf(s,sid,tmp_path/'printed.pdf')
    d=pdfium.PdfDocument(str(p));page=d[0]
    from reportlab.lib.utils import ImageReader
    pic=page.render(scale=RENDER_DPI/72).to_pil().convert('RGB')
    page.close();d.close()
    # El primer participante sí presentó examen; el segundo está ausente.
    a=np.asarray(pic).copy();x,y=bubble_positions('Carta',1)[0][0]
    cv2.circle(a,(int(x*RENDER_DPI/72),int((PAPERS['Carta'][1]-y)*RENDER_DPI/72)),14,(0,0,0),-1)
    can=Canvas(str(tmp_path/'scan.pdf'),pagesize=PAPERS['Carta']);can.drawImage(ImageReader(Image.fromarray(a)),0,0,width=PAPERS['Carta'][0],height=PAPERS['Carta'][1]);can.showPage();can.save()
    assert scan_document(s,sid,tmp_path/'scan.pdf')['validadas']==1
    result=s.results(sid)
    assert result['definitivo'] is True
    assert result['ausentes']==1
    assert result['promedio']==100


def test_formula_injection_protected(tmp_path):
    from openpyxl import load_workbook
    store=OMRStore(tmp_path/'db')
    sid=store.create_session('Prueba',questions(1),[{'id':'000001','nombre':'=HYPERLINK("x")'}])
    f=export_report(store,sid,tmp_path/'out.xlsx')
    wb=load_workbook(f)
    value=wb['Resultados']['C4']
    assert value.data_type!='f'
    wb.close()

@pytest.mark.parametrize('n',[1,20,100])
@pytest.mark.parametrize('paper',['A4','Carta','Oficio'])
def test_reconocimiento_integral_9_formatos(n,paper,tmp_path):
    store=OMRStore(tmp_path/'store');sid=store.create_session('Geometría',questions(n),people(1),paper)
    original=create_forms_pdf(store,sid,tmp_path/'forms.pdf')
    values=[['ABCD'[i%4] for i in range(n)]]
    fake_scanned_pdf(original,tmp_path/'scanned.pdf',paper,values)
    summary=scan_document(store,sid,tmp_path/'scanned.pdf')
    assert summary['validadas']==1,summary
    assert store.results(sid)['participantes'][0]['aciertos']==n

@pytest.mark.parametrize('grey',[160,190,220])
def test_very_light_mark_flagged_instead_of_assumed_blank(grey,tmp_path):
    store=OMRStore(tmp_path/'st');sid=store.create_session('Marca tenue',questions(1),people(1),'Carta')
    paper=create_forms_pdf(store,sid,tmp_path/'page.pdf')
    # Lápiz 160: trazo único con contraste suficiente. Lápiz 190:
    # debe requerir revisión; 220 NO debe interpretarse como blanco seguro.
    doc=pdfium.PdfDocument(str(paper));p=doc[0]
    frame=np.asarray(p.render(scale=RENDER_DPI/72).to_pil().convert('RGB')).copy()
    p.close();doc.close()
    x,y=bubble_positions('Carta',1)[0][0]
    cv2.circle(frame,(round(x*RENDER_DPI/72),round((PAPERS['Carta'][1]-y)*RENDER_DPI/72)),14,(grey,grey,grey),-1)
    dst=Canvas(str(tmp_path/'scan.pdf'),pagesize=PAPERS['Carta'])
    dst.drawImage(ImageReader(Image.fromarray(frame)),0,0,width=PAPERS['Carta'][0],height=PAPERS['Carta'][1])
    dst.showPage();dst.save()
    reading=scan_document(store,sid,tmp_path/'scan.pdf')
    if grey==160:
        assert reading['validadas']==1,reading
    elif grey==190:
        assert reading['revisar']==1,reading
    else:
        # 220 es demasiado tenue: jamás inventar una respuesta válida.
        assert reading['validadas']==0,reading


def _fade_scan_to_xerox_grayscale(src, target, paper):
    """Simula impresión y escaneo de marcas negras convertidas a gris ~105.

    Datos ficticios; nunca cargar las hojas reales con nombres al repositorio.
    """
    doc=pdfium.PdfDocument(str(src))
    out=Canvas(str(target),pagesize=PAPERS[paper],pageCompression=1)
    for i in range(len(doc)):
        pg=doc[i]
        try:
            image=np.asarray(pg.render(scale=RENDER_DPI/72).to_pil().convert('RGB'))
        finally:
            pg.close()
        # Negro => 105, papel blanco => 242. El umbral histórico 85 no puede
        # encontrar los cuatro cuadrados, como sucedió con el escáner físico.
        faded=np.clip(image.astype(np.float32)*.54+105,0,255).astype(np.uint8)
        out.drawImage(ImageReader(Image.fromarray(faded)),0,0,
                      width=PAPERS[paper][0],height=PAPERS[paper][1])
        out.showPage()
    doc.close()
    out.save()


def test_registro_xerox_gris_y_reconocimiento_de_errores(tmp_path):
    from omr_evaluaciones.motor import render_review_with_acetato
    store=OMRStore(tmp_path/'data')
    sid=store.create_session('Evaluación de prueba',questions(20),people(2),'Carta',
        'ecologico',nombre_evaluacion='Evaluación ADQUISICIÓN',
        cuestionario_id='a'*32,revision_biblioteca=2)
    forms=create_forms_pdf(store,sid,tmp_path/'forms.pdf')
    correct=['ABCD'[i%4] for i in range(20)]
    one=correct.copy()
    one[2]='A' # respuesta incorrecta deliberada
    scanned=tmp_path/'marcadas.pdf'
    fake_scanned_pdf(forms,scanned,'Carta',[one,correct],
                     double=(1,8))
    faint_scan=tmp_path/'escaneo_gris_xerox_simulado.pdf'
    _fade_scan_to_xerox_grayscale(scanned,faint_scan,'Carta')
    scanned_result=scan_document(store,sid,faint_scan)
    assert scanned_result['leidas']==2
    assert scanned_result['sin_identificar']==0,scanned_result
    assert scanned_result['validadas']==1,scanned_result
    assert scanned_result['revisar']==1,scanned_result
    assert store.sessions()[0]['nombre_evaluacion']=='Evaluación ADQUISICIÓN'
    assert store.sessions()[0]['cuestionario_id']=='a'*32
    assert store.sessions()[0]['revision_biblioteca']==2
    page=store.pages(sid)[1]
    aligned=render_review_with_acetato(
        cv2.imread(page['imagen']),'Carta',questions(20),
        show_acetato=True,issue_numbers=[9])
    assert aligned.size==(round(PAPERS['Carta'][0]*RENDER_DPI/72),
                          round(PAPERS['Carta'][1]*RENDER_DPI/72))
    assert store.results(sid)['definitivo'] is False


def test_reprocesamiento_original_sin_duplicar_ni_borrar_evidencia(tmp_path):
    import hashlib
    store=OMRStore(tmp_path/'data')
    sid=store.create_session('Prueba',questions(20),people(1),'Carta')
    pdf=create_forms_pdf(store,sid,tmp_path/'impresas.pdf')
    sample=tmp_path/'escaneo.pdf'
    fake_scanned_pdf(pdf,sample,'Carta',[
        ['ABCD'[i%4] for i in range(20)]])
    fingerprint=hashlib.sha256(sample.read_bytes()).hexdigest()
    page_data=np.full((2200,1700,3),255,dtype=np.uint8)
    old_id,status=store.register_page(
        sid,fingerprint,0,page_data,None,[None]*20,
        [{'pregunta':None,'razon':'Antes no se reconocía QR'}],
        'sin_identificar')
    assert status=='sin_identificar'
    old_image=store.pages(sid)[0]['imagen']
    result=scan_document(store,sid,sample)
    assert result['reprocesadas']==1,result
    assert result['validadas']==1,result
    assert len(store.pages(sid))==1
    assert store.pages(sid)[0]['id']==old_id
    assert Path(old_image).is_file() # evidencia antigua no se destruye
    assert store.results(sid)['validados']==1
    assert scan_document(store,sid,sample)['repetidas']==1


def test_captura_manual_auditada_y_sin_calificar_desconocidos(tmp_path):
    store=OMRStore(tmp_path/'data')
    sid=store.create_session('Prueba',questions(20),people(1),'Carta')
    page=np.full((2200,1700,3),255,dtype=np.uint8)
    pid,_=store.register_page(
        sid,'a'*64,0,page,None,[None]*20,
        [{'pregunta':None,'razon':'QR ilegible'}],'sin_identificar')
    decisions=['ABCD'[i%4] for i in range(20)]
    with pytest.raises(ValueError,match='identifica'):
        store.capture_manual_sheet(pid,decisions,'Revisado','Inspector')
    person=store.session(sid)['personal'][0]
    store.identify_page(pid,person['id'],person['folio'],
                        'Verifiqué nombre, ID y folio','Inspector')
    with pytest.raises(ValueError,match='Revisa todos'):
        store.capture_manual_sheet(pid,['SIN REVISAR']*20,
                                   'Revisión completa','Inspector')
    decisions[1]='B'
    decisions[2]='BLANCO'
    assert store.capture_manual_sheet(pid,decisions,
        'Captura íntegra cotejada con acetato','Inspector')==20
    assert store.pages(sid)[0]['estado']=='validada'
    result=store.results(sid)
    assert result['validados']==1
    assert result['participantes'][0]['blancos']==1
    assert len(store.revisions(sid))==21 # enlace ID y 20 reactivos



def test_resuelve_sesion_por_qr_firmado_con_titulos_identicos(tmp_path):
    """Evita asignar un PDF a otra evaluación por nombre o posición en historial."""
    from omr_evaluaciones.motor import resolve_pdf_session
    store=OMRStore(tmp_path/'db')
    sid_a=store.create_session(
        'Evaluación de conocimientos',questions(20),people(1),'Carta',
        'ecologico',nombre_evaluacion='Curso de inducción')
    sid_b=store.create_session(
        'Evaluación de conocimientos',questions(20),
        [{'id':'002','nombre':'Otra persona de prueba'}],
        'Carta','normal',nombre_evaluacion='Evaluación de seguridad')
    pdf=create_forms_pdf(store,sid_b,tmp_path/'hoja_b.pdf')
    assert resolve_pdf_session(store,pdf)==sid_b
    assert resolve_pdf_session(store,pdf)!=sid_a



def test_lote_cabos_checadores_no_mezcla_claves(tmp_path):
    """Cabos y Checadores mezclados: cada QR dirige su hoja al examen correcto."""
    import fitz
    from omr_evaluaciones.motor import inspect_pdf_sessions
    store=OMRStore(tmp_path/'store')
    cabos=store.create_session('Examen Cabos',questions(10),people(1),
        'Carta','normal',nombre_evaluacion='Cabos')
    checadores=store.create_session('Examen Checadores',
        [{'tema':'Verificación','pregunta':f'Control {i+1}',
          'correcta':'DCBA'[i%4]} for i in range(10)],
        [{'id':'C002','nombre':'Checador ficticio'}],
        'Carta','ecologico',nombre_evaluacion='Checadores')
    a=create_forms_pdf(store,cabos,tmp_path/'Cabos.pdf')
    b=create_forms_pdf(store,checadores,tmp_path/'Checadores.pdf')
    # Hojas impresas y contestadas, no se decide a partir de texto OCR.
    sa=tmp_path/'Scan_Cabos.pdf'
    sb=tmp_path/'Scan_Checadores.pdf'
    fake_scanned_pdf(a,sa,'Carta',[list('ABCDABCDAB')])
    fake_scanned_pdf(b,sb,'Carta',[list('DCBADC BADC'.replace(' ',''))])
    mixed=tmp_path/'Hojas_traspapeladas.pdf'
    with fitz.open() as merged:
        for path in (sa,sb):
            with fitz.open(path) as doc:
                merged.insert_pdf(doc)
        merged.save(mixed)
    inspected=inspect_pdf_sessions(store,mixed)
    assert inspected['total_paginas']==2
    assert inspected['mezclado'] is True
    assert inspected['no_identificadas']==[]
    assert [item['sesion_id'] for item in inspected['paginas']]==[
        cabos,checadores]
    assert [g['paginas'] for g in inspected['grupos']]==[[1],[2]]
    first=scan_document(store,cabos,mixed,page_indices=[0])
    second=scan_document(store,checadores,mixed,page_indices=[1])
    assert first['leidas']==1 and second['leidas']==1
    assert first['validadas']==1 and second['validadas']==1
    assert len(store.pages(cabos))==1
    assert len(store.pages(checadores))==1
    assert store.pages(cabos)[0]['token']==store.session(cabos)['personal'][0]['token']
    assert store.pages(checadores)[0]['token']==store.session(checadores)['personal'][0]['token']
    assert store.results(cabos)['validados']==1
    assert store.results(checadores)['validados']==1


def test_hoja_sin_qr_no_se_atribuye_automaticamente(tmp_path):
    import fitz
    from omr_evaluaciones.motor import (
        inspect_pdf_sessions, create_generic_forms_pdf,
    )
    store=OMRStore(tmp_path/'store')
    sid=store.create_session('Cabos',questions(4),people(1),
                             'Carta','normal')
    signed=create_forms_pdf(store,sid,tmp_path/'con_qr.pdf')
    generic=create_generic_forms_pdf(questions(4),'Anónimo','Carta',
                                      tmp_path/'sin_qr.pdf')
    mixed=tmp_path/'mezclado.pdf'
    with fitz.open() as target:
        with fitz.open(generic) as anon:
            target.insert_pdf(anon)
        with fitz.open(signed) as ok:
            target.insert_pdf(ok)
        target.save(mixed)
    result=inspect_pdf_sessions(store,mixed)
    assert result['no_identificadas'][0]['pagina']==1
    assert result['grupos'][0]['sesion_id']==sid
    assert result['grupos'][0]['paginas']==[2]
    scan_document(store,sid,mixed,page_indices=[1])
    assert len(store.pages(sid))==1
    assert store.results(sid)['validados']==1
    # El índice original se conserva y puede reimportarse sin duplicar notas.
    assert store.pages(sid)[0]['pagina']==1
    assert scan_document(store,sid,mixed,page_indices=[1])['repetidas']==1


def test_validar_indices_de_paginas_de_lote(tmp_path):
    store=OMRStore(tmp_path/'store')
    sid=store.create_session('Prueba',questions(2),people(1),'Carta')
    form=create_forms_pdf(store,sid,tmp_path/'single.pdf')
    with pytest.raises(ValueError,match='fuera del PDF'):
        scan_document(store,sid,form,page_indices=[99])
    with pytest.raises(ValueError,match='fuera del PDF'):
        scan_document(store,sid,form,page_indices=[])



@pytest.mark.parametrize('shade,expected',[
    (150,'validada'),(165,'validada'),(175,'validada'),
    (190,'revisar'),(220,'revisar'),
])
def test_grafito_hb_diferentes_intensidades_sin_falsas_notas(
        tmp_path,shade,expected):
    """Sobre los círculos impresos, escala de grises de lápiz #2.

    150-175 = un relleno suficiente y único. 190/220 = leve, pide revisión.
    """
    store=OMRStore(tmp_path/'data')
    sid=store.create_session('Lápiz de prueba',questions(8),people(1),'Carta')
    sheet=create_forms_pdf(store,sid,tmp_path/'sheet.pdf')
    pdf=pdfium.PdfDocument(str(sheet))
    page=pdf[0]
    pixels=np.asarray(page.render(scale=RENDER_DPI/72)
        .to_pil().convert('RGB')).copy()
    page.close()
    pdf.close()
    for i,pts in enumerate(bubble_positions('Carta',8)):
        x,y=pts[i%4]
        cv2.circle(pixels,(round(x*RENDER_DPI/72),
                            round((PAPERS['Carta'][1]-y)*RENDER_DPI/72)),
                   round(5.5*RENDER_DPI/72),(shade,shade,shade),
                   thickness=-1,lineType=cv2.LINE_AA)
    scan=tmp_path/'scan.pdf'
    c=Canvas(str(scan),pagesize=PAPERS['Carta'])
    c.drawImage(ImageReader(Image.fromarray(pixels)),0,0,
                width=PAPERS['Carta'][0],height=PAPERS['Carta'][1])
    c.showPage();c.save()
    report=scan_document(store,sid,scan)
    if expected=='validada':
        assert report['validadas']==1,report
        assert store.results(sid)['participantes'][0]['aciertos']==8
    else:
        assert report['revisar']==1,report
        assert store.results(sid)['validados']==0


def test_grafito_doble_oscuro_sigue_pendiente(tmp_path):
    store=OMRStore(tmp_path/'data')
    sid=store.create_session('Dos marcas',questions(2),people(1),'Carta')
    pdf=create_forms_pdf(store,sid,tmp_path/'blank.pdf')
    pages=pdfium.PdfDocument(str(pdf));page=pages[0]
    pixels=np.asarray(page.render(scale=RENDER_DPI/72)
                      .to_pil().convert('RGB')).copy()
    page.close();pages.close()
    for k in (0,1):
        x,y=bubble_positions('Carta',2)[0][k]
        cv2.circle(pixels,(round(x*RENDER_DPI/72),
                           round((PAPERS['Carta'][1]-y)*RENDER_DPI/72)),
                   round(5.5*RENDER_DPI/72),(155,155,155),
                   thickness=-1,lineType=cv2.LINE_AA)
    scan=tmp_path/'scan.pdf'
    output=Canvas(str(scan),pagesize=PAPERS['Carta'])
    output.drawImage(ImageReader(Image.fromarray(pixels)),0,0,
                     width=PAPERS['Carta'][0],height=PAPERS['Carta'][1])
    output.showPage();output.save()
    result=scan_document(store,sid,scan)
    assert result['revisar']==1,result
    assert 1 in [r['pregunta'] for r in store.pages(sid)[0]['dudas']]


def test_lotes_parciales_dias_distintos_y_reimportaciones_sin_duplicar(tmp_path):
    """Una aplicación recibe lotes en varios días, sin segundas calificaciones."""
    import fitz
    store=OMRStore(tmp_path/'omr')
    sid=store.create_session('Evaluación de cabos',questions(8),people(3),
                             'Carta','normal')
    forms=create_forms_pdf(store,sid,tmp_path/'forms.pdf')
    scan=tmp_path/'todos_marcados.pdf'
    known=[['ABCD'[i%4] for i in range(8)] for person in range(3)]
    fake_scanned_pdf(forms,scan,'Carta',known)
    part1=tmp_path/'jornada_1.pdf'
    part2=tmp_path/'jornada_2.pdf'
    with fitz.open(scan) as pages:
        with fitz.open() as a:
            a.insert_pdf(pages,from_page=0,to_page=1)
            a.save(part1)
        with fitz.open() as b:
            b.insert_pdf(pages,from_page=2,to_page=2)
            b.save(part2)
    first=scan_document(store,sid,part1)
    assert first['validadas']==2
    second=scan_document(store,sid,part2)
    assert second['validadas']==1
    assert len(store.pages(sid))==3
    assert store.results(sid)['validados']==3
    assert len(store.sessions())==1
    assert scan_document(store,sid,part1)['repetidas']==2
    # Nuevo PDF con el mismo contenido y folios; no recapturar todo.
    copy=tmp_path/'jornada_1_reexportada.pdf'
    with fitz.open(part1) as doc:
        metadata=dict(doc.metadata)
        metadata['subject']='Lote recibido en un segundo día'
        doc.set_metadata(metadata)
        doc.save(copy)
    assert copy.read_bytes()!=part1.read_bytes()
    assert scan_document(store,sid,copy)['repetidas']==2
    assert len(store.pages(sid))==3
    assert store.results(sid)['validados']==3


def test_reproceso_mejora_pendientes_sin_borrar_revision_humana(tmp_path):
    store=OMRStore(tmp_path/'data')
    sid=store.create_session('Examen',questions(3),people(1),'Carta')
    token=store.session(sid)['personal'][0]['token']
    bitmap=np.full((2200,1700,3),255,dtype=np.uint8)
    old,_=store.register_page(
        sid,'0'*64,0,bitmap,token,[None,None,None],
        [{'pregunta':1,'razon':'lápiz tenue'},
         {'pregunta':2,'razon':'lápiz tenue'}],'revisar')
    recovered,status=store.register_page(
        sid,'0'*64,0,bitmap,token,['A','B',None],
        [{'pregunta':3,'razon':'lápiz tenue'}],'revisar')
    assert recovered==old and status=='reprocesada_revisar'
    assert len(store.pages(sid))==1
    assert store.pages(sid)[0]['respuestas'][:2]==['A','B']
    store.review(old,3,'C','Cotejado en escaneo original','Evaluador')
    again,status=store.register_page(
        sid,'0'*64,0,bitmap,token,['D','D','D'],[],
        'validada')
    assert status=='repetida'
    assert store.pages(sid)[0]['respuestas']==['A','B','C']
