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
