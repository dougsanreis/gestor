import {
  Brain,
  Loader2,
  Sparkles,
  Zap,
  Share2,
  Fingerprint,
  Gauge,
  Activity,
  Scissors,
  FlaskConical,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  EMOTION_META,
  type EmotionKind,
  type IntelligenceStatus,
  type ViralIntelligence,
} from "@/lib/syra";

const PACE_LABEL: Record<string, string> = {
  slow: "lento (respira)",
  medium: "médio",
  fast: "rápido (acelera)",
  explosive: "explosivo (clímax)",
  pause: "pausa (identidade)",
};

const MOMENT_LABEL: Record<string, string> = {
  status_change: "Mudança de status",
  expectation_break: "Quebra de expectativa",
  shareable_line: "Frase replicável",
};

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{value}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}

function NarrativeRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-primary">{label}</p>
      <p className="mt-0.5 text-sm text-foreground/90">{value}</p>
    </div>
  );
}

export function ViralIntelligencePanel({
  intelligence,
  status,
  hasTranscript,
  analyzing,
  onAnalyze,
}: {
  intelligence: ViralIntelligence | null;
  status: IntelligenceStatus;
  hasTranscript: boolean;
  analyzing: boolean;
  onAnalyze: () => void;
}) {
  const running = analyzing || status === "ANALYZING";

  return (
    <div className="glass-panel overflow-hidden rounded-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
            <Brain className="size-5 text-accent" /> Viral Intelligence
            {status === "SIMULATED" && (
              <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
                SIMULADO
              </span>
            )}
          </h2>
          <p className="text-sm text-muted-foreground">
            Narrativa → emoção → identidade → retenção. Analisado antes da edição.
          </p>
        </div>
        <Button size="sm" onClick={onAnalyze} disabled={running || !hasTranscript}>
          {running ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {intelligence ? "Reanalisar" : "Analisar inteligência viral"}
        </Button>
      </div>

      <div className="p-5">
        {!hasTranscript ? (
          <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            A inteligência narrativa só roda sobre <strong>transcrição real</strong>. Conclua a
            transcrição (worker STT) ou use a simulação para testar o fluxo.
          </div>
        ) : status === "FAILED" ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            A última análise falhou. Tente novamente.
          </div>
        ) : !intelligence ? (
          <div className="rounded-xl border border-dashed border-accent/40 bg-accent/5 p-6 text-center">
            <FlaskConical className="mx-auto size-7 text-accent" />
            <p className="mt-2 text-sm font-medium">Inteligência ainda não gerada</p>
            <p className="text-sm text-muted-foreground">
              Rode a análise para mapear narrativa, emoção, identidade e score viral V2.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Viral Score V2 */}
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <Gauge className="size-4 text-primary" /> Viral Score V2
                </h3>
                <div className="text-right">
                  <span className="font-display text-3xl font-semibold text-gradient">
                    {intelligence.scores.viral_score}
                  </span>
                  <span className="text-sm text-muted-foreground"> /100</span>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <ScoreBar label="Curiosity" value={intelligence.scores.curiosity} />
                <ScoreBar label="Tension" value={intelligence.scores.tension} />
                <ScoreBar label="Transformation" value={intelligence.scores.transformation} />
                <ScoreBar label="Identity" value={intelligence.scores.identity} />
                <ScoreBar label="Share" value={intelligence.scores.share} />
                <ScoreBar label="Replay" value={intelligence.scores.replay} />
              </div>
            </div>

            {/* Narrative graph */}
            <div>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="size-4 text-accent" /> Narrative Graph
              </h3>
              <div className="grid gap-2 sm:grid-cols-2">
                <NarrativeRow label="Herói" value={intelligence.narrative.hero} />
                <NarrativeRow label="Problema" value={intelligence.narrative.problem} />
                <NarrativeRow label="Pressão" value={intelligence.narrative.pressure} />
                <NarrativeRow label="Decisão" value={intelligence.narrative.decision} />
                <NarrativeRow label="Transformação" value={intelligence.narrative.transformation} />
                <NarrativeRow label="Prova" value={intelligence.narrative.proof} />
                <div className="sm:col-span-2">
                  <NarrativeRow label="Lenda" value={intelligence.narrative.legend} />
                </div>
              </div>
            </div>

            {/* Emotion graph */}
            {intelligence.emotion_timeline.length > 0 && (
              <div>
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <Activity className="size-4 text-primary" /> Emotion Graph
                </h3>
                <div className="flex h-3 w-full overflow-hidden rounded-full">
                  {(() => {
                    const total =
                      Math.max(...intelligence.emotion_timeline.map((s) => s.end)) || 1;
                    return intelligence.emotion_timeline.map((seg, i) => (
                      <div
                        key={i}
                        title={`${EMOTION_META[seg.emotion]?.label ?? seg.emotion} (${seg.start}-${seg.end}s)`}
                        style={{
                          width: `${((seg.end - seg.start) / total) * 100}%`,
                          backgroundColor: EMOTION_META[seg.emotion]?.color ?? "var(--muted)",
                        }}
                      />
                    ));
                  })()}
                </div>
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                  {Array.from(new Set(intelligence.emotion_timeline.map((s) => s.emotion))).map(
                    (em) => (
                      <span key={em} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <span
                          className="size-2 rounded-full"
                          style={{ backgroundColor: EMOTION_META[em as EmotionKind]?.color }}
                        />
                        {EMOTION_META[em as EmotionKind]?.label ?? em}
                      </span>
                    ),
                  )}
                </div>
              </div>
            )}

            {/* Identity + Share */}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-border/60 bg-background/40 p-4">
                <p className="flex items-center gap-2 text-sm font-semibold">
                  <Fingerprint className="size-4 text-accent" /> Identity Engine
                </p>
                <p className="mt-1 font-display text-lg font-semibold capitalize">
                  {intelligence.identity.archetype}
                </p>
                <p className="text-xs text-muted-foreground">{intelligence.identity.rationale}</p>
              </div>
              <div className="rounded-xl border border-border/60 bg-background/40 p-4">
                <p className="flex items-center gap-2 text-sm font-semibold">
                  <Share2 className="size-4 text-primary" /> Share Engine
                </p>
                <p className="mt-1 font-display text-lg font-semibold capitalize">
                  {intelligence.share.reason}
                </p>
                <p className="text-xs text-muted-foreground">{intelligence.share.explanation}</p>
              </div>
            </div>

            {/* Viral moments */}
            {intelligence.viral_moments.length > 0 && (
              <div>
                <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                  <Zap className="size-4 text-warning" /> Viral Moments
                </h3>
                <ul className="space-y-2">
                  {intelligence.viral_moments.map((m, i) => (
                    <li key={i} className="rounded-lg border border-border/60 bg-background/40 p-3">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-semibold text-warning">
                          {MOMENT_LABEL[m.type] ?? m.type}
                        </span>
                        <span className="text-sm font-medium">{m.label}</span>
                      </div>
                      {m.quote && (
                        <p className="mt-1 text-sm italic text-muted-foreground">“{m.quote}”</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Rhythm */}
            {intelligence.rhythm.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-semibold">Rhythm Engine</h3>
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  {intelligence.rhythm.map((r, i) => (
                    <span key={i} className="flex items-center gap-1.5">
                      <span className="rounded-md bg-muted px-2 py-1">
                        <span className="font-medium">{r.phase}</span>
                        <span className="text-muted-foreground"> · {PACE_LABEL[r.pace] ?? r.pace}</span>
                      </span>
                      {i < intelligence.rhythm.length - 1 && (
                        <span className="text-muted-foreground">→</span>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Editorial plan */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Scissors className="size-4 text-primary" /> Editorial Master Plan
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                {(
                  [
                    ["Cortes", intelligence.editorial_plan.cuts],
                    ["Zooms", intelligence.editorial_plan.zooms],
                    ["Captions", intelligence.editorial_plan.captions],
                    ["CTA", intelligence.editorial_plan.cta],
                  ] as const
                ).map(([label, items]) => (
                  <div key={label} className="rounded-lg border border-border/60 bg-background/40 p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {label}
                    </p>
                    <ul className="mt-1 space-y-0.5">
                      {items.length === 0 ? (
                        <li className="text-xs text-muted-foreground">—</li>
                      ) : (
                        items.map((it, i) => (
                          <li key={i} className={cn("text-sm text-foreground/90")}>
                            • {it}
                          </li>
                        ))
                      )}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
