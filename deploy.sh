#!/bin/bash
# deploy.sh — Rebuild garantido usando código do GitHub
set -e

WORK_DIR="/usr/local/src/tracker/tracker"
RAW="https://raw.githubusercontent.com/maikellt/tracker/main"

echo "=================================================="
echo " CashbackTracker — Deploy Fase 3"
echo "=================================================="

cd "$WORK_DIR"

echo ""
echo "[1/4] Atualizando Dockerfile e requirements via curl..."
curl -fsSL "${RAW}/Dockerfile"       -o Dockerfile
curl -fsSL "${RAW}/requirements.txt" -o requirements.txt
echo "  ✓ Dockerfile e requirements atualizados"

echo ""
echo "[2/4] Parando container e removendo imagem antiga..."
docker-compose down
docker rmi tracker:latest 2>/dev/null && echo "  ✓ Imagem antiga removida" || echo "  (sem imagem anterior)"

echo ""
echo "[3/4] Build (o Dockerfile baixa o código do GitHub automaticamente)..."
docker build --no-cache --build-arg CACHE_BUST=$(date +%s) -t tracker:latest .

echo ""
echo "[4/4] Subindo container..."
docker-compose up -d
echo "Aguardando startup (25s)..."
sleep 25

echo ""
echo "=== Verificando o que está dentro do container ==="
echo "Linhas no /app/main.py:"
docker exec tracker wc -l /app/main.py

echo "Rotas registradas:"
docker exec tracker grep -n "@app\.get\|@app\.post\|@app\.put\|@app\.delete" /app/main.py

echo ""
echo "=== Testando endpoints ==="
for rota in "/" "/static/app.js" "/static/index.html" "/health" "/sites" "/config"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8086${rota}")
    [ "$code" = "200" ] && echo "  ✓ ${rota} → ${code}" || echo "  ✗ ${rota} → ${code} ← FALHOU"
done

echo ""
echo "=== Log de startup ==="
docker logs tracker 2>&1 | grep -E "STARTUP|Rotas|Application startup" | tail -5

echo ""
echo "Acesso: http://$(hostname -I | awk '{print $1}'):8086"
