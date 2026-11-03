// Validação declarativa de entrada. Cada campo descreve tipo e regras.
import { HttpError } from './http.js';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function isValidDate(value) {
  if (!DATE_RE.test(value)) return false;
  const d = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value;
}

/**
 * Valida `input` contra `schema` e devolve um objeto limpo só com os campos conhecidos.
 * Regras: type ('string'|'number'|'integer'|'email'|'date'|'enum'), required, min, max, values, default.
 */
export function validate(input, schema) {
  const out = {};
  const errors = {};
  for (const [field, rule] of Object.entries(schema)) {
    let value = input?.[field];
    if (typeof value === 'string') value = value.trim();
    if (value === undefined || value === null || value === '') {
      if (rule.required) errors[field] = 'Campo obrigatório';
      else out[field] = rule.default ?? null;
      continue;
    }
    switch (rule.type) {
      case 'string':
      case 'email':
        if (typeof value !== 'string') { errors[field] = 'Deve ser texto'; break; }
        if (rule.min && value.length < rule.min) { errors[field] = `Mínimo de ${rule.min} caracteres`; break; }
        if (value.length > (rule.max ?? 200)) { errors[field] = `Máximo de ${rule.max ?? 200} caracteres`; break; }
        if (rule.type === 'email' && !EMAIL_RE.test(value)) { errors[field] = 'E-mail inválido'; break; }
        out[field] = value;
        break;
      case 'number':
      case 'integer': {
        const n = typeof value === 'string' ? Number(value.replace(',', '.')) : value;
        if (typeof n !== 'number' || !Number.isFinite(n)) { errors[field] = 'Deve ser número'; break; }
        if (rule.type === 'integer' && !Number.isInteger(n)) { errors[field] = 'Deve ser número inteiro'; break; }
        if (rule.min !== undefined && n < rule.min) { errors[field] = `Deve ser ≥ ${rule.min}`; break; }
        if (rule.max !== undefined && n > rule.max) { errors[field] = `Deve ser ≤ ${rule.max}`; break; }
        out[field] = n;
        break;
      }
      case 'date':
        if (typeof value !== 'string' || !isValidDate(value)) { errors[field] = 'Data inválida (AAAA-MM-DD)'; break; }
        out[field] = value;
        break;
      case 'enum':
        if (!rule.values.includes(value)) { errors[field] = `Valor inválido. Use: ${rule.values.join(', ')}`; break; }
        out[field] = value;
        break;
      default:
        throw new Error(`Tipo de regra desconhecido: ${rule.type}`);
    }
  }
  if (Object.keys(errors).length) throw new HttpError(422, 'Dados inválidos', errors);
  return out;
}

export function parseId(value) {
  const id = Number(value);
  if (!Number.isInteger(id) || id <= 0) throw new HttpError(400, 'ID inválido');
  return id;
}

/** Lê ?from=&to= da query; padrão = últimos 30 dias. */
export function parsePeriod(query) {
  const today = new Date();
  const to = query.to || today.toISOString().slice(0, 10);
  const fromDefault = new Date(today.getTime() - 29 * 86400_000).toISOString().slice(0, 10);
  const from = query.from || fromDefault;
  if (!isValidDate(from) || !isValidDate(to)) throw new HttpError(400, 'Período inválido (AAAA-MM-DD)');
  if (from > to) throw new HttpError(400, 'A data inicial deve ser anterior à final');
  return { from, to };
}
