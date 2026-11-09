"""Una sola hoja de respuestas en ambos modos, QR condicionado solo por la lista."""
from __future__ import annotations

import csv
import json
from hashlib import sha256
from zipfile import ZipFile

import pypdfium2 as pdfium
import pytest
from openpyxl import Workbook

from generacion_integrada import preparar_examen
from omr_evaluaciones.motor import OMRStore, scan_document
from preview_pdf import build_preview_pdf
from src.evaluaciones.core import read_questions
from vista_previa import PreviewData


def examen(tmp_path):
    archivo=tmp_path/'Preguntas.xlsx'
    book=Workbook()
    page=book.active
    page.title='Preguntas'
    page.append(['Tema','Pregunta','A','B','C','D','Correcta'])
    for i in range(1,5):
        page.append(['Cultura general',f'Reactivo de ejemplo {i}',
                     'Opción uno','Opción dos','Opción tres','Opción cuatro','ABCD'[i-1]])
    book.save(archivo)
    return archivo


def plantilla_personas(tmp_path):
    archivo=tmp_path/'Personal.csv'
    with archivo.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['ID_personal','Nombre','Area_adscripcion','Grupo','Turno'])
        writer.writerow(['000001','Participante de prueba Uno','Pruebas','A','Día'])
        writer.writerow(['000002','Participante de prueba Dos','Pruebas','A','Día'])
    return archivo


def pdf_pages(archivo):
    doc=pdfium.PdfDocument(str(archivo))
    try:
        return len(doc)
    finally:
        doc.close()


def extraer_pdf(archivo):
    import fitz
    with fitz.open(archivo) as documento:
        return [pagina.get_text() for pagina in documento]


@pytest.mark.parametrize('modo',['normal','ecologico'])
@pytest.mark.parametrize('con_personal',[False,True])
def test_dos_modalidades_lista_opcional_misma_hoja(tmp_path,modo,con_personal):
    preguntas=examen(tmp_path)
    personal=plantilla_personas(tmp_path) if con_personal else None
    folder=preparar_examen(
        preguntas,tmp_path/'salidas','Evaluación ficticia','Prueba',
        empresa='Institución ficticia',puesto='A',tamano_papel='Carta',
        modo_examen=modo,lista_personal=personal,omr_root=tmp_path/'omr',
    )
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['modo_examen']==modo
    assert manifest['participantes']==(2 if con_personal else 0)
    assert manifest['folio_qr_habilitado']==con_personal
    assert manifest['formato_hoja']=='universal-omr-v1'
    assert manifest['reutilizable']==(modo=='ecologico')
    for name in ['Cuadernillo.pdf','Hoja_respuestas.pdf','Acetato_clave.pdf',
                 'Clave_docente.pdf','LEEME_IMPRESION.txt']:
        assert (folder/name).is_file()
    for filename,digest in manifest['archivos_sha256'].items():
        assert sha256((folder/filename).read_bytes()).hexdigest()==digest

    hojas=extraer_pdf(folder/'Hoja_respuestas.pdf')
    assert len(hojas)==(2 if con_personal else 1)
    assert 'HOJA DE RESPUESTAS' in hojas[0]
    assert 'ACETATO' in extraer_pdf(folder/'Acetato_clave.pdf')[0]
    assert pdf_pages(folder/'Acetato_clave.pdf')==1
    if con_personal:
        sid=manifest['sesion_omr']
        assert sid and sid in (folder/'Sesion_OMR.txt').read_text(encoding='utf-8')
        session=OMRStore(tmp_path/'omr').session(sid)
        assert len(session['personal'])==2
        assert '000001' in '\n'.join(hojas)
        assert 'EX-' in hojas[0]
    else:
        assert manifest['sesion_omr'] is None
        assert not (folder/'Sesion_OMR.txt').exists()
        assert 'Folio:' in hojas[0]
        assert 'EX-' not in hojas[0]
        assert 'Nombre:' in hojas[0]

    if modo=='normal' and con_personal:
        paquetes=folder/'Por_participante'
        assert len([x for x in paquetes.iterdir() if x.is_dir()])==2
        with ZipFile(folder/'Paquetes_individuales.zip') as zipfile:
            names=zipfile.namelist()
        assert len(names)==4
        assert sum(n.endswith('/Cuadernillo.pdf') for n in names)==2
        individual=sorted(paquetes.glob('*/Hoja_respuestas.pdf'))
        assert len(individual)==2
        assert all(pdf_pages(p)==1 for p in individual)
        assert all('EX-' in extraer_pdf(p)[0] for p in individual)
    else:
        assert not (folder/'Por_participante').exists()
        assert not (folder/'Paquetes_individuales.zip').exists()


