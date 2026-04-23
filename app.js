/* ─────────────────────────────────────────────
   CashbackTracker — app.js
   Fase 3: Dashboard Web
   ───────────────────────────────────────────── */

// ══════════════════════════════════════════════
//  ESTADO GLOBAL
// ══════════════════════════════════════════════
const estado = {
  sites:          [],       // GET /sites
  config:         {},       // GET /config
  parceiros:      { cashback: [], pontos_milhas: [] },
  snapshots:      [],       // GET /sites/{id}/snapshots (todos os dias)
  max:            null,     // GET /sites/{id}/max
  currentSiteId:  null,
  diasGrafico:    30,
  // filtros do painel
  parceirosSelecionados: null,   // null = todos | Set = filtrado
  filtraSoAcesso:        false,
  tenhoAcesso:           {},     // { [parceiro]: boolean } — memória apenas
  chartInstance:         null,
};

// ══════════════════════════════════════════════
//  INICIALIZAÇÃO
// ══════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', async () => {
  inicializarTabs();
  inicializarModal();
  verificarHealth();

  await Promise.all([
    carregarSites(),
    carregarConfig(),
  ]);

  renderPainel();
  renderSites();
  renderConfig();
});

// ══════════════════════════════════════════════
//  API HELPERS
// ══════════════════════════════════════════════
async function api(path, opcoes = {}) {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opcoes,
  });
  if (!resp.ok) {
    let detalhe = '';
    try { detalhe = (await resp.json()).detail || ''; } catch (_) {}
    throw Object.assign(new Error(detalhe || `HTTP ${resp.status}`), { status: resp.status });
  }
  if (resp.status === 204) return null;
  return resp.json();
}

async function verificarHealth() {
  const dot   = document.getElementById('health-dot');
  const label = document.getElementById('health-label');
  try {
    const data = await api('/health');
    dot.className   = 'health-dot ok';
    label.textContent = 'online';
    label.title = data.timestamp || '';
  } catch (_) {
    dot.className   = 'health-dot err';
    label.textContent = 'offline';
  }
}

async function carregarSites() {
  try {
    estado.sites = await api('/sites');
  } catch (_) {
    estado.sites = [];
  }
}

async function carregarConfig() {
  try {
    estado.config = await api('/config');
  } catch (_) {
    estado.config = {};
  }
}

// ══════════════════════════════════════════════
//  TABS
// ══════════════════════════════════════════════
function inicializarTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
  });
}

// ══════════════════════════════════════════════
//  MODAL
// ══════════════════════════════════════════════
function inicializarModal() {
  document.getElementById('modal-cancelar').addEventListener('click', fecharModal);
  document.getElementById('modal-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) fecharModal();
  });
}

function abrirModal(mensagem) {
  return new Promise(resolve => {
    document.getElementById('modal-mensagem').textContent = mensagem;
    document.getElementById('modal-overlay').classList.remove('hidden');
    const confirmar = document.getElementById('modal-confirmar');
    const handler = () => { fecharModal(); confirmar.removeEventListener('click', handler); resolve(true); };
    confirmar.addEventListener('click', handler);
  });
}

function fecharModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
}

// ══════════════════════════════════════════════
//  HELPERS DE UI
// ══════════════════════════════════════════════
function mostrarFeedback(elId, tipo, msg) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.className   = `feedback ${tipo}`;
  el.textContent = msg;
  if (tipo === 'ok') setTimeout(() => el.classList.add('hidden'), 4000);
}

function ocultarFeedback(elId) {
  const el = document.getElementById(elId);
  if (el) el.classList.add('hidden');
}

function formatarData(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (_) { return iso; }
}

function formatarSoData(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('pt-BR');
  } catch (_) { return iso; }
}

function formatarValor(v, unidade) {
  if (v === null || v === undefined) return '—';
  return unidade === '%' ? `${v}%` : `${v} pts`;
}

