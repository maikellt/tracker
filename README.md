# CashbackTracker

Monitor de cashback e pontos/milhas do comparemania.com.br

## Status

- [x] Fase 1 — Scraper + Armazenamento
- [ ] Fase 2 — API REST + Agendador
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

- Health:   `http://localhost:8086/health`
- API Docs: `http://localhost:8086/docs`

## Verificar logs

```bash
docker-compose logs -f
```

## Executar testes da Fase 1

```bash
chmod +x test_fase1.sh && ./test_fase1.sh
```

## Pré-requisito no host

```bash
mkdir -p /data/tracker && chmod 755 /data/tracker
```

## Estrutura

```
tracker/
├── main.py           # FastAPI app + startup
├── scraper.py        # HTTP scraping + parsing + normalização
├── database.py       # SQLite: criação e operações
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── test_fase1.sh
├── .gitignore
└── README.md
```

## Banco de dados

SQLite em `/app/data/tracker.db` (mapeado para `/data/tracker/tracker.db` no host).

Tabelas: `sites`, `snapshots`, `erros_scraping`.

## Formato de log

```
[YYYY-MM-DD HH:MM:SS] [SITE] [AÇÃO] mensagem
```

Exemplo:
```
[2026-04-21 06:00:01] [Drogaria SP] [SCRAPING] Iniciando coleta
[2026-04-21 06:00:03] [Drogaria SP] [PARCEIRO] Dotz → 3.0% cashback
[2026-04-21 06:00:05] [Drogaria SP] [OK] 5 parceiros cashback, 1 pontos/milhas
```
