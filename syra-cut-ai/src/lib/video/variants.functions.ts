import { createServerFn } from "@tanstack/react-start";
import { getRequestHeader } from "@tanstack/react-start/server";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import type { Json } from "@/integrations/supabase/types";
import { buildSimulatedVariants } from "./fallback-simulation";
import type { AiEditorialPlan, AiPipelineMode } from "./job-contract";

/**
 * Plans the editorial cut with the AI Provider Router (Claude → Grok → Mistral
 * → Local heuristic) over the REAL transcript, then dispatches the worker if
 * configured. AI failures NEVER mark the job FAILED — the router always
 * returns a valid plan, and worker absence falls back to simulated variants.
 */
export const planAndDispatchVariants = createServerFn({ method: "POST" })
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
    const transcript = (job.transcript ?? "").trim();
    if (!transcript) {
      throw new Error(
        "Sem transcrição real. O roteador de IA não roda sem transcript (regra suprema).",
      );
    }

    await supabase
      .from("video_jobs")
      .update({ status: "ANALYZING", progress: 35 })
      .eq("id", job.id);
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "AI_ROUTER_START",
      message: "AIProviderRouter: Claude → Grok → Mistral → Local.",
    });

    // ---- Router cascade (never throws) ----
    const { planEditorial } = await import("./ai-provider-router.server");
    const { plan: aiPlan, mode, attempts, degraded } = await planEditorial(transcript);

    await supabase
      .from("video_jobs")
      .update({
        ai_plan: { ...aiPlan, mode } as unknown as Json,
        title_suggestion: aiPlan.title,
        virality_score: aiPlan.virality_score,
      })
      .eq("id", job.id);

    for (const a of attempts) {
      await supabase.from("video_job_events").insert({
        job_id: job.id,
        event_type: a.log.replace(/[\[\]]/g, ""),
        message: a.error
          ? `${a.log} ${a.provider}: ${a.error}`
          : `${a.log} ${a.provider} respondeu.`,
        payload: { provider: a.provider, status: a.status } as unknown as Json,
      });
    }
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "AI_ROUTER_DONE",
      message: `AI Mode: ${mode}${degraded ? " (degradado)" : ""}.`,
      payload: { mode, degraded } as unknown as Json,
    });

    // ---- Worker dispatch (or graceful simulation) ----
    const { readWorkerEnv, dispatchToWorker } = await import("./video-worker-client.server");
    const env = readWorkerEnv();

    async function fallbackToSimulation(reason: string) {
      await supabase
        .from("video_jobs")
        .update({
          status: "READY_FOR_HUMAN_REVIEW",
          progress: 100,
          simulated: true,
          variants: buildSimulatedVariants(transcript) as unknown as Json,
        })
        .eq("id", job!.id);
      await supabase.from("video_job_events").insert({
        job_id: job!.id,
        event_type: "CONFIG_REQUIRED",
        message: reason,
      });
    }

    if (!env) {
      await fallbackToSimulation(
        "Worker não configurado (WORKER_API_URL/KEY). Variantes marcadas como SIMULADO.",
      );
      return { worker: false, simulated: true, mode };
    }

    if (!job.source_file_path) {
      // Real pipeline data missing — this IS a render-side failure.
      await supabase
        .from("video_jobs")
        .update({ status: "FAILED", error_message: "Job sem arquivo de origem." })
        .eq("id", job.id);
      throw new Error("Job sem arquivo de origem.");
    }

    const { data: signed } = await supabase.storage
      .from("source-videos")
      .createSignedUrl(job.source_file_path, 60 * 60);
    if (!signed?.signedUrl) {
      await supabase
        .from("video_jobs")
        .update({ status: "FAILED", error_message: "Falha ao assinar URL de origem." })
        .eq("id", job.id);
      throw new Error("Falha ao assinar URL de origem.");
    }

    const callbackUrl = (await import("./video-worker-client.server")).resolveCallbackUrl(
      getRequestHeader("host"),
      getRequestHeader("x-forwarded-proto"),
    );

    try {
      await dispatchToWorker({
        env,
        jobId: job.id,
        userId,
        sourceUrl: signed.signedUrl,
        callbackUrl,
        aiPlan: aiPlan as AiEditorialPlan,
      });
      await supabase
        .from("video_jobs")
        .update({ status: "RENDERING", progress: 60 })
        .eq("id", job.id);
      await supabase.from("video_job_events").insert({
        job_id: job.id,
        event_type: "WORKER_DISPATCHED",
        message: "Worker acionado com 3 variantes (viral_cut, clean_caption, speed_dynamic).",
      });
      return { worker: true, simulated: false, mode };
    } catch (e) {
      // Worker indisponível ≠ falha de render. Caímos em modo simulado com aviso claro.
      const msg = e instanceof Error ? e.message : String(e);
      await fallbackToSimulation(
        `Worker indisponível (${msg}). Variantes marcadas como SIMULADO — pipeline preservado.`,
      );
      return { worker: false, simulated: true, mode: "FALLBACK" satisfies AiPipelineMode };
    }
  });

