import { z } from "zod";
import { env } from "./env.js";
import { isAllowedUrl, isSafeJobId } from "./security.js";
import type { CreateJobPayload, VariantId } from "./types.js";

const VariantEnum = z.enum(["viral_cut", "clean_caption", "speed_dynamic"]);

/**
 * O app tem dois despachantes com formatos diferentes:
 *  - video-jobs.functions.ts → { source_file_url, target_format, max_duration: 75, output_profiles: [...] }
 *  - video-worker-client.server.ts → { source_file_url, target_ratio, max_duration: 90, variants: [{id, speed, zoom, captions}], ai_plan }
 * O worker original só aceitava `variants` como lista de strings e devolvia 400 para o segundo.
 */
const PayloadSchema = z
  .object({
    job_id: z
      .string()
      .refine(isSafeJobId, "job_id deve ser UUID ou slug [A-Za-z0-9_-] de até 64 caracteres"),
    user_id: z.string().optional(),
    input_url: z.string().url().optional(),
    source_file_url: z.string().url().optional(),
    callback_url: z.string().url(),
    variants: z
      .array(z.union([VariantEnum, z.object({ id: VariantEnum }).passthrough()]))
      .optional(),
    output_profiles: z.array(z.string()).optional(),
    ai_mode: z.string().optional(),
    max_duration: z.number().positive().optional(),
    target_ratio: z.string().optional(),
    target_format: z.string().optional(),
    ai_plan: z.unknown().optional(),
  })
  .passthrough();

export type ParseResult =
  | { ok: true; payload: CreateJobPayload }
  | { ok: false; status: number; error: string; details?: unknown };

export function parseCreateJob(body: unknown, e = env): ParseResult {
  const parsed = PayloadSchema.safeParse(body ?? {});
  if (!parsed.success)
    return { ok: false, status: 400, error: "payload inválido", details: parsed.error.flatten() };
  const d = parsed.data;
  const inputUrl = d.input_url ?? d.source_file_url;
  if (!inputUrl) return { ok: false, status: 400, error: "input_url/source_file_url ausente" };
  for (const r of [d.target_ratio, d.target_format]) {
    if (r && r !== "9:16")
      return { ok: false, status: 400, error: `proporção ${r} não suportada (apenas 9:16)` };
  }
  if (!isAllowedUrl(inputUrl, e.INPUT_ALLOWED_HOSTS, e.ALLOW_INSECURE_DEV))
    return {
      ok: false,
      status: 400,
      error: "host do vídeo de origem não está em INPUT_ALLOWED_HOSTS",
    };
  if (!isAllowedUrl(d.callback_url, e.CALLBACK_ALLOWED_HOSTS, e.ALLOW_INSECURE_DEV))
    return { ok: false, status: 400, error: "host do callback não está em CALLBACK_ALLOWED_HOSTS" };
  const variants: VariantId[] | undefined = d.variants?.map((v) =>
    typeof v === "string" ? v : v.id,
  );
  return {
    ok: true,
    payload: {
      job_id: d.job_id,
      user_id: d.user_id,
      input_url: inputUrl,
      callback_url: d.callback_url,
      variants: variants && variants.length ? [...new Set(variants)] : undefined,
      ai_mode: d.ai_mode,
      max_duration: d.max_duration,
    },
  };
}
