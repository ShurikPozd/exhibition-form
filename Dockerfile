# Анкета выставки: веб-приложение на FastAPI + SQLite.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Зависимости отдельным слоем: правка кода не заставляет переустанавливать пакеты
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Приложение пишет только в data/, поэтому работает не от root
RUN useradd --create-home --uid 10001 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"]

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
