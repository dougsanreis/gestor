import { useRef, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { UploadCloud, Loader2, AlertTriangle, FileVideo } from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { dispatchVideoJob } from "@/lib/video-jobs.functions";
import { UPLOAD_LIMITS, formatBytes } from "@/lib/syra";

export const Route = createFileRoute("/_authenticated/upload")({
  head: () => ({ meta: [{ title: "Enviar vídeo — SYRA VideoOS" }] }),
  component: UploadPage,
});

function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(video.duration) ? video.duration : null);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    video.src = url;
  });
}

function UploadPage() {
  const navigate = useNavigate();
  const dispatch = useServerFn(dispatchVideoJob);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");

  async function handleFile(file: File) {
    const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
    if (
      !UPLOAD_LIMITS.acceptedTypes.includes(file.type) &&
      !UPLOAD_LIMITS.acceptedExtensions.includes(ext)
    ) {
      toast.error("Formato inválido. Use MP4, MOV ou WebM.");
      return;
    }
    if (file.size > UPLOAD_LIMITS.maxSizeBytes) {
      toast.error(`Arquivo acima de ${UPLOAD_LIMITS.maxSizeLabel}.`);
      return;
    }

    setBusy(true);
    try {
      setStage("Lendo metadados…");
      const duration = await readDuration(file);
      if (duration && duration > UPLOAD_LIMITS.maxDurationSeconds) {
        toast.error("Vídeo muito longo. Limite do MVP: 3 minutos.");
        setBusy(false);
        return;
      }

      const { data: userData } = await supabase.auth.getUser();
      const userId = userData.user?.id;
      if (!userId) throw new Error("Sessão expirada. Entre novamente.");

      const jobId = crypto.randomUUID();
      const cleanExt = ext.replace(".", "") || "mp4";
      const path = `${userId}/${jobId}/source.${cleanExt}`;

      setStage("Enviando para o storage…");
      const { error: upErr } = await supabase.storage
        .from("source-videos")
        .upload(path, file, { contentType: file.type || "video/mp4", upsert: false });
      if (upErr) throw upErr;

      setStage("Criando job…");
      const { error: insErr } = await supabase.from("video_jobs").insert({
        id: jobId,
        user_id: userId,
        source_file_path: path,
        source_file_name: file.name,
        source_file_size: file.size,
        duration_seconds: duration ?? null,
        status: "UPLOADED",
        progress: 0,
      });
      if (insErr) throw insErr;

      await supabase.from("video_job_events").insert({
        job_id: jobId,
        event_type: "UPLOADED",
        message: `Arquivo ${file.name} (${formatBytes(file.size)}) salvo no storage.`,
      });

      setStage("Acionando pipeline…");
      const result = await dispatch({ data: { jobId } });
      if (result && "configured" in result && !result.configured) {
        toast.info("Job criado. Worker externo ainda não configurado — use a simulação no detalhe.");
      } else {
        toast.success("Job criado e pipeline acionado.");
      }

      navigate({ to: "/jobs/$jobId", params: { jobId } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha no upload.");
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl">
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">Enviar vídeo</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Aceitamos MP4, MOV e WebM. Limite do MVP: {UPLOAD_LIMITS.maxSizeLabel} ou 3 minutos.
        </p>

        <div className="mt-4 flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>Para melhor performance, use vídeos curtos.</span>
        </div>

        <div
          role="button"
          tabIndex={0}
          onClick={() => !busy && inputRef.current?.click()}
          onKeyDown={(e) => e.key === "Enter" && !busy && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (busy) return;
            const file = e.dataTransfer.files?.[0];
            if (file) handleFile(file);
          }}
          className={cn(
            "mt-6 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-border p-12 text-center transition-colors",
            dragging && "border-primary bg-primary/5",
            busy && "pointer-events-none opacity-70",
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
          {busy ? (
            <>
              <Loader2 className="size-10 animate-spin text-primary" />
              <p className="mt-4 font-medium">{stage}</p>
              <p className="text-sm text-muted-foreground">Não feche esta aba.</p>
            </>
          ) : (
            <>
              <span className="flex size-14 items-center justify-center rounded-2xl bg-primary/15 text-primary">
                <UploadCloud className="size-7" />
              </span>
              <p className="mt-4 font-medium">Arraste seu vídeo aqui</p>
              <p className="text-sm text-muted-foreground">ou clique para selecionar</p>
              <Button className="mt-5" type="button">
                <FileVideo className="size-4" /> Escolher arquivo
              </Button>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