// ══════════════════════════════════════════════
//  PAINEL
// ══════════════════════════════════════════════
async function renderPainel() {
  const sites = estado.sites.filter(s => s.ativo);

  // --- Alertas ---
  renderAlertas();

  // --- Popula select de sites ---
  const sel = document.getElementById('site-select');
  sel.innerHTML = '';
  if (sites.length === 0) {
    sel.innerHTML = '<option value="">Nenhum site ativo</option>';
  } else {
    sites.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.nome;
      sel.appendChild(opt);
    });
  }

  sel.removeEventListener('change', onSiteChange);
  sel.addEventListener('change', onSiteChange);

  // --- Botão toggle dias ---
  document.querySelectorAll('.dias-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.dias-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      estado.diasGrafico = parseInt(btn.dataset.dias, 10);
      renderGrafico();
    });
  });

  // --- Filtro "somente com acesso" ---
  const filtroAcesso = document.getElementById('filtro-acesso');
  filtroAcesso.checked = estado.filtraSoAcesso;
  filtroAcesso.addEventListener('change', () => {
    estado.filtraSoAcesso = filtroAcesso.checked;
    renderTabelaParceiros();
  });

  // --- Dropdown parceiros ---
  const dropBtn = document.getElementById('parceiros-filter-btn');
  const dropPanel = document.getElementById('parceiros-dropdown');
  dropBtn.addEventListener('click', e => {
    e.stopPropagation();
    dropPanel.classList.toggle('open');
    dropBtn.classList.toggle('active');
  });
  document.addEventListener('click', () => {
    dropPanel.classList.remove('open');
    dropBtn.classList.remove('active');
  });

  if (sites.length > 0) {
    estado.currentSiteId = sites[0].id;
    await carregarDadosSite(estado.currentSiteId);
  } else {
    renderCards(null);
    renderTabelaParceiros();
    renderGrafico();
  }
}

function renderAlertas() {
  const container = document.getElementById('alertas-container');
  container.innerHTML = '';
  const alertas = estado.sites.filter(s => s.ativo && s.alerta_sem_dados);
  alertas.forEach(s => {
    const div = document.createElement('div');
    div.className = 'alerta-banner';
    div.innerHTML = `⚠️ <strong>${s.nome}</strong> — nenhum valor coletado nos últimos 2 dias. Verificar estrutura da página.`;
    container.appendChild(div);
  });
}

async function onSiteChange(e) {
  estado.currentSiteId = parseInt(e.target.value, 10);
  await carregarDadosSite(estado.currentSiteId);
}

async function carregarDadosSite(siteId) {
  try {
    const [parc, snaps, maxVals] = await Promise.all([
      api(`/sites/${siteId}/parceiros`),
      api(`/sites/${siteId}/snapshots?dias=90`),
      api(`/sites/${siteId}/max?dias=30`),
    ]);
    estado.parceiros = parc;
    estado.snapshots = snaps;
    estado.max       = maxVals;
  } catch (_) {
    estado.parceiros = { cashback: [], pontos_milhas: [] };
    estado.snapshots = [];
    estado.max       = null;
  }

  // Rebuild filtro de parceiros
  const todosParceiros = [
    ...estado.parceiros.cashback.map(p => p.parceiro),
    ...estado.parceiros.pontos_milhas.map(p => p.parceiro),
  ];
  estado.parceirosSelecionados = null; // resetar ao trocar site
  renderDropdownParceiros(todosParceiros);

  renderCards(estado.max);
  renderTabelaParceiros();
  renderGrafico();
}

// ── Cards de resumo ──
function renderCards(max) {
  const container = document.getElementById('cards-row');
  container.innerHTML = '';

  const cashback = max?.cashback;
  const pontos   = max?.pontos_milhas;

  const cardCashback = criarCard(
    'Máx. cashback (30d)',
    cashback ? `${cashback.valor}%` : '—',
    cashback ? `${cashback.parceiro} · ${formatarSoData(cashback.data)}` : 'Sem dados no período',
  );
  const cardPontos = criarCard(
    'Máx. pontos/milhas (30d)',
    pontos ? `${pontos.valor} pts` : '—',
    pontos ? `${pontos.parceiro} · ${formatarSoData(pontos.data)}` : 'Sem dados no período',
  );

  container.appendChild(cardCashback);
  container.appendChild(cardPontos);
}

function criarCard(label, valor, meta) {
  const div = document.createElement('div');
  div.className = 'card';
  div.innerHTML = `
    <div class="card-label">${label}</div>
    <div class="card-value">${valor}</div>
    <div class="card-meta">${meta}</div>
  `;
  return div;
}

