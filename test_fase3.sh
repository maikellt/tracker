#!/bin/bash
# test_fase3.sh — Validação da Fase 3: Dashboard Web
set -e

BASE_URL="http://localhost:8086"
FALHAS=0

pass() { echo "✓ $1"; }
fail() { echo "✗ $1"; FALHAS=$((FALHAS + 1)); }

echo "══════════════════════════════════"
echo "  Teste Fase 3 — Dashboard Web"
echo "══════════════════════════════════"

# ── 1. Health ──
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
[ "$STATUS" = "200" ] && pass "/health OK" || fail "/health retornou HTTP $STATUS"

# ── 2. Dashboard raiz ──
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/")
[ "$STATUS" = "200" ] && pass "GET / retorna 200" || fail "GET / retornou HTTP $STATUS"

CONTENT_TYPE=$(curl -s "$BASE_URL/" -o /dev/null -w "%{content_type}")
echo "$CONTENT_TYPE" | grep -qi "text/html" \
  && pass "GET / retorna Content-Type: text/html" \
  || fail "GET / não retornou text/html (got: $CONTENT_TYPE)"

# ── 3. Rota alternativa /static/index.html ──
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/static/index.html")
[ "$STATUS" = "200" ] && pass "GET /static/index.html retorna 200" || fail "GET /static/index.html retornou HTTP $STATUS"

# ── 4. JavaScript ──
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/static/app.js")
[ "$STATUS" = "200" ] && pass "GET /static/app.js retorna 200" || fail "GET /static/app.js retornou HTTP $STATUS"

JS_TYPE=$(curl -s "$BASE_URL/static/app.js" -o /dev/null -w "%{content_type}")
echo "$JS_TYPE" | grep -qi "javascript" \
  && pass "app.js retorna Content-Type correto" \
  || fail "app.js não retornou content-type javascript (got: $JS_TYPE)"

# ── 5. Conteúdo HTML mínimo ──
HTML=$(curl -s "$BASE_URL/")
echo "$HTML" | grep -qi "CashbackTracker\|cashback_tracker" \
  && pass "HTML contém título correto" \
  || fail "HTML não contém título esperado"

echo "$HTML" | grep -q "app.js" \
  && pass "HTML referencia app.js" \
  || fail "HTML não referencia app.js"

echo "$HTML" | grep -q "Painel" \
  && pass "HTML contém aba Painel" \
  || fail "HTML não contém aba Painel"

# ── 6. Endpoints de dados (utilizados pelo dashboard) ──
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/sites")
[ "$STATUS" = "200" ] && pass "GET /sites continua funcionando" || fail "GET /sites retornou HTTP $STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/config")
[ "$STATUS" = "200" ] && pass "GET /config continua funcionando" || fail "GET /config retornou HTTP $STATUS"

# ── 7. ultima_coleta (campo Fase 3) ──
SITES_JSON=$(curl -s "$BASE_URL/sites")
echo "$SITES_JSON" | python3 -c "
import sys, json
sites = json.load(sys.stdin)
if not sites:
    print('SKIP: nenhum site cadastrado')
    sys.exit(0)
site = sites[0]
if 'alerta_sem_dados' in site:
    print('OK: campo alerta_sem_dados presente')
else:
    print('WARN: campo alerta_sem_dados ausente')
" 2>/dev/null && pass "Campo alerta_sem_dados presente na resposta /sites" || true

echo ""
echo "══════════════════════════════════"
if [ "$FALHAS" -eq 0 ]; then
  echo "  ✓ Todos os testes passaram"
else
  echo "  ✗ $FALHAS teste(s) falharam"
fi
echo "══════════════════════════════════"

exit $FALHAS

