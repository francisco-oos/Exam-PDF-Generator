"""Aplicación local de exámenes OMR: folios, QR, lectura, revisión y resultados.

Módulo original para Exam-PDF-Generator. Los referentes de diseño ScoreForm
 y OMRChecker se estudian sin copiar su código (licencias MIT).
"""
from .motor import OMRStore, create_forms_pdf, scan_document, export_report, read_roster, bubble_positions
__all__ = ['OMRStore','create_forms_pdf','scan_document','export_report','read_roster','bubble_positions']
