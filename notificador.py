import smtplib
import ssl
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests


def carregar_config_notif() -> dict:
    """Carrega configurações de notificação do banco de dados."""
    from database import obter_configuracao
    return obter_configuracao("notificacoes") or {}


def salvar_config_notif(cfg: dict):
    """Salva configurações de notificação no banco de dados."""
    from database import salvar_configuracao
    salvar_configuracao("notificacoes", cfg)


def enviar_telegram(token: str, chat_id: str, mensagem: str) -> tuple[bool, str]:
    if not token or not chat_id:
        return False, "Token ou Chat ID não configurados"
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": mensagem,
            "parse_mode": "HTML",
        }, timeout=10)
        data = resp.json()
        if data.get("ok"):
            return True, "OK"
        return False, data.get("description", "Erro desconhecido")
    except Exception as e:
        return False, str(e)


def enviar_email(
    smtp_user: str,
    smtp_password: str,
    destinatario: str,
    assunto: str,
    corpo_html: str,
) -> tuple[bool, str]:
    if not smtp_user or not smtp_password or not destinatario:
        return False, "Credenciais de email não configuradas"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"]    = f"CashbackTracker <{smtp_user}>"
        msg["To"]      = destinatario
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, destinatario, msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)


def formatar_mensagem_alerta(alertas: list[dict]) -> tuple[str, str]:
    linhas_tg = ["🔔 <b>CashbackTracker — Alertas</b>\n"]
    rows_email = []
    for a in alertas:
        unidade = "%" if a["tipo"] == "cashback" else " pts"
        linhas_tg.append(
            f"• <b>{a['parceiro']}</b> — {a['site_nome']}\n"
            f"  Categoria: {a['categoria']} | {a['tipo'].replace('_', '/')} "
            f"<b>{a['valor']}{unidade}</b> (limiar: {a['limiar']}{unidade})"
        )
        rows_email.append(f"""
        <tr style="border-bottom:1px solid #30363d">
          <td style="padding:8px"><b>{a['parceiro']}</b></td>
          <td style="padding:8px;color:#8b949e">{a['site_nome']}</td>
          <td style="padding:8px">{a['categoria']}</td>
          <td style="padding:8px">{a['tipo'].replace('_','/')}</td>
          <td style="padding:8px;text-align:right;color:#3fb950;font-weight:bold">{a['valor']}{unidade}</td>
          <td style="padding:8px;text-align:right;color:#8b949e">{a['limiar']}{unidade}</td>
        </tr>""")
    html = f"""
    <h2 style="font-family:sans-serif;color:#3fb950">🔔 CashbackTracker — Alertas</h2>
    <table style="font-family:sans-serif;font-size:14px;border-collapse:collapse;width:100%">
      <thead>
        <tr style="background:#161b22;color:#8b949e">
          <th style="padding:8px;text-align:left">Parceiro</th>
          <th style="padding:8px;text-align:left">Site</th>
          <th style="padding:8px;text-align:left">Categoria</th>
          <th style="padding:8px;text-align:left">Tipo</th>
          <th style="padding:8px;text-align:right">Valor</th>
          <th style="padding:8px;text-align:right">Limiar</th>
        </tr>
      </thead>
      <tbody>{''.join(rows_email)}</tbody>
    </table>"""
    return "\n".join(linhas_tg), html


def formatar_mensagem_teste() -> tuple[str, str]:
    tg = "✅ <b>CashbackTracker</b>\n\nNotificação de teste — configuração funcionando corretamente!"
    email = """
    <h2 style="font-family:sans-serif;color:#3fb950">✅ CashbackTracker</h2>
    <p style="font-family:sans-serif;font-size:14px">
      Notificação de teste — configuração funcionando corretamente!
    </p>"""
    return tg, email
