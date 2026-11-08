FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY main.py ./
COPY src ./src
COPY agents ./agents
COPY company ./company
COPY vendor/agency-agents ./vendor/agency-agents

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 aios \
    && mkdir -p /data \
    && chown -R aios:aios /app /data

USER aios

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
