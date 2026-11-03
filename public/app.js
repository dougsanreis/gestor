// Gestor de Anúncios — interface SPA em JavaScript puro (sem frameworks, sem build).
'use strict';

/* ======================= Utilitários ======================= */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Escapa HTML para evitar XSS ao interpolar dados do usuário em templates. */
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const int = new Intl.NumberFormat('pt-BR');
const dec = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmt = {
  money: (n) => brl.format(n || 0),
  int: (n) => int.format(n || 0),
  pct: (n) => `${dec.format(n || 0)}%`,
  x: (n) => `${dec.format(n || 0)}x`,
  date: (s) => (s ? s.split('-').reverse().join('/') : '—'),
  shortDate: (s) => s.slice(8, 10) + '/' + s.slice(5, 7),
};

const LABELS = {
  platform: { meta: 'Meta Ads', google: 'Google Ads', tiktok: 'TikTok Ads', linkedin: 'LinkedIn Ads' },
  status: { rascunho: 'Rascunho', ativa: 'Ativa', pausada: 'Pausada', encerrada: 'Encerrada' },
  objective: { conversao: 'Conversão', trafego: 'Tráfego', alcance: 'Alcance', leads: 'Geração de leads', engajamento: 'Engajamento' },
};
const platformTag = (p) => `<span class="pf pf-${esc(p)}">${esc(LABELS.platform[p] || p)}</span>`;
const statusTag = (s) => `<span class="badge st-${esc(s)}">${esc(LABELS.status[s] || s)}</span>`;
const options = (map, selected, empty) =>
  (empty !== undefined ? `<option value="">${esc(empty)}</option>` : '') +
  Object.entries(map).map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(selected ?? '') ? 'selected' : ''}>${esc(l)}</option>`).join('');

function isoDate(d) { return d.toISOString().slice(0, 10); }
function periodFromDays(days) {
  const to = new Date();
  return { from: isoDate(new Date(to.getTime() - (days - 1) * 86400000)), to: isoDate(to) };
}

/* ======================= Estado e API ======================= */
const state = {
  token: safeStorage('get', 'token'),
  user: null,
  days: Number(safeStorage('get', 'days')) || 30,
};

function safeStorage(op, key, value) {
  try {
    if (op === 'get') return localStorage.getItem(key);
    if (op === 'set') localStorage.setItem(key, value);
    if (op === 'del') localStorage.removeItem(key);
  } catch { /* navegação privada: segue sem persistir */ }
  return null;
}

class ApiError extends Error {
  constructor(status, data) { super(data?.error || `Erro ${status}`); this.status = status; this.details = data?.details; }
}

async function api(path, { method = 'GET', body, raw = false } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  if (res.status === 401 && path !== '/api/auth/login') {
    logout(false);
    throw new ApiError(401, { error: 'Sessão expirada. Faça login novamente.' });
  }
  if (raw && res.ok) return res;
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

function qs(params) {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null)).toString();
  return s ? `?${s}` : '';
}

/* ======================= Feedback visual ======================= */
function toast(message, type = 'ok') {
  const el = document.createElement('div');
  el.className = `toast ${type === 'err' ? 'err' : ''}`;
  el.textContent = message;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), 3500);
}

function closeModal() { $('#modal-root').innerHTML = ''; }

/** Abre um modal com formulário. onSubmit recebe os dados; erros 422 são mostrados por campo. */
function formModal({ title, fields, submitLabel = 'Salvar', onSubmit }) {
  $('#modal-root').innerHTML = `
    <div class="modal-backdrop">
      <div class="card modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <h2>${esc(title)}</h2>
        <form class="form" novalidate>
          ${fields}
          <div class="form-actions full"></div>
        </form>
      </div>
    </div>`;
  const form = $('#modal-root form');
  const actions = $('.form-actions', form);
  actions.innerHTML = `<button type="button" data-cancel>Cancelar</button><button class="btn-primary" type="submit">${esc(submitLabel)}</button>`;
  $('[data-cancel]', form).onclick = closeModal;
  $('.modal-backdrop').addEventListener('mousedown', (e) => { if (e.target.classList.contains('modal-backdrop')) closeModal(); });
  $('input, select', form)?.focus();

  form.onsubmit = async (e) => {
    e.preventDefault();
    $$('.error', form).forEach((el) => (el.textContent = ''));
    const data = Object.fromEntries(new FormData(form));
    const btn = $('button[type=submit]', form);
    btn.disabled = true;
    try {
      await onSubmit(data);
      closeModal();
    } catch (err) {
      if (err.details) {
        for (const [field, msg] of Object.entries(err.details)) {
          const slot = $(`[data-error="${field}"]`, form);
          if (slot) slot.textContent = msg;
        }
      }
      toast(err.message, 'err');
    } finally {
      btn.disabled = false;
    }
  };
}

function field(label, name, { type = 'text', value = '', full = false, attrs = '', select } = {}) {
  const control = select
    ? `<select name="${name}" ${attrs}>${select}</select>`
    : `<input name="${name}" type="${type}" value="${esc(value)}" ${attrs}>`;
  return `<label class="${full ? 'full' : ''}">${esc(label)}${control}<span class="error" data-error="${name}"></span></label>`;
}

async function confirmAction(message) {
  return new Promise((resolve) => {
    $('#modal-root').innerHTML = `
      <div class="modal-backdrop"><div class="card modal" role="alertdialog">
        <h2>Confirmar</h2><p>${esc(message)}</p>
        <div class="form-actions"><button data-no>Cancelar</button><button class="btn-primary" data-yes>Confirmar</button></div>
      </div></div>`;
    $('[data-no]').onclick = () => { closeModal(); resolve(false); };
    $('[data-yes]').onclick = () => { closeModal(); resolve(true); };
    $('[data-yes]').focus();
  });
}

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

/* ======================= Gráficos (SVG puro) ======================= */
function lineChart(daily) {
  if (!daily.length) return '<p class="empty">Sem dados no período.</p>';
  const W = 760, H = 260, P = { t: 12, r: 12, b: 28, l: 64 };
  const max = Math.max(...daily.flatMap((d) => [d.spend, d.revenue]), 1) * 1.1;
  const x = (i) => P.l + (daily.length === 1 ? (W - P.l - P.r) / 2 : (i * (W - P.l - P.r)) / (daily.length - 1));
  const y = (v) => H - P.b - (v / max) * (H - P.t - P.b);
  const path = (key) => daily.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d[key]).toFixed(1)}`).join('');
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  const step = Math.ceil(daily.length / 8);
  return `
    <div class="legend"><span class="l-spend">Investimento</span><span class="l-revenue">Receita</span></div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Investimento e receita por dia" data-chart>
      ${ticks.map((v) => `<line class="grid-line" x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}"/>
        <text class="axis" x="${P.l - 8}" y="${y(v) + 4}" text-anchor="end">${esc(brl.format(Math.round(v)).replace(',00', ''))}</text>`).join('')}
      ${daily.map((d, i) => (i % step === 0 ? `<text class="axis" x="${x(i)}" y="${H - 8}" text-anchor="middle">${fmt.shortDate(d.date)}</text>` : '')).join('')}
      <path class="line-spend" d="${path('spend')}"/>
      <path class="line-revenue" d="${path('revenue')}"/>
      <line class="hover-line" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}" visibility="hidden"/>
      <rect x="${P.l}" y="${P.t}" width="${W - P.l - P.r}" height="${H - P.t - P.b}" fill="transparent" data-hover/>
    </svg>`;
}

