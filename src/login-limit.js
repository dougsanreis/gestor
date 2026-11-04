// Local, per-process failed-login limiter. Never trusts forwarded client headers.
export class LoginLimiter {
  constructor({clock = () => Date.now(), windowMs = 60_000, maxFailures = 5, maxClients = 2048} = {}) {
    this.clock=clock; this.windowMs=windowMs; this.maxFailures=maxFailures; this.maxClients=maxClients;
    this.clients=new Map();
  }
  check(address) {
    const now=this.clock();
    for (const [key, entry] of this.clients) if (now >= entry.until) this.clients.delete(key);
    if (typeof address !== 'string' || !address || address.length > 128) return this.windowMs;
    const entry=this.clients.get(address);
    if (!entry && this.clients.size >= this.maxClients) return this.windowMs;
    return entry && entry.failures >= this.maxFailures ? Math.max(1,entry.until-now) : 0;
  }
  fail(address) {
    const existing=this.clients.get(address);
    if (existing) existing.failures += 1;
    else this.clients.set(address,{failures:1,until:this.clock()+this.windowMs});
  }
  succeed(address) { this.clients.delete(address); }
}
