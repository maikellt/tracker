#!/usr/bin/env python3
"""
migrar_para_turso.py — Migra dados do SQLite local para o Turso

Uso:
  TURSO_URL=libsql://seu-db.turso.io TURSO_TOKEN=seu_token \
    python3 migrar_para_turso.py [caminho_do_sqlite]

Caminho padrão do SQLite: /data/tracker/tracker.db
"""
import os
import sys
import sqlite3

import libsql_experimental as libsql

DB_PATH     = sys.argv[1] if len(sys.argv) > 1 else "/data/tracker/tracker.db"
TURSO_URL   = os.environ.get("TURSO_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")

if not TURSO_URL or not TURSO_TOKEN:
    print("ERRO: defina TURSO_URL e TURSO_TOKEN no ambiente")
    sys.exit(1)

if not os.path.exists(DB_PATH):
    print(f"ERRO: arquivo SQLite não encontrado em {DB_PATH}")
    sys.exit(1)

print(f"\nConectando ao SQLite: {DB_PATH}")
src = sqlite3.connect(DB_PATH)
src.row_factory = sqlite3.Row

print(f"Conectando ao Turso: {TURSO_URL}")
dst = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)

# ── Criar schema no Turso ─────────────────────────────────────────────────────
print("\n→ Criando schema no Turso...")
dst.execute("""
    CREATE TABLE IF NOT EXISTS sites (
        id        INTEGER PRIMARY KEY,
        url       TEXT NOT NULL UNIQUE,
        nome      TEXT NOT NULL,
        categoria TEXT NOT NULL,
        ativo     INTEGER DEFAULT 1
    )
""")
dst.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id           INTEGER PRIMARY KEY,
        site_id      INTEGER REFERENCES sites(id),
        parceiro     TEXT    NOT NULL,
        tipo         TEXT    NOT NULL,
        percentual   REAL,
        unidade      TEXT,
        capturado_em DATETIME DEFAULT (datetime('now'))
    )
""")
dst.execute("""
    CREATE TABLE IF NOT EXISTS erros_scraping (
        id         INTEGER PRIMARY KEY,
        site_id    INTEGER REFERENCES sites(id),
        motivo     TEXT    NOT NULL,
        tentado_em DATETIME DEFAULT (datetime('now'))
    )
""")
dst.commit()
print("  ✓ Schema criado")

# ── Migrar sites ──────────────────────────────────────────────────────────────
print("\n→ Migrando tabela sites...")
sites = src.execute("SELECT id, url, nome, categoria, ativo FROM sites").fetchall()
for s in sites:
    dst.execute(
        "INSERT OR IGNORE INTO sites (id, url, nome, categoria, ativo) VALUES (?, ?, ?, ?, ?)",
        (s["id"], s["url"], s["nome"], s["categoria"], s["ativo"]),
    )
dst.commit()
print(f"  ✓ {len(sites)} site(s) migrado(s)")

# ── Migrar snapshots em lotes ─────────────────────────────────────────────────
print("\n→ Migrando tabela snapshots...")
total = src.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
print(f"  Total: {total} registros")

LOTE = 500
offset = 0
migrados = 0
while True:
    rows = src.execute(
        "SELECT id, site_id, parceiro, tipo, percentual, unidade, capturado_em "
        "FROM snapshots ORDER BY id LIMIT ? OFFSET ?",
        (LOTE, offset)
    ).fetchall()
    if not rows:
        break
    for r in rows:
        dst.execute(
            "INSERT OR IGNORE INTO snapshots "
            "(id, site_id, parceiro, tipo, percentual, unidade, capturado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (r["id"], r["site_id"], r["parceiro"], r["tipo"],
             r["percentual"], r["unidade"], r["capturado_em"]),
        )
    dst.commit()
    migrados += len(rows)
    print(f"  {migrados}/{total}", end="\r")
    offset += LOTE

print(f"\n  ✓ {migrados} snapshot(s) migrado(s)")

# ── Migrar erros ──────────────────────────────────────────────────────────────
print("\n→ Migrando tabela erros_scraping...")
erros = src.execute("SELECT id, site_id, motivo, tentado_em FROM erros_scraping").fetchall()
for e in erros:
    dst.execute(
        "INSERT OR IGNORE INTO erros_scraping (id, site_id, motivo, tentado_em) VALUES (?, ?, ?, ?)",
        (e["id"], e["site_id"], e["motivo"], e["tentado_em"]),
    )
dst.commit()
print(f"  ✓ {len(erros)} erro(s) migrado(s)")

src.close()

# ── Verificação final ─────────────────────────────────────────────────────────
print("\n→ Verificação final no Turso:")

def count(table):
    r = dst.execute(f"SELECT COUNT(*) as n FROM {table}")
    rows = r.fetchall()
    return rows[0][0] if rows else 0

print(f"  sites:           {count('sites')}")
print(f"  snapshots:       {count('snapshots')}")
print(f"  erros_scraping:  {count('erros_scraping')}")

print("\n✅ Migração concluída com sucesso!")
print("\nPróximos passos:")
print("  1. Defina TURSO_URL e TURSO_TOKEN no docker-compose.yml")
print("  2. docker-compose down && docker-compose build --no-cache && docker-compose up -d")