/** Ativa o tooltip do gráfico de linhas. */
function bindLineChart(root, daily) {
  const svg = $('[data-chart]', root);
  if (!svg) return;
  const hover = $('[data-hover]', svg);
  const line = $('.hover-line', svg);
  let tip;
  hover.addEventListener('mousemove', (e) => {
    const box = svg.getBoundingClientRect();
    const vb = svg.viewBox.baseVal;
    const sx = ((e.clientX - box.left) / box.width) * vb.width;
    const x0 = Number(hover.getAttribute('x')), w = Number(hover.getAttribute('width'));
    const i = Math.max(0, Math.min(daily.length - 1, Math.round(((sx - x0) / w) * (daily.length - 1))));
    const d = daily[i];
    const px = daily.length === 1 ? x0 + w / 2 : x0 + (i * w) / (daily.length - 1);
    line.setAttribute('x1', px); line.setAttribute('x2', px); line.setAttribute('visibility', 'visible');
    if (!tip) { tip = document.createElement('div'); tip.className = 'tooltip'; document.body.append(tip); }
    tip.textContent = `${fmt.date(d.date)} · Invest. ${fmt.money(d.spend)} · Receita ${fmt.money(d.revenue)} · ROAS ${fmt.x(d.roas)}`;
    tip.style.left = `${Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8)}px`;
    tip.style.top = `${e.clientY - 40}px`;
  });
  hover.addEventListener('mouseleave', () => { tip?.remove(); tip = null; line.setAttribute('visibility', 'hidden'); });
}

