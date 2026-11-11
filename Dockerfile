FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Mount a persistent Railway volume at /data for SQLite state.
RUN mkdir -p /data && chown -R 10001:10001 /data /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=10001:10001 . .

ENV OPENCOMPANY_DATABASE_PATH=/data/opencompany_core.sqlite3
USER 10001:10001

EXPOSE 8000
CMD ["python", "main.py"]
