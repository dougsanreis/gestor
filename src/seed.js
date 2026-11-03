// Popula o banco com dados de demonstração (usuários, clientes, campanhas e 60 dias de métricas).
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
import { openDatabase, transaction } from './db.js';
import { hashPassword } from './auth.js';
import { config } from './config.js';

export const DEMO_USERS = [
  { name: 'Administrador', email: 'admin@gestor.local', password: 'admin123', role: 'admin' },
  { name: 'Gestora de Tráfego', email: 'gestor@gestor.local', password: 'gestor123', role: 'gestor' },
];

const CLIENTS = [
  ['Ana Souza', 'Bella Moda Ltda', 'ana@bellamoda.com.br', '(11) 98888-1111', 'E-commerce de moda'],
  ['Carlos Lima', 'Clínica Sorriso', 'contato@clinicasorriso.com.br', '(21) 97777-2222', 'Saúde / Odontologia'],
  ['Fernanda Rocha', 'EducaMais Cursos', 'fernanda@educamais.com', '(31) 96666-3333', 'Infoprodutos'],
  ['Roberto Alves', 'AutoPeças Rápido', 'roberto@autopecasrapido.com', '(41) 95555-4444', 'Varejo automotivo'],
];

// [clienteIdx, nome, plataforma, objetivo, status, orçamento diário, ticket médio, perfil de desempenho]
const CAMPAIGNS = [
  [0, 'Coleção Verão - Conversão', 'meta', 'conversao', 'ativa', 250, 180, 1.2],
  [0, 'Remarketing Carrinho', 'google', 'conversao', 'ativa', 120, 210, 1.6],
  [0, 'Reels Influenciadoras', 'tiktok', 'alcance', 'pausada', 80, 150, 0.6],
  [1, 'Implante Dentário - Leads', 'google', 'leads', 'ativa', 150, 900, 1.1],
  [1, 'Clareamento Promo', 'meta', 'leads', 'ativa', 90, 350, 0.9],
  [2, 'Lançamento Curso Excel', 'meta', 'conversao', 'ativa', 400, 297, 1.3],
  [2, 'Webinar Gratuito', 'linkedin', 'leads', 'encerrada', 200, 497, 0.7],
  [3, 'Pesquisa - Peças Freio', 'google', 'trafego', 'ativa', 70, 260, 1.0],
  [3, 'Black Friday Teaser', 'meta', 'engajamento', 'rascunho', 150, 200, 0],
];

const PLATFORM_BASE = { // CPM médio (R$) e CTR médio
  meta: { cpm: 18, ctr: 0.014 }, google: { cpm: 35, ctr: 0.045 },
  tiktok: { cpm: 10, ctr: 0.009 }, linkedin: { cpm: 60, ctr: 0.006 },
};

// Gerador pseudoaleatório determinístico: os alunos sempre veem os mesmos números.
function rng(seed) {
  return () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
}

export function seedDatabase(db, { days = 60 } = {}) {
  const rand = rng(42);
  transaction(db, () => {
    const insUser = db.prepare('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)');
    for (const u of DEMO_USERS) insUser.run(u.name, u.email, hashPassword(u.password), u.role);

    const insClient = db.prepare('INSERT INTO clients (name, company, email, phone, segment) VALUES (?, ?, ?, ?, ?)');
    const clientIds = CLIENTS.map((c) => Number(insClient.run(...c).lastInsertRowid));

    const insCampaign = db.prepare(`INSERT INTO campaigns
      (client_id, name, platform, objective, status, daily_budget, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`);
    const insMetric = db.prepare(`INSERT INTO metrics
      (campaign_id, date, impressions, clicks, spend, conversions, revenue) VALUES (?, ?, ?, ?, ?, ?, ?)`);

    const today = new Date();
    const dayStr = (offset) => new Date(today.getTime() - offset * 86400_000).toISOString().slice(0, 10);

    for (const [ci, name, platform, objective, status, budget, ticket, perf] of CAMPAIGNS) {
      const ended = status === 'encerrada';
      const start = dayStr(days - 1);
      const end = ended ? dayStr(20) : null;
      const id = Number(insCampaign.run(clientIds[ci], name, platform, objective, status, budget, start, end).lastInsertRowid);
      if (status === 'rascunho') continue;

      const base = PLATFORM_BASE[platform];
      for (let offset = days - 1; offset >= 0; offset--) {
        if (ended && offset < 20) continue;
        if (status === 'pausada' && offset < 10) continue;
        const weekend = [0, 6].includes(new Date(today.getTime() - offset * 86400_000).getDay());
        const spend = budget * (0.75 + rand() * 0.3) * (weekend ? 0.85 : 1);
        const impressions = Math.round((spend / (base.cpm * (0.85 + rand() * 0.3))) * 1000);
        const clicks = Math.round(impressions * base.ctr * (0.8 + rand() * 0.4));
        const convRate = 0.025 * perf * (0.7 + rand() * 0.6);
        const conversions = Math.round(clicks * convRate);
        const revenue = conversions * ticket * (0.85 + rand() * 0.3);
        insMetric.run(id, dayStr(offset), impressions, clicks, Math.round(spend * 100) / 100,
          conversions, Math.round(revenue * 100) / 100);
      }
    }
  });
}

export function isEmpty(db) {
  return db.prepare('SELECT COUNT(*) AS n FROM users').get().n === 0;
}

// Execução direta: `npm run seed` recria o banco do zero.
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv.includes('--reset')) {
    for (const suffix of ['', '-wal', '-shm']) fs.rmSync(config.dbPath + suffix, { force: true });
  }
  const db = openDatabase(config.dbPath);
  if (!isEmpty(db)) {
    console.log('O banco já possui dados. Use `npm run seed` (com --reset) para recriar.');
  } else {
    seedDatabase(db);
    console.log(`Banco populado em ${config.dbPath}`);
    for (const u of DEMO_USERS) console.log(`  ${u.role.padEnd(6)} -> ${u.email} / ${u.password}`);
  }
  db.close();
}
