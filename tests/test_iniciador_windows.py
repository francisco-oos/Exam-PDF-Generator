"""Ejecuta la comprobación real del BAT con una dependencia ausente."""
from pathlib import Path
import re
import subprocess
import sys


def test_entorno_anterior_sin_pypdf_requiere_instalacion():
    launcher = (Path(__file__).resolve().parents[1] /
                'Iniciar_Windows.bat').read_text(encoding='utf-8')
    probe = re.findall(r'python\.exe" -c "([^"]+)"', launcher)[0]
    # Reproduce una actualización: las versiones antiguamente comprobadas
    # están instaladas, pero falta la dependencia de la nueva bandeja.
    setup = '''
import builtins
import importlib.metadata as metadata
metadata.version = lambda name: {'openpyxl': '3.1.5',
    'reportlab': '5.1.0', 'pypdfium2': '5.15.1'}[name]
original_import = builtins.__import__
def without_pypdf(name, *args, **kwargs):
    if name == 'pypdf':
        raise ModuleNotFoundError("No module named 'pypdf'")
    return original_import(name, *args, **kwargs)
builtins.__import__ = without_pypdf
'''
    result = subprocess.run([sys.executable, '-c', setup + '\n' + probe],
                            capture_output=True, text=True)
    assert result.returncode != 0, 'El BAT omite instalar pypdf faltante'
    assert 'pypdf' in result.stderr
