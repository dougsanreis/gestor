import { createServerFn } from "@tanstack/react-start";
import { getRequestHeader } from "@tanstack/react-start/server";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

const SOURCE_BUCKET = "source-videos";

/**
 * Mirrors the requested "create-video-job" edge function.
 * Validates ownership (RLS), flips status to QUEUED, logs the event and
 * dispatches the external worker when WORKER_API_URL/KEY are configured.
 */
export const dispatchVideoJob = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ jobId: z.string().uuid() }).parse(d))
  .handler(async ({ data, context }) => {
    const { supabase, userId } = context;

    const { data: job, error } = await supabase
      .from("video_jobs")
      .select("*")
      .eq("id", data.jobId)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (!job) throw new Error("Job não encontrado.");
    if (!job.source_file_path) throw new Error("Job sem arquivo de origem.");

    await supabase.from("video_jobs").update({ status: "QUEUED", progress: 5 }).eq("id", job.id);
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "QUEUED",
      message: "Job enfileirado para processamento.",
    });

    const workerUrl = process.env.WORKER_API_URL;
    const workerKey = process.env.WORKER_API_KEY;

    if (!workerUrl || !workerKey) {
      await supabase.from("video_job_events").insert({
        job_id: job.id,
        event_type: "CONFIG_REQUIRED",
        message:
          "Worker externo não configurado (WORKER_API_URL/WORKER_API_KEY ausentes). O job permanece em QUEUED.",
      });
      return { worker: false, configured: false };
    }

    const { data: signed } = await supabase.storage
      .from(SOURCE_BUCKET)
      .createSignedUrl(job.source_file_path, 60 * 60);

    const { resolveCallbackUrl } = await import("./video/video-worker-client.server");
    const callbackUrl = resolveCallbackUrl(
      getRequestHeader("host"),
      getRequestHeader("x-forwarded-proto"),
    );

    try {
      const res = await fetch(`${workerUrl.replace(/\/$/, "")}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${workerKey}` },
        body: JSON.stringify({
          job_id: job.id,
          user_id: userId,
          source_file_url: signed?.signedUrl,
          target_format: "9:16",
          max_duration: 75,
          output_profiles: ["tiktok_viral", "reels_premium", "shorts_clean"],
          callback_url: callbackUrl,
        }),
      });
      if (!res.ok) throw new Error(`Worker respondeu ${res.status}`);

      await supabase.from("video_job_events").insert({
        job_id: job.id,
        event_type: "WORKER_DISPATCHED",
        message: "Worker externo acionado com sucesso.",
      });
      return { worker: true, configured: true };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      await supabase
        .from("video_jobs")
        .update({ status: "FAILED", error_message: `Falha ao acionar worker: ${msg}` })
        .eq("id", job.id);
      await supabase.from("video_job_events").insert({
        job_id: job.id,
        event_type: "FAILED",
        message: `Falha ao acionar worker: ${msg}`,
      });
      return { worker: false, configured: true, error: msg };
    }
  });

/** Mirrors "get-signed-video-url" — RLS guarantees the user owns the path. */
export const getSignedVideoUrl = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) =>
    z
      .object({
        bucket: z.enum(["source-videos", "rendered-videos", "reports"]),
        path: z.string().min(1),
      })
      .parse(d),
  )
  .handler(async ({ data, context }) => {
    const { data: signed, error } = await context.supabase.storage
      .from(data.bucket)
      .createSignedUrl(data.path, 60 * 60);
    if (error || !signed) throw new Error(error?.message ?? "Não foi possível gerar a URL.");
    return { url: signed.signedUrl };
  });

/**
 * Development/admin only: simulate a worker callback so the full UI flow can be
 * exercised before a real worker exists. NEVER produces a fake rendered video —
 * the result is clearly flagged as simulated (no output_file_url).
 */
export const simulateJobCallback = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) =>
    z.object({ jobId: z.string().uuid(), outcome: z.enum(["success", "failure"]) }).parse(d),
  )
  .handler(async ({ data, context }) => {
    const { supabase } = context;
    const { data: job } = await supabase
      .from("video_jobs")
      .select("id")
      .eq("id", data.jobId)
      .maybeSingle();
    if (!job) throw new Error("Job não encontrado.");

    if (data.outcome === "failure") {
      await supabase
        .from("video_jobs")
        .update({
          status: "FAILED",
          progress: 0,
          simulated: true,
          error_message: "[SIMULADO] Falha de processamento simulada pelo modo desenvolvedor.",
        })
        .eq("id", job.id);
      await supabase.from("video_job_events").insert({
        job_id: job.id,
        event_type: "FAILED",
        message: "[SIMULADO] Falha simulada pelo modo desenvolvedor.",
      });
      return { ok: true };
    }

    const report = {
      simulated: true,
      width: 1080,
      height: 1920,
      codec: "h264",
      duration: 42.4,
      cuts: 11,
      subtitle_words: 164,
      hook: "0.0s-3.0s",
      segment_ranking: [1, 4, 2],
    };

    const { buildSimulatedVariants } = await import("./video/fallback-simulation");

    await supabase
      .from("video_jobs")
      .update({
        status: "READY_FOR_HUMAN_REVIEW",
        progress: 100,
        simulated: true,
        transcript:
          "[SIMULADO] Eu estava quebrado, devendo todo mundo, dormindo no carro. Todos diziam pra eu desistir e arranjar um emprego normal. Mas teve um dia, exatamente esse dia, que algo mudou. Eu peguei meu último dinheiro e em vez de comprar comida, comprei um curso. Foi aqui que tudo mudou. Em seis meses eu saí do carro pra um apartamento, e hoje eu emprego trinta pessoas. Ninguém esperava isso. Se você está no fundo do poço agora, presta atenção nos próximos segundos: o fundo do poço também é um lugar de onde dá pra construir.",
        title_suggestion: "[SIMULADO] Como dobrar seu alcance em 30 segundos",
        virality_score: 78,
        width: 1080,
        height: 1920,
        duration_seconds: 42.4,
        technical_report: report,
        variants: buildSimulatedVariants() as unknown as import("@/integrations/supabase/types").Json,
        error_message: null,
      })
      .eq("id", job.id);

    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "SIMULATED_CALLBACK",
      message:
        "[SIMULADO] Callback de sucesso simulado. Nenhum vídeo real foi renderizado — apenas o fluxo de UI.",
      payload: report,
    });
    return { ok: true };
  });
