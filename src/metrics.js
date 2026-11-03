// Fórmulas de KPIs de tráfego pago. Centralizadas aqui para serem reutilizadas e testadas.
const round = (n, d = 2) => Math.round(n * 10 ** d) / 10 ** d;
const safeDiv = (a, b) => (b > 0 ? a / b : 0);

/** Recebe totais brutos e devolve os totais + indicadores derivados. */
export function computeKpis(row = {}) {
  const impressions = Number(row.impressions) || 0;
  const clicks = Number(row.clicks) || 0;
  const spend = Number(row.spend) || 0;
  const conversions = Number(row.conversions) || 0;
  const revenue = Number(row.revenue) || 0;
  return {
    impressions,
    clicks,
    spend: round(spend),
    conversions,
    revenue: round(revenue),
    ctr: round(safeDiv(clicks, impressions) * 100), // Click-through rate (%)
    cpc: round(safeDiv(spend, clicks)),             // Custo por clique
    cpm: round(safeDiv(spend, impressions) * 1000), // Custo por mil impressões
    cpa: round(safeDiv(spend, conversions)),        // Custo por aquisição
    conversion_rate: round(safeDiv(conversions, clicks) * 100), // Taxa de conversão (%)
    roas: round(safeDiv(revenue, spend)),           // Retorno sobre investimento em anúncios
    profit: round(revenue - spend),
  };
}

export const SUM_COLUMNS = `
  COALESCE(SUM(m.impressions), 0) AS impressions,
  COALESCE(SUM(m.clicks), 0)      AS clicks,
  COALESCE(SUM(m.spend), 0)       AS spend,
  COALESCE(SUM(m.conversions), 0) AS conversions,
  COALESCE(SUM(m.revenue), 0)     AS revenue`;
