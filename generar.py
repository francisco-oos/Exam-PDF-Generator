"""CLI local para automatizar la generación en Windows, Linux y Docker."""
import argparse
import sys
from pathlib import Path
from src.evaluaciones.core import ExamError, generate


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generador empresarial de exámenes impresos')
    parser.add_argument('--entrada', type=Path, required=True, help='Excel XLSX de preguntas')
    parser.add_argument('--salida', type=Path, default=Path(__file__).resolve().parent / 'salidas')
    parser.add_argument('--titulo', default='Evaluación de conocimientos')
    parser.add_argument('--subtitulo', default='Opción múltiple')
    parser.add_argument('--empresa', default='', help='Encabezado institucional')
    parser.add_argument('--puesto', default='', help='Función o área evaluada')
    parser.add_argument('--instrucciones', default='', help='Instrucciones impresas al participante')
    parser.add_argument('--logo', type=Path, help='Archivo PNG/JPEG local (opcional)')
    parser.add_argument('--tamano-papel', choices=('Carta','A4','Oficio'), default='A4',
                        help='Oficio mexicano: 8.5 x 13 pulgadas')
    parser.add_argument('--letra', type=float, default=9.0,
                        help='Tamaño de respuesta entre 8 y 12 puntos, saltos 0.5')
    parser.add_argument('--reutilizable', action='store_true',
                        help='Quitar datos personales del cuadernillo e imprimir marca de agua')
    parser.add_argument('--color-respuestas', default='#213A4C',
                        help='Color hexadecimal de encabezados y círculos de la hoja')
    parser.add_argument('--color-titulo', default='#213A4C')
    parser.add_argument('--color-subtitulo', default='#5E7180')
    args = parser.parse_args(argv)
    try:
        directory = generate(args.entrada, args.salida, args.titulo, args.subtitulo,
                             empresa=args.empresa,puesto=args.puesto,
                             instrucciones=args.instrucciones,logo=args.logo,
                             tamano_papel=args.tamano_papel,letra=args.letra,
                             reutilizable=args.reutilizable,color_respuestas=args.color_respuestas,
                             color_titulo=args.color_titulo,color_subtitulo=args.color_subtitulo)
    except (ExamError,OSError,ValueError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr)
        return 2
    print('Generados correctamente:')
    for p in sorted(directory.rglob('*')):
        if p.is_file():print(p)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
