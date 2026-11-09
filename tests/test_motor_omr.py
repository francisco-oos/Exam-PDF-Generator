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
    # A 180/190 es más clara que la tinta normal; debe ser dudosa, no blanco falso.
    doc=pdfium.PdfDocument(str(paper));p=doc[0]
    frame=np.asarray(p.render(scale=RENDER_DPI/72).to_pil().convert('RGB')).copy()
    p.close();doc.close()
    x,y=bubble_positions('Carta',1)[0][0]
    cv2.circle(frame,(round(x*RENDER_DPI/72),round((PAPERS['Carta'][1]-y)*RENDER_DPI/72)),14,(grey,grey,grey),-1)
    dst=Canvas(str(tmp_path/'scan.pdf'),pagesize=PAPERS['Carta'])
    dst.drawImage(ImageReader(Image.fromarray(frame)),0,0,width=PAPERS['Carta'][0],height=PAPERS['Carta'][1])
    dst.showPage();dst.save()
    reading=scan_document(store,sid,tmp_path/'scan.pdf')
    if grey<=190:assert reading['revisar']==1,reading
