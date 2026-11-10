"""Arranque local de la tableta u oficina, no expone LAN por accidente."""
from __future__ import annotations
import os
import uvicorn
from .app import create_app
from .runtime import data_directory, config_file


def main():
    mode=os.getenv("OMR_WEB_MODE","pilot")
    if mode!="pilot":
        raise SystemExit("La licencia central no está integrada: modo producción bloqueado.")
    host=os.getenv("OMR_WEB_BIND","127.0.0.1")
    cert=config_file(os.getenv("OMR_WEB_CERT"))
    key=config_file(os.getenv("OMR_WEB_KEY"))
    if host not in ("localhost","127.0.0.1","::1"):
        if not cert or not key or not cert.is_file() or not key.is_file():
            raise SystemExit(
                "Para entrar desde otros dispositivos de la LAN se requiere HTTPS. "
                "Configura OMR_WEB_CERT y OMR_WEB_KEY o usa un proxy HTTPS.")
    # Ruta estable aun si Windows inicia el proceso con otro directorio activo.
    # Nunca usar datos/omr de Tk por accidente durante el piloto.
    app=create_app(data_directory())
    engine=app.state.engine
    print("\nOMR · CENTRO DE CONTROL (PILOTO, SIN LICENCIA CENTRAL ACTIVA)")
    if engine.needs_setup:
        print("CÓDIGO DE PRIMER ADMINISTRADOR (solo esta consola):",
              engine._setup_token)
    port=int(os.getenv("OMR_WEB_PORT","8877"))
    print(f"Abre https://{host}:{port} si configuraste certificado; "
          f"de lo contrario http://127.0.0.1:{port}")
    uvicorn.run(app,host=host,port=port,
                ssl_certfile=str(cert) if cert else None,
                ssl_keyfile=str(key) if key else None,
                proxy_headers=False,access_log=False)


if __name__=="__main__":
    main()
