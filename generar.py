"""CLI local para automatizar la generación en Windows, Linux y Docker."""
import argparse
import sys
from pathlib import Path
from src.evaluaciones.core import ExamError, generate


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generador empresarial de exámenes impresos')
    parser.add_argument('--entrada', type=Path, required=True, help='Excel XLSX de preguntas')
    parser.add_argument('--salida', type=Path, default=Path(__file__).resolve().parent / 'salidas')
    parser.add_argument('--titulo', default='Evaluación de manejo de material')
    parser.add_argument('--subtitulo', default='Opción múltiple')
    parser.add_argument('--empresa', default='', help='Encabezado institucional')
    parser.add_argument('--puesto', default='', help='Función o área evaluada')
    parser.add_argument('--instrucciones', default='', help='Instrucciones impresas al participante')
    parser.add_argument('--logo', type=Path, help='Archivo PNG/JPEG local (opcional)')
    args = parser.parse_args(argv)
    try:
        directory = generate(args.entrada, args.salida, args.titulo, args.subtitulo,
                             empresa=args.empresa,puesto=args.puesto,
                             instrucciones=args.instrucciones,logo=args.logo)
    except (ExamError,OSError,ValueError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr)
        return 2
    print('Generados correctamente:')
    for p in sorted(directory.rglob('*')):
        if p.is_file():print(p)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
