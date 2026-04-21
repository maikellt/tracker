# CashbackTracker

Monitor de cashback e pontos/milhas do comparemania.com.br

## Status

- [x] Fase 1 — Scraper + Armazenamento
- [x] Fase 2 — API REST + Agendador
- [ ] Fase 3 — Dashboard Web
- [ ] Fase 4 — Notificações

## Como executar

```bash
git clone https://github.com/maikellt/tracker.git
cd tracker
mkdir -p /data/tracker && chmod 755 /data/tracker
docker build -t tracker:latest .
docker-compose up -d
```

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Status da aplicação |
| GET | `/sites` | Lista todos os sites |
| POST | `/sites` | Cadastra ou reativa um site |
| DELETE | `/sites/{id}` | Desativa um site |
| GET | `/sites/{id}/parceiros` | Parceiros do site (ativo/inativo) |
| GET | `/sites/{id}/snapshots` | Histórico de snapshots |
| GET | `/sites/{id}/max` | Valor máximo no período |
| GET | `/config` | Configuração do agendador |
| PUT | `/config` | Atualiza configuração |

- API Docs: `http://localhost:8086/docs`

## Agendador

- **Job fixo:** executa coleta no horário definido em `SCRAPE_TIME` (padrão `06:00` BRT)
- **Job intervalo:** verifica a cada hora se algum site precisa de coleta com base em `SCRAPE_INTERVAL_HOURS` (padrão `24`)
- **Regra de desempate:** coleta por intervalo é suprimida se o job fixo disparar em ≤30 min

## Formato de log

```
[YYYY-MM-DD HH:MM:SS] [SITE] [AÇÃO] mensagem
[YYYY-MM-DD HH:MM:SS] [AGENDADOR] mensagem
```

## Banco de dados

SQLite em `/app/data/tracker.db` (mapeado para `/data/tracker/tracker.db` no host).

Tabelas: `sites`, `snapshots`, `erros_scraping`.

## Pré-requisito no host

```bash
mkdir -p /data/tracker && chmod 755 /data/tracker
```
