import { HttpError } from '../http.js';
import { parseId, parsePeriod, validate } from '../validation.js';
import { computeKpis, SUM_COLUMNS } from '../metrics.js';

export const PLATFORMS = ['meta', 'google', 'tiktok', 'linkedin'];
export const STATUSES = ['rascunho', 'ativa', 'pausada', 'encerrada'];
export const OBJECTIVES = ['conversao', 'trafego', 'alcance', 'leads', 'engajamento'];

const CAMPAIGN_SCHEMA = {
  client_id: { type: 'integer', required: true, min: 1 },
  name: { type: 'string', required: true, min: 2, max: 120 },
  platform: { type: 'enum', required: true, values: PLATFORMS },
  objective: { type: 'enum', values: OBJECTIVES, default: 'conversao' },
  status: { type: 'enum', values: STATUSES, default: 'rascunho' },
  daily_budget: { type: 'number', min: 0, max: 1_000_000, default: 0 },
  start_date: { type: 'date' },
  end_date: { type: 'date' },
};

const METRIC_SCHEMA = {
  date: { type: 'date', required: true },
  impressions: { type: 'integer', min: 0, default: 0 },
  clicks: { type: 'integer', min: 0, default: 0 },
  spend: { type: 'number', min: 0, default: 0 },
  conversions: { type: 'integer', min: 0, default: 0 },
  revenue: { type: 'number', min: 0, default: 0 },
};

export function registerCampaignRoutes(router, db) {
  const findCampaign = (id) => {
    const c = db.prepare(`
      SELECT c.*, cl.name AS client_name FROM campaigns c
      JOIN clients cl ON cl.id = c.client_id WHERE c.id = ?`).get(id);
    if (!c) throw new HttpError(404, 'Campanha não encontrada');
    return c;
  };

  const checkBusinessRules = (d) => {
    if (!db.prepare('SELECT 1 FROM clients WHERE id = ?').get(d.client_id)) {
      throw new HttpError(422, 'Dados inválidos', { client_id: 'Cliente não existe' });
    }
    if (d.start_date && d.end_date && d.end_date < d.start_date) {
      throw new HttpError(422, 'Dados inválidos', { end_date: 'Término deve ser após o início' });
    }
  };

  // Lista com filtros e KPIs agregados do período.
  router.add('GET', '/api/campaigns', ({ query }) => {
    const { from, to } = parsePeriod(query);
    const where = [];
    const args = [from, to];
    if (query.client_id) { where.push('c.client_id = ?'); args.push(parseId(query.client_id)); }
    if (query.status) { where.push('c.status = ?'); args.push(query.status); }
    if (query.platform) { where.push('c.platform = ?'); args.push(query.platform); }
    if (query.q) { where.push('c.name LIKE ?'); args.push(`%${query.q}%`); }
    const rows = db.prepare(`
      SELECT c.*, cl.name AS client_name, ${SUM_COLUMNS}
      FROM campaigns c
      JOIN clients cl ON cl.id = c.client_id
      LEFT JOIN metrics m ON m.campaign_id = c.id AND m.date BETWEEN ? AND ?
      ${where.length ? `WHERE ${where.join(' AND ')}` : ''}
      GROUP BY c.id
      ORDER BY c.created_at DESC, c.id DESC`).all(...args);
    return rows.map(({ impressions, clicks, spend, conversions, revenue, ...c }) => ({
      ...c,
      kpis: computeKpis({ impressions, clicks, spend, conversions, revenue }),
    }));
  });

  router.add('GET', '/api/campaigns/:id', ({ params }) => findCampaign(parseId(params.id)));

  router.add('POST', '/api/campaigns', (ctx) => {
    const d = validate(ctx.body, CAMPAIGN_SCHEMA);
    checkBusinessRules(d);
    const { lastInsertRowid } = db.prepare(`
      INSERT INTO campaigns (client_id, name, platform, objective, status, daily_budget, start_date, end_date)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(d.client_id, d.name, d.platform, d.objective, d.status, d.daily_budget, d.start_date, d.end_date);
    ctx.status = 201;
    return findCampaign(lastInsertRowid);
  });

  router.add('PUT', '/api/campaigns/:id', ({ params, body }) => {
    const id = parseId(params.id);
    findCampaign(id);
    const d = validate(body, CAMPAIGN_SCHEMA);
    checkBusinessRules(d);
    db.prepare(`
      UPDATE campaigns SET client_id = ?, name = ?, platform = ?, objective = ?, status = ?,
        daily_budget = ?, start_date = ?, end_date = ? WHERE id = ?`)
      .run(d.client_id, d.name, d.platform, d.objective, d.status, d.daily_budget, d.start_date, d.end_date, id);
    return findCampaign(id);
  });

  // Troca rápida de status (ativar / pausar / encerrar).
  router.add('PATCH', '/api/campaigns/:id/status', ({ params, body }) => {
    const id = parseId(params.id);
    findCampaign(id);
    const { status } = validate(body, { status: { type: 'enum', required: true, values: STATUSES } });
    db.prepare('UPDATE campaigns SET status = ? WHERE id = ?').run(status, id);
    return findCampaign(id);
  });

  router.add('DELETE', '/api/campaigns/:id', ({ params }) => {
    const { changes } = db.prepare('DELETE FROM campaigns WHERE id = ?').run(parseId(params.id));
    if (!changes) throw new HttpError(404, 'Campanha não encontrada');
  });

  // ---- Métricas diárias da campanha ----
  router.add('GET', '/api/campaigns/:id/metrics', ({ params, query }) => {
    const id = parseId(params.id);
    findCampaign(id);
    const { from, to } = parsePeriod(query);
    const rows = db.prepare(`
      SELECT * FROM metrics WHERE campaign_id = ? AND date BETWEEN ? AND ? ORDER BY date DESC`)
      .all(id, from, to);
    const totals = db.prepare(`
      SELECT ${SUM_COLUMNS} FROM metrics m WHERE m.campaign_id = ? AND m.date BETWEEN ? AND ?`)
      .get(id, from, to);
    return {
      period: { from, to },
      totals: computeKpis(totals),
      daily: rows.map((r) => ({ id: r.id, date: r.date, ...computeKpis(r) })),
    };
  });

  // Upsert: se já existir lançamento no mesmo dia, ele é substituído.
  router.add('POST', '/api/campaigns/:id/metrics', (ctx) => {
    const id = parseId(ctx.params.id);
    findCampaign(id);
    const d = validate(ctx.body, METRIC_SCHEMA);
    if (d.clicks > d.impressions) {
      throw new HttpError(422, 'Dados inválidos', { clicks: 'Cliques não podem superar impressões' });
    }
    db.prepare(`
      INSERT INTO metrics (campaign_id, date, impressions, clicks, spend, conversions, revenue)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (campaign_id, date) DO UPDATE SET
        impressions = excluded.impressions, clicks = excluded.clicks, spend = excluded.spend,
        conversions = excluded.conversions, revenue = excluded.revenue`)
      .run(id, d.date, d.impressions, d.clicks, d.spend, d.conversions, d.revenue);
    const row = db.prepare('SELECT * FROM metrics WHERE campaign_id = ? AND date = ?').get(id, d.date);
    ctx.status = 201;
    return { id: row.id, campaign_id: id, date: row.date, ...computeKpis(row) };
  });

  router.add('DELETE', '/api/metrics/:id', ({ params }) => {
    const { changes } = db.prepare('DELETE FROM metrics WHERE id = ?').run(parseId(params.id));
    if (!changes) throw new HttpError(404, 'Métrica não encontrada');
  });
}