@pytest.mark.parametrize('modo',['normal','ecologico'])
@pytest.mark.parametrize('con_personal',[False,True])
def test_vista_previa_igual_en_dos_modos_y_sin_qr_si_no_hay_lista(
        tmp_path,modo,con_personal):
    archivo=examen(tmp_path)
    d=PreviewData(
        questions=tuple(read_questions(archivo)),titulo='Evaluación ficticia',
        tamano_papel='Carta',reutilizable=(modo=='ecologico'),
        modo_examen=modo,cantidad_personas=2 if con_personal else 0,
        participante_nombre='Participante Uno',participante_id='000001',
    )
    folio=build_preview_pdf(d,'Respuestas')
    acetato=build_preview_pdf(d,'Acetato')
    assert folio.startswith(b'%PDF-')
    assert acetato.startswith(b'%PDF-')
    import fitz
    with fitz.open(stream=folio,filetype='pdf') as doc:
        assert len(doc)==1
        texto=doc[0].get_text()
        assert ('EX-VISTA-PREVIA' in texto)==con_personal
        assert 'HOJA DE RESPUESTAS' in texto
    with fitz.open(stream=acetato,filetype='pdf') as doc:
        assert len(doc)==1
        assert 'ACETATO' in doc[0].get_text()
    assert not list(tmp_path.glob('**/sesiones.sqlite3'))


def test_no_se_permite_tercer_modo_folio(tmp_path):
    with pytest.raises(ValueError,match='normal o ecológico'):
        preparar_examen(examen(tmp_path),tmp_path/'salidas','Prueba','',
                        modo_examen='folio',omr_root=tmp_path/'omr')
    assert not (tmp_path/'salidas').exists()


def test_lista_invalida_no_crea_salidas(tmp_path):
    roster=tmp_path/'mal.csv'
    roster.write_text('ID_personal,Nombre\n000001,Persona Uno\n000001,Persona Dos\n',
                      encoding='utf-8')
    with pytest.raises(ValueError,match='duplicado'):
        preparar_examen(examen(tmp_path),tmp_path/'salidas','Prueba','',
                        modo_examen='ecologico',lista_personal=roster,
                        omr_root=tmp_path/'omr')
    assert not (tmp_path/'salidas').exists()


@pytest.mark.parametrize('modo',['normal','ecologico'])
def test_qr_de_ambos_modos_es_legible_para_el_mismo_escaner(tmp_path,modo):
    folder=preparar_examen(
        examen(tmp_path),tmp_path/'salidas','Examen ficticio','',
        modo_examen=modo,lista_personal=plantilla_personas(tmp_path),
        omr_root=tmp_path/'omr',tamano_papel='Carta',
        color_respuestas='#213A4C',
    )
    sid=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['sesion_omr']
    lectura=scan_document(OMRStore(tmp_path/'omr'),sid,folder/'Hoja_respuestas.pdf')
    assert lectura['leidas']==2
    assert lectura['sin_identificar']==0,lectura


@pytest.mark.parametrize('modo',['normal','ecologico'])
def test_qr_rechaza_color_demasiado_claro_en_ambos_modos(tmp_path,modo):
    with pytest.raises(ValueError,match='oscuro'):
        preparar_examen(
            examen(tmp_path),tmp_path/'salidas','Prueba','',modo_examen=modo,
            lista_personal=plantilla_personas(tmp_path),
            omr_root=tmp_path/'omr',color_respuestas='#FFFF99',
        )
    assert not (tmp_path/'salidas').exists()