function barChart(rows) {
  if (!rows.length) return '<p class="empty">Sem dados no período.</p>';
  const W = 360, rowH = 46, H = rows.length * rowH;
  const max = Math.max(...rows.map((r) => r.spend), 1);
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Investimento por plataforma">
    ${rows.map((r, i) => {
      const y = i * rowH;
      const w = Math.max(2, (r.spend / max) * W);
      return `<text class="bar-label" x="0" y="${y + 14}">${esc(LABELS.platform[r.platform])} — ${esc(fmt.money(r.spend))} · ROAS ${esc(fmt.x(r.roas))}</text>
        <rect class="bar-track" x="0" y="${y + 22}" width="${W}" height="12" rx="6"/>
        <rect class="bar-${esc(r.platform)}" x="0" y="${y + 22}" width="${w.toFixed(1)}" height="12" rx="6"/>`;
    }).join('')}
  </svg>`;
}

function kpiCards(t) {
  const card = (label, value, hint = '', cls = '') =>
    `<div class="card kpi"><div class="label">${label}</div><div class="value ${cls}">${value}</div><div class="hint">${hint}</div></div>`;
  return `<div class="grid kpis">
    ${card('Investimento', fmt.money(t.spend), `CPM ${fmt.money(t.cpm)}`)}
    ${card('Receita', fmt.money(t.revenue), `Lucro ${fmt.money(t.profit)}`)}
    ${card('ROAS', fmt.x(t.roas), 'receita ÷ investimento', t.roas >= 1 ? 'pos' : 'neg')}
    ${card('Conversões', fmt.int(t.conversions), `Taxa ${fmt.pct(t.conversion_rate)}`)}
    ${card('CPA', fmt.money(t.cpa), 'custo por conversão')}
    ${card('Cliques', fmt.int(t.clicks), `CTR ${fmt.pct(t.ctr)} · CPC ${fmt.money(t.cpc)}`)}
  </div>`;
}

function periodSelect() {
  return `<select data-period aria-label="Período">
    ${[7, 14, 30, 60].map((d) => `<option value="${d}" ${d === state.days ? 'selected' : ''}>Últimos ${d} dias</option>`).join('')}
  </select>`;
}
function bindPeriod(root, rerender) {
  const sel = $('[data-period]', root);
  if (sel) sel.onchange = () => { state.days = Number(sel.value); safeStorage('set', 'days', state.days); rerender(); };
}

/* ======================= Páginas ======================= */
const pages = {};

pages.login = (root) => {
  root.innerHTML = `
    <div class="login-wrap"><div class="card login">
      <h1>Gestor de Anúncios</h1>
      <p class="muted">Entre para gerenciar clientes e campanhas.</p>
      <form class="form" novalidate>
        ${field('E-mail', 'email', { type: 'email', value: 'admin@gestor.local', attrs: 'autocomplete="username" required' })}
        ${field('Senha', 'password', { type: 'password', attrs: 'autocomplete="current-password" required' })}
        <button class="btn-primary" type="submit">Entrar</button>
      </form>
      <div class="demo"><strong>Acessos de demonstração</strong><br>admin@gestor.local / admin123<br>gestor@gestor.local / gestor123</div>
    </div></div>`;
  const form = $('form', root);
  $('[name=password]', form).focus();
  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = $('button', form);
    btn.disabled = true;
    try {
      const data = await api('/api/auth/login', { method: 'POST', body: Object.fromEntries(new FormData(form)) });
      state.token = data.token;
      state.user = data.user;
      safeStorage('set', 'token', data.token);
      location.hash = '#/dashboard';
    } catch (err) {
      toast(err.message, 'err');
    } finally {
      btn.disabled = false;
    }
  };
};

pages.dashboard = async (main) => {
  const period = periodFromDays(state.days);
  const d = await api(`/api/dashboard${qs(period)}`);
  main.innerHTML = `
    <div class="page-head">
      <div><h1>Dashboard</h1><span class="muted">${fmt.date(d.period.from)} a ${fmt.date(d.period.to)} · ${d.counts.active_campaigns} campanhas ativas · ${d.counts.clients} clientes</span></div>
      <div class="toolbar">${periodSelect()}<button data-csv>Exportar CSV</button></div>
    </div>
    ${kpiCards(d.totals)}
    <div class="grid cols-2">
      <div class="card chart"><h2>Investimento × Receita por dia</h2>${lineChart(d.daily)}</div>
      <div class="card chart"><h2>Investimento por plataforma</h2>${barChart(d.by_platform)}</div>
    </div>
    <div class="card"><h2>Top 5 campanhas por lucro</h2><div class="table-wrap"><table>
      <thead><tr><th>Campanha</th><th>Cliente</th><th>Plataforma</th><th class="num">Investimento</th><th class="num">Receita</th><th class="num">Conversões</th><th class="num">ROAS</th></tr></thead>
      <tbody>${d.top_campaigns.map((c) => `<tr>
        <td><a href="#/campanhas/${c.id}">${esc(c.name)}</a></td><td>${esc(c.client_name)}</td><td>${platformTag(c.platform)}</td>
        <td class="num">${fmt.money(c.spend)}</td><td class="num">${fmt.money(c.revenue)}</td>
        <td class="num">${fmt.int(c.conversions)}</td><td class="num ${c.roas >= 1 ? 'pos' : 'neg'}">${fmt.x(c.roas)}</td></tr>`).join('')
        || '<tr><td colspan="7" class="empty">Sem dados no período.</td></tr>'}</tbody>
    </table></div></div>`;
  bindLineChart(main, d.daily);
  bindPeriod(main, () => render());
  $('[data-csv]', main).onclick = () => downloadCsv(period);
};

async function downloadCsv(period) {
  try {
    const res = await api(`/api/reports/campaigns.csv${qs(period)}`, { raw: true });
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement('a'), { href: url, download: `relatorio-campanhas_${period.from}_${period.to}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) { toast(err.message, 'err'); }
}

