import "dotenv/config";

function str(name: string, fallback = ""): string {
  return (process.env[name] ?? fallback).trim();
}
function num(name: string, fallback: number): number {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v > 0 ? v : fallback;
}
function list(name: string): string[] {
  return str(name)
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}
function hostOf(url: string): string {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

const SUPABASE_URL = str("SUPABASE_URL");

export const env = {
  PORT: num("PORT", 8787),
  WORKER_API_KEY: str("WORKER_API_KEY"),
  /** Só para desenvolvimento local: aceita requisições sem WORKER_API_KEY. */
  ALLOW_INSECURE_DEV: str("ALLOW_INSECURE_DEV") === "1",

  ANTHROPIC_API_KEY: str("ANTHROPIC_API_KEY"),
  ANTHROPIC_MODEL: str("ANTHROPIC_MODEL", "claude-opus-5-5"),
  XAI_API_KEY: str("XAI_API_KEY"),
  XAI_MODEL: str("XAI_MODEL", "grok-2-latest"),
  MISTRAL_API_KEY: str("MISTRAL_API_KEY"),
  MISTRAL_MODEL: str("MISTRAL_MODEL", "mistral-large-latest"),
  AI_TIMEOUT_MS: num("AI_TIMEOUT_MS", 120_000),

  OPENAI_API_KEY: str("OPENAI_API_KEY"),
  WHISPER_MODEL: str("WHISPER_MODEL", "whisper-1"),
  WHISPER_LANGUAGE: str("WHISPER_LANGUAGE", "pt"),
  STT_TIMEOUT_MS: num("STT_TIMEOUT_MS", 300_000),

  STORAGE_PROVIDER: str("STORAGE_PROVIDER", "supabase"),
  /** Servidor de teste: pasta do storage local e URL base para os links dos arquivos. */
  LOCAL_STORAGE_DIR: str("LOCAL_STORAGE_DIR", ".local-storage"),
  PUBLIC_BASE_URL: str("PUBLIC_BASE_URL", `http://localhost:${num("PORT", 8787)}`),
  /** openai (padrão) | command (executa STT_COMMAND <áudio> <saida.json>) | none */
  STT_PROVIDER: str("STT_PROVIDER", "openai"),
  STT_COMMAND: str("STT_COMMAND"),
  STORAGE_BUCKET: str("STORAGE_BUCKET", "rendered-videos"),
  REPORTS_BUCKET: str("REPORTS_BUCKET", "reports"),
  SUPABASE_URL,
  SUPABASE_SERVICE_ROLE_KEY: str("SUPABASE_SERVICE_ROLE_KEY"),

  /**
   * Hosts de onde o worker aceita baixar vídeo e para onde aceita mandar callback.
   * O callback leva o WORKER_API_KEY no header, então um host fora da lista vazaria a chave.
   * Padrão de download: o host do SUPABASE_URL (signed URLs do bucket source-videos).
   */
  INPUT_ALLOWED_HOSTS: list("INPUT_ALLOWED_HOSTS").length
    ? list("INPUT_ALLOWED_HOSTS")
    : [hostOf(SUPABASE_URL)].filter(Boolean),
  CALLBACK_ALLOWED_HOSTS: list("CALLBACK_ALLOWED_HOSTS"),

  MAX_JOB_DURATION_MS: num("MAX_JOB_DURATION_MS", 15 * 60 * 1000),
  MAX_INPUT_BYTES: num("MAX_INPUT_BYTES", 500 * 1024 * 1024),
  MAX_SOURCE_SECONDS: num("MAX_SOURCE_SECONDS", 20 * 60),
  MAX_QUEUE: num("MAX_QUEUE", 20),
  DOWNLOAD_TIMEOUT_MS: num("DOWNLOAD_TIMEOUT_MS", 5 * 60 * 1000),
  CALLBACK_TIMEOUT_MS: num("CALLBACK_TIMEOUT_MS", 15_000),
  FFMPEG_PATH: str("FFMPEG_PATH"),
  FFPROBE_PATH: str("FFPROBE_PATH"),
};

/** Problemas de configuração que impedem o worker de subir com segurança. */
export function configProblems(e = env): string[] {
  const problems: string[] = [];
  if (!e.WORKER_API_KEY && !e.ALLOW_INSECURE_DEV) {
    problems.push("WORKER_API_KEY ausente (defina, ou ALLOW_INSECURE_DEV=1 só em máquina local).");
  }
  if (e.STORAGE_PROVIDER === "local" && !e.ALLOW_INSECURE_DEV) {
    problems.push("STORAGE_PROVIDER=local é só para o servidor de teste (ALLOW_INSECURE_DEV=1).");
  }
  if (e.STT_PROVIDER === "command" && !e.STT_COMMAND) {
    problems.push("STT_PROVIDER=command exige STT_COMMAND.");
  }
  if (e.WORKER_API_KEY && e.WORKER_API_KEY.length < 24) {
    problems.push("WORKER_API_KEY curto demais (mínimo 24 caracteres).");
  }
  if (!e.ALLOW_INSECURE_DEV && e.CALLBACK_ALLOWED_HOSTS.length === 0) {
    problems.push("CALLBACK_ALLOWED_HOSTS vazio: liste o host do app (ex.: syra.lovable.app).");
  }
  if (!e.ALLOW_INSECURE_DEV && e.INPUT_ALLOWED_HOSTS.length === 0) {
    problems.push("INPUT_ALLOWED_HOSTS vazio e SUPABASE_URL ausente.");
  }
  return problems;
}
