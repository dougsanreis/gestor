import { HttpError } from '../http.js';
import { hashPassword } from '../auth.js';
import { parseId, validate } from '../validation.js';

const USER_FIELDS = 'id, name, email, role, created_at';

export function registerUserRoutes(router, db) {
  const adminOnly = { role: 'admin' };

  router.add('GET', '/api/users', () =>
    db.prepare(`SELECT ${USER_FIELDS} FROM users ORDER BY name`).all(), adminOnly);

  router.add('POST', '/api/users', (ctx) => {
    const data = validate(ctx.body, {
      name: { type: 'string', required: true, min: 2, max: 100 },
      email: { type: 'email', required: true },
      password: { type: 'string', required: true, min: 6, max: 100 },
      role: { type: 'enum', values: ['admin', 'gestor'], default: 'gestor' },
    });
    if (db.prepare('SELECT 1 FROM users WHERE email = ?').get(data.email)) {
      throw new HttpError(409, 'Já existe um usuário com este e-mail');
    }
    const { lastInsertRowid } = db
      .prepare('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)')
      .run(data.name, data.email, hashPassword(data.password), data.role);
    ctx.status = 201;
    return db.prepare(`SELECT ${USER_FIELDS} FROM users WHERE id = ?`).get(lastInsertRowid);
  }, adminOnly);

  router.add('DELETE', '/api/users/:id', ({ params, user }) => {
    const id = parseId(params.id);
    if (id === user.id) throw new HttpError(400, 'Você não pode excluir o próprio usuário');
    const { changes } = db.prepare('DELETE FROM users WHERE id = ?').run(id);
    if (!changes) throw new HttpError(404, 'Usuário não encontrado');
  }, adminOnly);
}
