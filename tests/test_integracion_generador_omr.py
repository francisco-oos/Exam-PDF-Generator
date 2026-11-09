"""Pruebas del inicio integral y transferencia del examen a OMR."""
from __future__ import annotations
import sys
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import pytest


def test_entrada_omr_abre_generador_completo(monkeypatch):
    import calificar_omr
    llamadas = []
    monkeypatch.setitem(sys.modules, "iniciar", SimpleNamespace(main=lambda: llamadas.append("generador")))
    calificar_omr.main([])
    assert llamadas == ["generador"]


def test_solo_calificar_es_opcion_explicita(monkeypatch):
    import calificar_omr
    import omr_evaluaciones.interfaz as interfaz
    llamadas = []
    monkeypatch.setattr(interfaz, "launch", lambda: llamadas.append("omr"))
    calificar_omr.main(["--solo-calificar"])
    assert llamadas == ["omr"]


def test_transferir_examen_y_regresar_al_diseno():
    """Prueba Tk real: conservar preguntas y recuperar la ventana principal."""
    try:
        parent = tk.Tk()
    except tk.TclError as exc:
        pytest.skip("Entorno sin Tcl/Tk operativo: " + str(exc))
    try:
        from src.evaluaciones.core import Question
        from omr_evaluaciones.interfaz import launch
        questions = [Question("Seguridad", "Pregunta 1", ("A", "B", "C", "D"), 2)]
        regresos = []
        app = launch(parent, questions=questions, title="Evaluación de prueba",
                     paper="Oficio", source="Cuestionario abierto",
                     on_return=lambda: regresos.append("editor"))
        assert app.questions[0] == {"tema":"Seguridad", "pregunta":"Pregunta 1", "correcta":"C"}
        assert app.paper.get() == "Oficio"
        assert app.title.get() == "Evaluación de prueba"
        assert app.file_questions.get() == "Cuestionario abierto"
        app.mode.set("ecologico")
        parent.update_idletasks()
        assert not app.buttons["Escanear PDF"].winfo_manager()
        app.return_to_generator()
        assert parent.winfo_exists()
        assert not app.window.winfo_exists()
        assert regresos == ["editor"]
    finally:
        try:
            parent.destroy()
        except tk.TclError:
            pass


def _descendants(widget):
    """Recorrer controles Tk para verificar el flujo visual sin capturas frágiles."""
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def test_inicio_presenta_una_sola_ventana_y_dos_modalidades():
    """Iniciar desde BAT o Linux invoca el mismo main: no deben verse dos vistas."""
    try:
        import iniciar
        root = iniciar.build_ui(open_editor=True)
    except tk.TclError as exc:
        pytest.skip("Entorno sin escritorio Tk: " + str(exc))
    try:
        root.after(180, root.quit)
        root.mainloop()
        root.update_idletasks()
        studios = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
        assert root.state() == "withdrawn"
        assert len(studios) == 1
        editor = studios[0]
        assert editor.winfo_viewable()
        controls = list(_descendants(editor))
        radios = [w for w in controls if isinstance(w, ttk.Radiobutton)]
        labels = [w.cget("text") for w in radios]
        assert len(labels)==2
        assert any(label.startswith("Normal") for label in labels)
        assert any(label.startswith("Ecológico") for label in labels)
        assert not any(label.startswith("Con folio") for label in labels)

        normal = next(w for w in radios if w.cget("text").startswith("Normal"))
        ecologico = next(w for w in radios if w.cget("text").startswith("Ecológico"))
        normal.invoke()
        ecologico.invoke()
        # El QR depende solo de Cargar lista, no de una tercera modalidad.
        actions = [w.cget("text") for w in controls if isinstance(w, tk.Button)]
        assert "Calificar y entregar" in actions
        assert "Generar PDF de examen" in actions
        assert "Generar PDFs de la modalidad elegida" in actions
        assert "Preparar hojas con folio y QR" not in actions
        text_buttons = [w.cget("text") for w in controls if isinstance(w, ttk.Button)]
        assert "Cargar lista" in text_buttons
        assert "Descargar plantilla de participantes" in text_buttons
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def test_calificar_ocupa_su_espacio_y_regresa_al_diseno(tmp_path):
    """El módulo OMR no debe resucitar la ventana principal oculta."""
    try:
        parent = tk.Tk()
    except tk.TclError as exc:
        pytest.skip("Entorno sin escritorio Tk: " + str(exc))
    try:
        from omr_evaluaciones.interfaz import OMRApp
        parent.withdraw()
        callbacks = []
        app = OMRApp(parent=parent, db_root=tmp_path,
                     on_return=lambda: callbacks.append("diseñador"),
                     start_page="Historial")
        assert app.active_view == "Historial"
        assert parent.state() == "withdrawn"
        assert app.window.winfo_exists()
        app.return_to_generator()
        assert callbacks == ["diseñador"]
        assert parent.state() == "withdrawn"
    finally:
        try:
            parent.destroy()
        except tk.TclError:
            pass


