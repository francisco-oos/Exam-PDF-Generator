"""Pruebas Tk de bandeja de escaneos sin abrir segundo programa."""
from hashlib import sha256
import tkinter as tk
from tkinter import ttk
import pytest

from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import letter

from omr_evaluaciones.interfaz import OMRApp
from omr_evaluaciones.documentos import DocumentInbox


def _widgets(widget):
    for child in widget.winfo_children():
        yield child
        yield from _widgets(child)


def _pdf(tmp_path):
    f=tmp_path/'sin_identificar.pdf'
    c=Canvas(str(f),pagesize=letter)
    c.drawString(55,760,'Hoja sin identificador sintético')
    c.showPage();c.save()
    digest=sha256(f.read_bytes()).hexdigest()
    inspection={
        'total_paginas':1,'paginas':[
            {'pagina':1,'sesion_id':None,'estado':'sin_identificar',
             'diagnostico':'Sin QR'}
        ],
        'grupos':[],'no_identificadas':[
            {'pagina':1,'sesion_id':None,'estado':'sin_identificar'}
        ],'mezclado':False,'pdf_sha256':digest,
    }
    return f,inspection


def _parent():
    try:
        root=tk.Tk()
    except tk.TclError as exc:
        pytest.skip('No existe escritorio Tk: '+str(exc))
    root.withdraw()
    return root


def test_bandeja_pdf_aparece_solo_en_calificacion_y_archiva_pendientes(
        tmp_path):
    parent=_parent()
    try:
        app=OMRApp(parent=parent,db_root=tmp_path/'omr',
                   review_only=True,on_return=lambda:None)
        assert 'Bandeja PDF' in app.buttons
        app.navigate('Bandeja PDF')
        assert app.active_view=='Bandeja PDF'
        file,inspection=_pdf(tmp_path)
        digest,_=app.inbox.archive(file,inspection)
        app.navigate('Bandeja PDF')
        labels=[w.cget('text') for w in _widgets(app.stage)
                if isinstance(w,tk.Button)]
        for expected in ['Subir página','Bajar página','Girar 90°',
                         'Extraer página','Exportar PDF ordenado',
                         'Copiar original','Vincular pendiente']:
            assert expected in labels
        trees=[w for w in _widgets(app.stage)
               if isinstance(w,ttk.Treeview)]
        assert len(trees)==2
        assert digest in trees[0].get_children()
        assert trees[1].get_children()
        app.return_to_generator()
    finally:
        try:parent.destroy()
        except tk.TclError:pass


@pytest.mark.parametrize('approve',[False,True])
def test_escaneo_no_identificado_puede_archivarse_sin_calificar(
        tmp_path,monkeypatch,approve):
    from omr_evaluaciones import interfaz
    parent=_parent()
    try:
        app=OMRApp(parent=parent,db_root=tmp_path/'omr',
                   review_only=True,on_return=lambda:None)
        pdf,inspection=_pdf(tmp_path)
        dialogs=[]
        monkeypatch.setattr(interfaz.messagebox,'askyesno',
            lambda *args,**kwargs:dialogs.append(args) or approve)
        app.scanning=True
        app.scan_updates.put(('preflight',pdf,inspection))
        app._finish_scan()
        assert len(dialogs)==1
        assert not app.scanning
        assert len(app.inbox.documents())==int(approve)
        assert app.store.sessions()==[]
        if approve:
            assert app.active_view=='Bandeja PDF'
            assert app.inbox.documents()[0]['pendientes']==1
        app.return_to_generator()
    finally:
        try:parent.destroy()
        except tk.TclError:pass
