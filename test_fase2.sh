#!/bin/bash
BASE_URL="http://localhost:8086"
CONTAINER="tracker"

echo "=== Teste Fase 2 ==="

# 1. GET /sites
echo ""
echo "--- GET /sites ---"
RESPOSTA=$(curl -s $BASE_URL/sites)
echo "$RESPOSTA" | python3 -m json.tool && echo "✓ GET /sites OK" || echo "✗ GET /sites falhou"

# 2. POST /sites — URL já existente (deve retornar 409 ou 200 se inativo)
echo ""
echo "--- POST /sites (URL existente) ---"
curl -s -X POST $BASE_URL/sites \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.comparemania.com.br/cashback-drogaria-sao-paulo","nome":"Drogaria SP","categoria":"Farmácia"}' \
  | python3 -m json.tool

# 3. GET /sites/1/parceiros
echo ""
echo "--- GET /sites/1/parceiros ---"
curl -s "$BASE_URL/sites/1/parceiros" | python3 -m json.tool && echo "✓ GET /parceiros OK" || echo "✗ GET /parceiros falhou"

# 4. GET /sites/1/snapshots
echo ""
echo "--- GET /sites/1/snapshots?dias=7 ---"
curl -s "$BASE_URL/sites/1/snapshots?dias=7" | python3 -m json.tool && echo "✓ GET /snapshots OK" || echo "✗ GET /snapshots falhou"

# 5. GET /sites/1/max
echo ""
echo "--- GET /sites/1/max?dias=30 ---"
curl -s "$BASE_URL/sites/1/max?dias=30" | python3 -m json.tool && echo "✓ GET /max OK" || echo "✗ GET /max falhou"

# 6. GET /config
echo ""
echo "--- GET /config ---"
curl -s $BASE_URL/config | python3 -m json.tool && echo "✓ GET /config OK" || echo "✗ GET /config falhou"

# 7. PUT /config
echo ""
echo "--- PUT /config ---"
curl -s -X PUT $BASE_URL/config \
  -H "Content-Type: application/json" \
  -d '{"scrape_time":"07:00","scrape_interval_hours":12}' \
  | python3 -m json.tool && echo "✓ PUT /config OK" || echo "✗ PUT /config falhou"

# 8. Verificar config atualizada
echo ""
echo "--- GET /config (após PUT) ---"
curl -s $BASE_URL/config | python3 -m json.tool

# 9. Restaurar config original
curl -s -X PUT $BASE_URL/config \
  -H "Content-Type: application/json" \
  -d '{"scrape_time":"06:00","scrape_interval_hours":24}' > /dev/null
echo "✓ Config restaurada para 06:00 / 24h"

# 10. Snapshots no banco
echo ""
COUNT=$(docker exec $CONTAINER python3 -c "
import sqlite3; conn = sqlite3.connect('/app/data/tracker.db')
c = conn.cursor(); c.execute('SELECT COUNT(*) FROM snapshots'); print(c.fetchone()[0])
")
echo "✓ Total de snapshots no banco: $COUNT"

echo ""
echo "=== Fim ==="
