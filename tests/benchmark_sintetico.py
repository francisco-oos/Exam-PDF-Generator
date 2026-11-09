"""Calcula cobertura y exactitud SOLO sobre hojas rasterizadas artificialmente.

Los datos no provienen de una Xerox C7120 ni sirven como certificación OMR real.
"""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from omr_evaluaciones.motor import OMRStore,scan_document,export_report
from omr_evaluaciones.demo import create_synthetic_scan

def run(output:Path):
    output.mkdir(parents=True,exist_ok=True)
    store=OMRStore(output/'datos_locales')
    n=20
    qs=[{'tema':f'Tema {i%4+1}','pregunta':f'Reactivo sintético {i+1}','correcta':'ABCD'[i%4]} for i in range(n)]
    people=[{'id':f'{i+1:06d}','nombre':f'Participante ficticio {i+1}',
             'area':'Entrenamiento','grupo':'A','turno':'Matutino'} for i in range(20)]
    sid=store.create_session('Evaluación OMR de demostración',qs,people,'Carta')
    forms,scan=create_synthetic_scan(store,sid,output,ambiguous=True)
    start=time.monotonic();reading=scan_document(store,sid,scan);seconds=round(time.monotonic()-start,3)
    result=store.results(sid)
    # Respuesta artificial conocida: 2 errores programados por cada 20 preguntas.
    expected=[]
    for pidx in range(20):
        expected.append([q['correcta'] if (i+pidx)%9 not in (4,7) else 'ABCD'[("ABCD".index(q['correcta'])+1)%4]
                         for i,q in enumerate(qs)])
    by_token={p['token']:i for i,p in enumerate(store.session(sid)['personal'])}
    # El orden del paquete PDF es el de creación de participantes, no alfabético.
    ordered=[p['token'] for p in store.session(sid)['personal']]
    # emparejar por página real: el escáner recibe una hoja por participante en orden de impresión
    page_tokens=[p['token'] for p in store.session(sid)['personal']]
    # count based on page_idx: en esta demo la página es el orden de la lista del PDF original,
    # que es la lista del diccionario store.session (orden SELECT nombre); ajustar en demo
    accepted=0;correct=0
    for page in store.pages(sid):
        if page['estado']!='validada':continue
        pidx=page['pagina']
        accepted+=len(page['respuestas'])
        correct+=sum(a==e for a,e in zip(page['respuestas'],expected[pidx]))
    metrics={'caso':'20 personas × 20 reactivos, hoja Carta, 200 DPI equivalente, un reactivo doble',
             'paginas':reading['leidas'],'qr_identificados':reading['validadas']+reading['revisar'],
             'hojas_validadas':reading['validadas'],'hojas_dudosas':reading['revisar'],
             'burbujas_validas':accepted,'lecturas_correctas_de_burbujas_aceptadas':correct,
             'precision_sintetica_en_aceptadas':round(100*correct/accepted,3) if accepted else 0,
             'porcentaje_de_hojas_auto_validadas':round(100*reading['validadas']/20,2),
             'segundos_para_20_paginas':seconds,
             'advertencia':'Sólo pruebas sobre PDFs sintéticos; no mide precisión de escaneo real Xerox.'}
    export_report(store,sid,output/'Resultados_OMR_Oficial_PROVISIONAL.xlsx')
    export_report(store,sid,output/'Resultados_OMR_Interno_PROVISIONAL.xlsx',internal=True)
    (output/'metricas_sinteticas.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False,indent=2))
    return metrics

if __name__=='__main__':run(Path(sys.argv[1]) if len(sys.argv)>1 else Path('demo'))
