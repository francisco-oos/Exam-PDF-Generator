"""Proceso privado y cancelable de vista PDF; nunca recibe objetos Tkinter.

Cada editor mantiene como máximo una solicitud en curso. La interfaz retiene
solo el último cambio pendiente y descarta respuestas de revisiones obsoletas.
El proceso no escribe documentos ni comparte claves por red.
"""
from multiprocessing import get_context
from queue import Empty


def _render_loop(requests, results):
    """Transforma datos inmutables en píxeles; los errores vuelven a la interfaz."""
    from preview_pdf import build_preview_pdf, render_pdf_bytes
    cached_key = None
    content = None
    while True:
        revision, data, view, page, width = requests.get()
        try:
            paths = [q.image for q in data.questions if q.image] + ([data.logo] if data.logo else [])
            resources = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
            key = (data, view, resources)
            if key != cached_key:
                content = build_preview_pdf(data, view)
                cached_key = key
            image, pages = render_pdf_bytes(content, page, width)
            results.put((revision, image, pages, None))
        except Exception as exc:
            results.put((revision, None, 0, str(exc)))


class PreviewWorker:
    """Aísla PDFium y permite cancelar sin esperar a una operación nativa."""

    def __init__(self):
        context = get_context('spawn')
        self.requests = context.Queue(maxsize=1)
        self.results = context.Queue(maxsize=1)
        self.process = context.Process(target=_render_loop,
                                       args=(self.requests, self.results), daemon=True)
        self.process.start()
        self.busy = False
        self.closed = False

    def submit(self, revision, data, view, page, width):
        """Envía una instantánea; el llamador espera poll antes de otra entrega."""
        if self.closed or self.busy:
            raise RuntimeError('El renderizador no está disponible.')
        self.requests.put_nowait((revision, data, view, page, width))
        self.busy = True

    def poll(self):
        """Consulta sin bloquear y detecta terminaciones inesperadas de PDFium."""
        try:
            result = self.results.get_nowait()
        except Empty:
            if not self.closed and not self.process.is_alive():
                raise RuntimeError('El proceso de vista PDF terminó. Cierra y reabre el editor.')
            return None
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
        for queue in (self.requests, self.results):
            queue.cancel_join_thread()
            queue.close()
