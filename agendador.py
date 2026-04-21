import os
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from database import obter_sites_ativos, obter_ultimo_scraping_sucesso
from scraper import coletar_site

# ── Estado global da configuração ────────────────────────────────────────────
_config = {
    "scrape_time": os.getenv("SCRAPE_TIME", "06:00"),
    "scrape_interval_hours": int(os.getenv("SCRAPE_INTERVAL_HOURS", "24")),
    "timezone": "America/Sao_Paulo",
}

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _log(mensagem: str):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] [AGENDADOR] {mensagem}", flush=True)


def _executar_coleta_todos():
    """Job 1 — horário fixo: coleta todos os sites ativos."""
    sites = obter_sites_ativos()
    _log(f"Job horário fixo disparado — {len(sites)} site(s) na fila")
    for site in sites:
        threading.Thread(
            target=coletar_site,
            args=(site["id"], site["url"], site["nome"]),
            daemon=True,
        ).start()


def _executar_coleta_por_intervalo():
    """
    Job 2 — intervalo por site: coleta sites cujo último scraping bem-sucedido
    está além do intervalo configurado, respeitando a regra de desempate ±30min
    com o horário fixo.
    """
    agora = datetime.now()
    intervalo_horas = _config["scrape_interval_hours"]
    scrape_time = _config["scrape_time"]

    # Calcula próximo disparo do job de horário fixo
    hora, minuto = map(int, scrape_time.split(":"))
    proximo_fixo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if proximo_fixo <= agora:
        proximo_fixo += timedelta(days=1)

    margem = timedelta(minutes=30)

    sites = obter_sites_ativos()
    for site in sites:
        ultimo = obter_ultimo_scraping_sucesso(site["id"])
        if ultimo is None:
            continue  # nunca coletou — já foi disparado na inicialização

        proximo_por_intervalo = ultimo + timedelta(hours=intervalo_horas)
        if proximo_por_intervalo > agora:
            continue  # ainda não é hora

        # Regra de desempate: suprimir se coincide com job fixo dentro de ±30min
        diff = abs((proximo_fixo - agora).total_seconds())
        if diff <= margem.total_seconds():
            _log(f"[{site['nome']}] Coleta por intervalo suprimida — próximo horário fixo em {int(diff/60)}min")
            continue

        _log(f"[{site['nome']}] Disparando coleta por intervalo")
        threading.Thread(
            target=coletar_site,
            args=(site["id"], site["url"], site["nome"]),
            daemon=True,
        ).start()


def iniciar_agendador():
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            return

        _scheduler = BackgroundScheduler(timezone=_config["timezone"])
        _registrar_jobs()
        _scheduler.start()
        _log("Agendador iniciado")


def parar_agendador():
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _log("Agendador parado")


def _registrar_jobs():
    """Registra os dois jobs no scheduler (deve ser chamado com lock ativo)."""
    hora, minuto = map(int, _config["scrape_time"].split(":"))

    # Job 1 — horário fixo diário
    _scheduler.add_job(
        _executar_coleta_todos,
        CronTrigger(hour=hora, minute=minuto, timezone=_config["timezone"]),
        id="job_fixo",
        replace_existing=True,
    )

    # Job 2 — verificação a cada hora se algum site precisa de coleta por intervalo
    _scheduler.add_job(
        _executar_coleta_por_intervalo,
        IntervalTrigger(hours=1),
        id="job_intervalo",
        replace_existing=True,
    )

    _log(f"Jobs registrados — horário fixo: {_config['scrape_time']}, intervalo: {_config['scrape_interval_hours']}h")


def reconfigurar_agendador(novo_scrape_time: str | None, novo_intervalo_horas: int | None):
    """Atualiza configuração e re-registra os jobs sem reiniciar o container."""
    with _lock:
        if novo_scrape_time:
            _config["scrape_time"] = novo_scrape_time
        if novo_intervalo_horas is not None:
            _config["scrape_interval_hours"] = novo_intervalo_horas

        if _scheduler and _scheduler.running:
            _registrar_jobs()
            _log(f"Agendador reconfigurado — novo horário: {_config['scrape_time']}, intervalo: {_config['scrape_interval_hours']}h")


def obter_config() -> dict:
    return {
        "scrape_time": _config["scrape_time"],
        "scrape_interval_hours": _config["scrape_interval_hours"],
        "timezone": _config["timezone"],
    }
