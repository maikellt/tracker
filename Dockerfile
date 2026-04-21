FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Forçar invalidação de cache do COPY
ARG CACHE_BUST=1
RUN echo "Cache bust: $CACHE_BUST"

COPY . .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "main.py"]
