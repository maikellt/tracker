#!/bin/bash
# deploy.sh — Deploy direto via download do GitHub (ignora estado do git local)
set -e

REPO="maikellt/tracker"
BRANCH="main"
WORK_DIR="/usr/local/src/tracker/tracker"
BASE_URL="http://localhost:8086"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"

echo "=================================================="
echo " CashbackTracker — Deploy Fase 3 (via download)"
echo "=================================================="
echo ""

cd "$WORK_DIR"

echo "[1/6] Baixando arquivos diretamente do GitHub..."
for arquivo in main.py scraper.py database.py agendador.py requirements.txt Dockerfile docker-compose.yml .gitignore .dockerignore test_fase1.sh test_fase2.sh test_fase3.sh; do
    curl -fsSL "${RAW}/${arquivo}" -o "${arquivo}" && echo "  ✓ ${arquivo}" || echo "  ✗ falhou: ${arquivo}"
done

echo ""
echo "[2/6] SHA do main.py baixado (primeiros 80 chars):"
head -c 80 main.py
echo ""
echo "Linhas no main.py: $(wc -l < main.py)"

echo ""
echo "[3/6] Verificando rotas no main.py baixado:"
grep -n '@app.get\|@app.post\|@app.put\|@app.delete' main.py | head -20

echo ""
echo "[4/6] Parando e removendo container..."
docker-compose down
docker rmi tracker:latest 2>/dev/null || true

echo ""
echo "[5/6] Build da imagem (sem cache, sem imagem anterior)..."
docker build --no-cache --progress=plain -t tracker:latest . 2>&1 | tail -5

echo ""
echo "[6/6] Subindo container..."
docker-compose up -d
echo "Aguardando startup (25s)..."
sleep 25

echo ""
echo "=== Verificação de rotas ==="
for rota in "/" "/static/app.js" "/static/index.html" "/health" "/sites" "/config"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8086${rota}")
    [ "$code" = "200" ] && echo "  ✓ ${rota} → HTTP ${code}" || echo "  ✗ ${rota} → HTTP ${code} ← FALHOU"
done

echo ""
echo "=== Log de startup ==="
docker logs tracker 2>&1 | grep -E "STARTUP|Rotas|started|Uvicorn" | tail -5

echo ""
echo "=== Linha uvicorn.run no main.py em uso ==="
docker exec tracker grep -n "uvicorn.run" /app/main.py

echo ""
echo "=== Rotas registradas no processo ==="
docker exec tracker python3 -c "
from main import app
print([r.path for r in app.routes if hasattr(r, 'path')])
" 2>&1

echo ""
echo "Acesso: http://$(hostname -I | awk '{print \$1}'):8086"
