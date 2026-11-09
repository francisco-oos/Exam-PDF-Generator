"""Aceptación automática de modalidades con y sin lista de personal.

Usa únicamente datos ficticios y una base OMR aislada; nunca archivos privados.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
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


def numero_paginas(archivo):
    doc=pdfium.PdfDocument(str(archivo))
    try:
        return len(doc)
    finally:
        doc.close()


@pytest.mark.parametrize('modo',['normal','ecologico','folio'])
@pytest.mark.parametrize('con_personal',[False,True])
def test_tres_modalidades_lista_opcional(tmp_path,modo,con_personal):
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
    assert (folder/'Cuadernillo.pdf').is_file()
    assert (folder/'Hoja_respuestas.pdf').is_file()
    assert (folder/'Acetato_clave.pdf').is_file()
    assert (folder/'Clave_docente.pdf').is_file()
    assert (folder/'LEEME_IMPRESION.txt').is_file()
    assert manifest['reutilizable']==(modo!='normal')
    for filename,digest in manifest['archivos_sha256'].items():
        from hashlib import sha256
        assert sha256((folder/filename).read_bytes()).hexdigest()==digest

    if modo=='normal' and con_personal:
        paquetes=folder/'Por_participante'
        assert len([x for x in paquetes.iterdir() if x.is_dir()])==2
        with ZipFile(folder/'Paquetes_individuales.zip') as archive:
            names=archive.namelist()
        assert len(names)==4
        assert sum(n.endswith('/Cuadernillo.pdf') for n in names)==2
        assert numero_paginas(folder/'Hoja_respuestas.pdf')==2
    elif modo=='ecologico' and con_personal:
        assert numero_paginas(folder/'Hoja_respuestas.pdf')==2
        assert not (folder/'Por_participante').exists()
    elif modo=='folio' and con_personal:
        sid=manifest['sesion_omr']
        assert sid and manifest['folio_qr_habilitado'] is True
        store=OMRStore(tmp_path/'omr')
        session=store.session(sid)
        assert len(session['personal'])==2
        assert numero_paginas(folder/'Hoja_respuestas.pdf')==2
        assert numero_paginas(folder/'Acetato_clave.pdf')==1
        assert sid in (folder/'Sesion_OMR.txt').read_text(encoding='utf-8')
        # En un PDF NO marcado deben verse el folio, nombre y una sola geometría.
        data=pdfium.PdfDocument(str(folder/'Hoja_respuestas.pdf'))
        try:
            assert len(data)==2
            assert data[0].get_size()==data[1].get_size()
        finally:
            data.close()
    else:
        assert manifest['sesion_omr'] is None
        assert not (folder/'Sesion_OMR.txt').exists()
        assert numero_paginas(folder/'Hoja_respuestas.pdf')==1


def test_vista_previa_folio_misma_pagina_y_acetato(tmp_path):
    archivo=examen(tmp_path)
    questions=tuple(read_questions(archivo))
    d=PreviewData(questions=questions, titulo='Evaluación ficticia',
                  tamano_papel='Carta',reutilizable=True,
                  modo_examen='folio',cantidad_personas=2,
                  participante_nombre='Participante Uno',
                  participante_id='000001')
    folio=build_preview_pdf(d,'Respuestas')
    acetato=build_preview_pdf(d,'Acetato')
    assert folio.startswith(b'%PDF-') and acetato.startswith(b'%PDF-')
    doc=pdfium.PdfDocument(folio)
    try:
        assert len(doc)==1
    finally:
        doc.close()
    assert not list(tmp_path.glob('**/sesiones.sqlite3'))


def test_lista_invalida_no_crea_salidas(tmp_path):
    archivo=examen(tmp_path)
    roster=tmp_path/'mal.csv'
    roster.write_text('ID_personal,Nombre\n000001,Persona Uno\n000001,Persona Dos\n',
                      encoding='utf-8')
    with pytest.raises(ValueError,match='duplicado'):
        preparar_examen(archivo,tmp_path/'salidas','Prueba','',
                        modo_examen='folio',lista_personal=roster,
                        omr_root=tmp_path/'omr')
    assert not (tmp_path/'salidas').exists()


def test_formulario_impreso_se_puede_reconocer(tmp_path):
    """QR impreso con colores institucionales debe resolver el mismo registro."""
    archivo=examen(tmp_path)
    roster=plantilla_personas(tmp_path)
    folder=preparar_examen(
        archivo,tmp_path/'salidas','Examen ficticio','',
        modo_examen='folio',lista_personal=roster,omr_root=tmp_path/'omr',
        tamano_papel='Carta',color_respuestas='#213A4C',
    )
    sid=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['sesion_omr']
    lectura=scan_document(OMRStore(tmp_path/'omr'),sid,folder/'Hoja_respuestas.pdf')
    assert lectura['leidas']==2
    assert lectura['sin_identificar']==0,lectura
