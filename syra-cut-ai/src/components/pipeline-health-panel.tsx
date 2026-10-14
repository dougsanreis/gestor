import { useQuery } from "@tanstack/react-query";
import { Activity, CheckCircle2, Loader2, Plug, XCircle, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

type Status = "ONLINE" | "OFFLINE" | "DEGRADED" | "UNKNOWN";

interface HealthResponse {
  ok: boolean;
  timestamp: string;
  gateway: { worker: Status; worker_latency_ms: number | null; worker_error: string | null };
  subsystems: {
    worker_gateway: Status;
    queue: Status;
    transcription: Status;
    ai_router: Status;
    render: Status;
    storage: Status;
    review: Status;
  };
  providers: { anthropic: Status; xai: Status; mistral: Status; lovable_ai: Status };
  requirements: {
    worker_url: boolean;
    worker_api_key: boolean;
    storage: boolean;
    callback: boolean;
    ffmpeg: boolean;
    whisper: boolean;
  };
  all_requirements_met: boolean;
  can_generate_real_variants: boolean;
}

const STATUS_STYLE: Record<Status, string> = {
  ONLINE: "bg-success/15 text-success",
  OFFLINE: "bg-destructive/15 text-destructive",
  DEGRADED: "bg-warning/15 text-warning",
  UNKNOWN: "bg-muted text-muted-foreground",
};

function StatusPill({ status }: { status: Status }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATUS_STYLE[status]}`}
    >
      {status}
    </span>
  );
}

const SUBSYSTEM_LABELS: { key: keyof HealthResponse["subsystems"]; label: string }[] = [
  { key: "worker_gateway", label: "Worker Gateway" },
  { key: "queue", label: "Queue" },
  { key: "transcription", label: "Transcription · Whisper" },
  { key: "ai_router", label: "AI Router · Claude/Grok/Mistral" },
  { key: "render", label: "Render Worker · FFmpeg" },
  { key: "storage", label: "Storage · R2/Supabase" },
  { key: "review", label: "Review Worker · ffprobe" },
];

const REQUIREMENT_LABELS: { key: keyof HealthResponse["requirements"]; label: string }[] = [
  { key: "worker_url", label: "Worker URL" },
  { key: "worker_api_key", label: "Worker API Key" },
  { key: "storage", label: "Storage" },
  { key: "callback", label: "Callback" },
  { key: "ffmpeg", label: "FFmpeg" },
  { key: "whisper", label: "Whisper" },
];

export function PipelineHealthPanel({
  onConnectWorker,
}: {
  onConnectWorker?: () => void;
}) {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["video-pipeline-health"],
    queryFn: async (): Promise<HealthResponse> => {
      const res = await fetch("/api/health/video-pipeline");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 30_000,
  });

  return (
    <div className="glass-panel rounded-2xl p-5">
      <div className="flex items-start justify-between gap-2">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <Activity className="size-5 text-primary" /> Infraestrutura do Pipeline
        </h2>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => refetch()}
          disabled={isFetching}
          title="Re-checar"
        >
          {isFetching ? <Loader2 className="size-3.5 animate-spin" /> : "↻"}
        </Button>
      </div>

      {isLoading ? (
        <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Checando…
        </div>
      ) : !data ? (
        <p className="mt-3 text-sm text-destructive">Health endpoint indisponível.</p>
      ) : (
        <>
          <ul className="mt-3 space-y-1.5">
            {SUBSYSTEM_LABELS.map(({ key, label }) => (
              <li key={key} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{label}</span>
                <StatusPill status={data.subsystems[key]} />
              </li>
            ))}
          </ul>

          {data.gateway.worker_latency_ms != null && (
            <p className="mt-2 text-[10px] text-muted-foreground">
              Worker latency: {data.gateway.worker_latency_ms}ms
              {data.gateway.worker_error && ` · ${data.gateway.worker_error}`}
            </p>
          )}

          <div className="mt-4 border-t border-border/40 pt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Pipeline Requirements
            </p>
            <ul className="space-y-1">
              {REQUIREMENT_LABELS.map(({ key, label }) => {
                const ok = data.requirements[key];
                return (
                  <li key={key} className="flex items-center gap-2 text-sm">
                    {ok ? (
                      <CheckCircle2 className="size-3.5 text-success" />
                    ) : (
                      <XCircle className="size-3.5 text-destructive" />
                    )}
                    <span className={ok ? "" : "text-muted-foreground"}>{label}</span>
                  </li>
                );
              })}
            </ul>
          </div>

          {!data.can_generate_real_variants && (
            <div className="mt-4 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs">
              <p className="flex items-center gap-1.5 font-medium text-warning">
                <AlertTriangle className="size-3.5" /> Worker não conectado
              </p>
              <p className="mt-1 text-muted-foreground">
                Geração de variantes reais está bloqueada até todos os requisitos ficarem ONLINE.
              </p>
              <Button
                size="sm"
                className="mt-2 w-full"
                onClick={onConnectWorker}
                variant="outline"
              >
                <Plug className="size-3.5" /> Conectar Worker Real
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function useCanGenerateRealVariants() {
  const { data } = useQuery({
    queryKey: ["video-pipeline-health"],
    queryFn: async (): Promise<HealthResponse> => {
      const res = await fetch("/api/health/video-pipeline");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 30_000,
  });
  return data?.can_generate_real_variants ?? false;
}
