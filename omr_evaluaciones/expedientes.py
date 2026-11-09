"""Expedientes OMR y entregables: PDFs evidenciales, bitácora y hashes.

Nunca mezcla las páginas de otra aplicación en las evidencias exportadas.
El PDF original global puede contener páginas de múltiples evaluaciones;
por privacidad solo se incluye íntegro si TODAS sus páginas pertenecen
a la sesión solicitada. La copia global permanece intacta.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import json
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from .documentos import DocumentInbox, sha_file
from .motor import OMRStore, SID_RE, export_report


def _paragraph_pdf(title, lines):
    """Documento PDF sencillo y legible; no incluye HMAC ni claves correctas."""
    stream=BytesIO()
    document=SimpleDocTemplate(stream,pagesize=A4,
                                leftMargin=42,rightMargin=42,
                                topMargin=44,bottomMargin=44)
    head=ParagraphStyle('title',fontName='Helvetica-Bold',
                         fontSize=14,leading=17,spaceAfter=11)
    normal=ParagraphStyle('line',fontName='Helvetica',
                           fontSize=9,leading=13,spaceAfter=5,
                           wordWrap='CJK')
    story=[Paragraph(escape(str(title)),head),Spacer(1,8)]
    for line in lines:
        text=str(line).replace('\r',' ').replace('\n',' ')
        story.append(Paragraph(escape(text),normal))
    document.build(story)
    return stream.getvalue()


def participant_receipt(store: OMRStore, sid: str, person_id: str,
                        target: Path):
    """Resultado de UNA persona; nunca expone preguntas, claves ni compañeros."""
    report=store.results(sid)
    data=next((p for p in report['participantes']
               if p['id']==str(person_id)),None)
    if not data:
        raise ValueError('El participante no está en esta aplicación.')
    lines=[
        'Evaluación: '+str(report['sesion'].get('nombre_evaluacion')
                           or report['sesion']['titulo']),
        'Aplicación: '+sid,
        'Folio: '+data['folio'],
        'Participante: '+data['nombre'],
        'ID: '+data['id'],
        'Preguntas: '+str(data['preguntas']),
        'Estado: '+data['estado'],
        'Aciertos: '+('Pendiente' if data['aciertos'] is None
                     else str(data['aciertos'])),
        'Calificación: '+('Pendiente' if data['porcentaje'] is None
                          else f'{data["porcentaje"]}%'),
        'Aviso: solo los resultados validados son definitivos.',
    ]
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name(target.name+'.part')
    try:
        temp.write_bytes(_paragraph_pdf('Resultado individual',lines))
        os.replace(temp,target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def _history_pdf(store,sid):
    entries=store.revisions(sid)
    lines=[f'Sesión: {sid}',
           f'Exportación UTC: {datetime.now(timezone.utc).isoformat()}',
           f'Registros de revisión: {len(entries)}']
    for row in entries:
        lines.append(
            f'{row["fecha"]} · Hoja {row["hoja_id"]} · '
            f'Pregunta {row["pregunta"] if row["pregunta"] is not None else "—"} · '
            f'{row["decision"]} · Revisor: {row["revisor"]} · '
            f'Motivo: {row["motivo"]}')
    return _paragraph_pdf('Bitácora interna de correcciones',lines)


def _effective_pages(store: OMRStore, inbox: DocumentInbox, sid: str):
    """Solo una hoja efectiva por folio y aplicación.

    Se conserva la lista ordenada por participante. Los conflictos
    pendientes no se incluyen como resultado definitivo; quedan en
    manifest y bitácora. Una hoja de otro examen jamás entra aquí.
    """
    session=store.session(sid)
    scanned=store.pages(sid)
    selections=[]
    missing=[]
    for person in session['personal']:
        rows=[p for p in scanned
              if p['token']==person['token'] and p['estado']=='validada']
        conflict=any(p['token']==person['token'] and
                     p['estado']=='duplicado' for p in scanned)
        if len(rows)!=1 or conflict:
            missing.append({'folio':person['folio'],'razon':
                            'Sin hoja validada única o con duplicados'})
            continue
        page=rows[0]
        with store.connect() as db:
            record=db.execute("""
                SELECT dp.sha,dp.pagina FROM paginas_documentos_omr dp
                WHERE dp.hoja_id=? AND dp.sesion_id=?
                ORDER BY CASE dp.estado WHEN 'procesada' THEN 0 ELSE 1 END,
                         dp.sha,dp.pagina LIMIT 1
            """,(page['id'],sid)).fetchone()
        if not record:
            missing.append({'folio':person['folio'],
                            'razon':'Escaneo histórico no indexado en bandeja'})
            continue
        selections.append({
            'folio':person['folio'],'nombre':person['nombre'],
            'sha':record['sha'],'pagina':record['pagina'],
            'hoja_id':page['id'],
        })
    return selections,missing


def export_session_bundle(store: OMRStore,inbox: DocumentInbox,sid: str,
                          destination: Path,*,internal=True,
                          include_originals=True):
    """ZIP de resultados y evidencias para la aplicación especificada.

    Modo interno: XLSX con bitácora, PDF de hojas efectivas,
    Bitácora.pdf, manifiesto e, si un PDF contiene SOLO hojas de la
    aplicación, su original intacto. Originales mixtos NO se adjuntan
    para proteger datos personales de otros exámenes.
    Modo oficial: XLSX sin claves ni datos de otras evaluaciones.
    """
    if not SID_RE.fullmatch(sid):
        raise ValueError('Sesión inválida.')
    destination=Path(destination)
    if destination.suffix.lower()!='.zip':
        raise ValueError('El expediente debe exportarse como ZIP.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.resolve().is_relative_to(inbox.originals.resolve()):
        raise ValueError('No escribir expedientes entre los originales.')
    session=store.session(sid)
    if not session['personal']:
        raise ValueError('La sesión no tiene participantes.')
    selections,missing=_effective_pages(store,inbox,sid) if internal else ([],[])
    with TemporaryDirectory(prefix='expediente_omr_') as temp_dir:
        folder=Path(temp_dir)
        content={}
        result_path=folder/('Resultados_Internos.xlsx' if internal else
                            'Resultados_Oficiales.xlsx')
        export_report(store,sid,result_path,internal=internal)
        content[result_path.name]=result_path.read_bytes()
        used_documents=set()
        if internal:
            content['Bitacora.pdf']=_history_pdf(store,sid)
            if selections:
                evidence=folder/'Evidencias_Ordenadas.pdf'
                inbox.assemble(
                    [(p['sha'],p['pagina'],0) for p in selections],evidence)
                content[evidence.name]=evidence.read_bytes()
                used_documents={p['sha'] for p in selections}
            if include_originals:
                # Mezclas de Cabos/Checadores nunca se filtran solo por
                # nombre del PDF: se evalúan TODAS sus páginas indexadas.
                with store.connect() as db:
                    candidates=[r['sha'] for r in db.execute("""
                        SELECT DISTINCT sha FROM paginas_documentos_omr
                        WHERE sesion_id=?
                    """,(sid,))]
                for digest in candidates:
                    pages=inbox.pages(digest)
                    if pages and all(p['sesion_id']==sid for p in pages):
                        content['PDF_originales/'+digest+'.pdf'] = (
                            inbox.original(digest).read_bytes())
                        used_documents.add(digest)
        # Manifest sin claves, tokens ni ruta absoluta del usuario.
        manifest={
            'schema':'omr-expediente-v1',
            'aplicacion':sid,
            'evaluacion':session.get('nombre_evaluacion') or session['titulo'],
            'revision_biblioteca':session.get('revision_biblioteca'),
            'tipo':'interno' if internal else 'oficial',
            'generado_utc':datetime.now(timezone.utc).isoformat(),
            'paginacion_evidencias':selections if internal else [],
            'folios_sin_evidencia_efectiva':missing if internal else [],
            'originales_no_incluidos_por_mezcla':(
                sorted(set(r['sha'] for r in inbox.pages_for_session(sid))
                       -set(k.split('/')[-1][:-4]
                            for k in content if k.startswith('PDF_originales/')))
                if internal else []),
            'archivos_sha256':{
                name:sha256(payload).hexdigest()
                for name,payload in content.items()
            },
        }
        # El manifiesto debe evitar filtrar metadatos de otras evaluaciones.
        content['Manifiesto.json']=json.dumps(
            manifest,ensure_ascii=False,indent=2).encode('utf-8')
        with NamedTemporaryFile(dir=destination.parent,
                                suffix='.part',delete=False) as temp_file:
            staged=Path(temp_file.name)
        try:
            with ZipFile(staged,'w',compression=ZIP_DEFLATED) as archive:
                for name,data in content.items():
                    archive.writestr(name,data)
            os.replace(staged,destination)
        finally:
            staged.unlink(missing_ok=True)
    return destination
