import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export const config = {
  port: Number(process.env.PORT) || 3000,
  // 127.0.0.1 = somente esta máquina (interface local). Use HOST=0.0.0.0 para expor na rede.
  host: process.env.HOST || '127.0.0.1',
  dbPath: process.env.DB_PATH || path.join(ROOT, 'data', 'gestor.db'),
  publicDir: path.join(ROOT, 'public'),
};
