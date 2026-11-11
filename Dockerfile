FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Mount a persistent Railway volume at /data for production SQLite state.
RUN mkdir -p /data
ENV OPENCOMPANY_DATABASE_PATH=/data/opencompany_core.sqlite3

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "main.py"]
