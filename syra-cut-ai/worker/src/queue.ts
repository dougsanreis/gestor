import path from "node:path";
import { env } from "./env.js";
import type { CreateJobPayload, JobRecord, VariantId, VariantOutput } from "./types.js";
import { ALL_VARIANTS } from "./types.js";
import { postCallback } from "./callback-client.js";
import {
  cleanupWorkDir,
  downloadToFile,
  extractAudio,
  makeWorkDir,
  preflightProblems,
  preflightWarnings,
  probeMedia,
} from "./ffmpeg-renderer.js";
import { transcribeAudio } from "./whisper-transcriber.js";
import { planEditorial } from "./ai-editorial-router.js";
import { clampMaxDuration, planCut, renderAndValidate, writeMissionReport } from "./pipeline.js";
import { storageKey, uploadRender, uploadReport } from "./storage.js";

const VARIANT_LABELS: Record<VariantId, string> = {
  viral_cut: "Viral Cut",
  clean_caption: "Clean Caption",
  speed_dynamic: "Speed Dynamic 1.08×",
};

const jobs = new Map<string, JobRecord>();
const queue: string[] = [];
let running = false;
const MAX_RETAINED = 200;

function log(job: JobRecord, msg: string): void {
  job.logs.push(`[${new Date().toISOString()}] ${msg}`);
  if (job.logs.length > 500) job.logs.splice(0, job.logs.length - 500);
  job.updated_at = Date.now();
  console.log(`[${job.id}] ${msg}`);
}

async function emit(job: JobRecord, final = false): Promise<void> {
  await postCallback(job, { final });
}

function newJob(payload: CreateJobPayload): JobRecord {
  const variants =
    payload.variants && payload.variants.length > 0 ? [...new Set(payload.variants)] : ALL_VARIANTS;
  return {
    id: payload.job_id,
    payload,
    status: "QUEUED",
    progress: 0,
    logs: [],
    variants: variants.map(
      (id): VariantOutput => ({ id, name: VARIANT_LABELS[id], status: "PENDING" }),
    ),
    ai_mode: "FALLBACK",
    ai_provider: null,
    created_at: Date.now(),
    updated_at: Date.now(),
    attempts: 0,
  };
}

function prune(): void {
  if (jobs.size <= MAX_RETAINED) return;
  const done = [...jobs.values()]
    .filter((j) => j.status === "READY" || j.status === "FAILED")
    .sort((a, b) => a.updated_at - b.updated_at);
  for (const j of done.slice(0, jobs.size - MAX_RETAINED)) jobs.delete(j.id);
}

export class QueueFullError extends Error {}

/** Idempotente: reenviar o mesmo job_id enquanto ele está na fila/rodando devolve o mesmo job. */
export function enqueue(payload: CreateJobPayload): { job: JobRecord; duplicate: boolean } {
  const existing = jobs.get(payload.job_id);
  if (existing && existing.status !== "READY" && existing.status !== "FAILED")
    return { job: existing, duplicate: true };
  if (queue.length >= env.MAX_QUEUE) throw new QueueFullError(`fila cheia (${env.MAX_QUEUE})`);
  const job = newJob(payload);
  if (existing) job.attempts = existing.attempts; // reprocessamento de job concluído
  jobs.set(job.id, job);
  queue.push(job.id);
  prune();
  void tick();
  return { job, duplicate: false };
}

export function getJob(id: string): JobRecord | undefined {
  return jobs.get(id);
}

export function retryJob(id: string): JobRecord | undefined {
  const job = jobs.get(id);
  if (!job) return undefined;
  if (job.status !== "FAILED") return job;
  job.status = "QUEUED";
  job.progress = 0;
  job.error = undefined;
  job.variants = job.variants.map((v) => ({ id: v.id, name: v.name, status: "PENDING" }));
  queue.push(job.id);
  void tick();
  return job;
}

async function tick(): Promise<void> {
  if (running) return;
  running = true;
  try {
    while (queue.length > 0) {
      const job = jobs.get(queue.shift()!);
      if (job) await runJob(job);
    }
  } finally {
    running = false;
  }
}

function checkDeadline(deadline: number): void {
  if (Date.now() > deadline)
    throw new Error(
      `job excedeu MAX_JOB_DURATION_MS (${Math.round(env.MAX_JOB_DURATION_MS / 60000)} min)`,
    );
}

