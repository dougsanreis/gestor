import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Plug,
  XCircle,
  Server,
  Database,
  Film,
  Mic,
  Sparkles,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  probeWorkerInfrastructure,
  type WorkerProbeResult,
} from "@/lib/video/infrastructure.functions";

export const Route = createFileRoute("/_authenticated/settings/video-infrastructure")({
  head: () => ({ meta: [{ title: "Video Infrastructure — SYRA VideoOS" }] }),
  component: VideoInfrastructurePage,
});

type Status = "ONLINE" | "OFFLINE" | "DEGRADED" | "UNKNOWN";

interface HealthResponse {
  subsystems: {
    worker_gateway: Status;
    queue: Status;
    transcription: Status;
    ai_router: Status;
    render: Status;
    storage: Status;
    review: Status;
  };
  requirements: Record<string, boolean>;
  can_generate_real_variants: boolean;
}

function StatusDot({ ok, pending }: { ok: boolean; pending?: boolean }) {
  if (pending) return <Loader2 className="size-4 animate-spin text-muted-foreground" />;
  return ok ? (
    <CheckCircle2 className="size-4 text-success" />
  ) : (
    <XCircle className="size-4 text-destructive" />
  );
}

function StepCard({
  icon,
  step,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  step: number;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="glass-panel rounded-2xl p-5">
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {icon}
        </div>
        <div className="flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Etapa {step}
          </p>
          <h2 className="font-display text-lg font-semibold">{title}</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function VideoInfrastructurePage() {
  const probe = useServerFn(probeWorkerInfrastructure);

  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<WorkerProbeResult | null>(null);

  const { data: serverHealth, refetch } = useQuery({
    queryKey: ["video-pipeline-health"],
    queryFn: async (): Promise<HealthResponse> => {
      const res = await fetch("/api/health/video-pipeline");
      return res.json();
    },
    refetchInterval: 30_000,
  });

  async function runTest() {
    if (!url || !key) {
      toast.error("Preencha URL e API Key do Worker");
      return;
    }
    setTesting(true);
    setResult(null);
    try {
      const r = await probe({ data: { url, key } });
      setResult(r);
      if (r.ready) toast.success("Pipeline pronto — todos os subsistemas OK");
      else if (r.worker.online) toast.info("Worker respondeu, mas faltam subsistemas");
      else toast.error(`Worker offline: ${r.worker.error ?? "sem resposta"}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha ao testar conexão");
    } finally {
      setTesting(false);
      refetch();
    }
  }

  const r = result;
  const pipelineReady = r?.ready ?? false;

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-8">
        <div className="flex items-center justify-between">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> Voltar
          </Link>
          {serverHealth && (
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
                serverHealth.can_generate_real_variants
                  ? "bg-success/15 text-success"
                  : "bg-warning/15 text-warning"
              }`}
            >
              {serverHealth.can_generate_real_variants ? "PIPELINE READY" : "BLOQUEADO"}
            </span>
          )}
        </div>

        <div>
          <h1 className="font-display text-3xl font-semibold">Video Infrastructure</h1>
          <p className="mt-1 text-muted-foreground">
            Conecte o Worker Gateway, Storage e Render Engine sem editar código. Quando todos os
            subsistemas estiverem online, a geração de variantes reais é liberada.
          </p>
        </div>

        <StepCard
          step={1}
          icon={<Server className="size-4" />}
          title="Worker Gateway"
          description="Endpoint HTTPS do Cloudflare Worker que coordena a fila de renderização."
        >
          <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
            <div>
              <Label htmlFor="worker-url">Worker URL</Label>
              <Input
                id="worker-url"
                placeholder="https://syra-video-gateway.workers.dev"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="worker-key">API Key</Label>
              <Input
                id="worker-key"
                type="password"
                placeholder="••••••••"
                value={key}
                onChange={(e) => setKey(e.target.value)}
              />
            </div>
          </div>
          <Button onClick={runTest} disabled={testing} className="mt-3">
            {testing ? <Loader2 className="size-4 animate-spin" /> : <Plug className="size-4" />}
            Testar Conexão
          </Button>
          {r && (
            <div className="mt-3 flex items-center justify-between rounded-lg border border-border/40 bg-background/30 px-3 py-2 text-sm">
              <span className="flex items-center gap-2">
                <StatusDot ok={r.worker.online} />
                {r.worker.online ? "ONLINE" : "OFFLINE"}
              </span>
              <span className="text-xs text-muted-foreground">
                {r.worker.latency_ms != null ? `${r.worker.latency_ms} ms` : "—"}
                {r.worker.error && ` · ${r.worker.error}`}
              </span>
            </div>
          )}
        </StepCard>

        <StepCard
          step={2}
          icon={<Database className="size-4" />}
          title="Storage"
          description="Bucket de upload, render e preview (Supabase Storage ou Cloudflare R2)."
        >
          <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/30 px-3 py-2 text-sm">
            <span className="flex items-center gap-2">
              <StatusDot ok={r?.storage.online ?? false} pending={testing} />
              {r ? (r.storage.online ? "Bucket acessível" : "Não configurado") : "Aguardando teste"}
            </span>
            <span className="text-xs text-muted-foreground">
              Reportado pelo worker /health
            </span>
          </div>
        </StepCard>

        <StepCard
          step={3}
          icon={<Film className="size-4" />}
          title="Render Engine"
          description="FFmpeg + ffprobe rodando no Render Worker."
        >
          <ul className="space-y-1.5 text-sm">
            <li className="flex items-center justify-between rounded-lg border border-border/40 bg-background/30 px-3 py-2">
              <span className="flex items-center gap-2">
                <StatusDot ok={r?.render.ffmpeg ?? false} pending={testing} /> ffmpeg
              </span>
            </li>
            <li className="flex items-center justify-between rounded-lg border border-border/40 bg-background/30 px-3 py-2">
              <span className="flex items-center gap-2">
                <StatusDot ok={r?.render.ffprobe ?? false} pending={testing} /> ffprobe
              </span>
            </li>
          </ul>
        </StepCard>

        <StepCard
          step={4}
          icon={<Mic className="size-4" />}
          title="Transcription"
          description="Whisper (OpenAI ou faster-whisper) para gerar transcript real."
        >
          <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/30 px-3 py-2 text-sm">
            <span className="flex items-center gap-2">
              <StatusDot ok={r?.transcription.whisper ?? false} pending={testing} />
              {r?.transcription.whisper ? "Whisper disponível" : "Whisper indisponível"}
            </span>
          </div>
        </StepCard>

        <StepCard
          step={5}
          icon={<Sparkles className="size-4" />}
          title="AI Router"
          description="Pelo menos um provider editorial precisa estar online."
        >
          <ul className="grid gap-1.5 text-sm sm:grid-cols-3">
            {(["claude", "grok", "mistral"] as const).map((p) => (
              <li
                key={p}
                className="flex items-center gap-2 rounded-lg border border-border/40 bg-background/30 px-3 py-2"
              >
                <StatusDot ok={r?.ai[p] ?? false} pending={testing} />
                <span className="capitalize">{p}</span>
              </li>
            ))}
          </ul>
        </StepCard>

        <div
          className={`glass-panel flex items-start gap-3 rounded-2xl border p-5 ${
            pipelineReady
              ? "border-success/30 bg-success/5"
              : "border-warning/30 bg-warning/5"
          }`}
        >
          <ShieldCheck
            className={`mt-0.5 size-5 ${pipelineReady ? "text-success" : "text-warning"}`}
          />
          <div className="flex-1">
            <p className="font-semibold">
              {pipelineReady ? "Pipeline Ready" : "Pipeline incompleto"}
            </p>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {pipelineReady
                ? "Todos os subsistemas verdes. Salve WORKER_API_URL e WORKER_API_KEY como secrets do projeto para liberar a geração de variantes reais em produção."
                : "Rode o teste e garanta que worker, render, transcription, storage e ao menos uma IA estejam ONLINE."}
            </p>
            {r && (
              <pre className="mt-3 max-h-48 overflow-auto rounded-lg bg-background/40 p-3 text-[11px]">
                {JSON.stringify(
                  {
                    worker: r.worker,
                    render: r.render,
                    transcription: r.transcription,
                    storage: r.storage,
                    ai: r.ai,
                    ready: r.ready,
                  },
                  null,
                  2,
                )}
              </pre>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
