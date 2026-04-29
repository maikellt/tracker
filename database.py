import os
import sqlite3
import threading
import logging
from datetime import datetime

import libsql_experimental as libsql

logger = logging.getLogger(__name__)

# ── Configuração ──────────────────────────────────────────────────────────────

TURSO_URL   = os.getenv("TURSO_URL", "")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")
LOCAL_DB    = "/tmp/tracker_local.db"  # SQLite em /tmp — rápido, efêmero

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

_turso_conn  = None
_thread_local = threading.local()
_sync_lock    = threading.Lock()


# ── Conexões ──────────────────────────────────────────────────────────────────

def _turso():
    global _turso_conn
    if _turso_conn is None and TURSO_URL and TURSO_TOKEN:
        _turso_conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
    return _turso_conn


def _local():
    """Retorna conexão SQLite exclusiva para a thread atual."""
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(LOCAL_DB)
        _thread_local.conn.row_factory = sqlite3.Row
        _thread_local.conn.execute("PRAGMA journal_mode=WAL")
        _thread_local.conn.execute("PRAGMA synchronous=NORMAL")
    return _thread_local.conn


def _local_exec(sql, params=()):
    return _local().execute(sql, params)


def _local_write(sql, params=()):
    conn = _local()
    result = conn.execute(sql, params)
    conn.commit()
    return result


def _turso_write_async(sql, params=()):
    """Replica escrita no Turso de forma assíncrona — não bloqueia."""
    def _sync():
        with _sync_lock:
            try:
                t = _turso()
                if t:
                    t.execute(sql, params)
                    t.commit()
            except Exception as e:
                logger.warning(f"[TURSO] Falha na replicação: {e}")
    threading.Thread(target=_sync, daemon=True).start()


# ── Schema ────────────────────────────────────────────────────────────────────

DDL = [
    """CREATE TABLE IF NOT EXISTS sites (
        id        INTEGER PRIMARY KEY,
        url       TEXT NOT NULL UNIQUE,
        nome      TEXT NOT NULL,
        categoria TEXT NOT NULL,
        ativo     INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS snapshots (
        id           INTEGER PRIMARY KEY,
        site_id      INTEGER REFERENCES sites(id),
        parceiro     TEXT    NOT NULL,
        tipo         TEXT    NOT NULL,
        percentual   REAL,
        unidade      TEXT,
        capturado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS erros_scraping (
        id         INTEGER PRIMARY KEY,
        site_id    INTEGER REFERENCES sites(id),
        motivo     TEXT    NOT NULL,
        tentado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS configuracoes (
        chave TEXT PRIMARY KEY,
        valor TEXT NOT NULL
    )""",
]


def _criar_schema_local():
    for ddl in DDL:
        _local_write(ddl)


# ── Sincronização Turso → SQLite local ───────────────────────────────────────

def _rows_turso(sql, params=()):
    t = _turso()
    if not t:
        return []
    cur = t.execute(sql, params)
    desc = cur.description
    if not desc:
        return []
    cols = [d[0] for d in desc]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _sincronizar_do_turso():
    """Copia todos os dados do Turso para o SQLite local."""
    logger.info("[SYNC] Iniciando sincronização Turso → local...")

    # Sites
    sites = _rows_turso("SELECT id, url, nome, categoria, ativo FROM sites")
    for s in sites:
        _local_write(
            "INSERT OR REPLACE INTO sites (id, url, nome, categoria, ativo) VALUES (?,?,?,?,?)",
            (s["id"], s["url"], s["nome"], s["categoria"], s["ativo"]),
        )
    logger.info(f"[SYNC] {len(sites)} site(s) sincronizado(s)")

    # Snapshots em lotes
    total = _rows_turso("SELECT COUNT(*) as n FROM snapshots")[0]["n"]
    LOTE, offset, sync = 1000, 0, 0
    while True:
        rows = _rows_turso(
            "SELECT id, site_id, parceiro, tipo, percentual, unidade, capturado_em "
            "FROM snapshots ORDER BY id LIMIT ? OFFSET ?",
            (LOTE, offset)
        )
        if not rows:
            break
        for r in rows:
            _local_write(
                "INSERT OR REPLACE INTO snapshots "
                "(id, site_id, parceiro, tipo, percentual, unidade, capturado_em) "
                "VALUES (?,?,?,?,?,?,?)",
                (r["id"], r["site_id"], r["parceiro"], r["tipo"],
                 r["percentual"], r["unidade"], r["capturado_em"]),
            )
        sync += len(rows)
        offset += LOTE
    logger.info(f"[SYNC] {sync}/{total} snapshot(s) sincronizado(s)")

    # Erros
    erros = _rows_turso("SELECT id, site_id, motivo, tentado_em FROM erros_scraping")
    for e in erros:
        _local_write(
            "INSERT OR REPLACE INTO erros_scraping (id, site_id, motivo, tentado_em) VALUES (?,?,?,?)",
            (e["id"], e["site_id"], e["motivo"], e["tentado_em"]),
        )
    logger.info(f"[SYNC] {len(erros)} erro(s) sincronizado(s)")
    logger.info("[SYNC] Sincronização concluída")


