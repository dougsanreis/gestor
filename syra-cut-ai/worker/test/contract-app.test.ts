import { test } from "node:test";
import assert from "node:assert/strict";
import { z } from "zod";
import { buildCallbackBody } from "../src/callback-client.js";
import type { JobRecord } from "../src/types.js";

/**
 * Cópia do bodySchema de src/routes/api/public/update-video-job.ts (app). Se o app mudar o
 * schema, atualize aqui: o teste existe para pegar divergência de contrato antes do deploy.
 */
const STATUSES = [
  "UPLOADED",
  "QUEUED",
  "PROCESSING",
  "TRANSCRIBING",
  "ANALYZING",
  "CUTTING",
  "RENDERING",
  "VALIDATING",
  "READY_FOR_HUMAN_REVIEW",
  "FAILED",
] as const;
const variantSchema = z.object({
  id: z.enum(["viral_cut", "clean_caption", "speed_dynamic"]),
  label: z.string().optional(),
  status: z.enum(["PENDING", "RENDERING", "READY", "FAILED"]),
  output_path: z.string().nullable().optional(),
  output_url: z.string().url().nullable().optional(),
  preview_url: z.string().url().nullable().optional(),
  duration: z.number().nullable().optional(),
  size: z.number().nullable().optional(),
  error: z.string().nullable().optional(),
});
const bodySchema = z.object({
  job_id: z.string().uuid(),
  status: z.enum(STATUSES),
  progress: z.number().int().min(0).max(100).optional(),
  output_file_url: z.string().url().optional().nullable(),
  output_file_path: z.string().optional().nullable(),
  transcript: z.string().optional().nullable(),
  title_suggestion: z.string().optional().nullable(),
  virality_score: z.number().int().optional().nullable(),
  error_message: z.string().optional().nullable(),
  technical_report: z.record(z.string(), z.unknown()).optional().nullable(),
  variants: z.array(variantSchema).optional().nullable(),
});

const base = (): JobRecord => ({
  id: "3f1c2a8e-1b2c-4d5e-8f90-123456789abc",
  payload: {
    job_id: "3f1c2a8e-1b2c-4d5e-8f90-123456789abc",
    input_url: "https://x",
    callback_url: "https://y",
  },
  status: "RENDERING",
  progress: 55.5,
  logs: [],
  ai_mode: "FULL",
  ai_provider: "anthropic",
  variants: [
    { id: "viral_cut", name: "Viral Cut", status: "VALIDATING" },
    { id: "clean_caption", name: "Clean Caption", status: "PENDING" },
  ],
  created_at: 0,
  updated_at: 0,
  attempts: 1,
});

test("callback intermediário passa no schema do app", () => {
  const r = bodySchema.safeParse(buildCallbackBody(base()));
  assert.ok(r.success, JSON.stringify(r.error?.issues));
});

test("callback READY passa no schema e no gate de qualidade do app", () => {
  const job = base();
  job.status = "READY";
  job.progress = 100;
  job.transcript = "fala real";
  job.title = "título";
  job.virality_score = 77;
  job.variants[0] = {
    ...job.variants[0],
    status: "READY",
    width: 1080,
    height: 1920,
    v_codec: "h264",
    duration: 18.2,
    download_url:
      "https://abc.supabase.co/storage/v1/object/sign/rendered-videos/u/j/final_viral_cut.mp4?token=t",
    preview_url:
      "https://abc.supabase.co/storage/v1/object/sign/rendered-videos/u/j/final_viral_cut.mp4?token=t",
    storage_path: "u/j/final_viral_cut.mp4",
  };
  job.variants[1] = { ...job.variants[1], status: "FAILED", error: "QA reprovou" };
  const body = buildCallbackBody(job);
  const r = bodySchema.safeParse(body);
  assert.ok(r.success, JSON.stringify(r.error?.issues));
  assert.equal(body.status, "READY_FOR_HUMAN_REVIEW");
  const rep = body.technical_report as Record<string, unknown>;
  assert.equal(rep.width, 1080);
  assert.equal(rep.height, 1920);
  assert.equal(rep.codec, "h264");
  assert.ok((rep.duration as number) > 3);
  assert.equal(body.output_file_path, "u/j/final_viral_cut.mp4");
});

test("callback FAILED passa no schema", () => {
  const job = base();
  job.status = "FAILED";
  job.error = "Transcrição não gerada";
  const r = bodySchema.safeParse(buildCallbackBody(job));
  assert.ok(r.success);
});
