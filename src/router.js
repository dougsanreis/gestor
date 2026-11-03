// Roteador minimalista: converte '/api/clients/:id' em expressão regular.
export class Router {
  constructor() {
    this.routes = [];
  }

  /**
   * @param {string} method  GET | POST | PUT | PATCH | DELETE
   * @param {string} pattern ex.: '/api/campaigns/:id'
   * @param {Function} handler (ctx) => resultado (objeto vira JSON; undefined vira 204)
   * @param {{auth?: boolean, role?: string}} options
   */
  add(method, pattern, handler, options = {}) {
    const keys = [];
    const source = pattern.replace(/:(\w+)/g, (_, key) => {
      keys.push(key);
      return '([^/]+)';
    });
    this.routes.push({
      method,
      regex: new RegExp(`^${source}/?$`),
      keys,
      handler,
      auth: options.auth !== false,
      role: options.role,
    });
  }

  match(method, pathname) {
    let pathMatched = false;
    for (const route of this.routes) {
      const m = route.regex.exec(pathname);
      if (!m) continue;
      pathMatched = true;
      if (route.method !== method) continue;
      const params = {};
      route.keys.forEach((k, i) => (params[k] = decodeURIComponent(m[i + 1])));
      return { route, params };
    }
    return pathMatched ? { methodNotAllowed: true } : null;
  }
}
