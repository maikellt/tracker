import os
import secrets
import threading
from datetime import timedelta

from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
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
)
from scraper import coletar_site
from notificador import carregar_config_notif, salvar_config_notif, enviar_telegram, enviar_email, formatar_mensagem_teste
from agendador import iniciar_agendador, parar_agendador, reconfigurar_agendador, obter_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_banco()
    iniciar_agendador()
    _disparar_coleta_inicial()
    yield
    parar_agendador()



# ── Autenticação JWT ──────────────────────────────────────────────────────────

def _inicializar_credenciais():
    """Gera senha e JWT_SECRET aleatórios se não definidos no ambiente.
    Exibe nos logs para que o operador possa configurar o acesso inicial."""
    user     = os.getenv("AUTH_USER", "admin")
    password = os.getenv("AUTH_PASSWORD", "")
    secret   = os.getenv("JWT_SECRET", "")
    gerado   = False

    if not password:
        password = secrets.token_urlsafe(16)
        gerado = True

    if not secret:
        secret = secrets.token_hex(32)

    if gerado:
        separador = "=" * 60
        print(f"\n{separador}", flush=True)
        print("  CASHBACKTRACKER — CREDENCIAIS DE ACESSO", flush=True)
        print(separador, flush=True)
        print(f"  Usuário : {user}", flush=True)
        print(f"  Senha   : {password}", flush=True)
        print(f"  (gerada automaticamente — defina AUTH_PASSWORD", flush=True)
        print(f"   no docker-compose.yml para tornar permanente)", flush=True)
        print(f"{separador}\n", flush=True)

    return user, password, secret


_AUTH_USER, _AUTH_PASS, _JWT_SECRET = _inicializar_credenciais()
_JWT_ALGO     = "HS256"
_JWT_EXPIRE_H = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login", auto_error=False)


def _criar_token(dados: dict) -> str:
    from datetime import datetime, timezone
    payload = dict(dados)
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRE_H)
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


def _verificar_token(token: str = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
        if payload.get("sub") != _AUTH_USER:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado ou inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )


class LoginEntrada(BaseModel):
    username: str
    password: str



app = FastAPI(title="CashbackTracker", version="3.0.0", lifespan=lifespan)

@app.post("/login")
def login(dados: LoginEntrada):
    if dados.username != _AUTH_USER or dados.password != _AUTH_PASS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    token = _criar_token({"sub": dados.username})
    return {"access_token": token, "token_type": "bearer", "expires_in": _JWT_EXPIRE_H * 3600}




def _disparar_coleta_inicial():
    sites = obter_sites_ativos()
    for site in sites:
        t = threading.Thread(
            target=coletar_site,
            args=(site["id"], site["url"], site["nome"]),
            daemon=True,
        )
        t.start()


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"status": "ok", "timestamp": agora}


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=FileResponse, include_in_schema=False)
async def dashboard():
    return FileResponse("/app/static/index.html", media_type="text/html")


@app.get("/static/index.html", response_class=FileResponse, include_in_schema=False)
async def dashboard_direto():
    return FileResponse("/app/static/index.html", media_type="text/html")


@app.get("/static/app.js", include_in_schema=False)
async def dashboard_js():
    return FileResponse("/app/static/app.js", media_type="application/javascript")


# ── Modelos ───────────────────────────────────────────────────────────────────

class SiteEntrada(BaseModel):
    url: str
    nome: str
    categoria: str


class ConfigEntrada(BaseModel):
    scrape_time: str | None = None
    scrape_interval_hours: int | None = None


# ── Sites ─────────────────────────────────────────────────────────────────────

@app.get("/sites", dependencies=[Depends(_verificar_token)])
def listar_sites():
    sites = obter_todos_sites()
    resultado = []
    for s in sites:
        alerta = verificar_alerta_sem_dados(s["id"]) if s["ativo"] else False
        resultado.append({
            "id": s["id"],
            "nome": s["nome"],
            "url": s["url"],
            "categoria": s["categoria"],
            "ativo": bool(s["ativo"]),
            "alerta_sem_dados": alerta,
        })
    return resultado


@app.post("/sites", status_code=201, dependencies=[Depends(_verificar_token)])
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

    threading.Thread(
        target=coletar_site,
        args=(site_id, dados.url, dados.nome),
        daemon=True,
    ).start()

    return obter_site_por_id(site_id)


