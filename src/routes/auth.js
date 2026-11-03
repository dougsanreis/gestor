import { HttpError } from '../http.js';
import { createSession, destroySession, verifyPassword } from '../auth.js';
import { validate } from '../validation.js';

export function registerAuthRoutes(router, db) {
  router.add('POST', '/api/auth/login', ({ body }) => {
    const data = validate(body, {
      email: { type: 'email', required: true },
      password: { type: 'string', required: true },
    });
    const user = db.prepare('SELECT * FROM users WHERE email = ?').get(data.email);
    if (!user || !verifyPassword(data.password, user.password_hash)) {
      throw new HttpError(401, 'E-mail ou senha incorretos');
    }
    const session = createSession(db, user.id);
    return {
      token: session.token,
      expires_at: session.expiresAt,
      user: { id: user.id, name: user.name, email: user.email, role: user.role },
    };
  }, { auth: false });

  router.add('POST', '/api/auth/logout', ({ user }) => {
    destroySession(db, user.token);
  });

  router.add('GET', '/api/auth/me', ({ user }) => {
    const { token, ...publicUser } = user;
    return publicUser;
  });
}
