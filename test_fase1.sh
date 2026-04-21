#!/bin/bash
set -e
BASE_URL="http://localhost:8086"
CONTAINER="tracker"

echo "=== Teste Fase 1 ==="

# 1. Health check
STATUS=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/health)
[ "$STATUS" = "200" ] && echo "✓ /health OK" || echo "✗ /health falhou (HTTP $STATUS)"

# 2. Banco criado (verifica dentro do container)
docker exec $CONTAINER python3 -c "import os; exit(0 if os.path.exists('/app/data/tracker.db') else 1)" \
  && echo "✓ Banco criado" || echo "✗ Banco não encontrado"

# 3. Snapshots no banco
COUNT=$(docker exec $CONTAINER python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/tracker.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM snapshots')
print(c.fetchone()[0])
" 2>/dev/null || echo 0)
[ "$COUNT" -gt "0" ] && echo "✓ $COUNT snapshots no banco" || echo "⚠ Nenhum snapshot (checar erros_scraping)"

# 4. Erros de scraping
ERROS=$(docker exec $CONTAINER python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/tracker.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM erros_scraping')
print(c.fetchone()[0])
" 2>/dev/null || echo 0)
[ "$ERROS" -gt "0" ] && echo "⚠ $ERROS erros registrados em erros_scraping" || echo "✓ Sem erros de scraping"

# 5. Detalhe dos snapshots
echo ""
echo "--- Snapshots coletados ---"
docker exec $CONTAINER python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/tracker.db')
c = conn.cursor()
c.execute('SELECT s.nome, sn.parceiro, sn.tipo, sn.percentual, sn.unidade FROM snapshots sn JOIN sites s ON s.id = sn.site_id ORDER BY s.nome, sn.tipo, sn.percentual DESC')
for row in c.fetchall():
    print(f'  {row[0]:15} | {row[1]:15} | {row[2]:15} | {row[3]} {row[4]}')
"

echo ""
echo "=== Fim ==="
