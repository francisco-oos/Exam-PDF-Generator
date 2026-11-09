"""Escaneo sintético reproducible: pinta círculos en el PDF real, no simula resultados.

Solo para probar el motor y los controles, no para estimar la exactitud de la Xerox.
"""
from pathlib import Path
import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from .motor import PAPERS,RENDER_DPI,bubble_positions,create_forms_pdf

def create_synthetic_scan(store,sid,folder:Path,ambiguous=True):
    s=store.session(sid)
    if not s['personal']:raise ValueError('La simulación requiere participantes.')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    original=create_forms_pdf(store,sid,folder/'Hojas_impresas_QR.pdf')
    output=folder/'Escaneo_sintetico_OMR.pdf'
    questions=s['preguntas'];paper=s['papel'];w,h=PAPERS[paper]
    positions=bubble_positions(paper,len(questions))
    document=pdfium.PdfDocument(str(original))
    pdf=Canvas(str(output),pagesize=(w,h),pageCompression=1)
    for pidx in range(len(document)):
        page=document[pidx]
        try:pic=page.render(scale=RENDER_DPI/72).to_pil().convert('RGB')
        finally:page.close()
        frame=np.asarray(pic).copy()
        for i,q in enumerate(questions):
            # Resultado predecible pero con errores auténticos respecto a la clave.
            answer=q['correcta'] if (i+pidx)%9 not in (4,7) else 'ABCD'[("ABCD".index(q['correcta'])+1)%4]
            x,y=positions[i]['ABCD'.index(answer)]
            xx=int(x*RENDER_DPI/72);yy=int((h-y)*RENDER_DPI/72)
            cv2.circle(frame,(xx,yy),round(5.2*RENDER_DPI/72),(18,18,18),-1,cv2.LINE_AA)
            if ambiguous and pidx==1 and i==3:
                other=("ABCD".index(answer)+1)%4
                x2,y2=positions[i][other]
                cv2.circle(frame,(int(x2*RENDER_DPI/72),int((h-y2)*RENDER_DPI/72)),round(5.2*RENDER_DPI/72),(18,18,18),-1,cv2.LINE_AA)
        pdf.drawImage(ImageReader(Image.fromarray(frame)),0,0,width=w,height=h)
        pdf.showPage()
    document.close();pdf.save()
    return original,output
