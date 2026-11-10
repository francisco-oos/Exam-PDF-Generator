"""Certificado de prueba para HTTPS LAN, no es una CA de producción.

Uso: python -m omr_web.certificate 192.168.1.15
La clave se guarda fuera de Git, en datos/omr/certs. El navegador debe
confiar explícitamente en este certificado o usar un certificado de CA local.
"""
from __future__ import annotations
import ipaddress
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .runtime import data_directory

def main(argv=None):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    args=list(argv if argv is not None else sys.argv[1:])
    if len(args)!=1:
        raise SystemExit("Uso: python -m omr_web.certificate IP_DE_LA_TABLETA")
    try:
        ip=ipaddress.ip_address(args[0])
    except ValueError as exc:
        raise SystemExit("Escribe una IP válida de la red local.") from exc
    if not ip.is_private and not ip.is_loopback:
        raise SystemExit("Solo se permiten IP privadas o de loopback.")
    base=data_directory()/"omr"/"certs"
    base.mkdir(parents=True,exist_ok=True)
    keyfile=base/"server.key"
    certfile=base/"server.pem"
    if keyfile.exists() or certfile.exists():
        raise SystemExit(
            "El certificado ya existe. No se sobrescribe una clave privada.")
    private_key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    identity=x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME,"OMR Centro de Control PILOTO")])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder()
        .subject_name(identity).issuer_name(identity)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=1))
        .not_valid_after(now+timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([
            x509.IPAddress(ip),
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]),critical=False)
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),
                       critical=True)
        .sign(private_key,hashes.SHA256()))
    private_data=private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    try:
        with keyfile.open("xb") as output:
            os.chmod(keyfile,0o600)
            output.write(private_data)
        certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    except Exception:
        keyfile.unlink(missing_ok=True)
        certfile.unlink(missing_ok=True)
        raise
    print("Certificado de PILOTO:",certfile)
    print("Clave privada SOLO EN EL SERVIDOR:",keyfile)
    print("Validez: 90 días. No publiques ni compartas server.key.")
    print("El navegador de cada capturista debe confiar en el certificado "
          "o usar TLS de una autoridad local confiable.")
if __name__=="__main__":
    main()