pages.clientes = async (main) => {
  main.innerHTML = `
    <div class="page-head"><h1>Clientes</h1>
      <div class="toolbar"><input type="search" placeholder="Buscar cliente…" data-q><button class="btn-primary" data-new>+ Novo cliente</button></div>
    </div>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr><th>Nome</th><th>Empresa</th><th>Segmento</th><th>Contato</th><th class="num">Campanhas</th><th></th></tr></thead>
      <tbody data-rows><tr><td colspan="6" class="empty">Carregando…</td></tr></tbody>
    </table></div></div>`;

  const load = async () => {
    const q = $('[data-q]', main).value;
    const rows = await api(`/api/clients${qs({ q })}`);
    $('[data-rows]', main).innerHTML = rows.map((c) => `<tr>
      <td><strong>${esc(c.name)}</strong></td><td>${esc(c.company || '—')}</td><td>${esc(c.segment || '—')}</td>
      <td>${esc(c.email || '')}<br><span class="muted">${esc(c.phone || '')}</span></td>
      <td class="num"><a href="#/campanhas?client_id=${c.id}">${c.active_campaigns} ativas / ${c.campaigns_count}</a></td>
      <td class="actions"><button class="btn-sm" data-edit="${c.id}">Editar</button> <button class="btn-sm btn-danger" data-del="${c.id}">Excluir</button></td>
    </tr>`).join('') || '<tr><td colspan="6" class="empty">Nenhum cliente encontrado.</td></tr>';
    $$('[data-edit]', main).forEach((b) => (b.onclick = () => clientForm(rows.find((c) => c.id === Number(b.dataset.edit)), load)));
    $$('[data-del]', main).forEach((b) => (b.onclick = async () => {
      const c = rows.find((r) => r.id === Number(b.dataset.del));
      if (!(await confirmAction(`Excluir "${c.name}"? As ${c.campaigns_count} campanha(s) e métricas dele também serão apagadas.`))) return;
      try { await api(`/api/clients/${c.id}`, { method: 'DELETE' }); toast('Cliente excluído'); load(); } catch (err) { toast(err.message, 'err'); }
    }));
  };
  let timer;
  $('[data-q]', main).oninput = () => { clearTimeout(timer); timer = setTimeout(load, 250); };
  $('[data-new]', main).onclick = () => clientForm(null, load);
  await load();
};

