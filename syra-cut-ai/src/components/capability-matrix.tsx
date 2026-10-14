import { cn } from "@/lib/utils";
import { CAPABILITY_MATRIX, type Capability, type CapabilityStatus } from "@/lib/syra";

const STATUS_STYLE: Record<CapabilityStatus, string> = {
  ACTIVE: "bg-success/15 text-success ring-success/30",
  CONFIG_REQUIRED: "bg-warning/15 text-warning ring-warning/30",
  PLANNED: "bg-muted text-muted-foreground ring-border",
  FAILED: "bg-destructive/15 text-destructive ring-destructive/30",
};

export function CapabilityMatrix({
  title = "Capability Matrix",
  subtitle = "Estado real de cada capacidade — nada é marcado como pronto sem evidência.",
  rows = CAPABILITY_MATRIX,
}: {
  title?: string;
  subtitle?: string;
  rows?: Capability[];
}) {
  return (
    <div className="glass-panel overflow-hidden rounded-2xl">
      <div className="border-b border-border px-5 py-4">
        <h2 className="font-display text-lg font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-5 py-3 font-medium">Capacidade</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Evidência</th>
              <th className="px-5 py-3 font-medium">Artefato</th>
              <th className="px-5 py-3 font-medium">Prioridade</th>
              <th className="px-5 py-3 font-medium">ROI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.name} className="border-t border-border/60">
                <td className="px-5 py-3 font-medium">{c.name}</td>
                <td className="px-5 py-3">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset",
                      STATUS_STYLE[c.status],
                    )}
                  >
                    {c.status}
                  </span>
                </td>
                <td className="px-5 py-3 text-muted-foreground">{c.evidence}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted-foreground">{c.artifact}</td>
                <td className="px-5 py-3 text-muted-foreground">{c.priority}</td>
                <td className="px-5 py-3 text-muted-foreground">{c.roi}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