@app.delete("/sites/{site_id}", status_code=204, dependencies=[Depends(_verificar_token)])
def remover_site(site_id: int):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    desativar_site(site_id)
    return Response(status_code=204)


@app.get("/sites/{site_id}/parceiros", dependencies=[Depends(_verificar_token)])
def parceiros_site(site_id: int):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    return obter_parceiros_site(site_id)


@app.get("/sites/{site_id}/snapshots", dependencies=[Depends(_verificar_token)])
def snapshots_site(
    site_id: int,
    parceiro: str | None = None,
    tipo: str | None = None,
    dias: int = 30,
):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    if dias > 90:
        dias = 90
    return obter_snapshots_site(site_id, parceiro=parceiro, tipo=tipo, dias=dias)


@app.get("/sites/{site_id}/max", dependencies=[Depends(_verificar_token)])
def max_site(site_id: int, dias: int = 30):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    if dias > 90:
        dias = 90
    return obter_max_site(site_id, dias=dias)


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/config", dependencies=[Depends(_verificar_token)])
def ler_config():
    return obter_config()


@app.put("/config", dependencies=[Depends(_verificar_token)])
def atualizar_config(dados: ConfigEntrada):
    reconfigurar_agendador(
        novo_scrape_time=dados.scrape_time,
        novo_intervalo_horas=dados.scrape_interval_hours,
    )
    return obter_config()




# ── Preferências ──────────────────────────────────────────────────────────────

PREFS_PATH = "/app/data/preferencias.json"

@app.get("/preferencias", dependencies=[Depends(_verificar_token)])
def ler_preferencias():
    import json
    if not os.path.exists(PREFS_PATH):
        return {}
    with open(PREFS_PATH, "r") as f:
        return json.load(f)

@app.put("/preferencias", dependencies=[Depends(_verificar_token)])
def salvar_preferencias(dados: dict):
    import json
    with open(PREFS_PATH, "w") as f:
        json.dump(dados, f)
    return dados



# ── Notificações ──────────────────────────────────────────────────────────────

class ConfigNotificacao(BaseModel):
    telegram_ativo:   bool       = False
    telegram_token:   str        = ""
    telegram_chat_id: str        = ""
    email_ativo:      bool       = False
    smtp_user:        str        = ""
    smtp_password:    str        = ""
    email_destino:    str        = ""
    limiares:         list[dict] = []


@app.get("/notificacoes/config", dependencies=[Depends(_verificar_token)])
def ler_config_notificacoes():
    cfg = carregar_config_notif()
    if cfg.get("smtp_password"):
        cfg["smtp_password"] = "••••••••"
    return cfg


@app.put("/notificacoes/config", dependencies=[Depends(_verificar_token)])
def salvar_config_notificacoes(dados: ConfigNotificacao):
    cfg_atual = carregar_config_notif()
    novo = dados.model_dump()
    if novo.get("smtp_password") == "••••••••":
        novo["smtp_password"] = cfg_atual.get("smtp_password", "")
    salvar_config_notif(novo)
    resultado = dict(novo)
    if resultado.get("smtp_password"):
        resultado["smtp_password"] = "••••••••"
    return resultado


@app.post("/notificacoes/teste", dependencies=[Depends(_verificar_token)])
def testar_notificacoes():
    cfg = carregar_config_notif()
    texto_tg, html_email = formatar_mensagem_teste()
    resultados = {}
    if cfg.get("telegram_ativo") and cfg.get("telegram_token") and cfg.get("telegram_chat_id"):
        ok_r, msg = enviar_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], texto_tg)
        resultados["telegram"] = {"ok": ok_r, "detalhe": msg}
    else:
        resultados["telegram"] = {"ok": False, "detalhe": "Não configurado ou desativado"}
    if cfg.get("email_ativo") and cfg.get("smtp_user") and cfg.get("smtp_password") and cfg.get("email_destino"):
        ok_r, msg = enviar_email(cfg["smtp_user"], cfg["smtp_password"], cfg["email_destino"],
                                 "CashbackTracker — Teste de notificação", html_email)
        resultados["email"] = {"ok": ok_r, "detalhe": msg}
    else:
        resultados["email"] = {"ok": False, "detalhe": "Não configurado ou desativado"}
    return resultados

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    porta = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=porta, log_level="info")

