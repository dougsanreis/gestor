import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import type { Json } from "@/integrations/supabase/types";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

/**
 * Runs the SYRA Viral Intelligence analysis over a job's REAL transcript.
 * Honors the supreme rule: refuses to run without a transcript.
 */
export const analyzeJobIntelligence = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ jobId: z.string().uuid() }).parse(d))
  .handler(async ({ data, context }) => {
    const { supabase } = context;

    const { data: job, error } = await supabase
      .from("video_jobs")
      .select("id, transcript, simulated")
      .eq("id", data.jobId)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (!job) throw new Error("Job não encontrado.");

    const transcript = (job.transcript ?? "").trim();
    if (!transcript) {
      throw new Error(
        "Sem transcrição. A inteligência narrativa só roda sobre transcrição real — configure o STT provider.",
      );
    }

    await supabase.from("video_jobs").update({ intelligence_status: "ANALYZING" }).eq("id", job.id);
    await supabase.from("video_job_events").insert({
      job_id: job.id,
      event_type: "INTELLIGENCE_ANALYZING",
      message: "Story / Emotion / Identity engines analisando o transcript.",
    });

    try {
      const { analyzeViralIntelligence } = await import("./intelligence.server");
      const intelligence = await analyzeViralIntelligence(transcript);

      await supabase
        .from("video_jobs")
        .update({
          intelligence: intelligence as unknown as Json,
          intelligence_status: job.simulated ? "SIMULATED" : "ACTIVE",
          virality_score: intelligence.scores.viral_score,
        })
        .eq("id", job.id);

      await supabase.from("video_job_events").insert({
        job_id: job.id,
        event_type: "INTELLIGENCE_READY",
        message: `Inteligência viral gerada. Viral score ${intelligence.scores.viral_score}/100 · identidade: ${intelligence.identity.archetype}.`,
        payload: intelligence as unknown as Json,
      });

      return { ok: true };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      await supabase.from("video_jobs").update({ intelligence_status: "FAILED" }).eq("id", job.id);
      await supabase.from("video_job_events").insert({
        job_id: job.id,
        event_type: "INTELLIGENCE_FAILED",
        message: `Falha na análise de inteligência: ${msg}`,
      });
      throw new Error(msg);
    }
  });
