import { useEffect } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Film, Loader2, CheckCircle2, AlertTriangle, ArrowRight, Upload } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import {
  type VideoJob,
  isProcessing,
  formatDuration,
  formatBytes,
} from "@/lib/syra";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({ meta: [{ title: "Dashboard — SYRA VideoOS" }] }),
  component: Dashboard,
});

async function fetchJobs(): Promise<VideoJob[]> {
  const { data, error } = await supabase
    .from("video_jobs")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw error;
  return data ?? [];
}

function Dashboard() {
  const router = useRouter();
  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["video_jobs"],
    queryFn: fetchJobs,
  });

  useEffect(() => {
    const channel = supabase
      .channel("dashboard-jobs")
      .on("postgres_changes", { event: "*", schema: "public", table: "video_jobs" }, () => {
        router.invalidate();
      })
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [router]);

  const total = jobs.length;
  const processing = jobs.filter((j) => isProcessing(j.status)).length;
  const ready = jobs.filter((j) => j.status === "READY_FOR_HUMAN_REVIEW").length;
  const failed = jobs.filter((j) => j.status === "FAILED").length;

  const stats = [
    { label: "Total de vídeos", value: total, icon: Film, tone: "text-foreground" },
    { label: "Em processamento", value: processing, icon: Loader2, tone: "text-primary" },
    { label: "Prontos p/ revisão", value: ready, icon: CheckCircle2, tone: "text-success" },
    { label: "Falhas", value: failed, icon: AlertTriangle, tone: "text-destructive" },
  ];

  return (
    <AppShell>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold sm:text-3xl">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Acompanhe todos os seus jobs de vídeo.</p>
        </div>
        <Button asChild>
          <Link to="/upload">
            <Upload className="size-4" /> Enviar vídeo
          </Link>
        </Button>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="glass-panel rounded-2xl p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{s.label}</span>
              <s.icon className={`size-5 ${s.tone}`} />
            </div>
            <p className="mt-3 font-display text-3xl font-semibold">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-8">
        <h2 className="mb-3 font-display text-lg font-semibold">Jobs recentes</h2>
        {isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Carregando…
          </div>
        ) : jobs.length === 0 ? (
          <div className="glass-panel rounded-2xl p-10 text-center">
            <Film className="mx-auto size-8 text-muted-foreground" />
            <p className="mt-3 font-medium">Nenhum job ainda</p>
            <p className="text-sm text-muted-foreground">Envie seu primeiro vídeo para começar.</p>
            <Button asChild className="mt-4">
              <Link to="/upload">
                <Upload className="size-4" /> Enviar vídeo
              </Link>
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <Link
                key={job.id}
                to="/jobs/$jobId"
                params={{ jobId: job.id }}
                className="glass-panel flex items-center gap-4 rounded-xl p-4 transition-colors hover:border-primary/40"
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <Film className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">
                    {job.source_file_name ?? "Vídeo sem nome"}
                    {job.simulated && (
                      <span className="ml-2 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
                        SIMULADO
                      </span>
                    )}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {formatBytes(job.source_file_size)} · {formatDuration(job.duration_seconds)} ·{" "}
                    {new Date(job.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {isProcessing(job.status) && (
                    <span className="hidden text-xs text-muted-foreground sm:inline">
                      {job.progress}%
                    </span>
                  )}
                  <StatusBadge status={job.status} pulse={isProcessing(job.status)} />
                  <ArrowRight className="size-4 text-muted-foreground" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