def test_menu_calificar_oculta_editor_y_lo_restaura(tmp_path, monkeypatch):
    """Flujo completo desde el menú: nunca deben coexistir dos vistas visibles."""
    try:
        import iniciar
        import omr_evaluaciones.interfaz as interfaz
        root = iniciar.build_ui(open_editor=True)
    except tk.TclError as exc:
        pytest.skip("Entorno sin escritorio Tk: " + str(exc))
    original_store = interfaz.OMRStore
    monkeypatch.setattr(interfaz, "OMRStore", lambda _path: original_store(tmp_path))
    try:
        root.after(180, root.quit)
        root.mainloop()
        editor = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        enter = next(w for w in _descendants(editor)
            if isinstance(w, tk.Button) and w.cget("text") == "Calificar y entregar")
        enter.invoke()
        root.update_idletasks()
        omr_windows = [w for w in root.winfo_children()
                       if isinstance(w, tk.Toplevel) and w is not editor]
        assert len(omr_windows) == 1
        omr_window = omr_windows[0]
        assert editor.state() == "withdrawn"
        assert root.state() == "withdrawn"
        assert omr_window.winfo_exists()

        back = next(w for w in _descendants(omr_window)
            if isinstance(w, tk.Button) and w.cget("text") == "← Diseño e impresión")
        back.invoke()
        root.update_idletasks()
        assert not omr_window.winfo_exists()
        assert editor.state() == "normal"
        assert root.state() == "withdrawn"
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass



def test_historial_unido_por_id_y_nombre_sin_duplicar_examen(tmp_path):
    """Un examen de Biblioteca contiene sus aplicaciones, folios y escaneos."""
    try:
        parent=tk.Tk()
    except tk.TclError as exc:
        pytest.skip('Tcl/Tk no utilizable: '+str(exc))
    try:
        from biblioteca import save_exam
        from src.evaluaciones.core import Question
        from omr_evaluaciones.motor import OMRStore
        from omr_evaluaciones.interfaz import OMRApp
        library=tmp_path/'biblioteca.sqlite3'
        exam_id=save_exam(
            library,nombre='Seguridad operativa - personal',
            empresa='Empresa ficticia',grupo='Equipo A',
            titulo='Evaluación de conocimientos',subtitulo='',
            instrucciones='',questions=[
                Question('Tema','¿Pregunta de prueba?',('A','B','C','D'),2)
            ])
        data=OMRStore(tmp_path/'omr')
        sid=data.create_session(
            'Evaluación de conocimientos',
            [{'tema':'Tema','pregunta':'¿Pregunta de prueba?','correcta':'C'}],
            [{'id':'000001','nombre':'Persona ficticia','grupo':'A'}],
            'Carta','normal',
            nombre_evaluacion='Seguridad operativa - personal',
            cuestionario_id=exam_id,revision_biblioteca=1,
        )
        parent.withdraw()
        app=OMRApp(
            parent=parent,db_root=tmp_path/'omr',
            library_db_path=library,review_only=True,
            on_return=lambda:None,
        )
        tree=next(w for w in _descendants(app.stage)
                  if isinstance(w,ttk.Treeview))
        assert tree.item('exam:'+exam_id,'text')=='Seguridad operativa - personal'
        assert tree.parent('session:'+sid)=='exam:'+exam_id
        assert tree.parent('folio:'+sid+':000001')=='session:'+sid
        assert 'EX-' in tree.item('folio:'+sid+':000001','text')
        assert tree.item('session:'+sid,'text').startswith('Aplicación ')
        assert 'Seguridad operativa - personal' not in tree.item(
            'session:'+sid,'text')
        assert tree.set('session:'+sid,'Participantes')=='1'
        data.rename_session(sid,'Capacitación 2026 - turno B')
        app.navigate('Historial')
        tree=next(w for w in _descendants(app.stage)
                  if isinstance(w,ttk.Treeview))
        assert 'Capacitación 2026' in tree.item('session:'+sid,'text')
        app.return_to_generator()
    finally:
        try:parent.destroy()
        except tk.TclError:pass



