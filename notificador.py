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
    """
    Formata alertas agrupados por categoria → site → parceiros.

    Telegram:
        🔔 CashbackTracker — Alertas

        📂 Farmácia
          Drogaria SP
            • Cashback | Americanas  5,0%  (limiar: 3%)
          Qualidoc
            • Pontos   | Smiles      2 pts (limiar: 1 pts)

    Email: tabela agrupada com cabeçalho de categoria e sub-cabeçalho de site.
    """
    from collections import defaultdict

    # Ordenar: categoria → site → tipo → parceiro (tudo alfabético)
    alertas_ord = sorted(
        alertas,
        key=lambda a: (
            a.get("categoria", "").lower(),
            a.get("site_nome", "").lower(),
            a.get("tipo", ""),
            a.get("parceiro", "").lower(),
        ),
    )

    # Agrupar em dois níveis: categoria → site → [alertas]
    grupos: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for a in alertas_ord:
        grupos[a.get("categoria", "Sem categoria")][a.get("site_nome", "")].append(a)

    # ── Telegram ─────────────────────────────────────────────────────────────
    linhas_tg = ["🔔 <b>CashbackTracker — Alertas</b>"]

    for categoria in sorted(grupos.keys(), key=str.lower):
        linhas_tg.append(f"\n📂 <b>{categoria}</b>")
        for site_nome in sorted(grupos[categoria].keys(), key=str.lower):
            linhas_tg.append(f"  <i>{site_nome}</i>")
            for a in grupos[categoria][site_nome]:
                unidade    = "%" if a["tipo"] == "cashback" else " pts"
                tipo_label = "Cashback" if a["tipo"] == "cashback" else "Pontos/Milhas"
                valor_fmt  = f"{a['valor']:g}{unidade}"
                limiar_fmt = f"{a['limiar']}{unidade}"
                linhas_tg.append(
                    f"    • {tipo_label} | <b>{a['parceiro']}</b>  "
                    f"<b>{valor_fmt}</b>  (limiar: {limiar_fmt})"
                )

    # ── Email HTML ────────────────────────────────────────────────────────────
    blocos_html = []

    for categoria in sorted(grupos.keys(), key=str.lower):
        # Cabeçalho de categoria
        blocos_html.append(
            f'''
      <tr>
        <td colspan="4" style="padding:12px 8px 4px;font-family:sans-serif;
            font-size:13px;font-weight:700;color:#58a6ff;
            border-top:2px solid #30363d;letter-spacing:.04em">
          📂 {categoria}
        </td>
      </tr>'''
        )

        for site_nome in sorted(grupos[categoria].keys(), key=str.lower):
            # Sub-cabeçalho de site
            blocos_html.append(
                f'''
      <tr>
        <td colspan="4" style="padding:6px 8px 2px 20px;font-family:sans-serif;
            font-size:12px;font-weight:600;color:#8b949e;font-style:italic">
          {site_nome}
        </td>
      </tr>'''
            )

            for a in grupos[categoria][site_nome]:
                unidade    = "%" if a["tipo"] == "cashback" else " pts"
                tipo_label = "Cashback" if a["tipo"] == "cashback" else "Pontos/Milhas"
                valor_fmt  = f"{a['valor']:g}{unidade}"
                limiar_fmt = f"{a['limiar']}{unidade}"
                blocos_html.append(
                    f'''
      <tr style="border-bottom:1px solid #21262d">
        <td style="padding:7px 8px 7px 32px;font-family:sans-serif;font-size:13px">
          <b>{a['parceiro']}</b>
        </td>
        <td style="padding:7px 8px;font-family:sans-serif;font-size:13px;
            color:#8b949e">{tipo_label}</td>
        <td style="padding:7px 8px;font-family:sans-serif;font-size:13px;
            text-align:right;color:#3fb950;font-weight:bold">{valor_fmt}</td>
        <td style="padding:7px 8px;font-family:sans-serif;font-size:13px;
            text-align:right;color:#8b949e">{limiar_fmt}</td>
      </tr>'''
                )

    linhas_html_body = "".join(blocos_html)
    html = f"""
    <div style="font-family:sans-serif;background:#0f1117;padding:20px;border-radius:8px">
      <h2 style="color:#3fb950;margin:0 0 16px">🔔 CashbackTracker — Alertas</h2>
      <table style="font-size:14px;border-collapse:collapse;width:100%;
                    background:#161b22;border-radius:6px;overflow:hidden">
        <thead>
          <tr style="background:#21262d">
            <th style="padding:8px 8px 8px 32px;text-align:left;color:#8b949e;
                font-size:11px;text-transform:uppercase;letter-spacing:.06em">Parceiro</th>
            <th style="padding:8px;text-align:left;color:#8b949e;
                font-size:11px;text-transform:uppercase;letter-spacing:.06em">Tipo</th>
            <th style="padding:8px;text-align:right;color:#8b949e;
                font-size:11px;text-transform:uppercase;letter-spacing:.06em">Valor</th>
            <th style="padding:8px;text-align:right;color:#8b949e;
                font-size:11px;text-transform:uppercase;letter-spacing:.06em">Limiar</th>
          </tr>
        </thead>
        <tbody>{linhas_html_body}</tbody>
      </table>
    </div>"""

    return "\n".join(linhas_tg), html


def formatar_mensagem_teste() -> tuple[str, str]:
    tg = "✅ <b>CashbackTracker</b>\n\nNotificação de teste — configuração funcionando corretamente!"
    email = """
    <h2 style="font-family:sans-serif;color:#3fb950">✅ CashbackTracker</h2>
    <p style="font-family:sans-serif;font-size:14px">
      Notificação de teste — configuração funcionando corretamente!
    </p>"""
    return tg, email
