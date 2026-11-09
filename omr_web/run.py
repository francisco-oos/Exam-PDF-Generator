"""Arranque local de la tableta u oficina, no expone LAN por accidente."""
from __future__ import annotations
import os
import secrets
from pathlib import Path
import uvicorn
from .app import create_app


def main():
    mode=os.getenv("OMR_WEB_MODE","pilot")
    if mode!="pilot":
        raise SystemExit("La licencia central no está integrada: modo producción bloqueado.")
    host=os.getenv("OMR_WEB_BIND","127.0.0.1")
    cert=os.getenv("OMR_WEB_CERT")
    key=os.getenv("OMR_WEB_KEY")
    if host not in ("localhost","127.0.0.1","::1"):
        if not cert or not key or not Path(cert).is_file() or not Path(key).is_file():
            raise SystemExit(
                "Para entrar desde otros dispositivos de la LAN se requiere HTTPS. "
                "Configura OMR_WEB_CERT y OMR_WEB_KEY o usa un proxy HTTPS.")
    app=create_app()
    engine=app.state.engine
    print("\nOMR · CENTRO DE CONTROL (PILOTO, SIN LICENCIA CENTRAL ACTIVA)")
    if engine.needs_setup:
        print("CÓDIGO DE PRIMER ADMINISTRADOR (solo esta consola):",
              engine._setup_token)
    port=int(os.getenv("OMR_WEB_PORT","8877"))
    print(f"Abre https://{host}:{port} si configuraste certificado; "
          f"de lo contrario http://127.0.0.1:{port}")
    uvicorn.run(app,host=host,port=port,ssl_certfile=cert,ssl_keyfile=key,
                proxy_headers=False,access_log=False)


if __name__=="__main__":
    main()
