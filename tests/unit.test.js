import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeKpis } from '../src/metrics.js';
import { validate, isValidDate, parsePeriod } from '../src/validation.js';
import { hashPassword, verifyPassword } from '../src/auth.js';
import { csvCell } from '../src/routes/dashboard.js';
import { Router } from '../src/router.js';

test('computeKpis calcula indicadores corretamente', () => {
  const k = computeKpis({ impressions: 10000, clicks: 200, spend: 100, conversions: 10, revenue: 500 });
  assert.equal(k.ctr, 2);
  assert.equal(k.cpc, 0.5);
  assert.equal(k.cpm, 10);
  assert.equal(k.cpa, 10);
  assert.equal(k.conversion_rate, 5);
  assert.equal(k.roas, 5);
  assert.equal(k.profit, 400);
});

test('computeKpis não divide por zero', () => {
  const k = computeKpis({});
  assert.deepEqual([k.ctr, k.cpc, k.cpa, k.roas], [0, 0, 0, 0]);
});

test('validate aplica regras e devolve erros por campo', () => {
  const schema = { name: { type: 'string', required: true, min: 2 }, n: { type: 'integer', min: 0 }, e: { type: 'enum', values: ['a'] } };
  assert.deepEqual(validate({ name: ' Ana ', n: '3', e: 'a', extra: 1 }, schema), { name: 'Ana', n: 3, e: 'a' });
  assert.throws(() => validate({ name: 'A', n: -1, e: 'b' }, schema), (err) => {
    assert.equal(err.status, 422);
    assert.deepEqual(Object.keys(err.details).sort(), ['e', 'n', 'name']);
    return true;
  });
});

test('isValidDate rejeita datas impossíveis', () => {
  assert.ok(isValidDate('2024-02-29'));
  assert.ok(!isValidDate('2023-02-29'));
  assert.ok(!isValidDate('2024-13-01'));
  assert.ok(!isValidDate('01/02/2024'));
});

test('parsePeriod valida intervalo', () => {
  assert.deepEqual(parsePeriod({ from: '2024-01-01', to: '2024-01-31' }), { from: '2024-01-01', to: '2024-01-31' });
  assert.throws(() => parsePeriod({ from: '2024-02-01', to: '2024-01-01' }));
});

test('hash de senha: verifica correta e rejeita incorreta', () => {
  const h = hashPassword('segredo');
  assert.ok(h.startsWith('scrypt$'));
  assert.ok(verifyPassword('segredo', h));
  assert.ok(!verifyPassword('errado', h));
  assert.notEqual(hashPassword('segredo'), h, 'salt aleatório gera hashes diferentes');
});

test('csvCell escapa separador e neutraliza fórmulas', () => {
  assert.equal(csvCell('a;b'), '"a;b"');
  assert.equal(csvCell('=SOMA(A1)'), "'=SOMA(A1)");
  assert.equal(csvCell(null), '');
});

test('Router extrai parâmetros e detecta método não permitido', () => {
  const r = new Router();
  r.add('GET', '/api/x/:id', () => {});
  assert.deepEqual(r.match('GET', '/api/x/7').params, { id: '7' });
  assert.ok(r.match('POST', '/api/x/7').methodNotAllowed);
  assert.equal(r.match('GET', '/api/y'), null);
});