def _sincronizar_configuracoes_do_turso():
    """Sincroniza tabela configuracoes do Turso para o SQLite local."""
    rows = _rows_turso("SELECT chave, valor FROM configuracoes")
    for r in rows:
        _local_write(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
            (r["chave"], r["valor"]),
        )
    logger.info(f"[SYNC] {len(rows)} configuração(ões) sincronizada(s)")


# ── Inicialização ─────────────────────────────────────────────────────────────

def inicializar_banco():
    _criar_schema_local()

    if TURSO_URL and TURSO_TOKEN:
        # Criar schema no Turso se necessário
        t = _turso()
        for ddl in DDL:
            t.execute(ddl)
        t.commit()
        # Sincronizar dados do Turso para local
        _sincronizar_do_turso()
    else:
        # Modo local puro (dev)
        for site in SITES_INICIAIS:
            _local_write(
                "INSERT OR IGNORE INTO sites (url, nome, categoria) VALUES (?,?,?)",
                (site["url"], site["nome"], site["categoria"]),
            )


# ── Sites ─────────────────────────────────────────────────────────────────────

def _row(sql, params=()):
    row = _local_exec(sql, params).fetchone()
    return dict(row) if row else None


def _rows(sql, params=()):
    return [dict(r) for r in _local_exec(sql, params).fetchall()]


def obter_sites_ativos():
    return _rows("SELECT id, url, nome FROM sites WHERE ativo = 1")


def obter_todos_sites():
    return _rows("SELECT * FROM sites ORDER BY id")


def obter_site_por_id(site_id: int):
    return _row("SELECT * FROM sites WHERE id = ?", (site_id,))


def obter_site_por_url(url: str):
    return _row("SELECT * FROM sites WHERE url = ?", (url,))


def inserir_site(url: str, nome: str, categoria: str) -> int:
    result = _local_write(
        "INSERT INTO sites (url, nome, categoria) VALUES (?,?,?)",
        (url, nome, categoria),
    )
    site_id = result.lastrowid
    _turso_write_async(
        "INSERT OR IGNORE INTO sites (id, url, nome, categoria) VALUES (?,?,?,?)",
        (site_id, url, nome, categoria),
    )
    return site_id


def reativar_site(site_id: int, nome: str, categoria: str):
    _local_write(
        "UPDATE sites SET ativo=1, nome=?, categoria=? WHERE id=?",
        (nome, categoria, site_id),
    )
    _turso_write_async(
        "UPDATE sites SET ativo=1, nome=?, categoria=? WHERE id=?",
        (nome, categoria, site_id),
    )


def desativar_site(site_id: int):
    _local_write("UPDATE sites SET ativo=0 WHERE id=?", (site_id,))
    _turso_write_async("UPDATE sites SET ativo=0 WHERE id=?", (site_id,))


# ── Snapshots ─────────────────────────────────────────────────────────────────

def banco_tem_dados() -> bool:
    """Retorna True se já existem snapshots no banco local.
    Chamado no startup para evitar coleta desnecessária após sincronização do Turso.
    Quando o container reinicia, o Turso sincroniza tudo — não há motivo para
    coletar imediatamente e potencialmente sobrescrever dados recentes."""
    row = _row("SELECT COUNT(*) as total FROM snapshots")
    return (row["total"] if row else 0) > 0


def salvar_snapshot(site_id: int, parceiro: str, tipo: str, percentual, unidade):
    result = _local_write(
        "INSERT INTO snapshots (site_id, parceiro, tipo, percentual, unidade) VALUES (?,?,?,?,?)",
        (site_id, parceiro, tipo, percentual, unidade),
    )
    snap_id = result.lastrowid
    # Buscar capturado_em gerado pelo SQLite para replicar igual
    row = _row("SELECT capturado_em FROM snapshots WHERE id=?", (snap_id,))
    cap = row["capturado_em"] if row else None
    _turso_write_async(
        "INSERT INTO snapshots (id, site_id, parceiro, tipo, percentual, unidade, capturado_em) "
        "VALUES (?,?,?,?,?,?,?)",
        (snap_id, site_id, parceiro, tipo, percentual, unidade, cap),
    )


def registrar_erro(site_id: int, motivo: str):
    result = _local_write(
        "INSERT INTO erros_scraping (site_id, motivo) VALUES (?,?)",
        (site_id, motivo),
    )
    err_id = result.lastrowid
    row = _row("SELECT tentado_em FROM erros_scraping WHERE id=?", (err_id,))
    tent = row["tentado_em"] if row else None
    _turso_write_async(
        "INSERT INTO erros_scraping (id, site_id, motivo, tentado_em) VALUES (?,?,?,?)",
        (err_id, site_id, motivo, tent),
    )