def test_migracion_legado_no_adivina_nombres_por_titulo(tmp_path):
    from biblioteca import save_exam, delete_exam
    from src.evaluaciones.core import Question
    from omr_evaluaciones.motor import OMRStore
    lib=tmp_path/'lib.sqlite3'
    question=Question('General','Pregunta de seguridad',
                      ('Uno','Dos','Tres','Cuatro'),1)
    def save(name):
        return save_exam(
            lib,nombre=name,empresa='Ejemplo',grupo='A',
            titulo='Evaluación de conocimientos',subtitulo='',
            instrucciones='',questions=[question],tamano_papel='Carta',
        )
    exam_id=save('Operaciones 2026')
    store=OMRStore(tmp_path/'omr')
    sid=store.create_session(
        'Evaluación de conocimientos',
        [{'tema':'General','pregunta':'Pregunta de seguridad','correcta':'B'}],
        [{'id':'00001','nombre':'Persona ficticia'}],paper='Carta')
    assert store.link_legacy_library_by_exact_key(lib)==1
    assert store.session(sid)['cuestionario_id']==exam_id
    assert store.session(sid)['nombre_evaluacion']=='Operaciones 2026'
    sid2=store.create_session(
        'Evaluación de conocimientos',
        [{'tema':'General','pregunta':'Pregunta de seguridad','correcta':'B'}],
        [{'id':'00002','nombre':'Persona de prueba'}],paper='Carta')
    other=save('Segundo cuestionario idéntico')
    assert store.link_legacy_library_by_exact_key(lib)==0
    assert store.session(sid2)['cuestionario_id'] is None
    delete_exam(lib,other)
    assert store.link_legacy_library_by_exact_key(lib)==1
    assert store.session(sid2)['cuestionario_id']==exam_id



def test_reactivos_provienen_del_examen_y_no_permiten_numeros_inventados():
    from omr_evaluaciones.interfaz import (
        review_question_options, selected_question_number,
    )
    questions=[
        {'tema':'Operación', 'pregunta':'¿Cómo inspeccionar el equipo?', 'correcta':'B'},
        {'tema':'Seguridad', 'pregunta':'¿Qué hacer con una doble marca?', 'correcta':'C'},
        {'tema':'Inventario','pregunta':'¿Cuándo registrar el movimiento?', 'correcta':'A'},
    ]
    options=review_question_options(questions)
    assert len(options)==3
    assert options[0].startswith('01 · ¿Cómo inspeccionar')
    assert options[1].startswith('02 · ¿Qué hacer')
    assert selected_question_number(options[1],options)==2
    assert selected_question_number(options[2],options)==3
    with pytest.raises(ValueError,match='Selecciona una pregunta'):
        selected_question_number('09',options)
    with pytest.raises(ValueError,match='Selecciona una pregunta'):
        selected_question_number('01 · Pregunta de otra evaluación',options)


def test_selector_de_revision_usa_preguntas_de_sesion_qr_y_guarda_indice_correcto(
        tmp_path):
    """El combo es de solo lectura; la selección se traduce al reactivo del OMR."""
    try:
        parent=tk.Tk()
    except tk.TclError as exc:
        pytest.skip('No hay escritorio Tk: '+str(exc))
    try:
        import numpy as np
        from omr_evaluaciones.motor import OMRStore
        from omr_evaluaciones.interfaz import OMRApp
        store=OMRStore(tmp_path/'omr')
        questions=[
            {'tema':'Seguridad','pregunta':'¿Cuál es el primer paso?','correcta':'A'},
            {'tema':'Operación','pregunta':'¿Cómo se reporta una falla?','correcta':'B'},
            {'tema':'Inventario','pregunta':'¿Quién registra el cierre?','correcta':'C'},
        ]
        sid=store.create_session('Evaluación',questions,
            [{'id':'00001','nombre':'Persona de prueba'}],'Carta','normal')
        token=store.session(sid)['personal'][0]['token']
        image=np.full((1000,850,3),255,dtype=np.uint8)
        _,state=store.register_page(sid,'a'*64,0,image,token,
            [None]*3,[{'pregunta':2,'razon':'doble marca'}],'revisar')
        assert state=='revisar'
        parent.withdraw()
        app=OMRApp(parent=parent,db_root=tmp_path/'omr',
            review_only=True,on_return=lambda:None)
        app.session_id=sid
        app.navigate('Revisión')
        selectors=[w for w in _descendants(app.stage)
                   if isinstance(w,ttk.Combobox) and
                   any('primer paso' in x for x in w.cget('values'))]
        assert len(selectors)==1
        selector=selectors[0]
        assert str(selector.cget('state'))=='readonly'
        assert selector.get().startswith('02 ·')  # primera duda elegida
        selector.current(2)
        selector.event_generate('<<ComboboxSelected>>')
        confirm=next(w for w in _descendants(app.stage)
             if isinstance(w,tk.Button) and w.cget('text')=='Confirmar decisión')
        confirm.invoke()
        revisions=store.revisions(sid)
        assert revisions[-1]['pregunta']==3
        assert revisions[-1]['decision']=='A'
        app.return_to_generator()
    finally:
        try:parent.destroy()
        except tk.TclError:pass



