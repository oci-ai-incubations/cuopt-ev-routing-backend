FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
# Alembic migrations + config — needed at runtime; init_db() runs
# `alembic upgrade head` from WORKDIR (/app) on FastAPI startup.
COPY alembic.ini ./
COPY alembic/ alembic/

RUN pip install --no-cache-dir --no-deps .

RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 appuser && \
    chown -R appuser:appgroup /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

CMD ["uvicorn", "cuopt_ev_routing_backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
