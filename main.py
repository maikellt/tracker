import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from database import (
    inicializar_banco,
    obter_sites_ativos,
    obter_todos_sites,
    obter_site_por_id,
    obter_site_por_url,
    inserir_site,
    reativar_site,
    desativar_site,
    obter_parceiros_site,
    obter_snapshots_site,
    obter_max_site,
    verificar_alerta_sem_dados,
    obter_ultima_coleta_site,
)
from scraper import coletar_site
from agendador import iniciar_agendador, parar_agendador, reconfigurar_agendador, obter_config


# ── Conteúdo estático embutido ────────────────────────────────────────────────

_INDEX_HTML = """<!DOCTYPE html>
<html lang="pt-BR" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CashbackTracker</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%2301696f'/><text x='50%25' y='56%25' dominant-baseline='middle' text-anchor='middle' font-size='18' fill='white'>₢</text></svg>" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0f1117; --surface: #161b22; --surface2: #1c2128; --border: #30363d;
      --text: #e6edf3; --muted: #8b949e; --faint: #484f58;
      --primary: #3fb950; --primary-d: #2ea043; --primary-bg: #1a2d1c;
      --accent: #58a6ff; --accent-bg: #1a2333;
      --warn: #d29922; --warn-bg: #2d2416;
      --error: #f85149; --error-bg: #2d1a1a;
      --radius: 8px; --radius-lg: 12px;
      --font: 'Inter', system-ui, sans-serif;
    }
    html { font-family: var(--font); font-size: 14px; color: var(--text); background: var(--bg); }
    body { min-height: 100dvh; display: flex; flex-direction: column; }
    a { color: var(--accent); text-decoration: none; }
    button { cursor: pointer; font-family: inherit; font-size: 13px; border: none; border-radius: var(--radius); transition: background 140ms, opacity 140ms; }
    input, select { font-family: inherit; font-size: 13px; background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: var(--radius); padding: 6px 10px; outline: none; width: 100%; }
    input:focus, select:focus { border-color: var(--accent); }
    label { font-size: 12px; color: var(--muted); display: block; margin-bottom: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }
    td { padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: var(--surface2); }
    .badge { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 500; padding: 2px 8px; border-radius: 20px; }
    .badge-green { background: var(--primary-bg); color: var(--primary); }
    .badge-gray  { background: #21262d; color: var(--muted); }
    .badge-warn  { background: var(--warn-bg); color: var(--warn); }
    .badge-red   { background: var(--error-bg); color: var(--error); }
    .btn { padding: 6px 14px; font-weight: 500; border-radius: var(--radius); border: 1px solid transparent; }
    .btn-primary { background: var(--primary); color: #0d1117; border-color: var(--primary); }
    .btn-primary:hover { background: var(--primary-d); }
    .btn-ghost { background: transparent; color: var(--text); border-color: var(--border); }
    .btn-ghost:hover { background: var(--surface2); }
    .btn-danger { background: transparent; color: var(--error); border-color: var(--error); }
    .btn-danger:hover { background: var(--error-bg); }
    .btn-sm { padding: 4px 10px; font-size: 12px; }
    header { display: flex; align-items: center; gap: 12px; padding: 0 20px; height: 52px; background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0; }
    .logo { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 15px; color: var(--text); }
    .logo svg { color: var(--primary); }
    nav { display: flex; gap: 2px; margin-left: 12px; }
    .tab-btn { padding: 6px 14px; background: transparent; border: none; color: var(--muted); border-radius: var(--radius); font-size: 13px; font-weight: 500; transition: color 140ms, background 140ms; }
    .tab-btn:hover { color: var(--text); background: var(--surface2); }
    .tab-btn.active { color: var(--text); background: var(--surface2); }
    main { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
    .tab-panel { display: none; flex: 1; overflow-y: auto; padding: 20px; }
    .tab-panel.active { display: flex; flex-direction: column; gap: 16px; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
    .card-header { padding: 14px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .card-header h2 { font-size: 13px; font-weight: 600; color: var(--text); }
    .card-body { padding: 16px; }
    .alert-banner { display: flex; align-items: flex-start; gap: 10px; padding: 12px 16px; background: var(--warn-bg); border: 1px solid #5a3e1a; border-radius: var(--radius); font-size: 13px; color: var(--warn); }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
    .summary-card { background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; }
    .summary-card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
    .summary-card .value { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--primary); }
    .summary-card .sub { font-size: 11px; color: var(--muted); margin-top: 4px; }
    .filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
    .filters .field { min-width: 160px; flex: 1; }
    .chart-wrap { position: relative; width: 100%; height: 280px; }
    .form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
    .feedback { font-size: 12px; margin-top: 8px; padding: 6px 10px; border-radius: var(--radius); }
    .feedback-ok   { background: var(--primary-bg); color: var(--primary); }
    .feedback-err  { background: var(--error-bg); color: var(--error); }
    .feedback-warn { background: var(--warn-bg); color: var(--warn); }
    .config-form { display: flex; flex-direction: column; gap: 16px; max-width: 400px; }
    .config-form .field { display: flex; flex-direction: column; gap: 4px; }
    dialog { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); color: var(--text); padding: 24px; max-width: 400px; width: 90vw; }
    dialog::backdrop { background: rgba(0,0,0,.6); }
    .dialog-title { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
    .dialog-msg { font-size: 13px; color: var(--muted); margin-bottom: 20px; line-height: 1.5; }
    .dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
    tr.inativo td { opacity: .5; }
    .toggle-acesso { display: flex; align-items: center; gap: 6px; cursor: pointer; user-select: none; font-size: 12px; color: var(--muted); }
    .toggle-acesso input[type=checkbox] { accent-color: var(--primary); width: 14px; height: 14px; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--faint); border-radius: 3px; }
    .empty { text-align: center; color: var(--muted); padding: 40px; font-size: 13px; }
    @media (max-width: 600px) { .tab-btn span { display: none; } header { padding: 0 12px; } .tab-panel { padding: 12px; } }
  </style>
</head>
<body>
<header>
  <div class="logo">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 6v2m0 8v2"/>
    </svg>
    CashbackTracker
  </div>
  <nav role="tablist" aria-label="Navegação principal">
    <button class="tab-btn active" role="tab" aria-selected="true"  aria-controls="tab-painel" id="btn-painel" onclick="mudarAba('painel')">&#128202; <span>Painel</span></button>
    <button class="tab-btn"        role="tab" aria-selected="false" aria-controls="tab-sites"  id="btn-sites"  onclick="mudarAba('sites')">&#127760; <span>Sites</span></button>
    <button class="tab-btn"        role="tab" aria-selected="false" aria-controls="tab-config" id="btn-config" onclick="mudarAba('config')">&#9881;&#65039; <span>Configurações</span></button>
  </nav>
</header>
<main>
  <section class="tab-panel active" id="tab-painel" role="tabpanel" aria-labelledby="btn-painel">
    <div id="alertas-container"></div>
    <div class="card">
      <div class="card-header"><h2>Filtros</h2></div>
      <div class="card-body">
        <div class="filters">
          <div class="field"><label for="filtro-site">Site</label><select id="filtro-site" onchange="aplicarFiltros()"><option value="">Todos</option></select></div>
          <div class="field"><label for="filtro-categoria">Categoria</label><select id="filtro-categoria" onchange="aplicarFiltros()"><option value="">Todas</option></select></div>
          <div class="field" style="max-width:180px"><label for="filtro-tipo">Tipo</label><select id="filtro-tipo" onchange="aplicarFiltros()"><option value="">Todos</option><option value="cashback">Cashback</option><option value="pontos_milhas">Pontos/Milhas</option></select></div>
          <div class="field" style="max-width:180px;display:flex;align-items:flex-end"><label class="toggle-acesso" style="margin:0"><input type="checkbox" id="filtro-acesso" onchange="aplicarFiltros()" /> Somente com acesso</label></div>
        </div>
      </div>
    </div>
    <div class="summary-grid">
      <div class="summary-card"><div class="label">Maior cashback</div><div class="value" id="sum-cashback">—</div><div class="sub" id="sum-cashback-sub"></div></div>
      <div class="summary-card"><div class="label">Maior pontos/milhas</div><div class="value" id="sum-pontos">—</div><div class="sub" id="sum-pontos-sub"></div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <h2>Histórico</h2>
        <div style="display:flex;gap:8px;align-items:center">
          <select id="grafico-site" onchange="carregarGrafico()" style="width:auto;min-width:130px;"></select>
          <select id="grafico-dias" onchange="carregarGrafico()" style="width:auto"><option value="30">30 dias</option><option value="60">60 dias</option><option value="90">90 dias</option></select>
        </div>
      </div>
      <div class="card-body"><div class="chart-wrap"><canvas id="grafico-historico"></canvas></div></div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Parceiros</h2><span id="contador-parceiros" style="font-size:12px;color:var(--muted)"></span></div>
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>Site</th><th>Parceiro</th><th>Tipo</th><th>Valor</th><th>Status</th><th>Última coleta</th><th>Tenho acesso</th></tr></thead>
          <tbody id="tabela-parceiros"></tbody>
        </table>
      </div>
      <div id="empty-parceiros" class="empty" style="display:none">Nenhum parceiro encontrado com os filtros selecionados.</div>
    </div>
  </section>
  <section class="tab-panel" id="tab-sites" role="tabpanel" aria-labelledby="btn-sites">
    <div class="card">
      <div class="card-header"><h2>Sites monitorados</h2><button class="btn btn-ghost btn-sm" onclick="carregarSites()">↻ Atualizar</button></div>
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>Nome</th><th>URL</th><th>Categoria</th><th>Status</th><th>Última coleta</th><th>Próx. horário</th><th>Alerta</th><th></th></tr></thead>
          <tbody id="tabela-sites"></tbody>
        </table>
      </div>
      <div id="empty-sites" class="empty" style="display:none">Nenhum site cadastrado.</div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Cadastrar novo site</h2></div>
      <div class="card-body">
        <form id="form-cadastro" onsubmit="cadastrarSite(event)">
          <div class="form-grid">
            <div><label for="novo-nome">Nome *</label><input id="novo-nome" type="text" placeholder="Ex: Drogaria SP" required /></div>
            <div><label for="novo-url">URL *</label><input id="novo-url" type="url" placeholder="https://www.comparemania.com.br/..." required /></div>
            <div><label for="novo-categoria">Categoria *</label><input id="novo-categoria" type="text" placeholder="Ex: Farmácia" list="sugestoes-categoria" required /><datalist id="sugestoes-categoria"></datalist></div>
          </div>
          <div style="margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <button type="submit" class="btn btn-primary">Cadastrar site</button>
            <div id="feedback-cadastro"></div>
          </div>
        </form>
      </div>
    </div>
  </section>
  <section class="tab-panel" id="tab-config" role="tabpanel" aria-labelledby="btn-config">
    <div class="card" style="max-width:480px">
      <div class="card-header"><h2>Configurações do agendador</h2></div>
      <div class="card-body">
        <form class="config-form" id="form-config" onsubmit="salvarConfig(event)">
          <div class="field"><label for="cfg-horario">Horário fixo diário (SCRAPE_TIME)</label><input id="cfg-horario" type="time" step="60" /></div>
          <div class="field"><label for="cfg-intervalo">Intervalo de re-execução em horas (mínimo: 1)</label><input id="cfg-intervalo" type="number" min="1" max="168" step="1" /></div>
          <div><button type="submit" class="btn btn-primary">Salvar configurações</button><div id="feedback-config" style="margin-top:8px"></div></div>
        </form>
      </div>
    </div>
    <div class="card" style="max-width:480px">
      <div class="card-header"><h2>Informações do sistema</h2></div>
      <div class="card-body" id="info-sistema" style="font-size:13px;color:var(--muted);display:flex;flex-direction:column;gap:8px;"><div>Carregando...</div></div>
    </div>
  </section>
</main>
<dialog id="modal-confirmacao" aria-modal="true" aria-labelledby="modal-titulo">
  <p class="dialog-title" id="modal-titulo">Confirmar ação</p>
  <p class="dialog-msg"   id="modal-msg">Tem certeza?</p>
  <div class="dialog-actions">
    <button class="btn btn-ghost btn-sm" onclick="document.getElementById('modal-confirmacao').close()">Cancelar</button>
    <button class="btn btn-danger btn-sm" id="modal-confirmar">Confirmar</button>
  </div>
</dialog>
<script src="/static/app.js"></script>
</body>
</html>"""

