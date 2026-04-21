import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from database import (
    inicializar_banco,
    obter_sites_ativos,
    obter_todos_sites,
    obter_site_por_id,
    obter_site_por_url,
    inserir_site,
    reativar_site,
    desativar_site,
    obter_parceiros_site,
    obter_snapshots_site,
    obter_max_site,
    verificar_alerta_sem_dados,
    obter_ultima_coleta_site,
)
from scraper import coletar_site
from agendador import iniciar_agendador, parar_agendador, reconfigurar_agendador, obter_config

# Resolve o diretório static de duas formas, usa o que existir
_BASE = Path(__file__).resolve().parent
STATIC_DIR = _BASE / "static"
if not STATIC_DIR.is_dir():
    STATIC_DIR = Path("/app/static")

ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"[{ts}] [STARTUP] STATIC_DIR = {STATIC_DIR} | existe = {STATIC_DIR.is_dir()}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_banco()
    iniciar_agendador()
    _disparar_coleta_inicial()
    yield
    parar_agendador()


app = FastAPI(title="CashbackTracker", version="3.0.0", lifespan=lifespan)


def _disparar_coleta_inicial():
    sites = obter_sites_ativos()
    for site in sites:
        t = threading.Thread(
            target=coletar_site,
            args=(site["id"], site["url"], site["nome"]),
            daemon=True,
        )
        t.start()


# ── Diagnóstico (remover após confirmar) ─────────────────────────────────────

@app.get("/debug-static", include_in_schema=False)
def debug_static():
    arquivos = []
    if STATIC_DIR.is_dir():
        arquivos = [str(p.name) for p in STATIC_DIR.iterdir()]
    return JSONResponse({
        "static_dir": str(STATIC_DIR),
        "existe": STATIC_DIR.is_dir(),
        "arquivos": arquivos,
        "cwd": os.getcwd(),
        "listdir_app": os.listdir("/app") if Path("/app").exists() else [],
    })


# ── Dashboard ─────────────────────────────────────────────────────────────────

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    ts2 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts2}] [STARTUP] StaticFiles montado em /static")

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(str(STATIC_DIR / "index.html"))
else:
    @app.get("/", include_in_schema=False)
    def dashboard_fallback():
        return JSONResponse({"erro": f"static nao encontrado em {STATIC_DIR}"}, status_code=503)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"status": "ok", "timestamp": agora}


# ── Modelos ───────────────────────────────────────────────────────────────────

class SiteEntrada(BaseModel):
    url: str
    nome: str
    categoria: str


class ConfigEntrada(BaseModel):
    scrape_time: str | None = None
    scrape_interval_hours: int | None = None


# ── Sites ─────────────────────────────────────────────────────────────────────

@app.get("/sites")
def listar_sites():
    sites = obter_todos_sites()
    resultado = []
    for s in sites:
        alerta = verificar_alerta_sem_dados(s["id"]) if s["ativo"] else False
        ultima_coleta = obter_ultima_coleta_site(s["id"])
        resultado.append({
            "id": s["id"],
            "nome": s["nome"],
            "url": s["url"],
            "categoria": s["categoria"],
            "ativo": bool(s["ativo"]),
            "alerta_sem_dados": alerta,
            "ultima_coleta": ultima_coleta,
        })
    return resultado


@app.post("/sites", status_code=201)
def cadastrar_site(dados: SiteEntrada, response: Response):
    existente = obter_site_por_url(dados.url)
    if existente:
        if existente["ativo"]:
            raise HTTPException(status_code=409, detail="Este site já está sendo monitorado")
        reativar_site(existente["id"], dados.nome, dados.categoria)
        site_id = existente["id"]
        response.status_code = 200
    else:
        site_id = inserir_site(dados.url, dados.nome, dados.categoria)
    threading.Thread(target=coletar_site, args=(site_id, dados.url, dados.nome), daemon=True).start()
    return obter_site_por_id(site_id)


@app.delete("/sites/{site_id}", status_code=204)
def remover_site(site_id: int):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    desativar_site(site_id)
    return Response(status_code=204)


@app.get("/sites/{site_id}/parceiros")
def parceiros_site(site_id: int):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    return obter_parceiros_site(site_id)


@app.get("/sites/{site_id}/snapshots")
def snapshots_site(site_id: int, parceiro: str | None = None, tipo: str | None = None, dias: int = 30):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    if dias > 90:
        dias = 90
    return obter_snapshots_site(site_id, parceiro=parceiro, tipo=tipo, dias=dias)


@app.get("/sites/{site_id}/max")
def max_site(site_id: int, dias: int = 30):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    if dias > 90:
        dias = 90
    return obter_max_site(site_id, dias=dias)


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/config")
def ler_config():
    return obter_config()


@app.put("/config")
def atualizar_config(dados: ConfigEntrada):
    reconfigurar_agendador(
        novo_scrape_time=dados.scrape_time,
        novo_intervalo_horas=dados.scrape_interval_hours,
    )
    return obter_config()


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    porta = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=porta, log_level="info")
