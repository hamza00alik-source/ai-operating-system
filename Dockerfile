FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Railway mounts persistent volumes after image creation. Fix ownership at
# container startup (not image build time), then run the application unprivileged.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data /app \
    && chown -R 10001:10001 /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=10001:10001 . .

ENV OPENCOMPANY_DATABASE_PATH=/data/opencompany_core.sqlite3

EXPOSE 8000

# The volume mount is root-owned on some hosts. Correct its ownership before
# dropping privileges; SQLite and the API never run as root.
USER root
CMD ["/bin/sh", "-c", "mkdir -p /data && chown -R 10001:10001 /data && exec gosu 10001:10001 python main.py"]
