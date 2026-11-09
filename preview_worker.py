"""Proceso privado y cancelable de vista PDF; nunca recibe objetos Tkinter.

Cada editor mantiene como máximo una solicitud en curso. La interfaz retiene
solo el último cambio pendiente y descarta respuestas de revisiones obsoletas.
El proceso no escribe documentos ni comparte claves por red.
"""
from multiprocessing import get_context


def _render_loop(channel):
    """Transforma datos inmutables en píxeles; los errores vuelven a la interfaz."""
    from preview_pdf import build_preview_pdf, render_pdf_bytes
    cached_key = None
    content = None
    channel.send(None)  # Confirma que el proceso ya está listo para recibir.
    while True:
        revision, data, view, page, width = channel.recv()
        try:
            paths = [q.image for q in data.questions if q.image] + ([data.logo] if data.logo else [])
            resources = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
            key = (data, view, resources)
            if key != cached_key:
                content = build_preview_pdf(data, view)
                cached_key = key
            image, pages = render_pdf_bytes(content, page, width)
            channel.send((revision, image, pages, None))
        except Exception as exc:
            channel.send((revision, None, 0, str(exc)))


class PreviewWorker:
    """Aísla PDFium y permite cancelar sin esperar a una operación nativa."""

    def __init__(self):
        context = get_context('spawn')
        self.channel, child = context.Pipe()
        self.process = context.Process(target=_render_loop,
                                       args=(child,), daemon=True)
        self.process.start()
        child.close()
        self.busy = True
        self.closed = False

    def submit(self, revision, data, view, page, width):
        """Envía una instantánea; el llamador espera poll antes de otra entrega."""
        if self.closed or self.busy:
            raise RuntimeError('El renderizador no está disponible.')
        self.channel.send((revision, data, view, page, width))
        self.busy = True

    def poll(self):
        """Consulta sin bloquear y detecta terminaciones inesperadas de PDFium."""
        if not self.channel.poll():
            if not self.closed and not self.process.is_alive():
                raise RuntimeError('El proceso de vista PDF terminó. Cierra y reabre el editor.')
            return None
        try:
            result = self.channel.recv()
        except EOFError as exc:
            raise RuntimeError('El proceso de vista PDF terminó inesperadamente.') from exc
        self.busy = False
        return result

    def close(self):
        """Cancela el proceso aislado; no espera al render ni toca archivos."""
        if self.closed:
            return
        self.closed = True
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=.2)
        self.channel.close()
