"""Punto de entrada del sistema completo de evaluaciones.

Se mantiene este comando por compatibilidad, pero ahora abre el generador
integrado. La vista aislada de calificación solo se abre si se solicita
explícitamente --solo-calificar, útil para pruebas técnicas.
"""
from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    """Permite regresar siempre al diseñador, impresión y biblioteca completos."""
    parser = argparse.ArgumentParser(description="Generador de exámenes y calificación OMR")
    parser.add_argument(
        "--solo-calificar", action="store_true",
        help="abre únicamente la vista de lectura OMR (modo técnico)",
    )
    options = parser.parse_args(argv)
    if options.solo_calificar:
        from omr_evaluaciones.interfaz import launch
        launch()
    else:
        from iniciar import main as start_generator
        start_generator()


if __name__ == "__main__":
    main()
