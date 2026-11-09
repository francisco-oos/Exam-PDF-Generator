"""Regresión sobre Tk real: ciclos de vida, errores y render en proceso aislado.

En Linux requiere DISPLAY (ejecutar con xvfb-run). No sustituye pruebas físicas
de DPI ni interacción manual con el administrador de ventanas de Windows.
"""
import time
import tkinter as tk

import pytest

from estudio_diseno import open_design_studio
from vista_previa import PreviewData
from src.evaluaciones.core import Question


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip('Se necesita escritorio o Xvfb para Tk real')
    errors = []
    window.report_callback_exception = lambda *args: errors.append(args)
    yield window, errors
    try:
        window.destroy()
    except tk.TclError:
        pass
    assert not errors


def variables(root):
    values = dict(titulo='Prueba', subtitulo='', empresa='', grupo='', papel='A4',
                  letra='9.0', color_titulo='#213A4C', color_subtitulo='#5E7180',
                  color_respuestas='#213A4C', color_acetato='#167341')
    result = {k: tk.StringVar(root, v) for k, v in values.items()}
    result['reutilizable'] = tk.BooleanVar(root, True)
    return result


def pump(root, seconds):
    until = time.monotonic()+seconds
    while time.monotonic() < until:
        root.update()
        time.sleep(.01)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def test_20_cierres_reaperturas_y_destruccion_padre(root):
    parent, errors = root
    vars = variables(parent)
    data = PreviewData(questions=tuple(Question('Tema', f'Pregunta {i}', ('a', 'b', 'c', 'd'), 0)
                                       for i in range(100)))
    for cycle in range(20):
        editor = open_design_studio(parent, datos_fn=lambda: data, variables=vars)
        parent.update()
        for index in range(15):
            vars['color_acetato'].set(f'#{index:06X}')
            vars['papel'].set(('A4', 'Carta', 'Oficio')[index % 3])
        pump(parent, .38)  # Incluye entrega de trabajo mientras sigue abierto.
        started = time.monotonic()
        if cycle % 3 == 0:
            editor.tk.call(editor.protocol('WM_DELETE_WINDOW'))
        elif cycle % 3 == 1:
            button = next(w for w in descendants(editor)
                          if isinstance(w, tk.Button) and w.cget('text') == 'Volver al generador')
            button.invoke()
        else:
            editor.destroy()  # También la destrucción externa limpia recursos.
        assert time.monotonic()-started < 1
        assert all(not v.trace_info() for v in vars.values())
        pump(parent, .03)
    editor = open_design_studio(parent, datos_fn=lambda: data, variables=vars)
    parent.update()
    parent.destroy()
    assert all(not v.trace_info() for v in vars.values())


def test_pdf_real_y_error_recuperable(root):
    parent, _ = root
    vars = variables(parent)
    fail = [False]
    def data():
        if fail[0]:
            raise ValueError('Color inválido de prueba')
        return PreviewData(questions=(Question('Tema', 'Pregunta', ('a', 'b', 'c', 'd'), 0),))
    editor = open_design_studio(parent, datos_fn=data, variables=vars)
    deadline = time.monotonic()+20
    def rendered():
        return any(isinstance(w, tk.Canvas) and any(w.type(i) == 'image' for i in w.find_all())
                   for w in descendants(editor))
    while not rendered() and time.monotonic() < deadline:
        pump(parent, .1)
    assert rendered(), 'El proceso debe devolver una página PDF real'
    fail[0] = True
    vars['titulo'].set('Cambio inválido')
    pump(parent, .5)
    labels = [str(w.cget('textvariable')) for w in descendants(editor) if isinstance(w, tk.Label)]
    assert any('Color inválido' in str(parent.getvar(v)) for v in labels if v)
    editor.focus_force()
    parent.update()
    editor.event_generate('<Escape>')
    parent.update()
    assert not editor.winfo_exists()


def test_exportacion_no_bloquea_tk(tmp_path, monkeypatch):
    import iniciar
    from biblioteca import export_workbook
    export_workbook([Question('Tema', 'Pregunta', ('a', 'b', 'c', 'd'), 0)],
                    tmp_path/'ejemplos'/'Plantilla_20_preguntas.xlsx')
    monkeypatch.setattr(iniciar, 'BASE', tmp_path)
    messages = []
    monkeypatch.setattr(iniciar.messagebox, 'showinfo', lambda *a, **k: messages.append(a))
    monkeypatch.setattr(iniciar.messagebox, 'showerror', lambda *a, **k: pytest.fail(str(a)))
    try:
        parent = iniciar.build_ui()
    except tk.TclError as exc:
        # GitHub Actions puede iniciar Windows con los archivos Tcl/Tk
        # incompletos. No es evidencia de un fallo de la app: reportar
        # como OMITIDO y exigir prueba real del UI antes de producir.
        if any(fragment in str(exc) for fragment in (
                'usable init.tcl', 'usable tk.tcl',
                'invalid command name "tcl_findLibrary"')):
            pytest.skip("El runner de Windows carece de Tcl/Tk utilizable; prueba manual pendiente.")
        raise
    try:
        errors = []
        parent.report_callback_exception = lambda *args: errors.append(args)
        button = next(w for w in descendants(parent)
                      if isinstance(w, tk.Button) and w.cget('text') == 'Generar documentos')
        start = time.monotonic()
        button.invoke()
        assert time.monotonic()-start < 2
        heartbeats = []
        parent.after(30, lambda: heartbeats.append(True))
        pump(parent, .15)
        assert heartbeats
        deadline = time.monotonic()+15
        while not messages and time.monotonic() < deadline:
            pump(parent, .1)
        assert messages and not errors
        assert len(list((tmp_path/'salidas').glob('*/*.pdf'))) == 4
    finally:
        parent.destroy()
