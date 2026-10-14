import { useState } from "react";
import { ChevronDown, Terminal } from "lucide-react";
import { cn } from "@/lib/utils";
import type { VideoJobEvent } from "@/lib/syra";

const TYPE_COLORS: Record<string, string> = {
  FAILED: "text-destructive",
  CONFIG_REQUIRED: "text-warning",
  SIMULATED_CALLBACK: "text-accent",
  WORKER_DISPATCHED: "text-primary",
  READY_FOR_HUMAN_REVIEW: "text-success",
};

export function LogsPanel({ events }: { events: VideoJobEvent[] }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="glass-panel overflow-hidden rounded-xl">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          <Terminal className="size-4 text-primary" />
          Logs técnicos
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {events.length}
          </span>
        </span>
        <ChevronDown
          className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="max-h-80 overflow-y-auto border-t border-border bg-background/40 p-4 font-mono text-xs">
          {events.length === 0 ? (
            <p className="text-muted-foreground">Nenhum evento registrado ainda.</p>
          ) : (
            <ul className="space-y-2">
              {events.map((e) => (
                <li key={e.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="text-muted-foreground">
                    {new Date(e.created_at).toLocaleTimeString()}
                  </span>
                  <span className={cn("font-semibold", TYPE_COLORS[e.event_type] ?? "text-foreground")}>
                    [{e.event_type}]
                  </span>
                  <span className="text-foreground/80">{e.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
