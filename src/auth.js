// Autenticação: hash de senha com scrypt + sessões por token (Bearer).
import crypto from 'node:crypto';
import { HttpError } from './http.js';

const SESSION_HOURS = 8;

export function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(password, salt, 64).toString('hex');
  return `scrypt$${salt}$${hash}`;
}

export function verifyPassword(password, stored) {
  const [algo, salt, hash] = String(stored).split('$');
  if (algo !== 'scrypt' || !salt || !hash) return false;
  const expected = Buffer.from(hash, 'hex');
  const actual = crypto.scryptSync(password, salt, expected.length);
  return crypto.timingSafeEqual(expected, actual);
}

export function createSession(db, userId) {
  const token = crypto.randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + SESSION_HOURS * 3600_000).toISOString();
  db.prepare('DELETE FROM sessions WHERE expires_at < ?').run(new Date().toISOString());
  db.prepare('INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)').run(token, userId, expiresAt);
  return { token, expiresAt };
}

export function destroySession(db, token) {
  db.prepare('DELETE FROM sessions WHERE token = ?').run(token);
}

export function getBearerToken(req) {
  const header = req.headers.authorization || '';
  const [type, token] = header.split(' ');
  return type === 'Bearer' && token ? token : null;
}

/** Retorna o usuário autenticado ou lança 401. */
export function authenticate(db, req) {
  const token = getBearerToken(req);
  if (!token) throw new HttpError(401, 'Autenticação necessária');
  const user = db
    .prepare(
      `SELECT u.id, u.name, u.email, u.role FROM sessions s
       JOIN users u ON u.id = s.user_id
       WHERE s.token = ? AND s.expires_at > ?`
    )
    .get(token, new Date().toISOString());
  if (!user) throw new HttpError(401, 'Sessão inválida ou expirada');
  return { ...user, token };
}