_APP_JS = """const API = '';
let todosOsSites = [];
let todosParceiros = [];
let acessoMap = {};
let configAtual = {};
let graficoInstance = null;

function formatarData(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso.includes('T') ? iso : iso + 'T00:00:00');
    return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

function formatarValor(v, unidade) {
  if (v === null || v === undefined) return '—';
  const n = Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 2 });
  return unidade === '%' ? `${n}%` : `${n} pts`;
}

function mostrarFeedback(elId, tipo, msg) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.className = `feedback feedback-${tipo}`;
  el.textContent = msg;
  el.style.display = 'block';
  if (tipo === 'ok') setTimeout(() => { el.style.display = 'none'; }, 4000);
}

function abrirModal(titulo, msg, callbackConfirmar) {
  document.getElementById('modal-titulo').textContent = titulo;
  document.getElementById('modal-msg').textContent = msg;
  const btn = document.getElementById('modal-confirmar');
  const novo = btn.cloneNode(true);
  btn.parentNode.replaceChild(novo, btn);
  novo.addEventListener('click', () => {
    document.getElementById('modal-confirmacao').close();
    callbackConfirmar();
  });
  document.getElementById('modal-confirmacao').showModal();
}

function mudarAba(aba) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected', 'false'); });
  document.getElementById(`tab-${aba}`).classList.add('active');
  const btn = document.getElementById(`btn-${aba}`);
  btn.classList.add('active');
  btn.setAttribute('aria-selected', 'true');
  if (aba === 'painel') inicializarPainel();
  if (aba === 'sites')  carregarSites();
  if (aba === 'config') carregarConfig();
}

async function inicializar() {
  await inicializarPainel();
}

async function inicializarPainel() {
  await Promise.all([carregarSitesBase(), carregarTodosParceiros()]);
  aplicarFiltros();
  carregarGrafico();
  renderizarAlertas();
}

function renderizarAlertas() {
  const container = document.getElementById('alertas-container');
  const comAlerta = todosOsSites.filter(s => s.alerta_sem_dados && s.ativo);
  container.innerHTML = '';
  comAlerta.forEach(s => {
    const div = document.createElement('div');
    div.className = 'alert-banner';
    div.innerHTML = `⚠️ <strong>${s.nome}</strong> — nenhum valor coletado nos últimos 2 dias. Verificar estrutura da página.`;
    container.appendChild(div);
  });
}

async function carregarSitesBase() {
  try {
    const res = await fetch(`${API}/sites`);
    todosOsSites = await res.json();
    ['filtro-site', 'grafico-site'].forEach(id => {
      const sel = document.getElementById(id);
      const val = sel.value;
      sel.innerHTML = id === 'filtro-site' ? '<option value="">Todos</option>' : '';
      todosOsSites.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.nome;
        sel.appendChild(opt);
      });
      if (val) sel.value = val;
    });
    const cats = [...new Set(todosOsSites.map(s => s.categoria))];
    const dl = document.getElementById('sugestoes-categoria');
    if (dl) { dl.innerHTML = ''; cats.forEach(c => { const o = document.createElement('option'); o.value = c; dl.appendChild(o); }); }
    const selCat = document.getElementById('filtro-categoria');
    const valCat = selCat.value;
    selCat.innerHTML = '<option value="">Todas</option>';
    cats.forEach(c => { const o = document.createElement('option'); o.value = c; o.textContent = c; selCat.appendChild(o); });
    if (valCat) selCat.value = valCat;
  } catch (e) { console.error('Erro ao carregar sites:', e); }
}

async function carregarTodosParceiros() {
  todosParceiros = [];
  const sites = todosOsSites.filter(s => s.ativo);
  await Promise.all(sites.map(async s => {
    try {
      const res = await fetch(`${API}/sites/${s.id}/parceiros`);
      const data = await res.json();
      ['cashback', 'pontos_milhas'].forEach(tipo => {
        (data[tipo] || []).forEach(p => {
          todosParceiros.push({ site_id: s.id, site_nome: s.nome, site_categoria: s.categoria, tipo, ...p });
        });
      });
    } catch {}
  }));
}

function aplicarFiltros() {
  const siteId       = document.getElementById('filtro-site').value;
  const categoria    = document.getElementById('filtro-categoria').value;
  const tipo         = document.getElementById('filtro-tipo').value;
  const apenasAcesso = document.getElementById('filtro-acesso').checked;
  let lista = todosParceiros;
  if (siteId)       lista = lista.filter(p => String(p.site_id) === siteId);
  if (categoria)    lista = lista.filter(p => p.site_categoria === categoria);
  if (tipo)         lista = lista.filter(p => p.tipo === tipo);
  if (apenasAcesso) lista = lista.filter(p => acessoMap[`${p.site_id}|${p.parceiro}`]);
  renderizarTabelaParceiros(lista);
  atualizarSummary(lista);
}

function renderizarTabelaParceiros(lista) {
  const tbody    = document.getElementById('tabela-parceiros');
  const empty    = document.getElementById('empty-parceiros');
  const contador = document.getElementById('contador-parceiros');
  tbody.innerHTML = '';
  if (!lista.length) { empty.style.display = 'block'; contador.textContent = ''; return; }
  empty.style.display = 'none';
  contador.textContent = `${lista.length} parceiro${lista.length !== 1 ? 's' : ''}`;
  lista.forEach(p => {
    const chave = `${p.site_id}|${p.parceiro}`;
    const temAcesso = !!acessoMap[chave];
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${p.site_nome}</td>
      <td><strong>${p.parceiro}</strong></td>
      <td>${p.tipo === 'cashback' ? 'Cashback' : 'Pontos/Milhas'}</td>
      <td style="font-variant-numeric:tabular-nums;font-weight:600">${formatarValor(p.ultimo_valor, p.unidade)}</td>
      <td><span class="badge ${p.status === 'ativo' ? 'badge-green' : 'badge-gray'}">${p.status === 'ativo' ? '● ativo' : '○ inativo'}</span></td>
      <td style="color:var(--muted)">${formatarData(p.ultima_coleta)}</td>
      <td><label class="toggle-acesso"><input type="checkbox" ${temAcesso ? 'checked' : ''} onchange="toggleAcesso('${chave}', this.checked)" /> tenho acesso</label></td>`;
    tbody.appendChild(tr);
  });
}

function toggleAcesso(chave, valor) {
  acessoMap[chave] = valor;
  if (document.getElementById('filtro-acesso').checked) aplicarFiltros();
}

function atualizarSummary(lista) {
  const cashbacks = lista.filter(p => p.tipo === 'cashback' && p.ultimo_valor !== null);
  const pontos    = lista.filter(p => p.tipo === 'pontos_milhas' && p.ultimo_valor !== null);
  if (cashbacks.length) {
    const melhor = cashbacks.reduce((a, b) => a.ultimo_valor > b.ultimo_valor ? a : b);
    document.getElementById('sum-cashback').textContent = formatarValor(melhor.ultimo_valor, melhor.unidade);
    document.getElementById('sum-cashback-sub').textContent = `${melhor.parceiro} · ${melhor.site_nome}`;
  } else {
    document.getElementById('sum-cashback').textContent = '—';
    document.getElementById('sum-cashback-sub').textContent = 'Sem dados no período';
  }
  if (pontos.length) {
    const melhor = pontos.reduce((a, b) => a.ultimo_valor > b.ultimo_valor ? a : b);
    document.getElementById('sum-pontos').textContent = formatarValor(melhor.ultimo_valor, melhor.unidade);
    document.getElementById('sum-pontos-sub').textContent = `${melhor.parceiro} · ${melhor.site_nome}`;
  } else {
    document.getElementById('sum-pontos').textContent = '—';
    document.getElementById('sum-pontos-sub').textContent = 'Sem dados no período';
  }
}

async function carregarGrafico() {
  const siteId = document.getElementById('grafico-site').value;
  const dias   = document.getElementById('grafico-dias').value || 30;
  if (!siteId) { limparGrafico(); return; }
  try {
    const [resCash, resPts] = await Promise.all([
      fetch(`${API}/sites/${siteId}/snapshots?tipo=cashback&dias=${dias}`),
      fetch(`${API}/sites/${siteId}/snapshots?tipo=pontos_milhas&dias=${dias}`),
    ]);
    const snapCash = await resCash.json();
    const snapPts  = await resPts.json();
    const { labels, dataCash, dataPts } = agregarPorDia(snapCash, snapPts, Number(dias));
    renderizarGrafico(labels, dataCash, dataPts);
  } catch (e) { console.error('Erro no gráfico:', e); }
}

function agregarPorDia(snapCash, snapPts, dias) {
  const hoje = new Date();
  const mapCash = {}, mapPts = {};
  snapCash.forEach(s => {
    if (s.percentual === null) return;
    const dia = (s.capturado_em.split('T')[0] || s.capturado_em.split(' ')[0]);
    if (!mapCash[dia] || s.percentual > mapCash[dia]) mapCash[dia] = s.percentual;
  });
  snapPts.forEach(s => {
    if (s.percentual === null) return;
    const dia = (s.capturado_em.split('T')[0] || s.capturado_em.split(' ')[0]);
    if (!mapPts[dia] || s.percentual > mapPts[dia]) mapPts[dia] = s.percentual;
  });
  const labels = [], dataCash = [], dataPts = [];
  for (let i = dias - 1; i >= 0; i--) {
    const d = new Date(hoje);
    d.setDate(d.getDate() - i);
    const iso = d.toISOString().split('T')[0];
    labels.push(iso.slice(5));
    dataCash.push(mapCash[iso] !== undefined ? mapCash[iso] : null);
    dataPts.push(mapPts[iso]   !== undefined ? mapPts[iso]  : null);
  }
  return { labels, dataCash, dataPts };
}

function renderizarGrafico(labels, dataCash, dataPts) {
  const ctx = document.getElementById('grafico-historico').getContext('2d');
  if (graficoInstance) { graficoInstance.destroy(); graficoInstance = null; }
  const maxCashIdx = dataCash.reduce((iMax, v, i, arr) => (v !== null && (arr[iMax] === null || v > arr[iMax]) ? i : iMax), 0);
  const maxPtsIdx  = dataPts.reduce((iMax, v, i, arr)  => (v !== null && (arr[iMax] === null || v > arr[iMax]) ? i : iMax), 0);
  graficoInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Cashback (%)', data: dataCash, borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,.12)', pointRadius: dataCash.map((v,i) => v!==null?(i===maxCashIdx?6:3):0), pointHoverRadius: 5, pointBackgroundColor: dataCash.map((v,i) => i===maxCashIdx?'#3fb950':'transparent'), pointBorderColor: '#3fb950', spanGaps: false, tension: 0.3, yAxisID: 'y', fill: true },
        { label: 'Pontos/Milhas', data: dataPts, borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,.08)', pointRadius: dataPts.map((v,i) => v!==null?(i===maxPtsIdx?6:3):0), pointHoverRadius: 5, pointBackgroundColor: dataPts.map((v,i) => i===maxPtsIdx?'#58a6ff':'transparent'), pointBorderColor: '#58a6ff', spanGaps: false, tension: 0.3, yAxisID: 'y2', fill: true },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#8b949e', boxWidth: 12, font: { size: 12 } } },
        tooltip: {
          backgroundColor: '#161b22', borderColor: '#30363d', borderWidth: 1, titleColor: '#e6edf3', bodyColor: '#8b949e',
          callbacks: {
            label(ctx) {
              if (ctx.parsed.y === null) return `${ctx.dataset.label}: sem dados`;
              const u = ctx.datasetIndex === 0 ? '%' : ' pts';
              return `${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString('pt-BR', { minimumFractionDigits: 1 })}${u}`;
            },
          },
        },
      },
      scales: {
        x:  { ticks: { color: '#8b949e', maxTicksLimit: 10, font: { size: 11 } }, grid: { color: '#21262d' } },
        y:  { position: 'left',  ticks: { color: '#3fb950', font: { size: 11 }, callback: v => `${v}%` },     grid: { color: '#21262d' }, beginAtZero: true },
        y2: { position: 'right', ticks: { color: '#58a6ff', font: { size: 11 }, callback: v => `${v} pts` }, grid: { drawOnChartArea: false }, beginAtZero: true },
      },
    },
  });
}

function limparGrafico() {
  if (graficoInstance) { graficoInstance.destroy(); graficoInstance = null; }
}

async function carregarSites() {
  try {
    const res = await fetch(`${API}/sites`);
    todosOsSites = await res.json();
    renderizarTabelaSites();
    const cats = [...new Set(todosOsSites.map(s => s.categoria))];
    const dl = document.getElementById('sugestoes-categoria');
    if (dl) { dl.innerHTML = ''; cats.forEach(c => { const o = document.createElement('option'); o.value = c; dl.appendChild(o); }); }
  } catch (e) { console.error('Erro ao carregar sites:', e); }
}

function renderizarTabelaSites() {
  const tbody = document.getElementById('tabela-sites');
  const empty = document.getElementById('empty-sites');
  tbody.innerHTML = '';
  if (!todosOsSites.length) { empty.style.display = 'block'; return; }
  empty.style.display = 'none';
  todosOsSites.forEach(s => {
    const tr = document.createElement('tr');
    if (!s.ativo) tr.classList.add('inativo');
    const statusBadge = s.ativo ? '<span class="badge badge-green">● ativo</span>' : '<span class="badge badge-gray">○ inativo</span>';
    const alertaCell  = s.alerta_sem_dados ? '<span title="Nenhum valor coletado nos últimos 2 dias">⚠️</span>' : '';
    const url    = (s.url || '').replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
    const nome   = (s.nome || '').replace(/'/g, "\\\\'");
    const cat    = (s.categoria || '').replace(/'/g, "\\\\'");
    const acaoBotao = s.ativo
      ? `<button class="btn btn-danger btn-sm" onclick="confirmarDesativar(${s.id},'${nome}')">Desativar</button>`
      : `<button class="btn btn-ghost btn-sm"  onclick="confirmarReativar(${s.id},'${nome}','${url}','${cat}')">Reativar</button>`;
    tr.innerHTML = `
      <td><strong>${s.nome}</strong></td>
      <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><a href="${s.url}" target="_blank" rel="noopener">${s.url}</a></td>
      <td>${s.categoria}</td>
      <td>${statusBadge}</td>
      <td style="color:var(--muted)">${formatarData(s.ultima_coleta)}</td>
      <td style="color:var(--muted);font-variant-numeric:tabular-nums">${configAtual.scrape_time || '—'}</td>
      <td>${alertaCell}</td>
      <td id="acao-site-${s.id}">${acaoBotao}</td>`;
    tbody.appendChild(tr);
  });
}

function confirmarDesativar(siteId, nome) {
  abrirModal('Desativar site', `Deseja desativar "${nome}"? O histórico será preservado.`, () => desativarSite(siteId, nome));
}

async function desativarSite(siteId, nome) {
  try {
    await fetch(`${API}/sites/${siteId}`, { method: 'DELETE' });
    const site = todosOsSites.find(s => s.id === siteId);
    if (site) { site.ativo = false; site.alerta_sem_dados = false; }
    const td = document.getElementById(`acao-site-${siteId}`);
    if (td) {
      const tr = td.closest('tr');
      tr.classList.add('inativo');
      tr.querySelector('td:nth-child(4)').innerHTML = '<span class="badge badge-gray">○ inativo</span>';
      const s = todosOsSites.find(s => s.id === siteId);
      const u = (s?.url || '').replace(/'/g, "\\\\'");
      const c = (s?.categoria || '').replace(/'/g, "\\\\'");
      const n = nome.replace(/'/g, "\\\\'");
      td.innerHTML = `<button class="btn btn-ghost btn-sm" onclick="confirmarReativar(${siteId},'${n}','${u}','${c}')">Reativar</button>`;
    }
  } catch (e) { alert('Erro ao desativar: ' + e.message); }
}

function confirmarReativar(siteId, nome, url, categoria) {
  abrirModal('Reativar site', `Deseja reativar "${nome}"? A coleta será reiniciada imediatamente.`, () => reativarSite(siteId, nome, url, categoria));
}

async function reativarSite(siteId, nome, url, categoria) {
  const td = document.getElementById(`acao-site-${siteId}`);
  if (td) td.innerHTML = '<span style="color:var(--muted);font-size:12px">Reativando...</span>';
  try {
    await fetch(`${API}/sites`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, nome, categoria }) });
    setTimeout(carregarSites, 2000);
  } catch (e) { if (td) td.innerHTML = `<span class="feedback feedback-err">Erro: ${e.message}</span>`; }
}

async function cadastrarSite(event) {
  event.preventDefault();
  const nome      = document.getElementById('novo-nome').value.trim();
  const url       = document.getElementById('novo-url').value.trim();
  const categoria = document.getElementById('novo-categoria').value.trim();
  const fb = 'feedback-cadastro';
  if (!nome || !categoria) { mostrarFeedback(fb, 'err', 'Nome e Categoria são obrigatórios.'); return; }
  if (!url.startsWith('http://') && !url.startsWith('https://')) { mostrarFeedback(fb, 'err', 'A URL deve começar com http:// ou https://'); return; }
  try {
    const res = await fetch(`${API}/sites`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, nome, categoria }) });
    if (res.status === 409) { mostrarFeedback(fb, 'err', 'Este site já está sendo monitorado.'); return; }
    if (!res.ok) { const err = await res.json(); mostrarFeedback(fb, 'err', err.detail || 'Erro ao cadastrar site.'); return; }
    mostrarFeedback(fb, 'ok', 'Site cadastrado! Coletando dados iniciais...');
    document.getElementById('form-cadastro').reset();
    await carregarSites();
    setTimeout(carregarSites, 10000);
  } catch (e) { mostrarFeedback(fb, 'err', 'Erro de conexão: ' + e.message); }
}

async function carregarConfig() {
  try {
    const res = await fetch(`${API}/config`);
    configAtual = await res.json();
    document.getElementById('cfg-horario').value   = configAtual.scrape_time || '';
    document.getElementById('cfg-intervalo').value = configAtual.scrape_interval_hours || 24;
    renderizarInfoSistema();
  } catch (e) { console.error('Erro ao carregar config:', e); }
}

function renderizarInfoSistema() {
  const el = document.getElementById('info-sistema');
  if (!el) return;
  el.innerHTML = `
    <div><span style="color:var(--muted)">Horário fixo:</span> <strong>${configAtual.scrape_time || '—'}</strong></div>
    <div><span style="color:var(--muted)">Intervalo:</span> <strong>${configAtual.scrape_interval_hours || '—'}h</strong></div>
    <div><span style="color:var(--muted)">Fuso horário:</span> <strong>${configAtual.timezone || 'America/Sao_Paulo'}</strong></div>`;
}

async function salvarConfig(event) {
  event.preventDefault();
  const scrape_time           = document.getElementById('cfg-horario').value;
  const scrape_interval_hours = parseInt(document.getElementById('cfg-intervalo').value, 10);
  const fb = 'feedback-config';
  if (!scrape_time) { mostrarFeedback(fb, 'err', 'Informe o horário fixo.'); return; }
  if (isNaN(scrape_interval_hours) || scrape_interval_hours < 1) { mostrarFeedback(fb, 'err', 'Intervalo deve ser no mínimo 1 hora.'); return; }
  try {
    const res = await fetch(`${API}/config`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scrape_time, scrape_interval_hours }) });
    if (!res.ok) { const e = await res.json(); mostrarFeedback(fb, 'err', e.detail || 'Erro ao salvar.'); return; }
    configAtual = await res.json();
    renderizarInfoSistema();
    mostrarFeedback(fb, 'ok', 'Configurações salvas. Próxima execução atualizada.');
  } catch (e) { mostrarFeedback(fb, 'err', 'Erro de conexão: ' + e.message); }
}

document.addEventListener('DOMContentLoaded', inicializar);
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_banco()
    iniciar_agendador()
    _disparar_coleta_inicial()
    yield
    parar_agendador()


app = FastAPI(title="CashbackTracker", version="3.0.0", lifespan=lifespan)


def _disparar_coleta_inicial():
    sites = obter_sites_ativos()
    for site in sites:
        t = threading.Thread(
            target=coletar_site,
            args=(site["id"], site["url"], site["nome"]),
            daemon=True,
        )
        t.start()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def dashboard():
    return HTMLResponse(content=_INDEX_HTML)


@app.get("/static/index.html", include_in_schema=False)
def static_index():
    return HTMLResponse(content=_INDEX_HTML)


@app.get("/static/app.js", include_in_schema=False)
def static_app_js():
    return PlainTextResponse(content=_APP_JS, media_type="application/javascript")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"status": "ok", "timestamp": agora}


# ── Modelos ───────────────────────────────────────────────────────────────────

class SiteEntrada(BaseModel):
    url: str
    nome: str
    categoria: str


class ConfigEntrada(BaseModel):
    scrape_time: str | None = None
    scrape_interval_hours: int | None = None


# ── Sites ─────────────────────────────────────────────────────────────────────

@app.get("/sites")
def listar_sites():
    sites = obter_todos_sites()
    resultado = []
    for s in sites:
        alerta = verificar_alerta_sem_dados(s["id"]) if s["ativo"] else False
        ultima_coleta = obter_ultima_coleta_site(s["id"])
        resultado.append({
            "id": s["id"],
            "nome": s["nome"],
            "url": s["url"],
            "categoria": s["categoria"],
            "ativo": bool(s["ativo"]),
            "alerta_sem_dados": alerta,
            "ultima_coleta": ultima_coleta,
        })
    return resultado


@app.post("/sites", status_code=201)
def cadastrar_site(dados: SiteEntrada, response: Response):
    existente = obter_site_por_url(dados.url)
    if existente:
        if existente["ativo"]:
            raise HTTPException(status_code=409, detail="Este site j\u00e1 est\u00e1 sendo monitorado")
        reativar_site(existente["id"], dados.nome, dados.categoria)
        site_id = existente["id"]
        response.status_code = 200
    else:
        site_id = inserir_site(dados.url, dados.nome, dados.categoria)
    threading.Thread(target=coletar_site, args=(site_id, dados.url, dados.nome), daemon=True).start()
    return obter_site_por_id(site_id)


@app.delete("/sites/{site_id}", status_code=204)
def remover_site(site_id: int):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site n\u00e3o encontrado")
    desativar_site(site_id)
    return Response(status_code=204)


@app.get("/sites/{site_id}/parceiros")
def parceiros_site(site_id: int):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site n\u00e3o encontrado")
    return obter_parceiros_site(site_id)


@app.get("/sites/{site_id}/snapshots")
def snapshots_site(site_id: int, parceiro: str | None = None, tipo: str | None = None, dias: int = 30):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site n\u00e3o encontrado")
    if dias > 90:
        dias = 90
    return obter_snapshots_site(site_id, parceiro=parceiro, tipo=tipo, dias=dias)


@app.get("/sites/{site_id}/max")
def max_site(site_id: int, dias: int = 30):
    site = obter_site_por_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site n\u00e3o encontrado")
    if dias > 90:
        dias = 90
    return obter_max_site(site_id, dias=dias)


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/config")
def ler_config():
    return obter_config()


@app.put("/config")
def atualizar_config(dados: ConfigEntrada):
    reconfigurar_agendador(
        novo_scrape_time=dados.scrape_time,
        novo_intervalo_horas=dados.scrape_interval_hours,
    )
    return obter_config()


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    porta = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=porta, log_level="info")
