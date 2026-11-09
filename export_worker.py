"""Exportación PDF aislada: no transporta widgets ni ejecuta callbacks de Tk."""
from generacion_integrada import preparar_examen


def export_documents(results, source, output, title, subtitle, options):
    """Devuelve carpeta o error mediante una cola privada del proceso padre."""
    try:
        results.send((preparar_examen(source, output, title, subtitle, **options), None))
    except Exception as exc:
        results.send((None, str(exc)))
