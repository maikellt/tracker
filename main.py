import logging
import os
import secrets
import threading
from datetime import timedelta

from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import (
    banco_tem_dados,
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
    obter_configuracao,
    salvar_configuracao,
    # Produtos
    inserir_produto,
    reativar_produto,
    obter_todos_produtos,
    obter_todos_produtos_ativos,
    obter_produto_por_id,
    obter_produto_por_url,
    desativar_produto,
    salvar_preco_produto,
    obter_ultimo_preco_produto,
    mapear_dominio_para_site_cashback,
    marcar_produto_bloqueado,
    salvar_preco_manual,
    atualizar_url_produto,
    obter_historico_precos_produto,
)
from scraper_produtos import coletar_preco_produto
import time as _time
_cache_cashback: dict = {}   # url -> (resultado, timestamp)
_CACHE_TTL = 300             # 5 minutos

def _cashback_cached(url: str) -> dict:
    agora = _time.time()
    if url in _cache_cashback:
        res, ts = _cache_cashback[url]
        if agora - ts < _CACHE_TTL:
            return res
    res = mapear_dominio_para_site_cashback(url)
    _cache_cashback[url] = (res, agora)
    return res


from scraper import coletar_site
from notificador import carregar_config_notif, salvar_config_notif, enviar_telegram, enviar_email, formatar_mensagem_teste
from agendador import iniciar_agendador, parar_agendador, reconfigurar_agendador, obter_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_banco()  # já sincroniza Turso → local internamente
    iniciar_agendador()
    # Só coleta no startup se o banco estiver vazio.
    # Quando o container reinicia, o Turso já sincronizou tudo —
    # disparar coleta imediata sobrescreveria dados recentes com valores
    # coletados fora do horário agendado.
    if banco_tem_dados():
        logger.info(
            "[STARTUP] Banco já possui dados (sincronizados do Turso) — "
            "coleta inicial suprimida. Próxima coleta no horário agendado."
        )
    else:
        logger.info("[STARTUP] Banco vazio — disparando coleta inicial.")
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

logger = logging.getLogger(__name__)

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
    produto_scrape_time: str | None = None


class ProdutoEntrada(BaseModel):
    nome: str
    url: str
    categoria: str
    dosagem: str | None = None
    quantidade: int | None = None
    unidade_qty: str = "comprimidos"


# ── Sites ─────────────────────────────────────────────────────────────────────

@app.get("/sites")
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


@app.get("/sites/{site_id}/parceiros")
def parceiros_site(site_id: int):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    return obter_parceiros_site(site_id)


@app.get("/sites/{site_id}/snapshots")
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


@app.get("/sites/{site_id}/max")
def max_site(site_id: int, dias: int = 30):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    if dias > 90:
        dias = 90
    return obter_max_site(site_id, dias=dias)


# ── Produtos ─────────────────────────────────────────────────────────────────

@app.get("/produtos/historico", dependencies=[Depends(_verificar_token)])
def historico_produtos(dias: int = 30):
    """Uma série por produto — menor preço final do dia e qual loja ofereceu."""
    if dias > 90:
        dias = 90

    produtos = obter_todos_produtos_ativos()
    grupos: dict = {}
    for p in produtos:
        grupos.setdefault(p["nome"], []).append(p)

    resultado = []
    for nome, itens in grupos.items():
        historico: dict = {}   # data -> {preco_final, loja}
        for p in itens:
            qtd      = p["quantidade"] or 1
            cashback = _cashback_cached(p["url"])
            cb_pct   = cashback["cashback_pct"]
            loja     = cashback["site_nome"] or p["url"].split("/")[2].replace("www.", "").split(".")[0]
            for entry in obter_historico_precos_produto(p["id"], dias):
                data    = entry["capturado_em"][:10]
                preco_f = round(entry["preco"] * (1 - cb_pct / 100), 2)
                if data not in historico or preco_f < historico[data]["preco"]:
                    historico[data] = {"preco": preco_f, "loja": loja}
        resultado.append({
            "nome":      nome,
            "historico": [{"data": k, "preco": v["preco"], "loja": v["loja"]}
                          for k, v in sorted(historico.items())],
        })
    return resultado


@app.get("/produtos/comparativo", dependencies=[Depends(_verificar_token)])
def comparativo_produtos():
    """Agrupa produtos por nome, calcula cashback e ordena por preço unitário."""
    grupos: dict = {}
    for p in obter_todos_produtos_ativos():
        ultimo   = obter_ultimo_preco_produto(p["id"])
        cashback = _cashback_cached(p["url"])
        preco    = ultimo["preco"] if ultimo else None
        cb_pct   = cashback["cashback_pct"]
        preco_final  = round(preco * (1 - cb_pct / 100), 2) if preco is not None else None
        quantidade   = p["quantidade"] or 1
        preco_unit   = round(preco_final / quantidade, 4) if preco_final is not None else None

        item = {
            "id":               p["id"],
            "url":              p["url"],
            "dosagem":          p["dosagem"],
            "quantidade":       p["quantidade"],
            "unidade_qty":      p["unidade_qty"],
            "preco":            preco,
            "preco_final":      preco_final,
            "preco_unitario":   preco_unit,
            "cashback_pct":     cb_pct,
            "cashback_parceiro": cashback["parceiro"],
            "site_nome":        cashback["site_nome"],
            "ultima_coleta":    ultimo["capturado_em"] if ultimo else None,
        }
        key = p["nome"]
        if key not in grupos:
            grupos[key] = {"nome": p["nome"], "categoria": p["categoria"], "itens": []}
        grupos[key]["itens"].append(item)

    for g in grupos.values():
        g["itens"].sort(key=lambda x: (x["preco_unitario"] is None, x["preco_unitario"] or 0))

    return list(grupos.values())


