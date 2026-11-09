"""Renderizado de la vista AMPLIADA desde los PDF reales, totalmente en memoria.

El diseñador y la impresora comparten las funciones de ReportLab; cambiar tamaño,
fuente o formato actualiza el número verdadero de páginas. No se crean archivos
transitorios ni se guardan claves en carpetas públicas.
"""
from __future__ import annotations

from io import BytesIO
from PIL import Image

from src.evaluaciones.core import (
    _answer_sheet, _exam_pdf, _font, paper_dimensions,
)
from vista_previa import PreviewData


def render_document_preview(data: PreviewData, view: str = 'Cuadernillo',
                            page: int = 0, width: int = 950) -> tuple[Image.Image, int]:
    """Regresa una página exacta y el total; nunca dibuja claves sobre el cuadernillo."""
    import pypdfium2 as pdfium  # PDFium: dependencia de licencia permisiva.
    from reportlab.lib import colors

    if view not in ('Cuadernillo', 'Respuestas', 'Acetato'):
        raise ValueError('Vista PDF no válida.')
    if not data.questions:
        raise ValueError('Selecciona un archivo con preguntas válidas para la vista exacta.')
    if not isinstance(page,int) or page < 0:
        raise ValueError('Número de página inválido.')
    width = max(300, min(int(width), 2200))
    buffer = BytesIO()
    normal,bold = _font()
    size=paper_dimensions(data.tamano_papel)
    if view == 'Cuadernillo':
        _exam_pdf(buffer, list(data.questions), data.titulo or 'Evaluación', data.subtitulo,
                  normal,bold,empresa=data.empresa,puesto=data.grupo,
                  instrucciones=data.instrucciones,logo=data.logo,
                  color_titulo=colors.HexColor(data.color_titulo),
                  color_subtitulo=colors.HexColor(data.color_subtitulo),
                  size=size,font_size=data.letra,reusable=data.reutilizable)
    else:
        _answer_sheet(buffer,list(data.questions),data.titulo or 'Evaluación',data.subtitulo,
                      acetate=view == 'Acetato',normal=normal,bold=bold,
                      title_color=colors.HexColor(data.color_titulo),
                      subtitle_color=colors.HexColor(data.color_subtitulo),
                      answer_color=colors.HexColor(data.color_respuestas),size=size,
                      acetate_color=colors.HexColor(data.color_acetato))
    doc = pdfium.PdfDocument(buffer.getvalue())
    try:
        pages = len(doc)
        page = min(page,pages-1)
        pdf_page = doc[page]
        try:
            page_w, _page_h = pdf_page.get_size()
            bitmap = pdf_page.render(scale=width/page_w)
            try:
                image = bitmap.to_pil().convert('RGB')
            finally:
                bitmap.close()
        finally:
            pdf_page.close()
    finally:
        doc.close()
    return image,pages
