import { parsePeriod } from '../validation.js';
import { computeKpis, SUM_COLUMNS } from '../metrics.js';

/** Escapa um valor para CSV (aspas, ponto-e-vírgula, quebras de linha e fórmulas). */
export function csvCell(value) {
  let s = value === null || value === undefined ? '' : String(value);
  if (/^[=+\-@]/.test(s)) s = `'${s}`; // evita "CSV injection" no Excel
  return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function registerDashboardRoutes(router, db) {
  router.add('GET', '/api/dashboard', ({ query }) => {
    const { from, to } = parsePeriod(query);
    const period = [from, to];

    const totals = db.prepare(`SELECT ${SUM_COLUMNS} FROM metrics m WHERE m.date BETWEEN ? AND ?`).get(...period);

    const daily = db.prepare(`
      SELECT m.date, ${SUM_COLUMNS} FROM metrics m
      WHERE m.date BETWEEN ? AND ? GROUP BY m.date ORDER BY m.date`).all(...period);

    const byPlatform = db.prepare(`
      SELECT c.platform, ${SUM_COLUMNS} FROM metrics m
      JOIN campaigns c ON c.id = m.campaign_id
      WHERE m.date BETWEEN ? AND ? GROUP BY c.platform ORDER BY spend DESC`).all(...period);

    const topCampaigns = db.prepare(`
      SELECT c.id, c.name, c.platform, cl.name AS client_name, ${SUM_COLUMNS}
      FROM metrics m JOIN campaigns c ON c.id = m.campaign_id JOIN clients cl ON cl.id = c.client_id
      WHERE m.date BETWEEN ? AND ? GROUP BY c.id
      ORDER BY (SUM(m.revenue) - SUM(m.spend)) DESC LIMIT 5`).all(...period);

    const counts = db.prepare(`
      SELECT
        (SELECT COUNT(*) FROM clients) AS clients,
        (SELECT COUNT(*) FROM campaigns) AS campaigns,
        (SELECT COUNT(*) FROM campaigns WHERE status = 'ativa') AS active_campaigns,
        (SELECT COALESCE(SUM(daily_budget), 0) FROM campaigns WHERE status = 'ativa') AS active_daily_budget`).get();

    return {
      period: { from, to },
      counts,
      totals: computeKpis(totals),
      daily: daily.map((d) => ({ date: d.date, ...computeKpis(d) })),
      by_platform: byPlatform.map((p) => ({ platform: p.platform, ...computeKpis(p) })),
      top_campaigns: topCampaigns.map(({ id, name, platform, client_name, ...t }) => ({
        id, name, platform, client_name, ...computeKpis(t),
      })),
    };
  });

  // Relatório CSV (separador ';' para abrir direto no Excel em português).
  router.add('GET', '/api/reports/campaigns.csv', ({ query, res }) => {
    const { from, to } = parsePeriod(query);
    const rows = db.prepare(`
      SELECT c.id, c.name, cl.name AS client_name, c.platform, c.status, c.daily_budget, ${SUM_COLUMNS}
      FROM campaigns c JOIN clients cl ON cl.id = c.client_id
      LEFT JOIN metrics m ON m.campaign_id = c.id AND m.date BETWEEN ? AND ?
      GROUP BY c.id ORDER BY cl.name, c.name`).all(from, to);
    const header = ['ID', 'Campanha', 'Cliente', 'Plataforma', 'Status', 'Orçamento diário',
      'Impressões', 'Cliques', 'CTR %', 'Investimento', 'CPC', 'Conversões', 'CPA', 'Receita', 'ROAS'];
    const lines = rows.map((r) => {
      const k = computeKpis(r);
      return [r.id, r.name, r.client_name, r.platform, r.status, r.daily_budget,
        k.impressions, k.clicks, k.ctr, k.spend, k.cpc, k.conversions, k.cpa, k.revenue, k.roas]
        .map(csvCell).join(';');
    });
    const body = '﻿' + [header.join(';'), ...lines].join('\r\n');
    res.writeHead(200, {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': `attachment; filename="relatorio-campanhas_${from}_${to}.csv"`,
    });
    res.end(body);
  });
}
