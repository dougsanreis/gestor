import { useEffect, useState } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  Loader2,
  Sparkles,
  FlaskConical,
  FileText,
  Gauge,
  AlertTriangle,
  RefreshCw,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { StageTimeline } from "@/components/stage-timeline";
import { LogsPanel } from "@/components/logs-panel";
import { ViralIntelligencePanel } from "@/components/viral-intelligence-panel";
import { VariantCards } from "@/components/variant-cards";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { getSignedVideoUrl, simulateJobCallback } from "@/lib/video-jobs.functions";
import { analyzeJobIntelligence } from "@/lib/intelligence.functions";
import {
  planAndDispatchVariants,
  retryJob,
  approveVariant,
  editVariantCaption,
  rerenderVariant,
  simulateVariantsNow,
} from "@/lib/video/variants.functions";
import type { VariantResult, VariantId, AiPipelineMode } from "@/lib/video/job-contract";
import {
  AiModeBadge,
  ProviderHealthPanel,
  type ProviderHealth,
  type ProviderStatus,
} from "@/components/ai-mode-badge";
import {
  type VideoJob,
  type VideoJobEvent,
  type ViralIntelligence,
  type IntelligenceStatus,
  EDITORIAL_CAPABILITIES,
  editorialState,
  formatDuration,
  isProcessing,
  statusMeta,
} from "@/lib/syra";
import {
  PipelineHealthPanel,
  useCanGenerateRealVariants,
} from "@/components/pipeline-health-panel";

export const Route = createFileRoute("/_authenticated/jobs/$jobId")({
  head: () => ({ meta: [{ title: "Job — SYRA VideoOS" }] }),
  component: JobDetail,
});

const EDITORIAL_STATE_STYLE = {
  ACTIVE: "bg-success/15 text-success",
  CONFIG_REQUIRED: "bg-warning/15 text-warning",
  PLANNED: "bg-muted text-muted-foreground",
  FAILED: "bg-destructive/15 text-destructive",
};

