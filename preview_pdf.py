"""Renderizado de la vista AMPLIADA desde los PDF reales, totalmente en memoria.

El diseñador y la impresora comparten las funciones de ReportLab; cambiar tamaño,
fuente o formato actualiza el número verdadero de páginas. No se crean archivos
transitorios ni se guardan claves en carpetas públicas.
"""
from __future__ import annotations

from io import BytesIO
from PIL import Image

from src.evaluaciones.core import (
    _exam_pdf, _font, paper_dimensions,
)
from vista_previa import PreviewData


def build_preview_pdf(data: PreviewData, view: str) -> bytes:
    """Genera el documento completo en memoria con el mismo motor de exportación."""
    from reportlab.lib import colors
    if view not in ('Cuadernillo', 'Respuestas', 'Acetato'):
        raise ValueError('Vista PDF no válida.')
    if not data.questions:
        raise ValueError('Selecciona un archivo con preguntas válidas para la vista exacta.')
    # UNA SOLA hoja: la geometría OMR es idéntica con o sin lista.
    # La presencia de personal solo añade nombre, folio y un QR de muestra.
    if view != 'Cuadernillo':
        from omr_evaluaciones.motor import (
            preview_formulario_omr, preview_acetato_omr,
        )
        qs=[{'tema':q.section,'pregunta':q.prompt,
             'correcta':'ABCD'[q.correct]} for q in data.questions]
        if view == 'Respuestas':
            return preview_formulario_omr(
                qs,data.titulo or 'Evaluación',data.tamano_papel,
                empresa=data.empresa,grupo=data.grupo,subtitulo=data.subtitulo,
                color_titulo=data.color_titulo,color_respuestas=data.color_respuestas,
                nombre=data.participante_nombre or 'Participante de ejemplo',
                identifier=data.participante_id or '000001',
                con_personal=data.cantidad_personas > 0,
            )
        return preview_acetato_omr(
            qs,data.tamano_papel,color=data.color_acetato,
        )
    buffer = BytesIO()
    normal,bold = _font()
    size=paper_dimensions(data.tamano_papel)
    if view == 'Cuadernillo':
        _exam_pdf(buffer, list(data.questions), data.titulo or 'Evaluación', data.subtitulo,
                  normal,bold,empresa=data.empresa,puesto=data.grupo,
                  instrucciones=data.instrucciones,logo=data.logo,
                  color_titulo=colors.HexColor(data.color_titulo),
                  color_subtitulo=colors.HexColor(data.color_subtitulo),
                  size=size,font_size=data.letra,reusable=data.reutilizable,
                  participante=({'id':data.participante_id,
                                 'nombre':data.participante_nombre,
                                 'grupo':data.grupo}
                                if data.modo_examen=='normal' and data.cantidad_personas
                                else None))
    return buffer.getvalue()


def render_pdf_bytes(content: bytes, page: int = 0, width: int = 950) -> tuple[Image.Image, int]:
    """Rasteriza una página y libera todos los objetos nativos de PDFium."""
    import pypdfium2 as pdfium
    if not isinstance(page, int) or page < 0:
        raise ValueError('Número de página inválido.')
    width = max(300, min(int(width), 2200))
    doc = pdfium.PdfDocument(content)
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


def render_document_preview(data: PreviewData, view: str = 'Cuadernillo',
                            page: int = 0, width: int = 950) -> tuple[Image.Image, int]:
    """Regresa la página solicitada y el total sin guardar documentos en disco."""
    return render_pdf_bytes(build_preview_pdf(data, view), page, width)
