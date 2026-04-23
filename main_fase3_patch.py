# ──────────────────────────────────────────────────────────
#  FASE 3 — adições ao main.py
#
#  1. Adicione FileResponse ao import do fastapi:
#
#     from fastapi.responses import FileResponse
#
#  2. Cole as três rotas abaixo dentro da sua aplicação FastAPI,
#     junto com os outros endpoints (ex: após o /health).
#     Não remova nenhum endpoint existente.
# ──────────────────────────────────────────────────────────


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def dashboard():
    """Serve o dashboard HTML."""
    return FileResponse("/app/static/index.html", media_type="text/html")


@app.get("/static/index.html", response_class=FileResponse, include_in_schema=False)
async def dashboard_direto():
    """Rota alternativa direta para o HTML."""
    return FileResponse("/app/static/index.html", media_type="text/html")


@app.get("/static/app.js", include_in_schema=False)
async def dashboard_js():
    """Serve o JavaScript do dashboard."""
    return FileResponse("/app/static/app.js", media_type="application/javascript")


# ──────────────────────────────────────────────────────────
#  CHECKLIST de alterações no main.py:
#
#  [ ] Adicionar FileResponse ao import do fastapi
#  [ ] Colar as 3 rotas acima
#  [ ] Nenhuma outra alteração necessária
#  [ ] NÃO adicionar aiofiles ao requirements.txt
#  [ ] NÃO usar StaticFiles/mount
# ──────────────────────────────────────────────────────────
