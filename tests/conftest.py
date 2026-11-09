"""Liberación de ciclos Tk en el hilo principal antes de iniciar cada escenario.

Los widgets destruidos pueden permanecer en ciclos Python hasta la siguiente
recolección. Si la inicia el servidor HTTP de otra prueba, sus finalizadores
intentan entrar en un intérprete Tk que ya no tiene mainloop.
"""
import gc

import pytest


@pytest.fixture(autouse=True)
def collect_previous_ui():
    gc.collect()
    yield
