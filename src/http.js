// Utilitários HTTP: erros padronizados, leitura de JSON e respostas.
export class HttpError extends Error {
  constructor(status, message, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

const MAX_BODY = 1024 * 1024; // 1 MB

export async function readJson(req) {
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) throw new HttpError(413, 'Corpo da requisição muito grande');
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  try {
    const data = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (data === null || typeof data !== 'object' || Array.isArray(data)) throw new Error();
    return data;
  } catch {
    throw new HttpError(400, 'JSON inválido');
  }
}

export function sendJson(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  });
  res.end(body);
}