def test_alerta_cabos_checadores_muestra_evaluaciones_y_paginas():
    from omr_evaluaciones.interfaz import describe_scan_inspection
    inspected={
        'total_paginas':4,'mezclado':True,
        'grupos':[
            {'sesion_id':'aaaaaa111111','evaluacion':'Cabos','paginas':[1,2]},
            {'sesion_id':'bbbbbb222222','evaluacion':'Checadores','paginas':[3]},
        ],
        'no_identificadas':[
            {'pagina':4,'sesion_id':None,'diagnostico':'QR ilegible'}
        ],
    }
    message=describe_scan_inspection(inspected,'aaaaaa111111')
    assert 'Cabos' in message and 'página(s) 1, 2' in message
    assert 'Checadores' in message and 'página(s) 3' in message
    assert 'OTRA EVALUACIÓN ABIERTA' in message
    assert 'SIN IDENTIFICAR' in message and 'páginas 4' in message
    assert 'NO se calificarán automáticamente' in message


def test_escaneo_de_usuario_no_muestra_botones_de_simulacion(tmp_path):
    from omr_evaluaciones.interfaz import OMRApp
    try:
        parent=tk.Tk()
    except tk.TclError as exc:
        pytest.skip('Entorno sin escritorio Tk: '+str(exc))
    try:
        parent.withdraw()
        app=OMRApp(parent=parent,db_root=tmp_path/'omr',
                   review_only=True,on_return=lambda:None)
        app.navigate('Escanear PDF')
        buttons=[w.cget('text') for w in _descendants(app.stage)
                 if isinstance(w,tk.Button)]
        assert 'Cargar PDF escaneado' in buttons
        assert not any('Simular' in v or 'ficticio' in v for v in buttons)
        app.return_to_generator()
    finally:
        try:parent.destroy()
        except tk.TclError:pass



def test_alerta_previa_impide_calificar_sin_confirmacion(tmp_path,monkeypatch):
    """La aprobación humana ocurre ANTES de registrar un lote mezclado."""
    try:
        parent=tk.Tk()
    except tk.TclError as exc:
        pytest.skip('Entorno sin escritorio Tk: '+str(exc))
    try:
        from omr_evaluaciones.interfaz import OMRApp, messagebox
        parent.withdraw()
        app=OMRApp(parent=parent,db_root=tmp_path/'omr',review_only=True,
                   on_return=lambda:None)
        inspection={
            'total_paginas':3,'mezclado':True,
            'grupos':[
                {'sesion_id':'aaaaaaaaaaaa','evaluacion':'Cabos','paginas':[1,2]},
                {'sesion_id':'bbbbbbbbbbbb','evaluacion':'Checadores','paginas':[3]},
            ],
            'no_identificadas':[],
        }
        dialogs=[]
        routed=[]
        monkeypatch.setattr(messagebox,'askyesno',
            lambda title,detail,**kwargs: dialogs.append((title,detail)) or False)
        monkeypatch.setattr(app,'_process_verified_groups',
            lambda *args:routed.append(args))
        app.scanning=True
        app.scan_updates.put(('preflight',tmp_path/'scan.pdf',{
            'inspection':inspection,'sha':'f'*64,
            'original_path':str(tmp_path/'scan.pdf'),'repetido':False,
        }))
        app._finish_scan()
        assert not app.scanning
        assert not routed
        assert len(dialogs)==1
        assert 'Cabos' in dialogs[0][1] and 'Checadores' in dialogs[0][1]
        assert 'No para cancelar' in dialogs[0][1]
        monkeypatch.setattr(messagebox,'askyesno',lambda *a,**k:True)
        app.scanning=True
        app.scan_updates.put(('preflight',tmp_path/'scan.pdf',{
            'inspection':inspection,'sha':'f'*64,
            'original_path':str(tmp_path/'scan.pdf'),'repetido':False,
        }))
        app._finish_scan()
        assert app.scanning
        assert routed and routed[0][1] is inspection
        app.scanning=False
        app.return_to_generator()
    finally:
        try:parent.destroy()
        except tk.TclError:pass
