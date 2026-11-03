// Camada de banco de dados: abre o SQLite nativo do Node e aplica o schema.
import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';

export const SCHEMA_VERSION = 1;

const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT    NOT NULL,
  email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT    NOT NULL,
  role          TEXT    NOT NULL DEFAULT 'gestor' CHECK (role IN ('admin','gestor')),
  created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT    PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  company    TEXT,
  email      TEXT,
  phone      TEXT,
  segment    TEXT,
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campaigns (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id    INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  name         TEXT    NOT NULL,
  platform     TEXT    NOT NULL CHECK (platform IN ('meta','google','tiktok','linkedin')),
  objective    TEXT    NOT NULL DEFAULT 'conversao' CHECK (objective IN ('conversao','trafego','alcance','leads','engajamento')),
  status       TEXT    NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho','ativa','pausada','encerrada')),
  daily_budget REAL    NOT NULL DEFAULT 0 CHECK (daily_budget >= 0),
  start_date   TEXT,
  end_date     TEXT,
  created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS metrics (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  date        TEXT    NOT NULL,
  impressions INTEGER NOT NULL DEFAULT 0 CHECK (impressions >= 0),
  clicks      INTEGER NOT NULL DEFAULT 0 CHECK (clicks >= 0),
  spend       REAL    NOT NULL DEFAULT 0 CHECK (spend >= 0),
  conversions INTEGER NOT NULL DEFAULT 0 CHECK (conversions >= 0),
  revenue     REAL    NOT NULL DEFAULT 0 CHECK (revenue >= 0),
  UNIQUE (campaign_id, date)
);

CREATE INDEX IF NOT EXISTS idx_campaigns_client ON campaigns(client_id);
CREATE INDEX IF NOT EXISTS idx_metrics_date     ON metrics(date);
CREATE INDEX IF NOT EXISTS idx_sessions_user    ON sessions(user_id);
`;

/** Abre (ou cria) o banco e garante que o schema exista. Use ':memory:' em testes. */
export function openDatabase(file) {
  if (file !== ':memory:') fs.mkdirSync(path.dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec('PRAGMA foreign_keys = ON;');
  if (file !== ':memory:') db.exec('PRAGMA journal_mode = WAL;');
  db.exec(SCHEMA);
  db.exec(`PRAGMA user_version = ${SCHEMA_VERSION};`);
  return db;
}

/** Executa uma função dentro de uma transação (commit/rollback automático). */
export function transaction(db, fn) {
  db.exec('BEGIN');
  try {
    const result = fn();
    db.exec('COMMIT');
    return result;
  } catch (err) {
    db.exec('ROLLBACK');
    throw err;
  }
}