function clientForm(client, done) {
  formModal({
    title: client ? 'Editar cliente' : 'Novo cliente',
    fields: [
      field('Nome do responsável *', 'name', { value: client?.name, full: true }),
      field('Empresa', 'company', { value: client?.company }),
      field('Segmento', 'segment', { value: client?.segment }),
      field('E-mail', 'email', { type: 'email', value: client?.email }),
      field('Telefone', 'phone', { value: client?.phone }),
    ].join(''),
    onSubmit: async (data) => {
      await api(client ? `/api/clients/${client.id}` : '/api/clients', { method: client ? 'PUT' : 'POST', body: data });
      toast(client ? 'Cliente atualizado' : 'Cliente criado');
      done();
    },
  });
}

pages.campanhas = async (main, params) => {
  const clients = await api('/api/clients');
  const clientMap = Object.fromEntries(clients.map((c) => [c.id, c.name]));
  const filters = { client_id: params.get('client_id') || '', platform: '', status: '', q: '' };
  main.innerHTML = `
    <div class="page-head"><h1>Campanhas</h1>
      <div class="toolbar">
        <input type="search" placeholder="Buscar…" data-f="q">
        <select data-f="client_id">${options(clientMap, filters.client_id, 'Todos os clientes')}</select>
        <select data-f="platform">${options(LABELS.platform, '', 'Todas as plataformas')}</select>
        <select data-f="status">${options(LABELS.status, '', 'Todos os status')}</select>
        ${periodSelect()}
        <button class="btn-primary" data-new>+ Nova campanha</button>
      </div>
    </div>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr><th class="col-name">Campanha</th><th>Plataforma</th><th>Status</th><th class="num">Orç./dia</th><th class="num">Investimento</th>
        <th class="num">Cliques</th><th class="num">CTR</th><th class="num">Conv.</th><th class="num">CPA</th><th class="num">ROAS</th><th></th></tr></thead>
      <tbody data-rows><tr><td colspan="11" class="empty">Carregando…</td></tr></tbody>
    </table></div></div>`;

  const load = async () => {
    const rows = await api(`/api/campaigns${qs({ ...filters, ...periodFromDays(state.days) })}`);
    $('[data-rows]', main).innerHTML = rows.map((c) => {
      const k = c.kpis;
      const toggle = c.status === 'ativa' ? ['pausada', 'Pausar'] : ['ativa', 'Ativar'];
      return `<tr>
        <td><a href="#/campanhas/${c.id}"><strong>${esc(c.name)}</strong></a><br><span class="muted">${esc(c.client_name)} · ${esc(LABELS.objective[c.objective])}</span></td>
        <td>${platformTag(c.platform)}</td><td>${statusTag(c.status)}</td>
        <td class="num">${fmt.money(c.daily_budget)}</td><td class="num">${fmt.money(k.spend)}</td>
        <td class="num">${fmt.int(k.clicks)}</td><td class="num">${fmt.pct(k.ctr)}</td><td class="num">${fmt.int(k.conversions)}</td>
        <td class="num">${fmt.money(k.cpa)}</td><td class="num ${k.spend ? (k.roas >= 1 ? 'pos' : 'neg') : ''}">${fmt.x(k.roas)}</td>
        <td class="actions">
          ${c.status !== 'encerrada' ? `<button class="btn-sm" data-status="${c.id}:${toggle[0]}">${toggle[1]}</button>` : ''}
          <button class="btn-sm" data-edit="${c.id}">Editar</button>
          <button class="btn-sm btn-danger" data-del="${c.id}">Excluir</button>
        </td></tr>`;
    }).join('') || '<tr><td colspan="11" class="empty">Nenhuma campanha encontrada.</td></tr>';

    $$('[data-status]', main).forEach((b) => (b.onclick = async () => {
      const [id, status] = b.dataset.status.split(':');
      try { await api(`/api/campaigns/${id}/status`, { method: 'PATCH', body: { status } }); toast(`Campanha ${LABELS.status[status].toLowerCase()}`); load(); }
      catch (err) { toast(err.message, 'err'); }
    }));
    $$('[data-edit]', main).forEach((b) => (b.onclick = () => campaignForm(rows.find((c) => c.id === Number(b.dataset.edit)), clientMap, load)));
    $$('[data-del]', main).forEach((b) => (b.onclick = async () => {
      const c = rows.find((r) => r.id === Number(b.dataset.del));
      if (!(await confirmAction(`Excluir a campanha "${c.name}" e todas as métricas dela?`))) return;
      try { await api(`/api/campaigns/${c.id}`, { method: 'DELETE' }); toast('Campanha excluída'); load(); } catch (err) { toast(err.message, 'err'); }
    }));
  };

  let timer;
  $$('[data-f]', main).forEach((el) => {
    const handler = () => { filters[el.dataset.f] = el.value; clearTimeout(timer); timer = setTimeout(load, el.tagName === 'INPUT' ? 250 : 0); };
    el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', handler);
  });
  bindPeriod(main, load);
  $('[data-new]', main).onclick = () => {
    if (!clients.length) return toast('Cadastre um cliente primeiro', 'err');
    campaignForm({ client_id: filters.client_id }, clientMap, load);
  };
  await load();
};