// ── Dropdown multi-select de parceiros ──
function renderDropdownParceiros(parceiros) {
  const panel = document.getElementById('parceiros-dropdown');
  const btn   = document.getElementById('parceiros-filter-btn');
  panel.innerHTML = '';

  if (parceiros.length === 0) {
    panel.innerHTML = '<div class="dropdown-item" style="color:var(--text3)">Nenhum parceiro</div>';
    return;
  }

  // Item "Todos"
  const itemTodos = document.createElement('div');
  itemTodos.className = 'dropdown-item';
  const cbTodos = document.createElement('input');
  cbTodos.type = 'checkbox';
  cbTodos.checked = estado.parceirosSelecionados === null;
  cbTodos.id = 'cb-todos';
  const lbTodos = document.createElement('label');
  lbTodos.htmlFor = 'cb-todos';
  lbTodos.textContent = 'Todos';
  itemTodos.appendChild(cbTodos);
  itemTodos.appendChild(lbTodos);
  panel.appendChild(itemTodos);

  const checkboxes = [];

  parceiros.forEach((p, i) => {
    const item = document.createElement('div');
    item.className = 'dropdown-item';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = `cb-p-${i}`;
    cb.dataset.parceiro = p;
    cb.checked = estado.parceirosSelecionados === null || estado.parceirosSelecionados.has(p);
    const lb = document.createElement('label');
    lb.htmlFor = `cb-p-${i}`;
    lb.textContent = p;
    item.appendChild(cb);
    item.appendChild(lb);
    panel.appendChild(item);
    checkboxes.push(cb);

    cb.addEventListener('change', () => {
      const sel = new Set(
        checkboxes.filter(c => c.checked).map(c => c.dataset.parceiro)
      );
      estado.parceirosSelecionados = sel.size === parceiros.length ? null : sel;
      cbTodos.checked = estado.parceirosSelecionados === null;
      atualizarBotaoFiltro(btn, estado.parceirosSelecionados, parceiros.length);
      renderTabelaParceiros();
    });
  });

  cbTodos.addEventListener('change', () => {
    checkboxes.forEach(cb => { cb.checked = cbTodos.checked; });
    estado.parceirosSelecionados = cbTodos.checked ? null : new Set();
    atualizarBotaoFiltro(btn, estado.parceirosSelecionados, parceiros.length);
    renderTabelaParceiros();
  });

  atualizarBotaoFiltro(btn, estado.parceirosSelecionados, parceiros.length);
}

function atualizarBotaoFiltro(btn, sel, total) {
  if (sel === null || sel.size === total) {
    btn.textContent = 'Parceiros';
    btn.classList.remove('active');
  } else {
    btn.textContent = `Parceiros (${sel.size})`;
    btn.classList.add('active');
  }
}

