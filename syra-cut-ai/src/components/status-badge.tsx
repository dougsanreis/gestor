import { cn } from "@/lib/utils";
import { statusMeta, type VideoJobStatus, type StatusTone } from "@/lib/syra";

const TONE_CLASSES: Record<StatusTone, string> = {
  neutral: "bg-muted text-muted-foreground ring-border",
  info: "bg-primary/15 text-primary ring-primary/30",
  accent: "bg-accent/15 text-accent ring-accent/30",
  success: "bg-success/15 text-success ring-success/30",
  danger: "bg-destructive/15 text-destructive ring-destructive/30",
};

export function StatusBadge({
  status,
  className,
  pulse,
}: {
  status: VideoJobStatus;
  className?: string;
  pulse?: boolean;
}) {
  const meta = statusMeta(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset",
        TONE_CLASSES[meta.tone],
        className,
      )}
    >
      {pulse && (
        <span
          className={cn(
            "size-1.5 rounded-full bg-current",
            meta.tone === "success" ? "" : "animate-pulse",
          )}
        />
      )}
      {meta.label}
    </span>
  );
}
