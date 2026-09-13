FROM python:3.13-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY app/ ./app/
RUN pip install --no-cache-dir --prefix=/install .


FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
	PYTHONDONTWRITEBYTECODE=1

RUN adduser --disabled-password --no-create-home appuser

COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini ./

EXPOSE 8000

USER appuser

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
