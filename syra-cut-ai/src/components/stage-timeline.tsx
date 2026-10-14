import { Check, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { PIPELINE_ORDER, STATUS_META, stageIndex, type VideoJobStatus } from "@/lib/syra";

export function StageTimeline({ status }: { status: VideoJobStatus }) {
  const failed = status === "FAILED";
  const current = stageIndex(status);

  return (
    <ol className="space-y-1">
      {PIPELINE_ORDER.map((stage, i) => {
        const meta = STATUS_META[stage];
        const done = !failed && current > i;
        const active = !failed && current === i;
        const isFinalReady = stage === "READY_FOR_HUMAN_REVIEW" && done;
        return (
          <li key={stage} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full ring-1 ring-inset transition-colors",
                  done || isFinalReady
                    ? "bg-success/15 text-success ring-success/40"
                    : active
                      ? "bg-primary/15 text-primary ring-primary/40"
                      : "bg-muted text-muted-foreground ring-border",
                )}
              >
                {done ? (
                  <Check className="size-3.5" />
                ) : active ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <span className="text-[11px] font-semibold">{i + 1}</span>
                )}
              </span>
              {i < PIPELINE_ORDER.length - 1 && (
                <span
                  className={cn("my-0.5 h-5 w-px", done ? "bg-success/40" : "bg-border")}
                />
              )}
            </div>
            <div className="pb-1">
              <p
                className={cn(
                  "text-sm font-medium leading-tight",
                  active ? "text-foreground" : done ? "text-foreground/80" : "text-muted-foreground",
                )}
              >
                {meta.label}
              </p>
              <p className="text-xs text-muted-foreground">{meta.description}</p>
            </div>
          </li>
        );
      })}
      {failed && (
        <li className="flex items-center gap-3 pt-1">
          <span className="flex size-7 items-center justify-center rounded-full bg-destructive/15 text-destructive ring-1 ring-inset ring-destructive/40">
            <X className="size-3.5" />
          </span>
          <p className="text-sm font-medium text-destructive">Pipeline interrompido (FAILED)</p>
        </li>
      )}
    </ol>
  );
}
