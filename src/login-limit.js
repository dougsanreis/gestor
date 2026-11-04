// SQLite coordinates a single local database across processes. Not multi-host.
export class LoginLimiter {
  constructor({db, clock = () => Date.now(), windowMs = 60_000, maxFailures = 5, maxClients = 2048} = {}) {
    if (!db) throw new Error('LOGIN_LIMIT_DATABASE_REQUIRED');
    this.db=db; this.clock=clock; this.windowMs=windowMs; this.maxFailures=maxFailures; this.maxClients=maxClients;
    db.exec('PRAGMA busy_timeout = 500');
    db.exec('CREATE TABLE IF NOT EXISTS login_attempt_limits (address TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at INTEGER NOT NULL)');
  }
  transaction(fn) {
    this.db.exec('BEGIN IMMEDIATE');
    try { const result=fn(); this.db.exec('COMMIT'); return result; }
    catch (error) { try { this.db.exec('ROLLBACK'); } catch {} throw error; }
  }
  reserve(address) {
    if (typeof address !== 'string' || !address || address.length > 128) return {retryMs:this.windowMs};
    return this.transaction(() => {
      const now=this.clock();
      this.db.prepare('DELETE FROM login_attempt_limits WHERE expires_at <= ?').run(now);
      const entry=this.db.prepare('SELECT attempts, expires_at FROM login_attempt_limits WHERE address = ?').get(address);
      if (!entry && this.db.prepare('SELECT COUNT(*) AS total FROM login_attempt_limits').get().total >= this.maxClients) return {retryMs:this.windowMs};
      if (entry && entry.attempts >= this.maxFailures) return {retryMs:Math.max(1,entry.expires_at-now)};
      const until=entry?.expires_at ?? now+this.windowMs;
      this.db.prepare('INSERT INTO login_attempt_limits (address, attempts, expires_at) VALUES (?, 1, ?) ON CONFLICT(address) DO UPDATE SET attempts=attempts+1').run(address,until);
      return {retryMs:0,expiresAt:until};
    });
  }
  releaseSuccessful(address, expiresAt) {
    this.transaction(() => {
      this.db.prepare('UPDATE login_attempt_limits SET attempts=attempts-1 WHERE address=? AND expires_at=? AND attempts>0').run(address,expiresAt);
      this.db.prepare('DELETE FROM login_attempt_limits WHERE address=? AND expires_at=? AND attempts=0').run(address,expiresAt);
    });
  }
}
