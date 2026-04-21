import os
import threading
import uvicorn
from datetime import datetime, timezone
from fastapi import FastAPI
from database import inicializar_banco, obter_sites_ativos
from scraper import coletar_site

app = FastAPI(title="CashbackTracker", version="1.0.0")


@app.get("/health")
def health():
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"status": "ok", "timestamp": agora}


def executar_coleta_inicial():
    sites = obter_sites_ativos()
    for site in sites:
        t = threading.Thread(target=coletar_site, args=(site["id"], site["url"], site["nome"]), daemon=True)
        t.start()


@app.on_event("startup")
def ao_iniciar():
    inicializar_banco()
    executar_coleta_inicial()


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    porta = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=porta, log_level="info")
