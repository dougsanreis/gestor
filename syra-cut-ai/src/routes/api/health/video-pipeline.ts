import { createFileRoute } from "@tanstack/react-router";

/**
 * GET /api/health/video-pipeline
 * Public read-only health probe for the SYRA pipeline infra.
 * Returns ONLINE / OFFLINE / DEGRADED per subsystem. Never throws.
 */
export const Route = createFileRoute("/api/health/video-pipeline")({
  server: {
    handlers: {
      GET: async () => {
        const workerUrl = process.env.WORKER_API_URL;
        const workerKey = process.env.WORKER_API_KEY;
        const supabaseUrl = process.env.SUPABASE_URL;
        const serviceRole = process.env.SUPABASE_SERVICE_ROLE_KEY;
        const anthropic = !!process.env.ANTHROPIC_API_KEY;
        const xai = !!process.env.XAI_API_KEY;
        const mistral = !!process.env.MISTRAL_API_KEY;
        const lovableAi = !!process.env.LOVABLE_API_KEY;

        // Probe worker /health endpoint (short timeout, never throws).
        let workerOnline: "ONLINE" | "OFFLINE" | "DEGRADED" = "OFFLINE";
        let workerLatencyMs: number | null = null;
        let workerError: string | null = null;
        if (workerUrl && workerKey) {
          const start = Date.now();
          try {
            const ctrl = new AbortController();
            const t = setTimeout(() => ctrl.abort(), 4000);
            const res = await fetch(`${workerUrl.replace(/\/$/, "")}/health`, {
              method: "GET",
              headers: { Authorization: `Bearer ${workerKey}` },
              signal: ctrl.signal,
            }).catch((e) => {
              throw e;
            });
            clearTimeout(t);
            workerLatencyMs = Date.now() - start;
            workerOnline = res.ok
              ? workerLatencyMs > 2000
                ? "DEGRADED"
                : "ONLINE"
              : "DEGRADED";
            if (!res.ok) workerError = `HTTP ${res.status}`;
          } catch (e) {
            workerOnline = "OFFLINE";
            workerError = e instanceof Error ? e.message : String(e);
          }
        } else {
          workerError = "WORKER_API_URL/KEY ausentes";
        }

        const storageStatus: "ONLINE" | "OFFLINE" =
          supabaseUrl && serviceRole ? "ONLINE" : "OFFLINE";

        // AI Router cascade ⇒ ONLINE if pelo menos um provider está configurado.
        const aiProvidersConfigured = [anthropic, xai, mistral, lovableAi].filter(Boolean).length;
        const aiRouterStatus: "ONLINE" | "OFFLINE" | "DEGRADED" =
          aiProvidersConfigured === 0
            ? "OFFLINE"
            : aiProvidersConfigured < 2
              ? "DEGRADED"
              : "ONLINE";

        // Transcription / Render / Review vivem dentro do worker — espelham worker.
        const transcriptionStatus = workerOnline;
        const renderStatus = workerOnline;
        const reviewStatus = workerOnline === "ONLINE" ? "ONLINE" : "DEGRADED";

        // Queue: hoje é in-memory dentro do worker. Espelha worker.
        const queueStatus = workerOnline;

        const requirements = {
          worker_url: !!workerUrl,
          worker_api_key: !!workerKey,
          storage: storageStatus === "ONLINE",
          callback: storageStatus === "ONLINE", // mesmo endpoint do app
          ffmpeg: workerOnline === "ONLINE", // só sabemos se worker responde
          whisper: workerOnline === "ONLINE",
        };

        const allRequirementsMet = Object.values(requirements).every(Boolean);

        return Response.json({
          ok: true,
          timestamp: new Date().toISOString(),
          gateway: {
            worker: workerOnline,
            worker_latency_ms: workerLatencyMs,
            worker_error: workerError,
          },
          subsystems: {
            worker_gateway: workerOnline,
            queue: queueStatus,
            transcription: transcriptionStatus,
            ai_router: aiRouterStatus,
            render: renderStatus,
            storage: storageStatus,
            review: reviewStatus,
          },
          providers: {
            anthropic: anthropic ? "ONLINE" : "OFFLINE",
            xai: xai ? "ONLINE" : "OFFLINE",
            mistral: mistral ? "ONLINE" : "OFFLINE",
            lovable_ai: lovableAi ? "ONLINE" : "OFFLINE",
          },
          requirements,
          all_requirements_met: allRequirementsMet,
          can_generate_real_variants: allRequirementsMet,
        });
      },
    },
  },
});
