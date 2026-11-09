"""Pruebas del inicio integral y transferencia del examen a OMR."""
from __future__ import annotations
import sys
from types import SimpleNamespace
import tkinter as tk
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


def test_inicio_presenta_una_sola_ventana_y_tres_modalidades():
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
        radios = [w for w in controls if isinstance(w, __import__("tkinter").ttk.Radiobutton)]
        labels = [w.cget("text") for w in radios]
        assert any(label.startswith("Normal") for label in labels)
        assert any(label.startswith("Ecológico") for label in labels)
        assert any(label.startswith("Con folio y QR") for label in labels)

        qr_button = next(w for w in controls
            if isinstance(w, tk.Button) and w.cget("text") == "Preparar hojas con folio y QR")
        normal = next(w for w in radios if w.cget("text").startswith("Normal"))
        folio = next(w for w in radios if w.cget("text").startswith("Con folio y QR"))
        normal.invoke()
        assert qr_button.winfo_manager() == ""
        folio.invoke()
        assert qr_button.winfo_manager() == "grid"

        actions = [w.cget("text") for w in controls if isinstance(w, tk.Button)]
        assert "Calificar y entregar" in actions
        assert "Generar cuadernillo, respuestas y acetato PDF" in actions
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
