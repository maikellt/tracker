#!/bin/bash
# deploy.sh — Rebuild usando Dockerfile com main.py embutido em base64
set -e

WORK_DIR="/usr/local/src/tracker/tracker"
RAW="https://raw.githubusercontent.com/maikellt/tracker/main"

echo "=================================================="
echo " CashbackTracker — Deploy Fase 3"
echo "=================================================="

cd "$WORK_DIR"

echo ""
echo "[1/4] Baixando Dockerfile atualizado do GitHub..."
curl -fsSL "${RAW}/Dockerfile" -o Dockerfile
echo "  ✓ Dockerfile: $(wc -l < Dockerfile) linhas"

echo ""
echo "[2/4] Parando container e removendo imagem antiga..."
docker-compose down
docker rmi tracker:latest 2>/dev/null && echo "  ✓ Imagem antiga removida" || echo "  (sem imagem anterior)"

echo ""
echo "[3/4] Build (main.py embutido no Dockerfile via base64)..."
docker build --no-cache -t tracker:latest .

echo ""
echo "[4/4] Subindo container..."
docker-compose up -d
echo "Aguardando startup (20s)..."
sleep 20

echo ""
echo "=== Verificando main.py dentro do container ==="
echo -n "Linhas: "
docker exec tracker wc -l /app/main.py
echo "Rotas:"
docker exec tracker grep "@app\.get\|@app\.post\|@app\.put\|@app\.delete" /app/main.py

echo ""
echo "=== Testando endpoints ==="
for rota in "/" "/static/app.js" "/static/index.html" "/health" "/sites" "/config"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8086${rota}")
    [ "$code" = "200" ] && echo "  ✓ ${rota} → ${code}" || echo "  ✗ ${rota} → ${code} ← FALHOU"
done

echo ""
docker logs tracker 2>&1 | grep -E "STARTUP|Rotas registradas|startup complete" | tail -3
echo ""
echo "Dashboard: http://$(hostname -I | awk '{print $1}'):8086"
