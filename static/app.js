const API = '';
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
    const url    = (s.url || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    const nome   = (s.nome || '').replace(/'/g, "\\'");
    const cat    = (s.categoria || '').replace(/'/g, "\\'");
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
      const u = (s?.url || '').replace(/'/g, "\\'");
      const c = (s?.categoria || '').replace(/'/g, "\\'");
      const n = nome.replace(/'/g, "\\'");
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