def obter_ultimo_scraping_sucesso(site_id: int):
    row = _row(
        "SELECT MAX(capturado_em) as ultima FROM snapshots WHERE site_id=?",
        (site_id,),
    )
    valor = row["ultima"] if row else None
    if valor:
        try:
            return datetime.fromisoformat(valor)
        except ValueError:
            return None
    return None


def obter_parceiros_site(site_id: int) -> dict:
    resultado = {"cashback": [], "pontos_milhas": []}

    for tipo in ["cashback", "pontos_milhas"]:
        row_data = _row(
            "SELECT MAX(capturado_em) as recente FROM snapshots WHERE site_id=? AND tipo=?",
            (site_id, tipo),
        )
        data_recente = row_data["recente"] if row_data else None
        if not data_recente:
            continue

        ativos = _rows(
            """SELECT parceiro, percentual, unidade, capturado_em
               FROM snapshots
               WHERE site_id=? AND tipo=? AND capturado_em=?
               ORDER BY percentual DESC""",
            (site_id, tipo, data_recente),
        )
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
            inativos = _rows(
                f"SELECT DISTINCT parceiro FROM snapshots "
                f"WHERE site_id=? AND tipo=? AND parceiro NOT IN ({placeholders})",
                (site_id, tipo, *nomes_ativos),
            )
        else:
            inativos = _rows(
                "SELECT DISTINCT parceiro FROM snapshots WHERE site_id=? AND tipo=?",
                (site_id, tipo),
            )

        for r in inativos:
            ultimo = _row(
                """SELECT percentual, unidade, capturado_em FROM snapshots
                   WHERE site_id=? AND tipo=? AND parceiro=?
                   ORDER BY capturado_em DESC LIMIT 1""",
                (site_id, tipo, r["parceiro"]),
            )
            resultado[tipo].append({
                "parceiro":      r["parceiro"],
                "status":        "inativo",
                "ultimo_valor":  ultimo["percentual"] if ultimo else None,
                "unidade":       ultimo["unidade"] if ultimo else None,
                "ultima_coleta": ultimo["capturado_em"] if ultimo else None,
            })

    return resultado


def obter_snapshots_site(site_id: int, parceiro=None, tipo=None, dias=30) -> list:
    query = """
        SELECT id, parceiro, tipo, percentual, unidade, capturado_em
        FROM snapshots
        WHERE site_id=? AND capturado_em >= datetime('now', ?)
    """
    params = [site_id, f"-{dias} days"]
    if parceiro:
        query += " AND LOWER(parceiro) LIKE LOWER(?)"
        params.append(f"%{parceiro}%")
    if tipo:
        query += " AND tipo=?"
        params.append(tipo)
    query += " ORDER BY capturado_em DESC"
    return _rows(query, params)


def obter_max_site(site_id: int, dias=30) -> dict:
    resultado = {"cashback": None, "pontos_milhas": None}
    for tipo in ["cashback", "pontos_milhas"]:
        row = _row(
            """SELECT percentual, parceiro, DATE(capturado_em) as data
               FROM snapshots
               WHERE site_id=? AND tipo=? AND percentual IS NOT NULL
                 AND capturado_em >= datetime('now', ?)
               ORDER BY percentual DESC LIMIT 1""",
            (site_id, tipo, f"-{dias} days"),
        )
        if row:
            resultado[tipo] = {
                "valor":    row["percentual"],
                "parceiro": row["parceiro"],
                "data":     row["data"],
            }
    return resultado


# ── Configurações persistidas ─────────────────────────────────────────────────

def obter_configuracao(chave: str) -> dict | None:
    """Retorna o valor JSON de uma chave de configuração, ou None se não existir."""
    import json
    row = _row("SELECT valor FROM configuracoes WHERE chave = ?", (chave,))
    if not row:
        return None
    try:
        return json.loads(row["valor"])
    except Exception:
        return None


def salvar_configuracao(chave: str, dados: dict):
    """Salva ou atualiza uma configuração no banco local e replica no Turso."""
    import json
    valor = json.dumps(dados, ensure_ascii=False)
    _local_write(
        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
        (chave, valor),
    )
    _turso_write_async(
        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
        (chave, valor),
    )


def verificar_alerta_sem_dados(site_id: int) -> bool:
    row = _row(
        """SELECT COUNT(*) as total FROM snapshots
           WHERE site_id=? AND percentual IS NOT NULL
             AND capturado_em >= datetime('now', '-2 days')""",
        (site_id,),
    )
    return (row["total"] if row else 0) == 0
