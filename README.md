# CashbackTracker

Monitor de cashback e pontos/milhas do comparemania.com.br

## Status

- [x] Fase 1 — Scraper + Armazenamento
- [x] Fase 2 — API REST + Agendador
- [x] Fase 3 — Dashboard Web
- [ ] Fase 4 — Notificações

## Como executar

```bash
git clone https://github.com/maikellt/tracker.git
cd tracker
mkdir -p /data/tracker && chmod 755 /data/tracker
docker build -t tracker:latest .
docker-compose up -d
```

## Acesso

| Recurso | URL |
|---------|-----|
| **Dashboard** | http://localhost:8086 |
| Health | http://localhost:8086/health |
| API Docs | http://localhost:8086/docs |

## Dashboard (Fase 3)

Interface web com três abas:

- **Painel** — tabela de parceiros filtrável, gráfico histórico (Chart.js), cards de resumo, banner de alerta
- **Sites** — listagem, cadastro, desativação e reativação de sites monitorados
- **Configurações** — ajuste de horário fixo e intervalo do agendador

## Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Status da aplicação |
| GET | `/sites` | Lista todos os sites (inclui `ultima_coleta`) |
| POST | `/sites` | Cadastra ou reativa um site |
| DELETE | `/sites/{id}` | Desativa um site |
| GET | `/sites/{id}/parceiros` | Parceiros do site (ativo/inativo) |
| GET | `/sites/{id}/snapshots` | Histórico de snapshots |
| GET | `/sites/{id}/max` | Valor máximo no período |
| GET | `/config` | Configuração do agendador |
| PUT | `/config` | Atualiza configuração |

## Agendador

- **Job fixo:** executa coleta no horário definido em `SCRAPE_TIME` (padrão `06:00` BRT)
- **Job intervalo:** verifica a cada hora se algum site precisa de coleta com base em `SCRAPE_INTERVAL_HOURS` (padrão `24`)
- **Regra de desempate:** coleta por intervalo é suprimida se o job fixo disparar em ≤30 min

## Banco de dados

SQLite em `/app/data/tracker.db` → mapeado para `/data/tracker/tracker.db` no host.

Tabelas: `sites`, `snapshots`, `erros_scraping`.
