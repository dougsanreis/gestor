import { createHash, timingSafeEqual } from "node:crypto";

/**
 * job_id vira nome de pasta (rm -rf no fim do job), chave de storage e caminho dentro
 * do filtro `ass=` do FFmpeg. Só aceitamos UUID ou slug simples: nada de "/", "..", ":".
 */
const JOB_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isSafeJobId(id: string): boolean {
  return JOB_ID_RE.test(id);
}

export function isUuid(id: string | undefined | null): id is string {
  return !!id && UUID_RE.test(id);
}

/** Compara o bearer em tempo constante (sem vazar o tamanho/prefixo por timing). */
export function bearerMatches(header: string | undefined, key: string): boolean {
  if (!key) return false;
  const token = (header ?? "").replace(/^Bearer\s+/i, "");
  const a = createHash("sha256").update(token).digest();
  const b = createHash("sha256").update(key).digest();
  return timingSafeEqual(a, b) && token.length > 0;
}

/**
 * Só HTTPS e só hosts da lista (subdomínios incluídos). Em dev, http://localhost é aceito
 * quando allowInsecure for true.
 */
export function isAllowedUrl(raw: string, allowedHosts: string[], allowInsecure = false): boolean {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return false;
  }
  const host = u.hostname.toLowerCase();
  if (u.username || u.password) return false;
  if (allowInsecure && allowedHosts.length === 0) return true;
  if (u.protocol !== "https:" && !(allowInsecure && u.protocol === "http:")) return false;
  return allowedHosts.some((h) => host === h || host.endsWith(`.${h}`));
}
