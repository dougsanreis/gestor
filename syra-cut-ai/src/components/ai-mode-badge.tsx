import { Activity, CheckCircle2, XCircle, MinusCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AiPipelineMode } from "@/lib/video/job-contract";

/** Compact AI Mode badge: FULL (Claude) · PARTIAL (Grok/Mistral) · FALLBACK (local). */
export function AiModeBadge({ mode }: { mode: AiPipelineMode | null | undefined }) {
  const resolved: AiPipelineMode = mode ?? "FALLBACK";
  const meta = {
    FULL: { label: "AI Mode · FULL", className: "bg-success/15 text-success", Icon: CheckCircle2 },
    PARTIAL: {
      label: "AI Mode · PARTIAL",
      className: "bg-warning/15 text-warning",
      Icon: MinusCircle,
    },
    FALLBACK: {
      label: "AI Mode · FALLBACK",
      className: "bg-muted text-muted-foreground",
      Icon: XCircle,
    },
  }[resolved];
  const Icon = meta.Icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-semibold",
        meta.className,
      )}
      title="Modo do roteador de IA (Claude → Grok → Mistral → Local)"
    >
      <Icon className="size-3" /> {meta.label}
    </span>
  );
}

export type ProviderStatus = "ONLINE" | "OFFLINE" | "DEGRADED" | "UNKNOWN";

export interface ProviderHealth {
  name: string;
  status: ProviderStatus;
  note?: string;
}

const STATUS_STYLE: Record<ProviderStatus, string> = {
  ONLINE: "bg-success/15 text-success",
  OFFLINE: "bg-destructive/15 text-destructive",
  DEGRADED: "bg-warning/15 text-warning",
  UNKNOWN: "bg-muted text-muted-foreground",
};

export function ProviderHealthPanel({ items }: { items: ProviderHealth[] }) {
  return (
    <div className="glass-panel rounded-2xl p-5">
      <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
        <Activity className="size-5 text-primary" /> Pipeline Health
      </h2>
      <ul className="mt-3 space-y-1.5">
        {items.map((it) => (
          <li key={it.name} className="flex items-center justify-between gap-2 text-sm">
            <div className="min-w-0">
              <span className="font-medium">{it.name}</span>
              {it.note && (
                <span className="ml-1 text-xs text-muted-foreground">· {it.note}</span>
              )}
            </div>
            <span
              className={cn(
                "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold",
                STATUS_STYLE[it.status],
              )}
            >
              {it.status}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