async function runJob(job: JobRecord): Promise<void> {
  job.attempts += 1;
  const started = Date.now();
  const deadline = started + env.MAX_JOB_DURATION_MS;
  let workDir = "";

  try {
    workDir = await makeWorkDir(job.id);
    const inputPath = path.join(workDir, "input");
    const audioPath = path.join(workDir, "audio.mp3");

    job.status = "DOWNLOADING";
    job.progress = 5;
    log(job, `baixando fonte (tentativa ${job.attempts})`);
    await emit(job);
    const bytes = await downloadToFile(job.payload.input_url, inputPath, env.MAX_INPUT_BYTES);

    const probe = await probeMedia(inputPath);
    const problems = preflightProblems(probe);
    if (problems.length) throw new Error(`fonte reprovada: ${problems.join("; ")}`);
    const warnings = preflightWarnings(probe);
    log(
      job,
      `fonte ok · ${(bytes / 1e6).toFixed(1)} MB · ${probe.width}x${probe.height} · ${probe.duration.toFixed(1)}s · ${probe.fps_avg} fps`,
    );
    for (const w of warnings) log(job, `aviso: ${w}`);
    checkDeadline(deadline);

    job.status = "TRANSCRIBING";
    job.progress = 15;
    await emit(job);
    await extractAudio(inputPath, audioPath);
    const transcript = await transcribeAudio(audioPath);
    // Falha cedo: o app reprova READY sem transcrição; renderizar antes só gastaria máquina.
    if (!transcript.text)
      throw new Error(`Transcrição não gerada: ${transcript.error ?? "motivo desconhecido"}`);
    job.transcript = transcript.text;
    log(
      job,
      `transcrição ok · ${transcript.words.length} palavras com tempo · ${transcript.segments.length} frases`,
    );
    checkDeadline(deadline);

    job.status = "ANALYZING";
    job.progress = 35;
    await emit(job);
    const maxTotal = clampMaxDuration(job.payload.max_duration);
    const router = await planEditorial(transcript.segments, transcript.text, maxTotal);
    job.ai_mode = router.mode;
    job.ai_provider = router.plan.provider;
    job.title = router.plan.title;
    job.virality_score = router.plan.virality_score;
    const plan = planCut({ probe, transcript, router, maxTotal });
    job.cuts = plan.edl.segments.length;
    job.subtitle_words = plan.subtitleWords;
    job.framing = plan.framing;
    log(
      job,
      `IA ${router.mode}/${router.plan.provider} · ${plan.edl.segments.length} trechos · ${plan.edl.total_duration.toFixed(1)}s · enquadramento ${plan.framing}`,
    );
    for (const n of plan.edl.notes) log(job, `EDL: ${n}`);
    checkDeadline(deadline);

    job.status = "RENDERING";
    job.progress = 45;
    await emit(job);
    const rendered = await renderAndValidate({
      inputPath,
      workDir,
      variants: job.variants.map((v) => v.id),
      transcript,
      plan,
      onVariant: async (id, phase) => {
        checkDeadline(deadline);
        const v = job.variants.find((x) => x.id === id)!;
        v.status = phase;
        await emit(job);
      },
    });

    job.status = "UPLOADING";
    job.progress = 85;
    await emit(job);
    for (const r of rendered) {
      const v = job.variants.find((x) => x.id === r.id)!;
      if (!r.ok || !r.outputPath) {
        v.status = "FAILED";
        v.error = r.error;
        log(job, `${r.id} FALHOU: ${r.error}`);
        continue;
      }
      try {
        const key = storageKey({
          userId: job.payload.user_id,
          jobId: job.id,
          file: `final_${r.id}.mp4`,
          attempt: job.attempts,
        });
        const up = await uploadRender({ key, localPath: r.outputPath });
        Object.assign(v, {
          status: "READY",
          storage_path: up.path,
          preview_url: up.preview_url,
          download_url: up.download_url,
          share_url: up.download_url,
          duration: r.duration,
          size: r.size,
          width: r.width,
          height: r.height,
          v_codec: r.v_codec,
          a_codec: r.a_codec,
          sha256: r.sha256,
          virality_score: router.plan.virality_score,
        } satisfies Partial<VariantOutput>);
        log(
          job,
          `${r.id} PRONTO · ${((r.size ?? 0) / 1e6).toFixed(1)} MB · ${r.duration?.toFixed(1)}s`,
        );
      } catch (e) {
        v.status = "FAILED";
        v.error = e instanceof Error ? e.message : String(e);
        log(job, `${r.id} upload FALHOU: ${v.error}`);
      }
    }

    const reportPath = await writeMissionReport({
      workDir,
      jobId: job.id,
      attempt: job.attempts,
      probe,
      warnings,
      transcript,
      router,
      plan,
      rendered,
    });
    job.report_path =
      (await uploadReport(
        storageKey({
          userId: job.payload.user_id,
          jobId: job.id,
          file: "mission_report.json",
          attempt: job.attempts,
        }),
        reportPath,
      )) ?? undefined;

    const ready = job.variants.filter((v) => v.status === "READY");
    if (ready.length === 0) throw new Error("nenhuma variante passou no QA/upload");

    job.status = "READY";
    job.progress = 100;
    log(
      job,
      `concluído em ${((Date.now() - started) / 1000).toFixed(1)}s · ${ready.length}/${job.variants.length} prontas · revisão humana obrigatória`,
    );
    await emit(job, true);
  } catch (e) {
    job.status = "FAILED";
    job.error = e instanceof Error ? e.message : String(e);
    for (const v of job.variants)
      if (v.status !== "READY" && v.status !== "FAILED") v.status = "FAILED";
    log(job, `FALHOU: ${job.error}`);
    await emit(job, true);
  } finally {
    if (workDir) await cleanupWorkDir(workDir);
  }
}
