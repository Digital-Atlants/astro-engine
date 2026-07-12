FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY astro_engine ./astro_engine

EXPOSE 8000

CMD ["sh", "-c", "uvicorn astro_engine.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