// ── Tabela de parceiros ──
function renderTabelaParceiros() {
  const tbody = document.getElementById('tabela-parceiros-body');
  const linhas = [
    ...estado.parceiros.cashback.map(p => ({ ...p, tipo: 'cashback' })),
    ...estado.parceiros.pontos_milhas.map(p => ({ ...p, tipo: 'pontos_milhas' })),
  ];

  // Filtro por parceiros selecionados
  let filtradas = linhas;
  if (estado.parceirosSelecionados !== null) {
    filtradas = filtradas.filter(p => estado.parceirosSelecionados.has(p.parceiro));
  }

  // Filtro "tenho acesso"
  if (estado.filtraSoAcesso) {
    filtradas = filtradas.filter(p => estado.tenhoAcesso[p.parceiro] === true);
  }

  if (filtradas.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Nenhum parceiro encontrado</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  filtradas.forEach(p => {
    const tr = document.createElement('tr');
    const temAcesso = estado.tenhoAcesso[p.parceiro] || false;
    const badgeStatus = p.status === 'ativo'
      ? '<span class="badge badge-green">ativo</span>'
      : '<span class="badge badge-gray">inativo</span>';
    const badgeTipo = p.tipo === 'cashback'
      ? '<span class="badge badge-amber">cashback</span>'
      : '<span class="badge badge-gray" style="color:var(--text2)">pontos/milhas</span>';

    tr.innerHTML = `
      <td><strong>${p.parceiro}</strong> ${badgeStatus}</td>
      <td>${badgeTipo}</td>
      <td class="mono">${formatarValor(p.ultimo_valor, p.unidade)}</td>
      <td class="text2" style="font-size:12px">${formatarData(p.ultima_coleta)}</td>
      <td><input type="checkbox" class="access-toggle" data-parceiro="${p.parceiro}" ${temAcesso ? 'checked' : ''}></td>
    `;
    tbody.appendChild(tr);

    tr.querySelector('.access-toggle').addEventListener('change', e => {
      estado.tenhoAcesso[p.parceiro] = e.target.checked;
      if (estado.filtraSoAcesso) renderTabelaParceiros();
    });
  });
}

// ── Gráfico ──
function renderGrafico() {
  const canvas = document.getElementById('grafico-historico');
  const emptyEl = document.getElementById('chart-empty');

  if (estado.snapshots.length === 0) {
    canvas.style.display = 'none';
    emptyEl.style.display = 'block';
    if (estado.chartInstance) { estado.chartInstance.destroy(); estado.chartInstance = null; }
    return;
  }

  canvas.style.display = 'block';
  emptyEl.style.display = 'none';

  const { datas, cashbackData, pontosData, cashbackMax, pontosMax } =
    prepararDadosGrafico(estado.snapshots, estado.diasGrafico);

  const labelsDatas = datas.map(d => {
    const [y, m, dia] = d.split('-');
    return `${dia}/${m}`;
  });

  const cashbackRadius = cashbackData.map((v, i) => {
    if (v === null) return 0;
    if (i === cashbackMax.idx) return 7;
    return 3;
  });
  const pontosRadius = pontosData.map((v, i) => {
    if (v === null) return 0;
    if (i === pontosMax.idx) return 7;
    return 3;
  });

  if (estado.chartInstance) {
    estado.chartInstance.destroy();
    estado.chartInstance = null;
  }

  estado.chartInstance = new Chart(canvas, {
    type: 'line',
    data: {
      labels: labelsDatas,
      datasets: [
        {
          label: 'Cashback (%)',
          data: cashbackData,
          borderColor: '#F59E0B',
          backgroundColor: 'rgba(245,158,11,.08)',
          borderWidth: 2,
          pointRadius: cashbackRadius,
          pointBackgroundColor: cashbackData.map((_, i) =>
            i === cashbackMax.idx ? '#F59E0B' : 'rgba(245,158,11,.6)'
          ),
          pointHoverRadius: 6,
          spanGaps: false,
          tension: 0.3,
          fill: true,
          yAxisID: 'y',
        },
        {
          label: 'Pontos/Milhas',
          data: pontosData,
          borderColor: '#60A5FA',
          backgroundColor: 'rgba(96,165,250,.06)',
          borderWidth: 2,
          pointRadius: pontosRadius,
          pointBackgroundColor: pontosData.map((_, i) =>
            i === pontosMax.idx ? '#60A5FA' : 'rgba(96,165,250,.6)'
          ),
          pointHoverRadius: 6,
          spanGaps: false,
          tension: 0.3,
          fill: true,
          yAxisID: 'y1',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { color: '#8A8A96', font: { family: 'IBM Plex Sans', size: 12 }, boxWidth: 12 },
        },
        tooltip: {
          backgroundColor: '#18181B',
          borderColor: '#2E2E34',
          borderWidth: 1,
          titleColor: '#EBEBEB',
          bodyColor: '#8A8A96',
          padding: 10,
          callbacks: {
            label: ctx => {
              if (ctx.parsed.y === null) return `${ctx.dataset.label}: valor não disponível`;
              const suf = ctx.datasetIndex === 0 ? '%' : ' pts';
              const isMax = ctx.datasetIndex === 0
                ? ctx.dataIndex === cashbackMax.idx
                : ctx.dataIndex === pontosMax.idx;
              return `${ctx.dataset.label}: ${ctx.parsed.y}${suf}${isMax ? ' ★ máx.' : ''}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#52525B', font: { family: 'IBM Plex Mono', size: 10 }, maxTicksLimit: 10 },
          grid: { color: 'rgba(255,255,255,.04)' },
        },
        y: {
          type: 'linear',
          position: 'left',
          ticks: { color: '#F59E0B', font: { family: 'IBM Plex Mono', size: 10 }, callback: v => `${v}%` },
          grid: { color: 'rgba(255,255,255,.04)' },
          title: { display: true, text: 'Cashback (%)', color: '#7C4F06', font: { size: 11 } },
        },
        y1: {
          type: 'linear',
          position: 'right',
          ticks: { color: '#60A5FA', font: { family: 'IBM Plex Mono', size: 10 }, callback: v => `${v}` },
          grid: { drawOnChartArea: false },
          title: { display: true, text: 'Pontos/Milhas', color: '#1D4ED8', font: { size: 11 } },
        },
      },
    },
  });
}

function prepararDadosGrafico(snapshots, dias) {
  // Construir range de datas
  const hoje = new Date();
  const datas = [];
  for (let i = dias - 1; i >= 0; i--) {
    const d = new Date(hoje);
    d.setDate(d.getDate() - i);
    datas.push(d.toISOString().split('T')[0]);
  }

  // Agregar max por dia e tipo
  const cashbackPorDia = {};
  const pontosPorDia   = {};

  for (const s of snapshots) {
    if (s.percentual === null || s.percentual === undefined) continue;
    const dia = (s.capturado_em || '').split('T')[0];
    if (!dia) continue;
    if (s.tipo === 'cashback') {
      if (cashbackPorDia[dia] === undefined || s.percentual > cashbackPorDia[dia])
        cashbackPorDia[dia] = s.percentual;
    } else {
      if (pontosPorDia[dia] === undefined || s.percentual > pontosPorDia[dia])
        pontosPorDia[dia] = s.percentual;
    }
  }

  const cashbackData = datas.map(d => cashbackPorDia[d] ?? null);
  const pontosData   = datas.map(d => pontosPorDia[d]   ?? null);

  // Encontrar índice do máximo
  const findMax = arr => {
    let maxVal = -Infinity, maxIdx = -1;
    arr.forEach((v, i) => { if (v !== null && v > maxVal) { maxVal = v; maxIdx = i; } });
    return { val: maxVal === -Infinity ? null : maxVal, idx: maxIdx };
  };

  return {
    datas,
    cashbackData,
    pontosData,
    cashbackMax: findMax(cashbackData),
    pontosMax:   findMax(pontosData),
  };
}

// ══════════════════════════════════════════════
//  SITES
// ══════════════════════════════════════════════
function renderSites() {
  renderTabelaSites();

  const btnCadastrar = document.getElementById('btn-cadastrar');
  btnCadastrar.addEventListener('click', () => cadastrarSite());

  // Sugestão de categoria baseada nos sites existentes
  const inputCat = document.getElementById('input-categoria');
  const categorias = [...new Set(estado.sites.map(s => s.categoria).filter(Boolean))];
  if (categorias.length > 0) {
    const datalist = document.createElement('datalist');
    datalist.id = 'cat-suggestions';
    categorias.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c;
      datalist.appendChild(opt);
    });
    document.body.appendChild(datalist);
    inputCat.setAttribute('list', 'cat-suggestions');
  }
}

function renderTabelaSites() {
  const tbody = document.getElementById('tabela-sites-body');
  const scrapeTime = estado.config.scrape_time || '—';

  if (estado.sites.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Nenhum site cadastrado</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  estado.sites.forEach(s => {
    const tr = document.createElement('tr');
    tr.id = `site-row-${s.id}`;
    if (!s.ativo) tr.classList.add('row-disabled');

    const badgeAtivo = s.ativo
      ? '<span class="badge badge-green">ativo</span>'
      : '<span class="badge badge-gray">inativo</span>';

    const alerta = (s.ativo && s.alerta_sem_dados)
      ? '<span title="Nenhum valor nos últimos 2 dias" style="cursor:help">⚠️</span>'
      : '<span style="color:var(--text3)">—</span>';

    const btnAcao = s.ativo
      ? `<button class="btn btn-danger btn-sm" data-acao="desativar" data-id="${s.id}" data-nome="${s.nome}">Desativar</button>`
      : `<button class="btn btn-ghost btn-sm" data-acao="reativar" data-id="${s.id}" data-url="${s.url}" data-nome="${s.nome}" data-cat="${s.categoria}">Reativar</button>`;

    tr.innerHTML = `
      <td><strong>${s.nome}</strong></td>
      <td><div class="url-cell" title="${s.url}">${s.url}</div></td>
      <td>${s.categoria || '—'}</td>
      <td>${badgeAtivo}</td>
      <td class="text2" style="font-size:12px">${s.ultima_coleta ? formatarData(s.ultima_coleta) : '—'}</td>
      <td class="mono" style="font-size:12px">${s.ativo ? scrapeTime : '—'}</td>
      <td>${alerta}</td>
      <td>
        ${btnAcao}
        <span class="site-feedback" id="feedback-site-${s.id}"></span>
      </td>
    `;
    tbody.appendChild(tr);
  });

  // Event listeners para botões de ação
  tbody.querySelectorAll('[data-acao]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.acao === 'desativar') {
        desativarSite(parseInt(btn.dataset.id), btn.dataset.nome);
      } else {
        reativarSite(
          parseInt(btn.dataset.id),
          btn.dataset.url,
          btn.dataset.nome,
          btn.dataset.cat,
        );
      }
    });
  });
}

async function cadastrarSite() {
  ocultarFeedback('form-feedback');
  const nome      = document.getElementById('input-nome').value.trim();
  const url       = document.getElementById('input-url').value.trim();
  const categoria = document.getElementById('input-categoria').value.trim();

  // Validações
  if (!nome || !categoria) {
    mostrarFeedback('form-feedback', 'err', 'Nome e Categoria são obrigatórios.');
    return;
  }
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    mostrarFeedback('form-feedback', 'err', 'URL deve começar com http:// ou https://');
    return;
  }

  const btn = document.getElementById('btn-cadastrar');
  btn.disabled = true;
  try {
    await api('/sites', {
      method: 'POST',
      body: JSON.stringify({ url, nome, categoria }),
    });
    mostrarFeedback('form-feedback', 'ok', `✓ Site "${nome}" cadastrado. Coletando dados iniciais...`);
    document.getElementById('input-nome').value      = '';
    document.getElementById('input-url').value       = '';
    document.getElementById('input-categoria').value = '';
    await carregarSites();
    renderTabelaSites();
    renderPainel();

    // Atualiza status após 10 segundos
    setTimeout(async () => {
      await carregarSites();
      renderTabelaSites();
    }, 10000);
  } catch (err) {
    if (err.status === 409) {
      mostrarFeedback('form-feedback', 'err', 'Este site já está sendo monitorado.');
    } else {
      mostrarFeedback('form-feedback', 'err', `Erro: ${err.message}`);
    }
  } finally {
    btn.disabled = false;
  }
}

async function desativarSite(id, nome) {
  const confirmado = await abrirModal(`Desativar "${nome}"? O histórico será preservado.`);
  if (!confirmado) return;

  const feedback = document.getElementById(`feedback-site-${id}`);
  try {
    await api(`/sites/${id}`, { method: 'DELETE' });
    if (feedback) { feedback.className = 'site-feedback ok'; feedback.textContent = '✓ desativado'; }
    await carregarSites();
    renderTabelaSites();
    renderPainel();
  } catch (err) {
    if (feedback) { feedback.className = 'site-feedback err'; feedback.textContent = err.message; }
  }
}

async function reativarSite(id, url, nome, categoria) {
  const confirmado = await abrirModal(`Reativar "${nome}"? O scraping será reiniciado.`);
  if (!confirmado) return;

  const feedback = document.getElementById(`feedback-site-${id}`);
  if (feedback) { feedback.className = 'site-feedback info'; feedback.textContent = 'Reativando...'; }

  try {
    await api('/sites', {
      method: 'POST',
      body: JSON.stringify({ url, nome, categoria }),
    });
    if (feedback) { feedback.className = 'site-feedback ok'; feedback.textContent = '✓ reativado — coletando dados'; }
    await carregarSites();
    renderTabelaSites();
    renderPainel();
  } catch (err) {
    if (feedback) { feedback.className = 'site-feedback err'; feedback.textContent = err.message; }
  }
}

// ══════════════════════════════════════════════
//  CONFIG
// ══════════════════════════════════════════════
function renderConfig() {
  const inputTime     = document.getElementById('input-scrape-time');
  const inputInterval = document.getElementById('input-interval');

  inputTime.value     = estado.config.scrape_time     || '06:00';
  inputInterval.value = estado.config.scrape_interval_hours || 24;

  const btn = document.getElementById('btn-salvar-config');
  btn.addEventListener('click', () => salvarConfig());
}

async function salvarConfig() {
  ocultarFeedback('config-feedback');
  const scrape_time           = document.getElementById('input-scrape-time').value;
  const scrape_interval_hours = parseInt(document.getElementById('input-interval').value, 10);

  if (!scrape_time) {
    mostrarFeedback('config-feedback', 'err', 'Informe um horário válido.');
    return;
  }
  if (!scrape_interval_hours || scrape_interval_hours < 1) {
    mostrarFeedback('config-feedback', 'err', 'Intervalo mínimo é 1 hora.');
    return;
  }

  const btn = document.getElementById('btn-salvar-config');
  btn.disabled = true;
  try {
    estado.config = await api('/config', {
      method: 'PUT',
      body: JSON.stringify({ scrape_time, scrape_interval_hours }),
    });
    mostrarFeedback('config-feedback', 'ok', '✓ Configurações salvas. Próxima execução atualizada.');
    renderTabelaSites(); // atualiza coluna "Próx. coleta"
  } catch (err) {
    mostrarFeedback('config-feedback', 'err', `Erro: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}