function campaignForm(c, clientMap, done) {
  const editing = Boolean(c?.id);
  formModal({
    title: editing ? 'Editar campanha' : 'Nova campanha',
    fields: [
      field('Nome da campanha *', 'name', { value: c?.name, full: true }),
      field('Cliente *', 'client_id', { select: options(clientMap, c?.client_id, 'Selecione…') }),
      field('Plataforma *', 'platform', { select: options(LABELS.platform, c?.platform, 'Selecione…') }),
      field('Objetivo', 'objective', { select: options(LABELS.objective, c?.objective || 'conversao') }),
      field('Status', 'status', { select: options(LABELS.status, c?.status || 'rascunho') }),
      field('Orçamento diário (R$)', 'daily_budget', { type: 'number', value: c?.daily_budget ?? '', attrs: 'min="0" step="0.01"' }),
      field('Início', 'start_date', { type: 'date', value: c?.start_date || isoDate(new Date()) }),
      field('Término', 'end_date', { type: 'date', value: c?.end_date || '' }),
    ].join(''),
    onSubmit: async (data) => {
      await api(editing ? `/api/campaigns/${c.id}` : '/api/campaigns', { method: editing ? 'PUT' : 'POST', body: data });
      toast(editing ? 'Campanha atualizada' : 'Campanha criada');
      done();
    },
  });
}

