FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd -m -u 10001 exam
COPY src ./src
COPY generar.py ./generar.py
USER exam
ENTRYPOINT ["python", "generar.py"]