function JobDetail() {
  const { jobId } = Route.useParams();
  const router = useRouter();
  const getUrl = useServerFn(getSignedVideoUrl);
  const simulate = useServerFn(simulateJobCallback);
  const analyzeIntel = useServerFn(analyzeJobIntelligence);
  const planDispatch = useServerFn(planAndDispatchVariants);
  const retry = useServerFn(retryJob);
  const approve = useServerFn(approveVariant);
  const editCap = useServerFn(editVariantCaption);
  const rerender = useServerFn(rerenderVariant);
  const simulateNow = useServerFn(simulateVariantsNow);
  const [analyzing, setAnalyzing] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [approvingId, setApprovingId] = useState<VariantId | null>(null);
  const [editingId, setEditingId] = useState<VariantId | null>(null);
  const [rerenderingId, setRerenderingId] = useState<VariantId | null>(null);
  const isDev = import.meta.env.DEV;
  const canGenerateReal = useCanGenerateRealVariants();

  const { data: job, isLoading } = useQuery({
    queryKey: ["video_job", jobId],
    queryFn: async (): Promise<VideoJob | null> => {
      const { data, error } = await supabase
        .from("video_jobs")
        .select("*")
        .eq("id", jobId)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });

  const { data: events = [] } = useQuery({
    queryKey: ["video_job_events", jobId],
    queryFn: async (): Promise<VideoJobEvent[]> => {
      const { data, error } = await supabase
        .from("video_job_events")
        .select("*")
        .eq("job_id", jobId)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data ?? [];
    },
  });

  const { data: sourceUrl } = useQuery({
    queryKey: ["signed", "source", job?.source_file_path],
    enabled: !!job?.source_file_path,
    queryFn: async () => {
      const res = await getUrl({
        data: { bucket: "source-videos", path: job!.source_file_path! },
      });
      return res.url;
    },
  });

  const { data: outputUrl } = useQuery({
    queryKey: ["signed", "output", job?.output_file_path],
    enabled: !!job?.output_file_path,
    queryFn: async () => {
      const res = await getUrl({
        data: { bucket: "rendered-videos", path: job!.output_file_path! },
      });
      return res.url;
    },
  });

  useEffect(() => {
    const channel = supabase
      .channel(`job-${jobId}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "video_jobs", filter: `id=eq.${jobId}` },
        () => router.invalidate(),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "video_job_events", filter: `job_id=eq.${jobId}` },
        () => router.invalidate(),
      )
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [jobId, router]);

  async function runSimulation(outcome: "success" | "failure") {
    try {
      await simulate({ data: { jobId, outcome } });
      toast.success(`Callback simulado (${outcome}).`);
      router.invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao simular.");
    }
  }

  async function runAnalysis() {
    setAnalyzing(true);
    try {
      await analyzeIntel({ data: { jobId } });
      toast.success("Inteligência viral gerada.");
      router.invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha na análise.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function runPlan() {
    setPlanning(true);
    try {
      const res = await planDispatch({ data: { jobId } });
      toast.success(
        res.simulated
          ? "Plano editorial pronto · variantes em modo SIMULADO (sem worker)."
          : "Plano editorial pronto · worker acionado.",
      );
      router.invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha no roteador de IA.");
    } finally {
      setPlanning(false);
    }
  }

  async function runSimulateNow() {
    setSimulating(true);
    try {
      await simulateNow({ data: { jobId } });
      toast.success("3 variantes simuladas geradas. Cards liberados para revisão.");
      router.invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao simular variantes.");
    } finally {
      setSimulating(false);
    }
  }

  async function runRetry() {
    try {
      await retry({ data: { jobId } });
      toast.success("Job reenfileirado.");
      router.invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao reenfileirar.");
    }
  }

  async function runApprove(variantId: VariantId, approved: boolean) {
    setApprovingId(variantId);
    try {
      await approve({ data: { jobId, variantId, approved } });
      toast.success(approved ? "Variante aprovada." : "Aprovação removida.");
      router.invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao aprovar.");
    } finally {
      setApprovingId(null);
    }
  }

  async function runEditCaption(variantId: VariantId, captionText: string) {
    setEditingId(variantId);
    try {
      await editCap({ data: { jobId, variantId, captionText } });
      toast.success("Legenda atualizada.");
      router.invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao editar legenda.");
    } finally {
      setEditingId(null);
    }
  }

  async function runRerender(variantId: VariantId) {
    setRerenderingId(variantId);
    try {
      await rerender({ data: { jobId, variantId } });
      toast.success("Re-render solicitado.");
      router.invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha no re-render.");
    } finally {
      setRerenderingId(null);
    }
  }

  if (isLoading) {
    return (
      <AppShell>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Carregando job…
        </div>
      </AppShell>
    );
  }

  if (!job) {
    return (
      <AppShell>
        <div className="glass-panel rounded-2xl p-10 text-center">
          <p className="font-medium">Job não encontrado</p>
          <Button asChild className="mt-4" variant="outline">
            <Link to="/dashboard">Voltar ao dashboard</Link>
          </Button>
        </div>
      </AppShell>
    );
  }

  const report = (job.technical_report ?? {}) as Record<string, unknown>;
  const ready = job.status === "READY_FOR_HUMAN_REVIEW";
  const hasOutput = !!job.output_file_url || !!job.output_file_path;
  const intelligence = (job.intelligence as ViralIntelligence | null) ?? null;
  const intelligenceStatus = (job.intelligence_status as IntelligenceStatus) ?? "PENDING";
  const hasTranscript = !!(job.transcript && job.transcript.trim().length > 0);
  const variants = ((job.variants as unknown as VariantResult[] | null) ?? []) as VariantResult[];
  const aiPlan = (job.ai_plan as { hooks?: string[]; mode?: AiPipelineMode } | null) ?? null;

  // Derive provider + worker health from events.
  const eventTypes = new Set(events.map((e) => e.event_type));
  function providerStatus(okTag: string, failTag: string): ProviderStatus {
    if (eventTypes.has(okTag)) return "ONLINE";
    if (eventTypes.has(failTag)) return "OFFLINE";
    return "UNKNOWN";
  }
  const workerStatus: ProviderStatus = eventTypes.has("WORKER_DISPATCHED")
    ? "ONLINE"
    : eventTypes.has("CONFIG_REQUIRED")
      ? "OFFLINE"
      : "UNKNOWN";
  const health: ProviderHealth[] = [
    { name: "Claude", status: providerStatus("CLAUDE_OK", "CLAUDE_FAIL") },
    { name: "Grok", status: providerStatus("GROK_OK", "GROK_FAIL") },
    { name: "Mistral", status: providerStatus("MISTRAL_OK", "MISTRAL_FAIL") },
    {
      name: "Worker",
      status: workerStatus,
      note: workerStatus === "OFFLINE" ? "modo simulado" : undefined,
    },
  ];

  return (
    <AppShell>
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Dashboard
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold">
            {job.source_file_name ?? "Vídeo"}
          </h1>
          <p className="text-sm text-muted-foreground">{statusMeta(job.status).description}</p>
        </div>
        <StatusBadge status={job.status} pulse={isProcessing(job.status)} />
      </div>

      {job.simulated && (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-accent/30 bg-accent/10 p-3 text-sm text-accent">
          <FlaskConical className="mt-0.5 size-4 shrink-0" />
          <span>
            Resultado SIMULADO pelo modo desenvolvedor — nenhum vídeo real foi renderizado nem
            transcrito.
          </span>
        </div>
      )}

      {job.status === "FAILED" && (
        <div className="mt-4 flex flex-wrap items-start justify-between gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{job.error_message ?? "Falha no pipeline."}</span>
          </div>
          <Button size="sm" variant="outline" onClick={runRetry}>
            <RefreshCw className="size-3.5" /> Tentar de novo
          </Button>
        </div>
      )}

      {isProcessing(job.status) && (
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs text-muted-foreground">
            <span>Progresso</span>
            <span>{job.progress}%</span>
          </div>
          <Progress value={job.progress} />
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="glass-panel rounded-2xl p-4">
              <p className="mb-2 text-sm font-medium text-muted-foreground">Original</p>
              {sourceUrl ? (
                <video src={sourceUrl} controls className="aspect-video w-full rounded-lg bg-black" />
              ) : (
                <div className="flex aspect-video items-center justify-center rounded-lg bg-muted text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                </div>
              )}
            </div>
            <div className="glass-panel rounded-2xl p-4">
              <p className="mb-2 text-sm font-medium text-muted-foreground">Final 9:16</p>
              {hasOutput && outputUrl ? (
                <video
                  src={outputUrl}
                  controls
                  className="mx-auto aspect-[9/16] max-h-80 rounded-lg bg-black"
                />
              ) : (
                <div className="flex aspect-[9/16] max-h-80 items-center justify-center rounded-lg bg-muted px-4 text-center text-xs text-muted-foreground">
                  {ready
                    ? "Sem arquivo final (resultado simulado ou worker não entregou MP4)."
                    : "O vídeo final aparece aqui após render + validação ffprobe."}
                </div>
              )}
            </div>
          </div>

          {ready && hasOutput && outputUrl && (
            <Button asChild className="w-full glow-border">
              <a href={outputUrl} download>
                <Download className="size-4" /> Baixar vídeo final
              </a>
            </Button>
          )}

          {!canGenerateReal && variants.length === 0 && (
            <div className="glass-panel flex flex-col gap-3 rounded-2xl border border-warning/30 p-4 text-sm">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
                <div>
                  <p className="font-medium">Pipeline bloqueado — modo produção desligado</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Geração de variantes reais exige worker, queue, FFmpeg, Whisper, storage e
                    callback ONLINE. Conecte o Worker Real para destravar o fluxo.
                  </p>
                  <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
                    <li>worker: <code>{workerStatus}</code></li>
                    <li>transcrição: <code>{hasTranscript ? "ok" : "—"}</code></li>
                    <li>ai_plan: <code>{aiPlan ? "ok" : "—"}</code></li>
                    <li>variantes: <code>{variants.length}</code></li>
                  </ul>
                </div>
              </div>
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  Modo dev · gerar 3 cards SIMULADOS (sem MP4 real)
                </summary>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2 w-full"
                  onClick={runSimulateNow}
                  disabled={simulating}
                >
                  {simulating ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <FlaskConical className="size-3.5" />
                  )}
                  Gerar 3 variantes SIMULADAS
                </Button>
              </details>
            </div>
          )}

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-lg font-semibold">3 variações editoriais</h2>
              {hasTranscript && job.status !== "RENDERING" && canGenerateReal && (
                <Button size="sm" onClick={runPlan} disabled={planning}>
                  {planning ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Wand2 className="size-3.5" />
                  )}
                  {variants.length > 0 ? "Refazer plano + render" : "Gerar Variantes Reais"}
                </Button>
              )}
            </div>
            {ready && variants.length === 0 ? (
              <div className="glass-panel flex flex-col items-center gap-3 rounded-2xl p-6 text-center">
                <AlertTriangle className="size-5 text-warning" />
                <div>
                  <p className="font-medium">Nenhuma variante renderizada encontrada</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    O job está pronto para revisão, mas o pipeline não gravou as 3 variantes.
                  </p>
                </div>
                {canGenerateReal && (
                  <Button size="sm" onClick={runPlan} disabled={planning}>
                    {planning ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Wand2 className="size-3.5" />
                    )}
                    Gerar variantes agora
                  </Button>
                )}
              </div>
            ) : (
              <VariantCards
                variants={variants}
                title={job.title_suggestion}
                hook={aiPlan?.hooks?.[0] ?? null}
                onApprove={runApprove}
                onEditCaption={runEditCaption}
                onRerender={runRerender}
                approvingId={approvingId}
                editingId={editingId}
                rerenderingId={rerenderingId}
              />
            )}
          </div>

          <div className="glass-panel rounded-2xl p-5">
            <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
              <FileText className="size-5 text-primary" /> Transcrição
            </h2>
            <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
              {job.transcript ?? "Sem transcrição. A legenda só pode vir de transcrição real."}
            </p>
          </div>

          <ViralIntelligencePanel
            intelligence={intelligence}
            status={intelligenceStatus}
            hasTranscript={hasTranscript}
            analyzing={analyzing}
            onAnalyze={runAnalysis}
          />

          <LogsPanel events={events} />
        </div>

        <div className="space-y-6">
          <div className="glass-panel rounded-2xl p-5">
            <div className="flex items-start justify-between gap-2">
              <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
                <Sparkles className="size-5 text-accent" /> Título sugerido
              </h2>
              <AiModeBadge mode={aiPlan?.mode ?? null} />
            </div>
            <p className="mt-2 text-sm">
              {job.title_suggestion ?? "Título indisponível"}
            </p>
            <div className="mt-4 flex items-center gap-3">
              <Gauge className="size-5 text-primary" />
              <div className="flex-1">
                <p className="text-xs text-muted-foreground">Virality score</p>
                <p className="font-display text-2xl font-semibold">
                  {job.virality_score ?? "—"}
                  {job.virality_score != null && (
                    <span className="text-sm text-muted-foreground"> / 100</span>
                  )}
                </p>
              </div>
            </div>
          </div>

          <ProviderHealthPanel items={health} />

          <PipelineHealthPanel
            onConnectWorker={() => {
              router.navigate({ to: "/settings/video-infrastructure" });
            }}
          />

          <div className="glass-panel rounded-2xl p-5">
            <h2 className="font-display text-lg font-semibold">Relatório técnico</h2>
            <dl className="mt-3 space-y-2 text-sm">
              {[
                ["Resolução", job.width && job.height ? `${job.width}×${job.height}` : "—"],
                ["Codec", (report.codec as string) ?? "—"],
                ["Duração", formatDuration(job.duration_seconds)],
                ["Cortes", report.cuts != null ? String(report.cuts) : "—"],
                ["Palavras legenda", report.subtitle_words != null ? String(report.subtitle_words) : "—"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="font-medium">{v}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="glass-panel rounded-2xl p-5">
            <h2 className="font-display text-lg font-semibold">Inteligência editorial</h2>
            <ul className="mt-3 space-y-1.5">
              {EDITORIAL_CAPABILITIES.map((cap) => {
                const state = editorialState(job, cap);
                return (
                  <li key={cap.name} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{cap.name}</span>
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                        EDITORIAL_STATE_STYLE[state],
                      )}
                    >
                      {state}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>

          {isDev && !job.simulated && job.status !== "READY_FOR_HUMAN_REVIEW" && (
            <div className="rounded-2xl border border-dashed border-accent/40 bg-accent/5 p-5">
              <p className="flex items-center gap-2 text-sm font-medium text-accent">
                <FlaskConical className="size-4" /> Modo desenvolvedor
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Simule o callback do worker para testar o fluxo. O resultado é claramente marcado
                como simulado.
              </p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={() => runSimulation("success")}>
                  Simular sucesso
                </Button>
                <Button size="sm" variant="outline" onClick={() => runSimulation("failure")}>
                  Simular falha
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 glass-panel rounded-2xl p-5">
        <h2 className="mb-3 font-display text-lg font-semibold">Pipeline</h2>
        <StageTimeline status={job.status} />
      </div>
    </AppShell>
  );
}
