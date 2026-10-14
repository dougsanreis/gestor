import { env } from "./env.js";
import { isAllowedUrl } from "./security.js";
import type { JobRecord, JobStatus, VariantOutput } from "./types.js";

/** Status interno do worker → enum video_job_status do app. */
export function mapStatus(s: JobStatus): string {
  switch (s) {
    case "QUEUED":
      return "QUEUED";
    case "DOWNLOADING":
      return "PROCESSING";
    case "TRANSCRIBING":
      return "TRANSCRIBING";
    case "ANALYZING":
      return "ANALYZING";
    case "RENDERING":
    case "UPLOADING":
      return "RENDERING";
    case "VALIDATING":
      return "VALIDATING";
    case "READY":
      return "READY_FOR_HUMAN_REVIEW";
    case "FAILED":
      return "FAILED";
    default:
      return "PROCESSING";
  }
}

function mapVariant(v: VariantOutput) {
  const status =
    v.status === "VALIDATING" || v.status === "RENDERING"
      ? "RENDERING"
      : v.status === "READY"
        ? "READY"
        : v.status === "FAILED"
          ? "FAILED"
          : "PENDING";
  return {
    id: v.id,
    label: v.name,
    status,
    output_path: v.storage_path ?? null,
    output_url: v.download_url ?? null,
    preview_url: v.preview_url ?? null,
    duration: v.duration ?? null,
    size: v.size ?? null,
    error: v.error ?? null,
  };
}

/** Corpo exatamente no formato que /api/public/update-video-job valida (zod). */
export function buildCallbackBody(job: JobRecord) {
  const primary =
    job.variants.find((v) => v.status === "READY" && v.id === "viral_cut") ??
    job.variants.find((v) => v.status === "READY");
  const technical_report: Record<string, unknown> = {
    ai_mode: job.ai_mode,
    ai_provider: job.ai_provider,
    attempts: job.attempts,
    framing: job.framing ?? null,
    cuts: job.cuts ?? null,
    subtitle_words: job.subtitle_words ?? null,
    report_path: job.report_path ?? null,
    variants: job.variants.map((v) => ({
      id: v.id,
      status: v.status,
      duration: v.duration,
      width: v.width,
      height: v.height,
      v_codec: v.v_codec,
      a_codec: v.a_codec,
      size: v.size,
      sha256: v.sha256,
      error: v.error,
    })),
  };
  if (primary) {
    technical_report.width = primary.width;
    technical_report.height = primary.height;
    technical_report.codec = primary.v_codec;
    technical_report.duration = primary.duration;
  }
  return {
    job_id: job.id,
    status: mapStatus(job.status),
    progress: Math.max(0, Math.min(100, Math.round(job.progress))),
    transcript: job.transcript ?? null,
    title_suggestion: job.title ?? null,
    virality_score: job.virality_score ?? null,
    output_file_url: primary?.download_url ?? null,
    output_file_path: primary?.storage_path ?? null,
    technical_report,
    variants: job.variants.map(mapVariant),
    error_message: job.error ?? null,
  };
}

/**
 * Envia o status ao app. Só para hosts permitidos (o header leva o WORKER_API_KEY).
 * Callback final (READY/FAILED) tenta 4 vezes com backoff; intermediários, 1 vez.
 */
export async function postCallback(
  job: JobRecord,
  opts: { final?: boolean } = {},
): Promise<boolean> {
  const url = job.payload.callback_url;
  if (!url) return false;
  if (!isAllowedUrl(url, env.CALLBACK_ALLOWED_HOSTS, env.ALLOW_INSECURE_DEV)) {
    console.warn(
      `[callback] ${job.id}: host do callback fora de CALLBACK_ALLOWED_HOSTS; não enviado`,
    );
    return false;
  }
  const body = JSON.stringify(buildCallbackBody(job));
  const tries = opts.final ? 4 : 1;
  for (let i = 1; i <= tries; i++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), env.CALLBACK_TIMEOUT_MS);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.WORKER_API_KEY}`,
        },
        body,
        signal: ctrl.signal,
        redirect: "error",
      });
      if (res.ok) return true;
      const text = (await res.text()).slice(0, 200);
      console.warn(`[callback] ${job.id} tentativa ${i}: HTTP ${res.status} ${text}`);
      if (res.status >= 400 && res.status < 500 && res.status !== 429) return false;
    } catch (e) {
      console.warn(`[callback] ${job.id} tentativa ${i}: ${e instanceof Error ? e.message : e}`);
    } finally {
      clearTimeout(timer);
    }
    if (i < tries) await new Promise((r) => setTimeout(r, 1000 * 2 ** i));
  }
  return false;
}
