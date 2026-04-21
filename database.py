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


# ── Helpers de sites ──────────────────────────────────────────────────────────

def _row_to_dict(row):
    return dict(row) if row else None


def obter_sites_ativos():
    conn = conectar()
    rows = conn.execute("SELECT id, url, nome FROM sites WHERE ativo = 1").fetchall()
    conn.close()
    return [{"id": r["id"], "url": r["url"], "nome": r["nome"]} for r in rows]


def obter_todos_sites():
    conn = conectar()
    rows = conn.execute("SELECT * FROM sites ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obter_site_por_id(site_id: int):
    conn = conectar()
    row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def obter_site_por_url(url: str):
    conn = conectar()
    row = conn.execute("SELECT * FROM sites WHERE url = ?", (url,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def inserir_site(url: str, nome: str, categoria: str) -> int:
    conn = conectar()
    cursor = conn.execute(
        "INSERT INTO sites (url, nome, categoria) VALUES (?, ?, ?)",
        (url, nome, categoria),
    )
    site_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return site_id


def reativar_site(site_id: int, nome: str, categoria: str):
    conn = conectar()
    conn.execute(
        "UPDATE sites SET ativo = 1, nome = ?, categoria = ? WHERE id = ?",
        (nome, categoria, site_id),
    )
    conn.commit()
    conn.close()


def desativar_site(site_id: int):
    conn = conectar()
    conn.execute("UPDATE sites SET ativo = 0 WHERE id = ?", (site_id,))
    conn.commit()
    conn.close()


# ── Snapshots ─────────────────────────────────────────────────────────────────

def salvar_snapshot(site_id: int, parceiro: str, tipo: str, percentual, unidade):
    conn = conectar()
    conn.execute(
        "INSERT INTO snapshots (site_id, parceiro, tipo, percentual, unidade) VALUES (?, ?, ?, ?, ?)",
        (site_id, parceiro, tipo, percentual, unidade),
    )
    conn.commit()
    conn.close()


def registrar_erro(site_id: int, motivo: str):
    conn = conectar()
    conn.execute(
        "INSERT INTO erros_scraping (site_id, motivo) VALUES (?, ?)",
        (site_id, motivo),
    )
    conn.commit()
    conn.close()


def obter_ultimo_scraping_sucesso(site_id: int):
    """Retorna o datetime da última coleta bem-sucedida (com ao menos 1 snapshot)."""
    conn = conectar()
    row = conn.execute(
        "SELECT MAX(capturado_em) FROM snapshots WHERE site_id = ?",
        (site_id,),
    ).fetchone()
    conn.close()
    valor = row[0] if row else None
    if valor:
        try:
            return datetime.fromisoformat(valor)
        except ValueError:
            return None
    return None


def obter_parceiros_site(site_id: int) -> dict:
    """
    Retorna parceiros agrupados por tipo, com status ativo/inativo.
    'ativo' = parceiro presente no snapshot mais recente do tipo.
    'inativo' = ausente no mais recente, mas com histórico.
    """
    conn = conectar()

    resultado = {"cashback": [], "pontos_milhas": []}

    for tipo in ["cashback", "pontos_milhas"]:
        # Data da coleta mais recente deste tipo
        row_data = conn.execute(
            """
            SELECT MAX(capturado_em) FROM snapshots
            WHERE site_id = ? AND tipo = ?
            """,
            (site_id, tipo),
        ).fetchone()
        data_recente = row_data[0] if row_data else None

        if not data_recente:
            continue

        # Parceiros presentes na coleta mais recente
        ativos = conn.execute(
            """
            SELECT parceiro, percentual, unidade, capturado_em
            FROM snapshots
            WHERE site_id = ? AND tipo = ? AND capturado_em = ?
            ORDER BY percentual DESC NULLS LAST
            """,
            (site_id, tipo, data_recente),
        ).fetchall()
        nomes_ativos = {r["parceiro"] for r in ativos}

        for r in ativos:
            resultado[tipo].append({
                "parceiro": r["parceiro"],
                "status": "ativo",
                "ultimo_valor": r["percentual"],
                "unidade": r["unidade"],
                "ultima_coleta": r["capturado_em"],
            })

        # Parceiros com histórico mas ausentes na última coleta
        inativos = conn.execute(
            """
            SELECT DISTINCT parceiro FROM snapshots
            WHERE site_id = ? AND tipo = ? AND parceiro NOT IN ({})
            """.format(",".join("?" * len(nomes_ativos))),
            (site_id, tipo, *nomes_ativos),
        ).fetchall()

        for r in inativos:
            ultimo = conn.execute(
                """
                SELECT percentual, unidade, capturado_em FROM snapshots
                WHERE site_id = ? AND tipo = ? AND parceiro = ?
                ORDER BY capturado_em DESC LIMIT 1
                """,
                (site_id, tipo, r["parceiro"]),
            ).fetchone()
            resultado[tipo].append({
                "parceiro": r["parceiro"],
                "status": "inativo",
                "ultimo_valor": ultimo["percentual"] if ultimo else None,
                "unidade": ultimo["unidade"] if ultimo else None,
                "ultima_coleta": ultimo["capturado_em"] if ultimo else None,
            })

    conn.close()
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

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "parceiro": r["parceiro"],
            "tipo": r["tipo"],
            "percentual": r["percentual"],
            "unidade": r["unidade"],
            "capturado_em": r["capturado_em"],
        }
        for r in rows
    ]


def obter_max_site(site_id: int, dias=30) -> dict:
    conn = conectar()
    resultado = {"cashback": None, "pontos_milhas": None}

    for tipo in ["cashback", "pontos_milhas"]:
        row = conn.execute(
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
        ).fetchone()
        if row:
            resultado[tipo] = {
                "valor": row["percentual"],
                "parceiro": row["parceiro"],
                "data": row["data"],
            }

    conn.close()
    return resultado


def verificar_alerta_sem_dados(site_id: int) -> bool:
    """
    Retorna True se o site não gerou nenhum snapshot com percentual não-nulo
    nos últimos 2 dias consecutivos.
    """
    conn = conectar()
    row = conn.execute(
        """
        SELECT COUNT(*) FROM snapshots
        WHERE site_id = ?
          AND percentual IS NOT NULL
          AND capturado_em >= datetime('now', '-2 days')
        """,
        (site_id,),
    ).fetchone()
    conn.close()
    return row[0] == 0


def obter_ultima_coleta_site(site_id: int):
    """Retorna o datetime ISO da ultima coleta (qualquer snapshot) do site."""
    conn = conectar()
    row = conn.execute(
        "SELECT MAX(capturado_em) as ultima FROM snapshots WHERE site_id = ?",
        (site_id,),
    ).fetchone()
    conn.close()
    return row["ultima"] if row and row["ultima"] else None
