// Monta a aplicação: API REST + arquivos estáticos da interface.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { Router } from './router.js';
import { HttpError, readJson, sendJson } from './http.js';
import { authenticate } from './auth.js';
import { registerAuthRoutes } from './routes/auth.js';
import { registerUserRoutes } from './routes/users.js';
import { registerClientRoutes } from './routes/clients.js';
import { registerCampaignRoutes } from './routes/campaigns.js';
import { registerDashboardRoutes } from './routes/dashboard.js';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'",
};

export function buildRouter(db, { loginClock } = {}) {
  const router = new Router();
  router.add('GET', '/api/health', () => ({ status: 'ok', time: new Date().toISOString() }), { auth: false });
  registerAuthRoutes(router, db, { clock: loginClock });
  registerUserRoutes(router, db);
  registerClientRoutes(router, db);
  registerCampaignRoutes(router, db);
  registerDashboardRoutes(router, db);
  return router;
}

function serveStatic(req, res, publicDir, pathname) {
  if (req.method !== 'GET' && req.method !== 'HEAD') throw new HttpError(405, 'Método não permitido');
  const root = path.resolve(publicDir);
  let file = path.resolve(root, '.' + decodeURIComponent(pathname));
  // Bloqueia "path traversal" (ex.: /../../etc/passwd)
  if (file !== root && !file.startsWith(root + path.sep)) throw new HttpError(403, 'Acesso negado');
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(root, 'index.html'); // SPA
  const ext = path.extname(file);
  res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream', ...SECURITY_HEADERS });
  if (req.method === 'HEAD') return res.end();
  fs.createReadStream(file).pipe(res);
}

export function createApp({ db, publicDir, logger = console, loginClock }) {
  const router = buildRouter(db, { loginClock });

  return http.createServer(async (req, res) => {
    const started = performance.now();
    const url = new URL(req.url, 'http://localhost');
    try {
      if (!url.pathname.startsWith('/api/')) return serveStatic(req, res, publicDir, url.pathname);

      const match = router.match(req.method, url.pathname);
      if (!match) throw new HttpError(404, 'Rota não encontrada');
      if (match.methodNotAllowed) throw new HttpError(405, 'Método não permitido');

      const { route, params } = match;
      const ctx = { req, res, db, params, query: Object.fromEntries(url.searchParams), user: null, status: 200, body: {} };
      if (route.auth) ctx.user = authenticate(db, req);
      if (route.role && ctx.user.role !== route.role) throw new HttpError(403, 'Permissão insuficiente');
      if (['POST', 'PUT', 'PATCH'].includes(req.method)) ctx.body = await readJson(req);

      const result = await route.handler(ctx);
      if (res.writableEnded || res.headersSent) return;
      if (result === undefined) { res.writeHead(204); res.end(); } else sendJson(res, ctx.status, result);
    } catch (err) {
      if (err instanceof HttpError) {
        sendJson(res, err.status, { error: err.message, ...(err.details && { details: err.details }) });
      } else {
        logger.error('[erro]', err);
        if (!res.headersSent) sendJson(res, 500, { error: 'Erro interno do servidor' });
      }
    } finally {
      if (url.pathname.startsWith('/api/')) {
        const ms = (performance.now() - started).toFixed(1);
        logger.log(`${new Date().toISOString()} ${req.method} ${url.pathname} -> ${res.statusCode} (${ms}ms)`);
      }
    }
  });
}
