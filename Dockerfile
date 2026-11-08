FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY main.py ./
COPY src ./src
COPY agents ./agents
COPY company ./company
COPY vendor/agency-agents ./vendor/agency-agents
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN pip install --no-cache-dir ".[mcp]" \
    && useradd --create-home --uid 10001 aios \
    && mkdir -p /data \
    && chown -R aios:aios /app /data \
    && chmod 0755 /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
