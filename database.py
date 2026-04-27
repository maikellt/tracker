import os
from datetime import datetime

import libsql_experimental as libsql

# ── Conexão ───────────────────────────────────────────────────────────────────

TURSO_URL   = os.getenv("TURSO_URL", "")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")

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
    if TURSO_URL and TURSO_TOKEN:
        conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
    else:
        # Fallback local para desenvolvimento
        import sqlite3
        conn = sqlite3.connect(os.getenv("DB_PATH", "/app/data/tracker.db"))
        conn.row_factory = sqlite3.Row
        return conn
    return conn


def _rows_to_dicts(rows):
    """Converte rows do libSQL para lista de dicts."""
    if rows is None:
        return []
    desc = rows.description
    if not desc:
        return []
    cols = [d[0] for d in desc]
    return [dict(zip(cols, row)) for row in rows.fetchall()]


def _row_to_dict(rows):
    dicts = _rows_to_dicts(rows)
    return dicts[0] if dicts else None


def inicializar_banco():
    conn = conectar()

    # libSQL não suporta executescript — executar DDL separadamente
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id        INTEGER PRIMARY KEY,
            url       TEXT NOT NULL UNIQUE,
            nome      TEXT NOT NULL,
            categoria TEXT NOT NULL,
            ativo     INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS erros_scraping (
            id         INTEGER PRIMARY KEY,
            site_id    INTEGER REFERENCES sites(id),
            motivo     TEXT    NOT NULL,
            tentado_em DATETIME DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    for site in SITES_INICIAIS:
        conn.execute(
            "INSERT OR IGNORE INTO sites (url, nome, categoria) VALUES (?, ?, ?)",
            (site["url"], site["nome"], site["categoria"]),
        )
    conn.commit()


# ── Sites ─────────────────────────────────────────────────────────────────────

def obter_sites_ativos():
    conn = conectar()
    rows = conn.execute("SELECT id, url, nome FROM sites WHERE ativo = 1")
    return [{"id": r["id"], "url": r["url"], "nome": r["nome"]}
            for r in _rows_to_dicts(rows)]


def obter_todos_sites():
    conn = conectar()
    rows = conn.execute("SELECT * FROM sites ORDER BY id")
    return _rows_to_dicts(rows)


def obter_site_por_id(site_id: int):
    conn = conectar()
    rows = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
    return _row_to_dict(rows)


def obter_site_por_url(url: str):
    conn = conectar()
    rows = conn.execute("SELECT * FROM sites WHERE url = ?", (url,))
    return _row_to_dict(rows)


def inserir_site(url: str, nome: str, categoria: str) -> int:
    conn = conectar()
    result = conn.execute(
        "INSERT INTO sites (url, nome, categoria) VALUES (?, ?, ?)",
        (url, nome, categoria),
    )
    conn.commit()
    return result.lastrowid


def reativar_site(site_id: int, nome: str, categoria: str):
    conn = conectar()
    conn.execute(
        "UPDATE sites SET ativo = 1, nome = ?, categoria = ? WHERE id = ?",
        (nome, categoria, site_id),
    )
    conn.commit()


def desativar_site(site_id: int):
    conn = conectar()
    conn.execute("UPDATE sites SET ativo = 0 WHERE id = ?", (site_id,))
    conn.commit()


# ── Snapshots ─────────────────────────────────────────────────────────────────

def salvar_snapshot(site_id: int, parceiro: str, tipo: str, percentual, unidade):
    conn = conectar()
    conn.execute(
        "INSERT INTO snapshots (site_id, parceiro, tipo, percentual, unidade) VALUES (?, ?, ?, ?, ?)",
        (site_id, parceiro, tipo, percentual, unidade),
    )
    conn.commit()


def registrar_erro(site_id: int, motivo: str):
    conn = conectar()
    conn.execute(
        "INSERT INTO erros_scraping (site_id, motivo) VALUES (?, ?)",
        (site_id, motivo),
    )
    conn.commit()


def obter_ultimo_scraping_sucesso(site_id: int):
    conn = conectar()
    rows = conn.execute(
        "SELECT MAX(capturado_em) as ultima FROM snapshots WHERE site_id = ?",
        (site_id,),
    )
    row = _row_to_dict(rows)
    valor = row["ultima"] if row else None
    if valor:
        try:
            return datetime.fromisoformat(valor)
        except ValueError:
            return None
    return None


def obter_parceiros_site(site_id: int) -> dict:
    conn = conectar()
    resultado = {"cashback": [], "pontos_milhas": []}

    for tipo in ["cashback", "pontos_milhas"]:
        rows_data = conn.execute(
            "SELECT MAX(capturado_em) as recente FROM snapshots WHERE site_id = ? AND tipo = ?",
            (site_id, tipo),
        )
        row_data = _row_to_dict(rows_data)
        data_recente = row_data["recente"] if row_data else None
        if not data_recente:
            continue

        rows_ativos = conn.execute(
            """
            SELECT parceiro, percentual, unidade, capturado_em
            FROM snapshots
            WHERE site_id = ? AND tipo = ? AND capturado_em = ?
            ORDER BY percentual DESC
            """,
            (site_id, tipo, data_recente),
        )
        ativos = _rows_to_dicts(rows_ativos)
        nomes_ativos = {r["parceiro"] for r in ativos}

        for r in ativos:
            resultado[tipo].append({
                "parceiro":      r["parceiro"],
                "status":        "ativo",
                "ultimo_valor":  r["percentual"],
                "unidade":       r["unidade"],
                "ultima_coleta": r["capturado_em"],
            })

        if nomes_ativos:
            placeholders = ",".join("?" * len(nomes_ativos))
            rows_inativos = conn.execute(
                f"""
                SELECT DISTINCT parceiro FROM snapshots
                WHERE site_id = ? AND tipo = ? AND parceiro NOT IN ({placeholders})
                """,
                (site_id, tipo, *nomes_ativos),
            )
            inativos = _rows_to_dicts(rows_inativos)
        else:
            rows_inativos = conn.execute(
                "SELECT DISTINCT parceiro FROM snapshots WHERE site_id = ? AND tipo = ?",
                (site_id, tipo),
            )
            inativos = _rows_to_dicts(rows_inativos)

        for r in inativos:
            rows_ultimo = conn.execute(
                """
                SELECT percentual, unidade, capturado_em FROM snapshots
                WHERE site_id = ? AND tipo = ? AND parceiro = ?
                ORDER BY capturado_em DESC LIMIT 1
                """,
                (site_id, tipo, r["parceiro"]),
            )
            ultimo = _row_to_dict(rows_ultimo)
            resultado[tipo].append({
                "parceiro":      r["parceiro"],
                "status":        "inativo",
                "ultimo_valor":  ultimo["percentual"] if ultimo else None,
                "unidade":       ultimo["unidade"] if ultimo else None,
                "ultima_coleta": ultimo["capturado_em"] if ultimo else None,
            })

    return resultado


def obter_snapshots_site(site_id: int, parceiro=None, tipo=None, dias=30) -> list:
    conn = conectar()
    query = """
        SELECT id, parceiro, tipo, percentual, unidade, capturado_em
        FROM snapshots
        WHERE site_id = ?
          AND capturado_em >= datetime('now', ?)
    """
    params = [site_id, f"-{dias} days"]

    if parceiro:
        query += " AND LOWER(parceiro) LIKE LOWER(?)"
        params.append(f"%{parceiro}%")
    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)

    query += " ORDER BY capturado_em DESC"
    rows = conn.execute(query, params)
    return _rows_to_dicts(rows)


def obter_max_site(site_id: int, dias=30) -> dict:
    conn = conectar()
    resultado = {"cashback": None, "pontos_milhas": None}

    for tipo in ["cashback", "pontos_milhas"]:
        rows = conn.execute(
            """
            SELECT percentual, parceiro, DATE(capturado_em) as data
            FROM snapshots
            WHERE site_id = ? AND tipo = ?
              AND percentual IS NOT NULL
              AND capturado_em >= datetime('now', ?)
            ORDER BY percentual DESC
            LIMIT 1
            """,
            (site_id, tipo, f"-{dias} days"),
        )
        row = _row_to_dict(rows)
        if row:
            resultado[tipo] = {
                "valor":    row["percentual"],
                "parceiro": row["parceiro"],
                "data":     row["data"],
            }

    return resultado


def verificar_alerta_sem_dados(site_id: int) -> bool:
    conn = conectar()
    rows = conn.execute(
        """
        SELECT COUNT(*) as total FROM snapshots
        WHERE site_id = ?
          AND percentual IS NOT NULL
          AND capturado_em >= datetime('now', '-2 days')
        """,
        (site_id,),
    )
    row = _row_to_dict(rows)
    return (row["total"] if row else 0) == 0
