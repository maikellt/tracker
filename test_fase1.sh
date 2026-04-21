#!/bin/bash
set -e
BASE_URL="http://localhost:8086"

echo "=== Teste Fase 1 ==="

STATUS=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/health)
[ "$STATUS" = "200" ] && echo "✓ /health OK" || echo "✗ /health falhou (HTTP $STATUS)"

[ -f "/data/tracker/tracker.db" ] && echo "✓ Banco criado" || echo "✗ Banco não encontrado"

COUNT=$(sqlite3 /data/tracker/tracker.db "SELECT COUNT(*) FROM snapshots;" 2>/dev/null || echo 0)
[ "$COUNT" -gt "0" ] && echo "✓ $COUNT snapshots no banco" || echo "⚠ Nenhum snapshot (checar erros_scraping)"

ERROS=$(sqlite3 /data/tracker/tracker.db "SELECT COUNT(*) FROM erros_scraping;" 2>/dev/null || echo 0)
[ "$ERROS" -gt "0" ] && echo "⚠ $ERROS erros registrados em erros_scraping" || echo "✓ Sem erros de scraping"

echo "=== Fim ==="
