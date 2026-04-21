import re
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from database import salvar_snapshot, registrar_erro

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 30
MAX_TENTATIVAS = 16
INTERVALO_RETRY = 900  # 15 minutos


def _log(nome_site: str, acao: str, mensagem: str):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] [{nome_site}] [{acao}] {mensagem}", flush=True)


def scrape_site(site_id: int, url: str) -> str:
    resposta = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resposta.raise_for_status()
    return resposta.text


def parsear_tabelas(html: str) -> dict:
    """
    Retorna dict com chaves 'cashback' e 'pontos_milhas',
    cada uma contendo lista de (parceiro, texto_valor).
    """
    soup = BeautifulSoup(html, "lxml")
    resultado = {"cashback": [], "pontos_milhas": []}

    for tabela in soup.find_all("table"):
        cabecalho = tabela.find("thead")
        if not cabecalho:
            continue
        texto_cabecalho = cabecalho.get_text(separator=" ").strip().lower()

        if "cashback" in texto_cabecalho:
            tipo = "cashback"
        elif "pontos" in texto_cabecalho or "milhas" in texto_cabecalho:
            tipo = "pontos_milhas"
        else:
            continue

        corpo = tabela.find("tbody")
        if not corpo:
            continue

        for linha in corpo.find_all("tr"):
            colunas = linha.find_all("td")
            if len(colunas) >= 2:
                parceiro = colunas[0].get_text(strip=True)
                valor_texto = colunas[1].get_text(strip=True)
                if parceiro:
                    resultado[tipo].append((parceiro, valor_texto))

    return resultado


def normalizar_valor(texto: str):
    """
    Converte string de valor em (float | None, str | None).
    Exemplos:
        '3% de cashback'  -> (3.0, '%')
        '1,50 pontos'     -> (1.5, 'pontos')
        '2 pts'           -> (2.0, 'pontos')
    """
    texto_lower = texto.lower()

    # Inferir unidade
    if "%" in texto_lower or "cashback" in texto_lower:
        unidade = "%"
    elif "ponto" in texto_lower or "pts" in texto_lower or "milha" in texto_lower:
        unidade = "pontos"
    else:
        unidade = None

    # Extrair número (suporte a vírgula decimal)
    match = re.search(r"(\d+[.,]?\d*)", texto)
    if match:
        numero_str = match.group(1).replace(",", ".")
        try:
            valor = float(numero_str)
            return (valor, unidade)
        except ValueError:
            pass

    return (None, None)


def coletar_site(site_id: int, url: str, nome_site: str):
    """Orquestra scrape → parse → normalizar → salvar, com retentativas."""
    tentativa = 0

    while tentativa <= MAX_TENTATIVAS:
        try:
            if tentativa > 0:
                _log(nome_site, "RETRY", f"Tentativa {tentativa}/{MAX_TENTATIVAS}")
            else:
                _log(nome_site, "SCRAPING", "Iniciando coleta")

            html = scrape_site(site_id, url)
            tabelas = parsear_tabelas(html)

            total_cashback = 0
            total_pontos = 0

            for parceiro, valor_texto in tabelas["cashback"]:
                percentual, unidade = normalizar_valor(valor_texto)
                if percentual is None:
                    _log(nome_site, "AVISO", f"Valor não extraído para parceiro {parceiro}")
                else:
                    _log(nome_site, "PARCEIRO", f"{parceiro} → {percentual}{unidade} cashback")
                salvar_snapshot(site_id, parceiro, "cashback", percentual, unidade)
                total_cashback += 1

            for parceiro, valor_texto in tabelas["pontos_milhas"]:
                percentual, unidade = normalizar_valor(valor_texto)
                if percentual is None:
                    _log(nome_site, "AVISO", f"Valor não extraído para parceiro {parceiro}")
                else:
                    _log(nome_site, "PARCEIRO", f"{parceiro} → {percentual} {unidade} pontos/milhas")
                salvar_snapshot(site_id, parceiro, "pontos_milhas", percentual, unidade)
                total_pontos += 1

            _log(nome_site, "OK", f"{total_cashback} parceiros cashback, {total_pontos} pontos/milhas")
            return  # sucesso — encerrar

        except requests.exceptions.Timeout:
            motivo = "Timeout ao acessar URL"
            _log(nome_site, "ERRO", motivo)
            registrar_erro(site_id, motivo)
        except requests.exceptions.HTTPError as e:
            motivo = f"HTTP {e.response.status_code} ao acessar URL"
            _log(nome_site, "ERRO", motivo)
            registrar_erro(site_id, motivo)
        except Exception as e:
            motivo = f"Exceção inesperada: {e}"
            _log(nome_site, "ERRO", motivo)
            registrar_erro(site_id, motivo)

        tentativa += 1
        if tentativa <= MAX_TENTATIVAS:
            time.sleep(INTERVALO_RETRY)

    _log(nome_site, "ERRO", "Máximo de tentativas atingido. Aguardando próximo ciclo.")
