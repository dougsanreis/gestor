import { HttpError } from '../http.js';
import { parseId, validate, validateResourceId } from '../validation.js';

const CLIENT_SCHEMA = {
  name: { type: 'string', required: true, min: 2, max: 100 },
  company: { type: 'string', max: 100 },
  email: { type: 'email' },
  phone: { type: 'string', max: 30 },
  segment: { type: 'string', max: 60 },
};

export function registerClientRoutes(router, db) {
  const findClient = (id) => {
    const client = db.prepare(`
      SELECT c.*, (SELECT COUNT(*) FROM campaigns WHERE client_id = c.id) AS campaigns_count
      FROM clients c WHERE c.id = ?`).get(id);
    if (!client) throw new HttpError(404, 'Cliente não encontrado');
    return client;
  };

  router.add('GET', '/api/clients', ({ query }) => {
    const q = `%${query.q ?? ''}%`;
    return db.prepare(`
      SELECT c.*,
        (SELECT COUNT(*) FROM campaigns WHERE client_id = c.id) AS campaigns_count,
        (SELECT COUNT(*) FROM campaigns WHERE client_id = c.id AND status = 'ativa') AS active_campaigns
      FROM clients c
      WHERE c.name LIKE ? OR IFNULL(c.company, '') LIKE ?
      ORDER BY c.name`).all(q, q);
  });

  router.add('GET', '/api/clients/:id', ({ params }) => findClient(parseId(params.id)));

  router.add('POST', '/api/clients', (ctx) => {
    const d = validate(ctx.body, CLIENT_SCHEMA);
    const { lastInsertRowid } = db
      .prepare('INSERT INTO clients (name, company, email, phone, segment) VALUES (?, ?, ?, ?, ?)')
      .run(d.name, d.company, d.email, d.phone, d.segment);
    ctx.status = 201;
    return findClient(lastInsertRowid);
  });

  router.add('PUT', '/api/clients/:id', ({ params, body }) => {
    const id = parseId(params.id);
    validateResourceId(body, id);
    findClient(id);
    const d = validate(body, CLIENT_SCHEMA);
    db.prepare('UPDATE clients SET name = ?, company = ?, email = ?, phone = ?, segment = ? WHERE id = ?')
      .run(d.name, d.company, d.email, d.phone, d.segment, id);
    return findClient(id);
  });

  router.add('DELETE', '/api/clients/:id', ({ params }) => {
    const { changes } = db.prepare('DELETE FROM clients WHERE id = ?').run(parseId(params.id));
    if (!changes) throw new HttpError(404, 'Cliente não encontrado');
  });
}
