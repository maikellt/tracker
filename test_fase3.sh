#!/bin/bash
BASE_URL="http://localhost:8086"
echo "=== Teste Fase 3 ==="

STATUS=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/health)
[ "$STATUS" = "200" ] && echo "✓ /health OK" || echo "✗ /health falhou (HTTP $STATUS)"

DASH=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/)
[ "$DASH" = "200" ] && echo "✓ / (dashboard) OK" || echo "✗ / falhou (HTTP $DASH)"

JS=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/static/app.js)
[ "$JS" = "200" ] && echo "✓ /static/app.js OK" || echo "✗ /static/app.js falhou (HTTP $JS)"

HTML=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/static/index.html)
[ "$HTML" = "200" ] && echo "✓ /static/index.html OK" || echo "✗ /static/index.html falhou (HTTP $HTML)"

SITES=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/sites)
[ "$SITES" = "200" ] && echo "✓ GET /sites OK" || echo "✗ GET /sites falhou (HTTP $SITES)"

CONFIG=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/config)
[ "$CONFIG" = "200" ] && echo "✓ GET /config OK" || echo "✗ GET /config falhou (HTTP $CONFIG)"

RESP=$(curl -s $BASE_URL/sites)
ULTIMA=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d and 'ultima_coleta' in d[0] else 'faltando')" 2>/dev/null)
[ "$ULTIMA" = "ok" ] && echo "✓ Campo ultima_coleta presente em /sites" || echo "⚠ Campo ultima_coleta ausente (banco pode estar desatualizado)"

# Verificar logs de erro
echo ""
echo "--- Ultimas linhas do log ---"
docker logs tracker --tail 5 2>/dev/null || echo "(docker logs nao disponivel aqui)"

echo "=== Fim ==="
echo "Dashboard: http://localhost:8086"
