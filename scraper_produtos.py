"""
scraper_produtos.py — Coleta de preços via Playwright (Chromium headless)
Serializa coletas com _coleta_lock para nunca abrir mais de 1 Chromium simultâneo.
"""
import asyncio
import json
import logging
import re
import threading
from datetime import datetime

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Flags para economizar memória — essencial no Render free tier (512 MB)
CHROMIUM_ARGS = [
    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
    "--single-process", "--no-zygote", "--disable-extensions",
    "--disable-background-networking", "--disable-default-apps",
    "--disable-sync", "--no-first-run", "--disable-translate",
    "--blink-settings=imagesEnabled=false",
    "--disable-renderer-backgrounding",
]

# Garante que apenas 1 Chromium roda por vez
_coleta_lock = threading.Lock()


def _log(nome: str, acao: str, msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [PRODUTO/{nome}] [{acao}] {msg}", flush=True)


def _parse_preco(texto: str) -> float | None:
    """Converte string de preço BR em float: 'R$ 1.234,56' → 1234.56"""
    if not texto:
        return None
    texto = re.sub(r'[R$\s]+', ' ', texto).strip()
    # 1.234,56  (ponto milhar, vírgula decimal)
    m = re.search(r'(\d{1,3}(?:\.\d{3})+),(\d{2})', texto)
    if m:
        return float(m.group(0).replace('.', '').replace(',', '.'))
    # 59,79
    m = re.search(r'(\d+),(\d{2})\b', texto)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    # 59.79  (formato US — alguns sites usam)
    m = re.search(r'(\d+)\.(\d{2})\b', texto)
    if m:
        v = float(f"{m.group(1)}.{m.group(2)}")
        if 0 < v < 100000:
            return v
    return None


async def _handle_route(route):
    """Bloqueia imagens, fontes e rastreadores — economiza ~40% de banda/memória."""
    url = route.request.url.lower()
    ext_bloquear = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico',
                    '.svg', '.woff', '.woff2', '.ttf', '.otf', '.mp4', '.mp3')
    rastreadores  = ('analytics', 'gtm', 'gtag', 'facebook', 'fbevents',
                     'hotjar', 'mixpanel', 'clarity', 'tiktok', 'doubleclick')
    if url.endswith(ext_bloquear) or any(r in url for r in rastreadores):
        await route.abort()
    else:
        await route.continue_()


async def _extrair_json_ld(page) -> float | None:
    """JSON-LD schema.org Product — funciona na maioria dos sites VTEX."""
    try:
        for script in await page.query_selector_all('script[type="application/ld+json"]'):
            try:
                data = json.loads(await script.inner_text())
                for item in (data if isinstance(data, list) else [data]):
                    if not isinstance(item, dict) or item.get('@type') != 'Product':
                        continue
                    offers = item.get('offers', {})
                    src = offers if isinstance(offers, dict) else {}
                    for campo in ('lowPrice', 'price'):
                        v = src.get(campo)
                        if v is not None:
                            return float(str(v).replace(',', '.'))
            except Exception:
                continue
    except Exception:
        pass
    return None


async def _extrair_meta(page) -> float | None:
    """Meta tags de preço (Open Graph, schema.org)."""
    for sel in [
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        'meta[itemprop="price"]',
        'meta[name="price"]',
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                v = _parse_preco(await el.get_attribute('content') or '')
                if v:
                    return v
        except Exception:
            continue
    return None


async def _extrair_css(page) -> float | None:
    """Seletores CSS como último recurso (VTEX, RD Saúde, Qualidoc, etc.)."""
    seletores = [
        '[class*="sellingPrice"]', '[class*="selling-price"]',
        '[class*="price-best"]',   '[class*="bestPrice"]',
        '[class*="price__best"]',  '.product__price',
        '[data-testid="price-value"]', '.product-price-value',
        '[class*="product-price"]',    '.price-value',
        '[data-testid="price"]',       '#preco-por', '.preco-por',
    ]
    for sel in seletores:
        try:
            el = await page.query_selector(sel)
            if el:
                v = _parse_preco(await el.inner_text())
                if v and v > 0:
                    return v
        except Exception:
            continue
    return None


async def _coletar_async(url: str, nome: str) -> float | None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        try:
            ctx = await browser.new_context(
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/124.0.0.0 Safari/537.36'
                ),
                locale='pt-BR',
            )
            page = await ctx.new_page()
            await page.route('**/*', _handle_route)
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await page.wait_for_timeout(3000)   # JS renderiza preços

            preco = await _extrair_json_ld(page)
            if preco:
                return preco
            preco = await _extrair_meta(page)
            if preco:
                return preco
            return await _extrair_css(page)
        finally:
            await browser.close()


def coletar_preco_produto(produto_id: int, url: str, nome: str):
    """Síncrono — chamado por threads do agendador e dos endpoints POST."""
    with _coleta_lock:
        try:
            _log(nome, 'SCRAPING', url)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                preco = loop.run_until_complete(_coletar_async(url, nome))
            finally:
                loop.close()

            if preco:
                from database import salvar_preco_produto, marcar_produto_bloqueado
                salvar_preco_produto(produto_id, preco)
                marcar_produto_bloqueado(produto_id, False)
                _log(nome, 'OK', f'R$ {preco:.2f}')
            else:
                from database import marcar_produto_bloqueado
                marcar_produto_bloqueado(produto_id, True)
                _log(nome, 'AVISO', 'Preço não encontrado — coleta bloqueada ou estrutura não suportada')
        except Exception as e:
            _log(nome, 'ERRO', str(e))


def coletar_todos_produtos():
    """Chamado pelo agendador — processa produtos ativos sequencialmente."""
    from database import obter_todos_produtos_ativos
    produtos = obter_todos_produtos_ativos()
    _log('GERAL', 'INICIO', f'{len(produtos)} produto(s) na fila')
    for p in produtos:
        coletar_preco_produto(p['id'], p['url'], p['nome'])
    _log('GERAL', 'FIM', 'Coleta de produtos concluída')
