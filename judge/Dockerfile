FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ gcc libpq-dev docker.io && \
    rm -rf /var/lib/apt/lists/*

COPY judge/requirements.txt /app/judge/requirements.txt
RUN pip install --no-cache-dir -r /app/judge/requirements.txt

COPY judge /app/judge
COPY backend /app/backend
COPY database /app/database

CMD ["python", "-m", "judge.worker.worker"]
