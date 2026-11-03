// Testes de integração: sobe o servidor real em porta aleatória com banco em memória.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { openDatabase } from '../src/db.js';
import { createApp } from '../src/app.js';
import { seedDatabase } from '../src/seed.js';

let server, base, token;
const silent = { log() {}, error() {} };

async function call(method, url, body, auth = token) {
  const res = await fetch(base + url, {
    method,
    headers: { ...(auth && { Authorization: `Bearer ${auth}` }), ...(body && { 'Content-Type': 'application/json' }) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = text;
  try { data = JSON.parse(text); } catch {}
  return { status: res.status, data, headers: res.headers };
}

before(async () => {
  const db = openDatabase(':memory:');
  seedDatabase(db, { days: 10 });
  server = createApp({ db, publicDir: path.resolve('public'), logger: silent });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => server.close());

test('health é público', async () => {
  const r = await call('GET', '/api/health', null, null);
  assert.equal(r.status, 200);
  assert.equal(r.data.status, 'ok');
});

test('rotas protegidas exigem token', async () => {
  assert.equal((await call('GET', '/api/clients', null, null)).status, 401);
  assert.equal((await call('GET', '/api/clients', null, 'token-falso')).status, 401);
});

test('login rejeita senha errada e aceita a correta', async () => {
  assert.equal((await call('POST', '/api/auth/login', { email: 'admin@gestor.local', password: 'x' })).status, 401);
  const r = await call('POST', '/api/auth/login', { email: 'admin@gestor.local', password: 'admin123' });
  assert.equal(r.status, 200);
  assert.equal(r.data.user.role, 'admin');
  assert.equal(r.data.user.password_hash, undefined);
  token = r.data.token;
  assert.equal((await call('GET', '/api/auth/me')).data.email, 'admin@gestor.local');
});

test('CRUD de clientes', async () => {
  const created = await call('POST', '/api/clients', { name: 'Loja Teste', email: 'loja@teste.com' });
  assert.equal(created.status, 201);
  const id = created.data.id;
  assert.equal((await call('PUT', `/api/clients/${id}`, { name: 'Loja Teste 2' })).data.name, 'Loja Teste 2');
  assert.ok((await call('GET', '/api/clients?q=Teste 2')).data.some((c) => c.id === id));
  assert.equal((await call('DELETE', `/api/clients/${id}`)).status, 204);
  assert.equal((await call('GET', `/api/clients/${id}`)).status, 404);
});

test('validação devolve 422 com detalhes por campo', async () => {
  const r = await call('POST', '/api/clients', { name: '', email: 'invalido' });
  assert.equal(r.status, 422);
  assert.ok(r.data.details.name && r.data.details.email);
  const j = await fetch(base + '/api/clients', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: '{quebrado' });
  assert.equal(j.status, 400);
});

test('fluxo completo: campanha, status, métricas e KPIs', async () => {
  const client = (await call('POST', '/api/clients', { name: 'Cliente Fluxo' })).data;
  const bad = await call('POST', '/api/campaigns', { client_id: client.id, name: 'X', platform: 'orkut' });
  assert.equal(bad.status, 422);
  const dates = await call('POST', '/api/campaigns', { client_id: client.id, name: 'Datas', platform: 'meta', start_date: '2024-05-10', end_date: '2024-05-01' });
  assert.equal(dates.status, 422);

  const camp = (await call('POST', '/api/campaigns', { client_id: client.id, name: 'Campanha Fluxo', platform: 'google', daily_budget: '50,5' })).data;
  assert.equal(camp.status, 'rascunho');
  assert.equal(camp.daily_budget, 50.5);

  assert.equal((await call('PATCH', `/api/campaigns/${camp.id}/status`, { status: 'ativa' })).data.status, 'ativa');

  const day = '2024-03-10';
  const m = await call('POST', `/api/campaigns/${camp.id}/metrics`, { date: day, impressions: 1000, clicks: 50, spend: 25, conversions: 5, revenue: 100 });
  assert.equal(m.status, 201);
  assert.equal(m.data.ctr, 5);
  assert.equal(m.data.roas, 4);
  // upsert no mesmo dia substitui o valor
  await call('POST', `/api/campaigns/${camp.id}/metrics`, { date: day, impressions: 1000, clicks: 50, spend: 50, conversions: 5, revenue: 100 });
  const list = await call('GET', `/api/campaigns/${camp.id}/metrics?from=2024-03-01&to=2024-03-31`);
  assert.equal(list.data.daily.length, 1);
  assert.equal(list.data.totals.roas, 2);

  const tooMany = await call('POST', `/api/campaigns/${camp.id}/metrics`, { date: day, impressions: 10, clicks: 50 });
  assert.equal(tooMany.status, 422);

  const filtered = await call('GET', `/api/campaigns?client_id=${client.id}&from=2024-03-01&to=2024-03-31`);
  assert.equal(filtered.data.length, 1);
  assert.equal(filtered.data[0].kpis.spend, 50);

  // excluir cliente apaga campanhas em cascata
  await call('DELETE', `/api/clients/${client.id}`);
  assert.equal((await call('GET', `/api/campaigns/${camp.id}`)).status, 404);
});

test('dashboard agrega dados do seed', async () => {
  const r = await call('GET', '/api/dashboard');
  assert.equal(r.status, 200);
  assert.ok(r.data.totals.spend > 0);
  assert.ok(r.data.daily.length > 0);
  assert.ok(r.data.by_platform.length > 0);
  assert.ok(r.data.top_campaigns.length <= 5);
  assert.equal((await call('GET', '/api/dashboard?from=2024-99-01')).status, 400);
});

test('relatório CSV', async () => {
  const r = await call('GET', '/api/reports/campaigns.csv');
  assert.equal(r.status, 200);
  assert.match(r.headers.get('content-type'), /text\/csv/);
  assert.match(r.data, /Campanha;Cliente;Plataforma/);
});

test('permissões: gestor não acessa usuários', async () => {
  const g = await call('POST', '/api/auth/login', { email: 'gestor@gestor.local', password: 'gestor123' });
  assert.equal((await call('GET', '/api/users', null, g.data.token)).status, 403);
  const created = await call('POST', '/api/users', { name: 'Novo', email: 'novo@x.com', password: '123456' });
  assert.equal(created.status, 201);
  assert.equal((await call('POST', '/api/users', { name: 'Novo', email: 'NOVO@x.com', password: '123456' })).status, 409);
});

test('logout invalida o token', async () => {
  const s = await call('POST', '/api/auth/login', { email: 'gestor@gestor.local', password: 'gestor123' });
  assert.equal((await call('POST', '/api/auth/logout', null, s.data.token)).status, 204);
  assert.equal((await call('GET', '/api/auth/me', null, s.data.token)).status, 401);
});

test('interface estática e proteção contra path traversal', async () => {
  const home = await fetch(base + '/');
  assert.equal(home.status, 200);
  assert.match(await home.text(), /Gestor de Anúncios/);
  assert.ok(home.headers.get('content-security-policy'));
  const trav = await fetch(base + '/%2e%2e/package.json');
  assert.notEqual(await trav.text().then((t) => t.includes('"name"')), true);
  assert.equal((await call('GET', '/api/nao-existe')).status, 404);
  assert.equal((await call('DELETE', '/api/health')).status, 405);
});