pages.campanha = async (main, params, id) => {
  const period = periodFromDays(state.days);
  const [c, m] = await Promise.all([api(`/api/campaigns/${id}`), api(`/api/campaigns/${id}/metrics${qs(period)}`)]);
  const daily = [...m.daily].reverse();
  main.innerHTML = `
    <div class="page-head">
      <div><a href="#/campanhas">← Campanhas</a><h1>${esc(c.name)}</h1>
        <span class="muted">${esc(c.client_name)} · ${platformTag(c.platform)} · ${statusTag(c.status)} · ${esc(LABELS.objective[c.objective])} · ${fmt.money(c.daily_budget)}/dia · ${fmt.date(c.start_date)} a ${fmt.date(c.end_date)}</span></div>
      <div class="toolbar">${periodSelect()}<button class="btn-primary" data-add>+ Lançar métricas do dia</button></div>
    </div>
    ${kpiCards(m.totals)}
    <div class="card chart mb"><h2>Desempenho diário</h2>${lineChart(daily)}</div>
    <div class="card"><h2>Lançamentos diários</h2><div class="table-wrap"><table>
      <thead><tr><th>Data</th><th class="num">Impressões</th><th class="num">Cliques</th><th class="num">CTR</th><th class="num">Investimento</th>
        <th class="num">CPC</th><th class="num">Conversões</th><th class="num">Receita</th><th class="num">ROAS</th><th></th></tr></thead>
      <tbody>${m.daily.map((d) => `<tr><td>${fmt.date(d.date)}</td><td class="num">${fmt.int(d.impressions)}</td><td class="num">${fmt.int(d.clicks)}</td>
        <td class="num">${fmt.pct(d.ctr)}</td><td class="num">${fmt.money(d.spend)}</td><td class="num">${fmt.money(d.cpc)}</td>
        <td class="num">${fmt.int(d.conversions)}</td><td class="num">${fmt.money(d.revenue)}</td><td class="num">${fmt.x(d.roas)}</td>
        <td class="actions"><button class="btn-sm" data-edit-m="${d.id}">Editar</button> <button class="btn-sm btn-danger" data-del-m="${d.id}">Excluir</button></td></tr>`).join('')
        || '<tr><td colspan="10" class="empty">Nenhuma métrica lançada no período.</td></tr>'}</tbody>
    </table></div></div>`;
  bindLineChart(main, daily);
  bindPeriod(main, () => render());
  const reload = () => render();
  $('[data-add]', main).onclick = () => metricForm(id, null, reload);
  $$('[data-edit-m]', main).forEach((b) => (b.onclick = () => metricForm(id, m.daily.find((d) => d.id === Number(b.dataset.editM)), reload)));
  $$('[data-del-m]', main).forEach((b) => (b.onclick = async () => {
    if (!(await confirmAction('Excluir este lançamento?'))) return;
    try { await api(`/api/metrics/${b.dataset.delM}`, { method: 'DELETE' }); toast('Lançamento excluído'); reload(); } catch (err) { toast(err.message, 'err'); }
  }));
};

function metricForm(campaignId, d, done) {
  formModal({
    title: d ? `Editar lançamento de ${fmt.date(d.date)}` : 'Lançar métricas do dia',
    fields: [
      field('Data *', 'date', { type: 'date', value: d?.date || isoDate(new Date()), full: true, attrs: d ? 'readonly' : '' }),
      field('Impressões', 'impressions', { type: 'number', value: d?.impressions ?? '', attrs: 'min="0" step="1"' }),
      field('Cliques', 'clicks', { type: 'number', value: d?.clicks ?? '', attrs: 'min="0" step="1"' }),
      field('Investimento (R$)', 'spend', { type: 'number', value: d?.spend ?? '', attrs: 'min="0" step="0.01"' }),
      field('Conversões', 'conversions', { type: 'number', value: d?.conversions ?? '', attrs: 'min="0" step="1"' }),
      field('Receita (R$)', 'revenue', { type: 'number', value: d?.revenue ?? '', attrs: 'min="0" step="0.01"', full: true }),
    ].join(''),
    onSubmit: async (data) => {
      await api(`/api/campaigns/${campaignId}/metrics`, { method: 'POST', body: data });
      toast('Métricas salvas');
      done();
    },
  });
}

