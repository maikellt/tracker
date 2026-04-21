FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

# Gerar arquivos estáticos (embutidos em setup_static.py)
RUN python setup_static.py && rm setup_static.py

EXPOSE 8000

CMD ["python", "main.py"]
