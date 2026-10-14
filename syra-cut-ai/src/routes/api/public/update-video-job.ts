import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";
import type { Json, TablesUpdate } from "@/integrations/supabase/types";

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

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Public worker callback ("update-video-job").
 * Auth: Bearer WORKER_API_KEY. Enforces render-quality rules before a job can
 * be marked READY_FOR_HUMAN_REVIEW — otherwise it is forced to FAILED.
 */
export const Route = createFileRoute("/api/public/update-video-job")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const workerKey = process.env.WORKER_API_KEY;
        if (!workerKey) {
          return json({ error: "Worker não configurado. Configure WORKER_API_KEY." }, 503);
        }

        const authHeader = request.headers.get("authorization") ?? "";
        const token = authHeader.replace(/^Bearer\s+/i, "");
        const { createHash, timingSafeEqual } = await import("node:crypto");
        const digest = (v: string) => createHash("sha256").update(v).digest();
        if (!token || !timingSafeEqual(digest(token), digest(workerKey))) {
          return json({ error: "Unauthorized" }, 401);
        }

        let parsed;
        try {
          parsed = bodySchema.parse(await request.json());
        } catch (e) {
          return json({ error: "Payload inválido", detail: String(e) }, 400);
        }

        const { supabaseAdmin } = await import("@/integrations/supabase/client.server");

        const { data: job } = await supabaseAdmin
          .from("video_jobs")
          .select("id, transcript")
          .eq("id", parsed.job_id)
          .maybeSingle();
        if (!job) return json({ error: "Job não encontrado" }, 404);

        const report = (parsed.technical_report ?? {}) as Record<string, unknown>;
        const num = (k: string) => (typeof report[k] === "number" ? (report[k] as number) : undefined);

        let finalStatus = parsed.status;
        let errorMessage = parsed.error_message ?? null;
        const transcript = parsed.transcript ?? null;

        // Title must come from transcript; never invented.
        let titleSuggestion = parsed.title_suggestion ?? null;
        if (!transcript || transcript.trim().length === 0) {
          titleSuggestion = titleSuggestion ?? "Título indisponível";
        }

        // Render-quality gate for the "ready" state.
        if (parsed.status === "READY_FOR_HUMAN_REVIEW") {
          const failures: string[] = [];
          if (!parsed.output_file_url) failures.push("output_file_url ausente");
          if (num("width") !== 1080) failures.push("width != 1080");
          if (num("height") !== 1920) failures.push("height != 1920");
          if (report.codec !== "h264") failures.push("codec != h264");
          const dur = num("duration");
          if (dur === undefined || dur <= 3) failures.push("duration <= 3s");
          if (!transcript || transcript.trim().length === 0)
            failures.push("Transcrição não gerada. Configure STT provider.");

          if (failures.length > 0) {
            finalStatus = "FAILED";
            errorMessage = `Validação reprovada: ${failures.join("; ")}`;
          }
        }

        const update: TablesUpdate<"video_jobs"> = {
          status: finalStatus,
          simulated: false,
        };
        if (parsed.progress !== undefined) update.progress = parsed.progress;
        if (parsed.output_file_url !== undefined) update.output_file_url = parsed.output_file_url;
        if (parsed.output_file_path !== undefined) update.output_file_path = parsed.output_file_path;
        if (transcript !== null) update.transcript = transcript;
        if (titleSuggestion !== null) update.title_suggestion = titleSuggestion;
        if (parsed.virality_score !== undefined) update.virality_score = parsed.virality_score;
        if (parsed.technical_report !== undefined)
          update.technical_report = (parsed.technical_report ?? null) as Json;
        if (num("width") !== undefined) update.width = num("width");
        if (num("height") !== undefined) update.height = num("height");
        if (num("duration") !== undefined) update.duration_seconds = num("duration");
        if (parsed.variants && parsed.variants.length > 0) {
          update.variants = parsed.variants.map((v) => ({
            ...v,
            label: v.label ?? v.id,
            simulated: false,
          })) as Json;
        }
        update.error_message = errorMessage;
        if (finalStatus === "READY_FOR_HUMAN_REVIEW") update.progress = 100;

        const { error: updErr } = await supabaseAdmin
          .from("video_jobs")
          .update(update)
          .eq("id", job.id);
        if (updErr) return json({ error: updErr.message }, 500);

        await supabaseAdmin.from("video_job_events").insert({
          job_id: job.id,
          event_type: finalStatus,
          message:
            finalStatus === "FAILED"
              ? errorMessage ?? "Job marcado como FAILED pelo worker."
              : `Worker atualizou status para ${finalStatus}.`,
          payload: (parsed.technical_report ?? null) as Json,
        });

        return json({ ok: true, status: finalStatus });
      },
    },
  },
});
