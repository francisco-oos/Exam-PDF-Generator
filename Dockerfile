# La aplicación funciona dentro del contenedor, sin Python en el anfitrión.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EXAM_DATA_DIR=/datos \
    EXAM_PORT=8765

WORKDIR /app
# Fuentes del sistema para acentos españoles en PDF.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home --shell /usr/sbin/nologin exam
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY generar.py crear_ejemplo.py web_app.py biblioteca.py ./
COPY plantillas ./plantillas
# Genera una plantilla ficticia dentro de la imagen; nunca usa datos personales.
RUN python crear_ejemplo.py \
    && mkdir -p /datos/entradas /datos/salidas \
    && chown -R exam:exam /datos /app

USER exam
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:8765/salud', timeout=2).status == 200" || exit 1
CMD ["python", "web_app.py"]
