FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copiar só o requirements primeiro (cache de pip)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baixar código-fonte diretamente do GitHub (ignora estado do git local)
ARG CACHE_BUST=1
RUN echo "Build: $CACHE_BUST" && \
    curl -fsSL "https://raw.githubusercontent.com/maikellt/tracker/main/main.py"           -o /app/main.py      && \
    curl -fsSL "https://raw.githubusercontent.com/maikellt/tracker/main/scraper.py"        -o /app/scraper.py   && \
    curl -fsSL "https://raw.githubusercontent.com/maikellt/tracker/main/database.py"       -o /app/database.py  && \
    curl -fsSL "https://raw.githubusercontent.com/maikellt/tracker/main/agendador.py"      -o /app/agendador.py && \
    echo "Linhas main.py: $(wc -l < /app/main.py)" && \
    echo "Rotas:" && grep "@app\.get\|@app\.post\|@app\.put\|@app\.delete" /app/main.py

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "main.py"]
