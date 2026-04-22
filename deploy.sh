#!/bin/bash
# deploy.sh — Sincronização forçada e rebuild completo do CashbackTracker
set -e

REPO_DIR="/usr/local/src/tracker/tracker"
CONTAINER="tracker"
BASE_URL="http://localhost:8086"
ESPERADO_SHA=$(git -C "$REPO_DIR" ls-remote origin HEAD 2>/dev/null | cut -f1 | head -c 8)

echo "=================================================="
echo " CashbackTracker — Deploy Fase 3"
echo "=================================================="
echo ""

cd "$REPO_DIR"

# 1. Verificar estado atual
echo "[1/6] Estado atual do repositório local:"
git log --oneline -3

echo ""
echo "[2/6] Sincronizando com GitHub (reset forçado)..."
git fetch origin
git reset --hard origin/main
git clean -fd
echo "✓ Código sincronizado. SHA atual: $(git rev-parse --short HEAD)"

echo ""
echo "[3/6] Parando container atual..."
docker-compose down || true

echo ""
echo "[4/6] Construindo imagem (sem cache)..."
docker build --no-cache --progress=plain -t tracker:latest . 2>&1 | grep -E "Step|COPY|transferring|Successfully|ERROR"

echo ""
echo "[5/6] Subindo container..."
docker-compose up -d
echo "Aguardando startup (20s)..."
sleep 20

echo ""
echo "[6/6] Validando rotas..."
check() {
    local rota=$1
    local code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$rota")
    if [ "$code" = "200" ]; then
        echo "  ✓ $rota → HTTP $code"
    else
        echo "  ✗ $rota → HTTP $code  ← FALHOU"
    fi
}

check "/"
check "/static/app.js"
check "/static/index.html"
check "/health"
check "/sites"
check "/config"

echo ""
echo "Últimas linhas do log (procurando [STARTUP]):"
docker logs $CONTAINER --tail 15 2>&1 | grep -E "STARTUP|Rotas|ERROR|error|rotas" || docker logs $CONTAINER --tail 10

echo ""
echo "=================================================="
echo " Acesso: http://$(hostname -I | awk '{print $1}'):8086"
echo "=================================================="
