# Skriptorij V8 Turbo — Dockerfile
# Multi-stage build za produkciju

FROM python:3.11-slim AS base

# Sistemske zavisnosti
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instaliraj Python zavisnosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiraj kod aplikacije
COPY . .

# Kreiraj data direktorij
RUN mkdir -p data

# Port na kom Flask sluša
EXPOSE 8080

# Varijabla okoline za konfiguraciju
ENV SKRIPTORIJ_PORT=8080
ENV PYTHONUNBUFFERED=1

# Pokretanje aplikacije
CMD ["python", "main.py"]