/** Retry: reset error state and re-run plan+dispatch. */
export const retryJob = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ jobId: z.string().uuid() }).parse(d))
  .handler(async ({ data, context }) => {
    const { supabase } = context;
    const { data: job } = await supabase
      .from("video_jobs")
      .select("id, retry_count")
      .eq("id", data.jobId)
      .maybeSingle();
    if (!job) throw new Error("Job não encontrado.");
    await supabase
      .from("video_jobs")
      .update({
        status: "QUEUED",
        progress: 5,
        error_message: null,
        retry_count: (job.retry_count ?? 0) + 1,
      })
      .eq("id", job.id);
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "RETRY",
      message: `Retry #${(job.retry_count ?? 0) + 1} iniciado.`,
    });
    return { ok: true };
  });

/** Human-in-the-loop approval: marks a variant as approved on the job. */
export const approveVariant = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) =>
    z
      .object({
        jobId: z.string().uuid(),
        variantId: z.enum(["viral_cut", "clean_caption", "speed_dynamic"]),
        approved: z.boolean().default(true),
      })
      .parse(d),
  )
  .handler(async ({ data, context }) => {
    const { supabase } = context;
    const { data: job, error } = await supabase
      .from("video_jobs")
      .select("id, variants")
      .eq("id", data.jobId)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (!job) throw new Error("Job não encontrado.");
    const list = (Array.isArray(job.variants) ? job.variants : []) as unknown as Array<
      Record<string, unknown>
    >;
    const next = list.map((v) =>
      v.id === data.variantId
        ? { ...v, approved: data.approved, approved_at: new Date().toISOString() }
        : v,
    );
    await supabase
      .from("video_jobs")
      .update({ variants: next as unknown as Json })
      .eq("id", job.id);
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: data.approved ? "VARIANT_APPROVED" : "VARIANT_UNAPPROVED",
      message: `Variante ${data.variantId} ${data.approved ? "aprovada" : "desaprovada"} pelo revisor.`,
    });
    return { ok: true };
  });

const VARIANT_ENUM = z.enum(["viral_cut", "clean_caption", "speed_dynamic"]);

/** Edit the caption text stored on a single variant (human-in-the-loop). */
export const editVariantCaption = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) =>
    z
      .object({
        jobId: z.string().uuid(),
        variantId: VARIANT_ENUM,
        captionText: z.string().min(0).max(8000),
      })
      .parse(d),
  )
  .handler(async ({ data, context }) => {
    const { supabase } = context;
    const { data: job, error } = await supabase
      .from("video_jobs")
      .select("id, variants")
      .eq("id", data.jobId)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (!job) throw new Error("Job não encontrado.");
    const list = (Array.isArray(job.variants) ? job.variants : []) as unknown as Array<
      Record<string, unknown>
    >;
    const next = list.map((v) =>
      v.id === data.variantId ? { ...v, editable_caption_text: data.captionText } : v,
    );
    await supabase
      .from("video_jobs")
      .update({ variants: next as unknown as Json })
      .eq("id", job.id);
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "VARIANT_CAPTION_EDITED",
      message: `Legenda da variante ${data.variantId} editada.`,
    });
    return { ok: true };
  });

/** Re-render a single variant: marks it queued and re-runs the plan/dispatch. */
export const rerenderVariant = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) =>
    z.object({ jobId: z.string().uuid(), variantId: VARIANT_ENUM }).parse(d),
  )
  .handler(async ({ data, context }) => {
    const { supabase } = context;
    const { data: job, error } = await supabase
      .from("video_jobs")
      .select("id, variants")
      .eq("id", data.jobId)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (!job) throw new Error("Job não encontrado.");
    const list = (Array.isArray(job.variants) ? job.variants : []) as unknown as Array<
      Record<string, unknown>
    >;
    const next = list.map((v) =>
      v.id === data.variantId
        ? { ...v, status: "VARIANT_QUEUED", error: null, approved: false }
        : v,
    );
    await supabase
      .from("video_jobs")
      .update({ variants: next as unknown as Json })
      .eq("id", job.id);
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "VARIANT_RERENDER_REQUESTED",
      message: `Re-render solicitado para variante ${data.variantId}.`,
    });
    return { ok: true };
  });

/**
 * Destrava o pipeline em modo SIMULADO mesmo sem transcrição/worker.
 * Gera os 3 cards com badge SIM. NUNCA forja MP4 (preview/download = null).
 * Usado quando o worker está offline e o usuário quer ver o fluxo.
 */
export const simulateVariantsNow = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ jobId: z.string().uuid() }).parse(d))
  .handler(async ({ data, context }) => {
    const { supabase } = context;
    const { data: job, error } = await supabase
      .from("video_jobs")
      .select("id, transcript")
      .eq("id", data.jobId)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (!job) throw new Error("Job não encontrado.");
    await supabase
      .from("video_jobs")
      .update({
        status: "READY_FOR_HUMAN_REVIEW",
        progress: 100,
        simulated: true,
        variants: buildSimulatedVariants(job.transcript) as unknown as Json,
      })
      .eq("id", job.id);
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "SIMULATED_VARIANTS_FORCED",
      message: "Variantes simuladas geradas manualmente (worker offline).",
    });
    return { ok: true };
  });
