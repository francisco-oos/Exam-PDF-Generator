"""Smoke tests of the Docker browser UI; also run without Docker in pytest."""
from __future__ import annotations
import io
import re
import threading
import urllib.error
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path
from http.server import ThreadingHTTPServer

import pytest
import web_app as web
from openpyxl import Workbook


def _get(url):
    with urlopen(url, timeout=25) as r:
        return r.status, r.read().decode('utf-8')


def test_file_selection_is_not_a_path(tmp_path, monkeypatch):
    input_dir = tmp_path / 'entradas'
    input_dir.mkdir()
    doc = input_dir / 'safe.xlsx'
    doc.write_bytes(b'data')
    (input_dir / 'not_allowed.xlsm').write_bytes(b'data')
    monkeypatch.setattr(web, 'INPUTS', input_dir)
    monkeypatch.setattr(web, 'EXAMPLES', tmp_path / 'no_examples')
    items = web.available_exam_files()
    assert items == [(doc, 'Mis exámenes · safe.xlsx')]
    assert web._is_regular(doc, input_dir)
    assert not web._is_regular(tmp_path / 'out.xlsx', input_dir)


def test_web_flow_and_dangerous_requests(tmp_path, monkeypatch):
    input_dir = tmp_path / 'entradas'; input_dir.mkdir()
    wb=Workbook();s=wb.active;s.title='Preguntas';s.append(['Tema','Pregunta','A','B','C','D','Correcta']);s.append(['AFU','¿Cuántos?','Uno','Dos','Tres','Cuatro','B'])
    wb.save(input_dir / 'valid.xlsx')
    monkeypatch.setattr(web, 'INPUTS', input_dir)
    monkeypatch.setattr(web, 'EXAMPLES', tmp_path / 'no_examples')
    monkeypatch.setattr(web, 'OUTPUTS', tmp_path / 'salidas')
    server=ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    # Host validation is fixed to configured port. For the test, use the ephemeral port.
    monkeypatch.setattr(web, 'PORT', server.server_address[1])
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    url=f'http://127.0.0.1:{web.PORT}'
    try:
        status, html=_get(url+'/')
        assert status==200 and 'Preparar evaluación' in html
        bad=URLRequest(url+'/generar', {'token':'invalid','archivo':'0','logo':'0'})
        with pytest.raises(urllib.error.HTTPError) as ex:
            urlopen(bad,timeout=5)
        assert ex.value.code==403
        good=URLRequest(url+'/generar', {'token':web.TOKEN,'archivo':'0','logo':'0','empresa':'Empresa demo','puesto':'Cabos','titulo':'Examen AFU','subtitulo':'Local','instrucciones':'Elige una opción'})
        status,html2=download(good)
        assert status==200 and 'Documentos generados' in html2
        output=list((tmp_path/'salidas').iterdir())
        assert len(output)==1 and (output[0]/'Acetato_clave.pdf').is_file()
        href=re.search(r'href="(/descargar/[^\"]+/Cuadernillo.pdf)"',html2)
        assert href
        with urlopen(url+href.group(1),timeout=5) as pdf:
            assert pdf.status==200 and pdf.read(4)==b'%PDF'
        with pytest.raises(urllib.error.HTTPError) as ex:
            urlopen(url+'/descargar/../../requirements.txt',timeout=5)
        assert ex.value.code in (403,404)
        # Localhost-only Host header (DNS rebinding defense).
        req=Request(url,headers={'Host':'evil.example:8765'})
        with pytest.raises(urllib.error.HTTPError) as ex:
            urlopen(req,timeout=5)
        assert ex.value.code==403
    finally:
        server.shutdown();server.server_close();t.join(timeout=5)


def URLRequest(url, fields):
    return Request(url,data=urlencode(fields).encode('utf-8'),method='POST',headers={'Content-Type':'application/x-www-form-urlencoded'})


def download(req):
    with urlopen(req,timeout=25) as resp:
        return resp.status,resp.read().decode('utf-8')