pages.usuarios = async (main) => {
  if (state.user.role !== 'admin') { main.innerHTML = '<p class="empty">Acesso restrito a administradores.</p>'; return; }
  const users = await api('/api/users');
  main.innerHTML = `
    <div class="page-head"><h1>Usuários</h1><button class="btn-primary" data-new>+ Novo usuário</button></div>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr><th>Nome</th><th>E-mail</th><th>Perfil</th><th>Criado em</th><th></th></tr></thead>
      <tbody>${users.map((u) => `<tr><td>${esc(u.name)}</td><td>${esc(u.email)}</td>
        <td><span class="badge">${u.role === 'admin' ? 'Administrador' : 'Gestor'}</span></td><td>${fmt.date(u.created_at.slice(0, 10))}</td>
        <td class="actions">${u.id !== state.user.id ? `<button class="btn-sm btn-danger" data-del="${u.id}">Excluir</button>` : '<span class="muted">você</span>'}</td></tr>`).join('')}</tbody>
    </table></div></div>`;
  $('[data-new]', main).onclick = () => formModal({
    title: 'Novo usuário',
    fields: [
      field('Nome *', 'name', { full: true }),
      field('E-mail *', 'email', { type: 'email' }),
      field('Senha * (mín. 6)', 'password', { type: 'password', attrs: 'autocomplete="new-password"' }),
      field('Perfil', 'role', { select: options({ gestor: 'Gestor', admin: 'Administrador' }, 'gestor'), full: true }),
    ].join(''),
    onSubmit: async (data) => { await api('/api/users', { method: 'POST', body: data }); toast('Usuário criado'); render(); },
  });
  $$('[data-del]', main).forEach((b) => (b.onclick = async () => {
    if (!(await confirmAction('Excluir este usuário?'))) return;
    try { await api(`/api/users/${b.dataset.del}`, { method: 'DELETE' }); toast('Usuário excluído'); render(); } catch (err) { toast(err.message, 'err'); }
  }));
};

/* ======================= Roteamento (hash) ======================= */
function layout(active) {
  const link = (href, label, key) => `<a href="${href}" class="${active === key ? 'active' : ''}">${label}</a>`;
  return `
    <div class="layout">
      <aside class="sidebar">
        <div class="brand"><img src="/favicon.svg" alt="">Gestor de Anúncios</div>
        <nav class="nav">
          ${link('#/dashboard', 'Dashboard', 'dashboard')}
          ${link('#/clientes', 'Clientes', 'clientes')}
          ${link('#/campanhas', 'Campanhas', 'campanhas')}
          ${state.user.role === 'admin' ? link('#/usuarios', 'Usuários', 'usuarios') : ''}
        </nav>
        <div class="user"><strong>${esc(state.user.name)}</strong><br><span class="muted">${esc(state.user.email)}</span><br>
          <a href="#" data-logout>Sair</a></div>
      </aside>
      <main class="main"><p class="loading">Carregando…</p></main>
    </div>`;
}

async function logout(callApi = true) {
  if (callApi && state.token) await api('/api/auth/logout', { method: 'POST' }).catch(() => {});
  state.token = null;
  state.user = null;
  safeStorage('del', 'token');
  if (location.hash !== '#/login') location.hash = '#/login';
  else render();
}

let renderSeq = 0;
async function render() {
  const seq = ++renderSeq;
  closeModal();
  $$('.tooltip').forEach((t) => t.remove());
  const app = $('#app');
  const [path, query = ''] = location.hash.slice(1).split('?');
  const params = new URLSearchParams(query);
  const parts = path.split('/').filter(Boolean);

  if (!state.token) return pages.login(app);
  if (!state.user) {
    try { state.user = await api('/api/auth/me'); } catch { return; }
  }
  if (parts[0] === 'login' || !parts.length) { location.hash = '#/dashboard'; return; }

  let page = parts[0];
  let id = null;
  if (page === 'campanhas' && parts[1]) { page = 'campanha'; id = Number(parts[1]); }
  if (!pages[page] || page === 'login') page = 'dashboard';

  app.innerHTML = layout(page === 'campanha' ? 'campanhas' : page);
  $('[data-logout]', app).onclick = (e) => { e.preventDefault(); logout(); };
  const main = $('main', app);
  try {
    await pages[page](main, params, id);
  } catch (err) {
    if (seq !== renderSeq || err.status === 401) return;
    main.innerHTML = `<div class="card empty">Não foi possível carregar: ${esc(err.message)}</div>`;
  }
}

window.addEventListener('hashchange', render);
render();
