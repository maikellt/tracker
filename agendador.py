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


def _agora_naive() -> datetime:
    """Retorna datetime local sem timezone (consistente com o SQLite)."""
    return datetime.now()


def _log(mensagem: str):
    agora = _agora_naive().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] [AGENDADOR] {mensagem}", flush=True)


def _executar_coleta_todos():
    """Job 1 — horário fixo: coleta todos os sites ativos."""
    from alertas import verificar_e_disparar_alertas
    sites = obter_sites_ativos()
    _log(f"Job horário fixo disparado — {len(sites)} site(s) na fila")
    threads = []
    for site in sites:
        t = threading.Thread(
            target=coletar_site,
            args=(site["id"], site["url"], site["nome"]),
            daemon=True,
        )
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=120)
    verificar_e_disparar_alertas()


def _executar_coleta_por_intervalo():
    """
    Job 2 — intervalo por site: coleta sites cujo último scraping bem-sucedido
    está além do intervalo configurado, respeitando a regra de desempate ±30min
    com o horário fixo.
    """
    agora = _agora_naive()
    intervalo_horas = _config["scrape_interval_hours"]
    scrape_time = _config["scrape_time"]

    # Próximo disparo do job de horário fixo (naive, horário local)
    hora, minuto = map(int, scrape_time.split(":"))
    proximo_fixo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if proximo_fixo <= agora:
        proximo_fixo += timedelta(days=1)

    margem = timedelta(minutes=30)

    _log(f"Job intervalo verificando — intervalo={intervalo_horas}h, próximo fixo em {int((proximo_fixo - agora).total_seconds() / 60)}min")
    _threads_intervalo = []
    _disparou_intervalo = False

    sites = obter_sites_ativos()
    for site in sites:
        ultimo = obter_ultimo_scraping_sucesso(site["id"])

        if ultimo is None:
            _log(f"[{site['nome']}] Sem coleta anterior — disparando agora")
            threading.Thread(
                target=coletar_site,
                args=(site["id"], site["url"], site["nome"]),
                daemon=True,
            ).start()
            continue

        # Garante datetime naive para comparação consistente
        if ultimo.tzinfo is not None:
            ultimo = ultimo.replace(tzinfo=None)

        proximo_por_intervalo = ultimo + timedelta(hours=intervalo_horas)
        minutos_restantes = int((proximo_por_intervalo - agora).total_seconds() / 60)

        if proximo_por_intervalo > agora:
            _log(f"[{site['nome']}] Próxima coleta em {minutos_restantes}min — aguardando")
            continue

        # Regra de desempate: suprimir se job fixo disparar em ≤30min
        diff = abs((proximo_fixo - agora).total_seconds())
        if diff <= margem.total_seconds():
            _log(f"[{site['nome']}] Coleta suprimida — job fixo em {int(diff / 60)}min")
            continue

        _log(f"[{site['nome']}] Disparando coleta por intervalo (ultimo: {ultimo.strftime('%H:%M:%S')})")
        t = threading.Thread(
            target=coletar_site,
            args=(site["id"], site["url"], site["nome"]),
            daemon=True,
        )
        t.start()
        _threads_intervalo.append(t)
        _disparou_intervalo = True


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


    if _disparou_intervalo:
        from alertas import verificar_e_disparar_alertas
        for t in _threads_intervalo:
            t.join(timeout=120)
        verificar_e_disparar_alertas()


def _registrar_jobs():
    hora, minuto = map(int, _config["scrape_time"].split(":"))

    # Job 1 — horário fixo diário
    _scheduler.add_job(
        _executar_coleta_todos,
        CronTrigger(hour=hora, minute=minuto, timezone=_config["timezone"]),
        id="job_fixo",
        replace_existing=True,
    )

    # Job 2 — verificação a cada hora
    _scheduler.add_job(
        _executar_coleta_por_intervalo,
        IntervalTrigger(hours=1),
        id="job_intervalo",
        replace_existing=True,
    )

    _log(f"Jobs registrados — horário fixo: {_config['scrape_time']}, intervalo: {_config['scrape_interval_hours']}h")


def reconfigurar_agendador(novo_scrape_time: str | None, novo_intervalo_horas: int | None):
    with _lock:
        if novo_scrape_time:
            _config["scrape_time"] = novo_scrape_time
        if novo_intervalo_horas is not None:
            _config["scrape_interval_hours"] = novo_intervalo_horas

        if _scheduler and _scheduler.running:
            _registrar_jobs()
            _log(f"Agendador reconfigurado — horário: {_config['scrape_time']}, intervalo: {_config['scrape_interval_hours']}h")


def obter_config() -> dict:
    return {
        "scrape_time": _config["scrape_time"],
        "scrape_interval_hours": _config["scrape_interval_hours"],
        "timezone": _config["timezone"],
    }