@app.get("/produtos", dependencies=[Depends(_verificar_token)])
def listar_produtos():
    resultado = []
    for p in obter_todos_produtos():
        ultimo   = obter_ultimo_preco_produto(p["id"])
        cashback = _cashback_cached(p["url"])
        preco    = ultimo["preco"] if ultimo else None
        cb_pct   = cashback["cashback_pct"]
        preco_f  = round(preco * (1 - cb_pct / 100), 2) if preco is not None else None
        preco_u  = round(preco_f / (p["quantidade"] or 1), 4) if preco_f is not None else None
        resultado.append({
            **p,
            "preco":              preco,
            "preco_final":        preco_f,
            "preco_unitario":     preco_u,
            "cashback_pct":       cb_pct,
            "cashback_parceiro":  cashback["parceiro"],
            "site_nome_cashback": cashback["site_nome"],
            "ultima_coleta":      ultimo["capturado_em"] if ultimo else None,
            "bloqueado":          bool(p.get("bloqueado")),
        })
    return resultado


@app.post("/produtos", status_code=201, dependencies=[Depends(_verificar_token)])
def cadastrar_produto(dados: ProdutoEntrada, response: Response):
    existente = obter_produto_por_url(dados.url)
    if existente:
        if existente["ativo"]:
            raise HTTPException(status_code=409, detail="Este produto já está cadastrado")
        reativar_produto(existente["id"], dados.nome, dados.categoria,
                         dados.dosagem, dados.quantidade, dados.unidade_qty)
        produto_id = existente["id"]
        response.status_code = 200
    else:
        produto_id = inserir_produto(dados.nome, dados.url, dados.categoria,
                                     dados.dosagem, dados.quantidade, dados.unidade_qty)

    threading.Thread(
        target=coletar_preco_produto,
        args=(produto_id, dados.url, dados.nome),
        daemon=True,
    ).start()

    return obter_produto_por_id(produto_id)


@app.delete("/produtos/{produto_id}", status_code=204, dependencies=[Depends(_verificar_token)])
def remover_produto(produto_id: int):
    p = obter_produto_por_id(produto_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    desativar_produto(produto_id)
    return Response(status_code=204)


@app.patch("/produtos/{produto_id}", dependencies=[Depends(_verificar_token)])
def atualizar_produto(produto_id: int, dados: dict):
    p = obter_produto_por_id(produto_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if "url" in dados and dados["url"]:
        atualizar_url_produto(produto_id, dados["url"].strip())
        threading.Thread(
            target=coletar_preco_produto,
            args=(produto_id, dados["url"].strip(), p["nome"]),
            daemon=True,
        ).start()
    return obter_produto_por_id(produto_id)


@app.put("/produtos/{produto_id}/preco", dependencies=[Depends(_verificar_token)])
def salvar_preco_produto_manual(produto_id: int, dados: dict):
    p = obter_produto_por_id(produto_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    preco = dados.get("preco")
    if preco is None or float(preco) <= 0:
        raise HTTPException(status_code=422, detail="Preco invalido")
    salvar_preco_manual(produto_id, float(preco))
    return {"ok": True}


@app.post("/produtos/{produto_id}/coletar", dependencies=[Depends(_verificar_token)])
def coletar_produto_agora(produto_id: int):
    p = obter_produto_por_id(produto_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    threading.Thread(
        target=coletar_preco_produto,
        args=(produto_id, p["url"], p["nome"]),
        daemon=True,
    ).start()
    return {"status": "coleta_iniciada"}



# ── Busca ─────────────────────────────────────────────────────────────────────

@app.get("/busca/templates", dependencies=[Depends(_verificar_token)])
def listar_templates():
    return obter_configuracao("busca_templates") or []


@app.put("/busca/templates", dependencies=[Depends(_verificar_token)])
def salvar_templates(dados: list = Body(...)):
    salvar_configuracao("busca_templates", dados)
    return dados


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/config")
def ler_config():
    return obter_config()


@app.put("/config", dependencies=[Depends(_verificar_token)])
def atualizar_config(dados: ConfigEntrada):
    reconfigurar_agendador(
        novo_scrape_time=dados.scrape_time,
        novo_intervalo_horas=dados.scrape_interval_hours,
        novo_produto_scrape_time=dados.produto_scrape_time,
    )
    return obter_config()




# ── Preferências ──────────────────────────────────────────────────────────────


@app.get("/preferencias")
def ler_preferencias():
    return obter_configuracao("preferencias") or {}

@app.put("/preferencias", dependencies=[Depends(_verificar_token)])
def salvar_preferencias(dados: dict):
    salvar_configuracao("preferencias", dados)
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

