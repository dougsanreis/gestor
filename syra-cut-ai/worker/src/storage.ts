import { readFile } from "node:fs/promises";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { env } from "./env.js";
import { isUuid } from "./security.js";

let _client: SupabaseClient | null = null;
function client(): SupabaseClient {
  if (_client) return _client;
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error("Storage não configurado (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)");
  }
  _client = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _client;
}

/**
 * Caminho do contrato: {user_id}/{job_id}/... — as policies de storage do app liberam leitura
 * só quando a 1ª pasta é o uid do dono. Sem user_id válido, o arquivo fica inacessível para o
 * usuário depois que a signed URL expira, então exigimos UUID.
 * Retentativas ganham sufixo _r{n}: nunca sobrescrevemos um render anterior.
 */
export function storageKey(opts: {
  userId?: string;
  jobId: string;
  file: string;
  attempt: number;
}): string {
  const base = isUuid(opts.userId) ? `${opts.userId}/${opts.jobId}` : `_sem-usuario/${opts.jobId}`;
  const dot = opts.file.lastIndexOf(".");
  const name =
    opts.attempt > 1 && dot > 0
      ? `${opts.file.slice(0, dot)}_r${opts.attempt}${opts.file.slice(dot)}`
      : opts.file;
  return `${base}/${name}`;
}

export interface UploadResult {
  path: string;
  download_url: string;
  preview_url: string;
}

async function uploadFile(
  bucket: string,
  key: string,
  localPath: string,
  contentType: string,
): Promise<void> {
  // Cortes de até alguns minutos em 1080p ficam na casa de dezenas de MB: Buffer é seguro.
  const body = await readFile(localPath);
  const { error } = await client()
    .storage.from(bucket)
    .upload(key, body, { contentType, upsert: false });
  if (error) throw new Error(`upload para ${bucket}/${key} falhou: ${error.message}`);
}

export async function uploadRender(opts: {
  key: string;
  localPath: string;
}): Promise<UploadResult> {
  await uploadFile(env.STORAGE_BUCKET, opts.key, opts.localPath, "video/mp4");
  const { data: signed, error } = await client()
    .storage.from(env.STORAGE_BUCKET)
    .createSignedUrl(opts.key, 60 * 60 * 24 * 7);
  if (error || !signed) throw new Error(`signed URL falhou: ${error?.message}`);
  return { path: opts.key, download_url: signed.signedUrl, preview_url: signed.signedUrl };
}

/** Relatório do job (best-effort: falha aqui não derruba um render válido). */
export async function uploadReport(key: string, localPath: string): Promise<string | null> {
  try {
    await uploadFile(env.REPORTS_BUCKET, key, localPath, "application/json");
    return key;
  } catch (e) {
    console.warn(`[report] ${e instanceof Error ? e.message : e}`);
    return null;
  }
}
