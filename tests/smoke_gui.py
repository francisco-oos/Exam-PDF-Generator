from pathlib import Path
import sys,time,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from omr_evaluaciones.interfaz import OMRApp
from omr_evaluaciones.demo import create_synthetic_scan
from PIL import ImageGrab
with tempfile.TemporaryDirectory() as temp:
    app=OMRApp(db_root=Path(temp)/'db')
    errors=[]
    app.window.report_callback_exception=lambda *a:errors.append(str(a))
    app.window.update()
    app.load_example()
    app.sample_roster()
    app.navigate('Inicio')
    app.create_session()
    assert app.session_id
    app.preview_form();app.window.update()
    ImageGrab.grab().save('/mnt/data/omr_implement/demo/Vista_Real_Hoja_QR.png')
    _,scan=create_synthetic_scan(app.store,app.session_id,Path(temp)/'demo')
    app.navigate('Escanear PDF');app._run_scan(scan)
    deadline=time.monotonic()+25
    while app.scanning and time.monotonic()<deadline:
        app.window.update();time.sleep(.04)
    assert not app.scanning
    app.navigate('Revisión');app.window.update()
    ImageGrab.grab().save('/mnt/data/omr_implement/demo/Vista_Real_Revision.png')
    app.navigate('Resultados');app.window.update()
    ImageGrab.grab().save('/mnt/data/omr_implement/demo/Vista_Real_Resultados.png')
    assert not errors,errors
    assert len(app.store.pages(app.session_id))==8
    assert app.store.results(app.session_id)['validados']==7
    app.window.destroy()
print('GUI_SMOKE_OK: 8 páginas, 7 validadas, una ambigua, sin errores Tk; navegación y pantallas OK')
