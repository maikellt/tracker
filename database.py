import sqlite3
import os
from datetime import datetime

CAMINHO_BANCO = os.getenv("DB_PATH", "/app/data/tracker.db")

SITES_INICIAIS = [
    {
        "url": "https://www.comparemania.com.br/cashback-drogaria-sao-paulo",
        "nome": "Drogaria SP",
        "categoria": "Farmácia",
    },
    {
        "url": "https://www.comparemania.com.br/cashback-qualidoc",
        "nome": "Qualidoc",
        "categoria": "Farmácia",
    },
]


def conectar():
    os.makedirs(os.path.dirname(CAMINHO_BANCO), exist_ok=True)
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_banco():
    conn = conectar()
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS sites (
            id        INTEGER PRIMARY KEY,
            url       TEXT NOT NULL UNIQUE,
            nome      TEXT NOT NULL,
            categoria TEXT NOT NULL,
            ativo     INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id           INTEGER PRIMARY KEY,
            site_id      INTEGER REFERENCES sites(id),
            parceiro     TEXT    NOT NULL,
            tipo         TEXT    NOT NULL,
            percentual   REAL,
            unidade      TEXT,
            capturado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS erros_scraping (
            id         INTEGER PRIMARY KEY,
            site_id    INTEGER REFERENCES sites(id),
            motivo     TEXT    NOT NULL,
            tentado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    for site in SITES_INICIAIS:
        cursor.execute(
            "INSERT OR IGNORE INTO sites (url, nome, categoria) VALUES (?, ?, ?)",
            (site["url"], site["nome"], site["categoria"]),
        )
    conn.commit()
    conn.close()


def obter_sites_ativos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, nome FROM sites WHERE ativo = 1")
    sites = [{"id": row["id"], "url": row["url"], "nome": row["nome"]} for row in cursor.fetchall()]
    conn.close()
    return sites


def salvar_snapshot(site_id: int, parceiro: str, tipo: str, percentual, unidade):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO snapshots (site_id, parceiro, tipo, percentual, unidade) VALUES (?, ?, ?, ?, ?)",
        (site_id, parceiro, tipo, percentual, unidade),
    )
    conn.commit()
    conn.close()


def registrar_erro(site_id: int, motivo: str):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO erros_scraping (site_id, motivo) VALUES (?, ?)",
        (site_id, motivo),
    )
    conn.commit()
    conn.close()
