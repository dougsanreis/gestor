import { VARIANT_SPECS, type AiEditorialPlan, type WorkerDispatchPayload } from "./job-contract";

export interface WorkerEnv {
  url: string;
  key: string;
}

/**
 * URL do callback do worker. Use APP_PUBLIC_URL (ex.: https://syra.lovable.app) em produção:
 * montar a partir do header Host deixa o destino (que recebe o WORKER_API_KEY) nas mãos de
 * quem faz a requisição. O worker também só aceita hosts de CALLBACK_ALLOWED_HOSTS.
 */
export function resolveCallbackUrl(host: string | undefined, proto: string | undefined): string {
  const base = process.env.APP_PUBLIC_URL?.trim().replace(/\/$/, "") || `${proto ?? "https"}://${host}`;
  return `${base}/api/public/update-video-job`;
}

export function readWorkerEnv(): WorkerEnv | null {
  const url = process.env.WORKER_API_URL;
  const key = process.env.WORKER_API_KEY;
  if (!url || !key) return null;
  return { url, key };
}

export async function dispatchToWorker(input: {
  env: WorkerEnv;
  jobId: string;
  userId: string;
  sourceUrl: string;
  callbackUrl: string;
  aiPlan: AiEditorialPlan | null;
}): Promise<void> {
  const payload: WorkerDispatchPayload = {
    job_id: input.jobId,
    user_id: input.userId,
    source_file_url: input.sourceUrl,
    target_ratio: "9:16",
    max_duration: 90,
    callback_url: input.callbackUrl,
    variants: VARIANT_SPECS.map((v) => ({
      id: v.id,
      speed: v.speed,
      zoom: v.zoom,
      captions: v.captions,
    })),
    ai_plan: input.aiPlan,
  };

  const res = await fetch(`${input.env.url.replace(/\/$/, "")}/process`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${input.env.key}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Worker respondeu ${res.status}: ${body.slice(0, 300)}`);
  }
}
