import type { AiSegment, EditorialPlan, TimedText } from "./types.js";

export interface Edl {
  segments: AiSegment[];
  /** Soma dos trechos em tempo da fonte (antes de aceleração). */
  total_duration: number;
  notes: string[];
}

export const MIN_SEGMENT = 1.0;
export const MIN_TOTAL = 4.0;
const SNAP_WINDOW = 0.8;
const PAD = 0.12;

/**
 * Encaixa um tempo no limite de frase mais próximo do Whisper (dentro de SNAP_WINDOW).
 * Evita cortar no meio de palavra quando a IA estima o timecode.
 */
function snap(t: number, boundaries: number[]): number {
  let best = t;
  let dist = SNAP_WINDOW;
  for (const b of boundaries) {
    const d = Math.abs(b - t);
    if (d < dist) {
      dist = d;
      best = b;
    }
  }
  return best;
}

/**
 * Plano local (sem IA) e também rede de segurança: segue a ordem da fala, junta frases
 * próximas e descarta pausas longas, até atingir a duração alvo.
 */
export function heuristicSegments(
  speech: TimedText[],
  sourceDuration: number,
  maxTotal: number,
): AiSegment[] {
  if (speech.length === 0) {
    return [
      {
        start: 0,
        end: Math.min(sourceDuration, maxTotal),
        keep: true,
        reason: "sem frases com tempo; início do vídeo",
      },
    ];
  }
  const out: AiSegment[] = [];
  for (const s of speech) {
    const start = Math.max(0, s.start - PAD);
    const end = Math.min(sourceDuration, s.end + PAD);
    const last = out[out.length - 1];
    if (last && start - last.end <= 0.7) last.end = end;
    else out.push({ start, end, keep: true, reason: "fala contínua (pausas longas removidas)" });
  }
  return out;
}

/**
 * EDL à prova de falhas: valida/limita o que a IA propôs, encaixa nos limites de fala,
 * mantém a ordem pedida, junta sobreposições, corta pelo limite de duração e cai para a
 * heurística se sobrar pouco.
 */
export function buildEdl(
  plan: EditorialPlan,
  opts: { sourceDuration: number; maxTotal: number; speech: TimedText[] },
): Edl {
  const notes: string[] = [];
  const dur = opts.sourceDuration;
  // Início só encaixa em início de frase e fim só em fim de frase: com frases coladas, o
  // "início da próxima" fica antes do fim da atual e cortaria a última palavra.
  const starts = opts.speech.map((s) => Math.max(0, s.start - PAD));
  const ends = opts.speech.map((s) => Math.min(dur, s.end + PAD));

  let segs = plan.segments
    .filter((s) => s.keep && Number.isFinite(s.start) && Number.isFinite(s.end))
    .map((s) => {
      const start = Math.max(0, Math.min(snap(s.start, starts), dur));
      const end = Math.max(0, Math.min(snap(s.end, ends), dur));
      return { start, end, reason: s.reason || "—", keep: true };
    })
    .filter((s) => s.end - s.start >= MIN_SEGMENT)
    .sort((a, b) => a.start - b.start);

  const merged: AiSegment[] = [];
  for (const s of segs) {
    const last = merged[merged.length - 1];
    if (last && s.start <= last.end + 0.2) last.end = Math.max(last.end, s.end);
    else merged.push({ ...s });
  }
  segs = merged;

  const proposedTotal = segs.reduce((a, s) => a + (s.end - s.start), 0);
  if (proposedTotal < MIN_TOTAL) {
    if (plan.segments.length > 0)
      notes.push(
        `plano da IA inválido ou curto (${proposedTotal.toFixed(1)}s); usando heurística local`,
      );
    segs = heuristicSegments(opts.speech, dur, opts.maxTotal);
  }

  const capped: AiSegment[] = [];
  let total = 0;
  for (const s of segs) {
    const len = s.end - s.start;
    if (total + len > opts.maxTotal) {
      const allowed = opts.maxTotal - total;
      if (allowed >= MIN_SEGMENT) {
        // Termina no último limite de fala que cabe, para não cortar frase no meio.
        const inside = ends.filter((b) => b > s.start + MIN_SEGMENT && b <= s.start + allowed);
        const end = inside.length ? Math.max(...inside) : s.start + allowed;
        capped.push({ ...s, end });
        total += end - s.start;
      }
      notes.push(`limitado a ${opts.maxTotal}s`);
      break;
    }
    capped.push(s);
    total += len;
  }
  return { segments: capped, total_duration: total, notes };
}
