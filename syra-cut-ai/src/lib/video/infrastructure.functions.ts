import { createServerFn } from "@tanstack/react-start";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

export interface WorkerProbeResult {
  worker: { online: boolean; latency_ms: number | null; error: string | null; http_status: number | null };
  render: { online: boolean; ffmpeg: boolean; ffprobe: boolean };
  transcription: { online: boolean; whisper: boolean };
  storage: { online: boolean };
  ai: { claude: boolean; grok: boolean; mistral: boolean };
  ready: boolean;
  raw: string | null;
}

/** Probe an arbitrary worker URL + key from the onboarding wizard (does NOT persist). */
export const probeWorkerInfrastructure = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input: { url: string; key: string }) => {
    if (!input?.url || typeof input.url !== "string") throw new Error("URL obrigatória");
    if (!input?.key || typeof input.key !== "string") throw new Error("API Key obrigatória");
    return input;
  })
  .handler(async ({ data }): Promise<WorkerProbeResult> => {
    const base = data.url.replace(/\/$/, "");
    const start = Date.now();
    let raw: unknown = null;
    let httpStatus: number | null = null;
    let workerOnline = false;
    let latency: number | null = null;
    let error: string | null = null;

    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 5000);
      const res = await fetch(`${base}/health`, {
        method: "GET",
        headers: { Authorization: `Bearer ${data.key}` },
        signal: ctrl.signal,
      });
      clearTimeout(t);
      latency = Date.now() - start;
      httpStatus = res.status;
      workerOnline = res.ok;
      try {
        raw = await res.json();
      } catch {
        raw = await res.text().catch(() => null);
      }
      if (!res.ok) error = `HTTP ${res.status}`;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }

    const h = (raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {}) as Record<
      string,
      unknown
    >;
    const providers = (h.providers ?? {}) as Record<string, unknown>;

    const ffmpegOk = h.ffmpeg === "ONLINE" || h.ffmpeg === true;
    // worker /health doesn't yet expose ffprobe separately — treat as paired with ffmpeg.
    const ffprobeOk = ffmpegOk;
    const whisperOk =
      providers.whisper === "ONLINE" || providers.whisper === true || !!h.whisper;
    const storageOk = h.storage === "ONLINE" || h.storage === true;
    const claude = providers.anthropic === "ONLINE" || providers.claude === "ONLINE";
    const grok = providers.xai === "ONLINE" || providers.grok === "ONLINE";
    const mistral = providers.mistral === "ONLINE";

    const ready =
      workerOnline && ffmpegOk && ffprobeOk && whisperOk && storageOk && (claude || grok || mistral);

    return {
      worker: { online: workerOnline, latency_ms: latency, error, http_status: httpStatus },
      render: { online: workerOnline && ffmpegOk, ffmpeg: ffmpegOk, ffprobe: ffprobeOk },
      transcription: { online: workerOnline && whisperOk, whisper: whisperOk },
      storage: { online: storageOk },
      ai: { claude, grok, mistral },
      ready,
      raw: raw == null ? null : typeof raw === "string" ? raw : JSON.stringify(raw),
    };
  });
