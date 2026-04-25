import logging
import threading
from datetime import datetime, timezone

from database import obter_sites_ativos, obter_parceiros_site
from notificador import (
    carregar_config_notif,
    enviar_telegram,
    enviar_email,
    formatar_mensagem_alerta,
)

logger = logging.getLogger(__name__)
_alertas_lock = threading.Lock()


def verificar_e_disparar_alertas():
    with _alertas_lock:
        _executar_verificacao()


def _executar_verificacao():
    cfg      = carregar_config_notif()
    limiares = cfg.get("limiares", [])
    if not limiares:
        return

    telegram_ativo = cfg.get("telegram_ativo", False)
    email_ativo    = cfg.get("email_ativo", False)
    if not telegram_ativo and not email_ativo:
        return

    sites  = obter_sites_ativos()
    alertas = []

    for site in sites:
        parceiros = obter_parceiros_site(site["id"])
        for tipo in ("cashback", "pontos_milhas"):
            for p in parceiros.get(tipo, []):
                if p["status"] != "ativo" or p["ultimo_valor"] is None:
                    continue
                for lim in limiares:
                    if lim.get("tipo") != tipo:
                        continue
                    cat = lim.get("categoria", "")
                    if cat and cat != site.get("categoria", ""):
                        continue
                    parc = lim.get("parceiro", "")
                    if parc and parc != p["parceiro"]:
                        continue
                    if p["ultimo_valor"] >= float(lim["valor"]):
                        alertas.append({
                            "parceiro":  p["parceiro"],
                            "site_nome": site["nome"],
                            "categoria": site.get("categoria", ""),
                            "tipo":      tipo,
                            "valor":     p["ultimo_valor"],
                            "limiar":    lim["valor"],
                        })

    if not alertas:
        return

    vistos, unicos = set(), []
    for a in alertas:
        chave = f"{a['parceiro']}|{a['site_nome']}|{a['tipo']}"
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(a)

    texto_tg, html_email = formatar_mensagem_alerta(unicos)
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if telegram_ativo:
        ok, msg = enviar_telegram(cfg.get("telegram_token",""), cfg.get("telegram_chat_id",""), texto_tg)
        logger.info(f"[ALERTA][TELEGRAM] {agora} — {'OK' if ok else 'ERRO: ' + msg}")

    if email_ativo:
        ok, msg = enviar_email(
            cfg.get("smtp_user",""), cfg.get("smtp_password",""),
            cfg.get("email_destino",""),
            f"CashbackTracker — {len(unicos)} alerta(s)", html_email,
        )
        logger.info(f"[ALERTA][EMAIL] {agora} — {'OK' if ok else 'ERRO: ' + msg}")
