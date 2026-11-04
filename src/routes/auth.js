import { HttpError } from '../http.js';
import { createSession, destroySession, verifyPassword } from '../auth.js';
import { validate } from '../validation.js';
import { LoginLimiter } from '../login-limit.js';

export function registerAuthRoutes(router, db, { clock } = {}) {
  const limiter = new LoginLimiter({db, clock});
  router.add('POST', '/api/auth/login', ({ body, req, res }) => {
    const data = validate(body, {
      email: { type: 'email', required: true },
      password: { type: 'string', required: true },
    });
    const address = req.socket.remoteAddress;
    let reservation;
    try { reservation = limiter.reserve(address); }
    catch { throw new HttpError(503, 'Limitador de login indisponível'); }
    if (reservation.retryMs) {
      res.setHeader('Retry-After', String(Math.ceil(reservation.retryMs / 1000)));
      throw new HttpError(429, 'Muitas tentativas. Tente novamente mais tarde');
    }
    const user = db.prepare('SELECT * FROM users WHERE email = ?').get(data.email);
    if (!user || !verifyPassword(data.password, user.password_hash)) {
      throw new HttpError(401, 'E-mail ou senha incorretos');
    }
    try { limiter.releaseSuccessful(address, reservation.expiresAt); }
    catch { throw new HttpError(503, 'Limitador de login indisponível'); }
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
