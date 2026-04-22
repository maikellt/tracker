#!/bin/bash
# diagnostico.sh — Verifica o que está realmente rodando no container
echo "=== DIAGNÓSTICO DO CONTAINER ==="
echo ""
echo "1. Linhas no /app/main.py dentro do container:"
docker exec tracker wc -l /app/main.py

echo ""
echo "2. Rotas @app registradas dentro do container:"
docker exec tracker grep -c "@app\.get\|@app\.post\|@app\.put\|@app\.delete" /app/main.py || echo "0"

echo ""
echo "3. Rota / existe no main.py do container?"
docker exec tracker grep -n 'app.get.*"/"' /app/main.py || echo "NÃO ENCONTRADO"

echo ""
echo "4. Últimas 10 linhas do /app/main.py (deve ter uvicorn.run):"
docker exec tracker tail -10 /app/main.py

echo ""
echo "5. SHA do commit que gerou a imagem (se existir):"
docker exec tracker cat /app/.git_sha 2>/dev/null || echo "(sem arquivo .git_sha)"

echo ""
echo "6. Data de modificação do /app/main.py:"
docker exec tracker stat /app/main.py | grep Modify

echo ""
echo "7. Imagem Docker em uso:"
docker inspect tracker --format "{{.Image}}" 2>/dev/null | head -c 20
echo ""
docker images tracker --format "table {{.ID}}\t{{.CreatedAt}}\t{{.Size}}"
