import { MAX_CLIPS, type VariantPreset } from "./presets.js";
import type { Interval } from "./scene-analysis.js";
import type { TimedText } from "./types.js";

/** Trecho da fonte que entra no vídeo final, na ordem de exibição. */
export interface Clip {
  start: number;
  end: number;
  /** Enquadramento ampliado (punch-in) neste trecho. */
  punch: boolean;
  /** Flash branco curto na entrada (depois do gancho). */
  flashIn: boolean;
  /** Trecho do gancho (cold open), repetido no começo. */
  hook: boolean;
}

const MIN_CLIP = 0.35;
export const MIN_HOOK_DISTANCE = 6;
const WORD_PAD = 0.06;

/** Remove de cada trecho as partes que caem em intervalos inutilizáveis (giro, borrão). */
export function subtractIntervals<T extends Interval>(segments: T[], bad: Interval[]): T[] {
  let out = segments.map((s) => ({ ...s }));
  for (const b of bad) {
    const next: T[] = [];
    for (const s of out) {
      if (b.end <= s.start || b.start >= s.end) {
        next.push(s);
        continue;
      }
      if (b.start - s.start >= MIN_CLIP) next.push({ ...s, end: b.start });
      if (s.end - b.end >= MIN_CLIP) next.push({ ...s, start: b.end });
    }
    out = next;
  }
  return out;
}

/**
 * Jump cuts: dentro de cada trecho, corta as pausas entre palavras maiores que `maxGap`.
 * Mantém um respiro de WORD_PAD em volta das palavras para não comer consoante.
 */
export function tightenByWords(
  segments: Interval[],
  words: TimedText[],
  maxGap: number,
): Interval[] {
  const out: Interval[] = [];
  for (const seg of segments) {
    const inside = words.filter((w) => w.end > seg.start && w.start < seg.end);
    if (inside.length === 0) {
      out.push({ ...seg });
      continue;
    }
    let curStart = Math.max(seg.start, inside[0].start - WORD_PAD * 2);
    let curEnd = Math.min(seg.end, inside[0].end + WORD_PAD);
    for (const w of inside.slice(1)) {
      const ws = Math.max(seg.start, w.start - WORD_PAD);
      const we = Math.min(seg.end, w.end + WORD_PAD);
      if (ws - curEnd > maxGap) {
        out.push({ start: curStart, end: curEnd });
        curStart = ws;
      }
      curEnd = Math.max(curEnd, we);
    }
    out.push({ start: curStart, end: Math.min(seg.end, curEnd + WORD_PAD) });
  }
  return out.filter((s) => s.end - s.start >= MIN_CLIP);
}

/** Se passar de MAX_CLIPS, junta os vizinhos com a menor pausa entre eles. */
export function capClips(clips: Interval[], max = MAX_CLIPS): Interval[] {
  const out = clips.map((c) => ({ ...c }));
  while (out.length > max) {
    let best = -1;
    let bestGap = Infinity;
    for (let i = 0; i < out.length - 1; i++) {
      const gap = out[i + 1].start - out[i].end;
      if (gap >= 0 && gap < bestGap) {
        bestGap = gap;
        best = i;
      }
    }
    if (best < 0) break;
    out[best].end = out[best + 1].end;
    out.splice(best + 1, 1);
  }
  return out;
}

/**
 * Valida o gancho proposto pela IA: 1,2–4,5 s, dentro do vídeo, fora de trechos ruins,
 * encaixado em início/fim de palavra.
 */
export function validateHook(
  hook: Interval | null | undefined,
  opts: { duration: number; words: TimedText[]; bad: Interval[] },
): Interval | null {
  if (!hook || !Number.isFinite(hook.start) || !Number.isFinite(hook.end)) return null;
  const firstWord = opts.words.find((w) => w.end > hook.start + 0.05);
  const lastWord = [...opts.words].reverse().find((w) => w.start < hook.end - 0.05);
  if (!firstWord || !lastWord) return null;
  const start = Math.max(0, firstWord.start - WORD_PAD);
  const end = Math.min(opts.duration, lastWord.end + WORD_PAD);
  const len = end - start;
  if (len < 1.2 || len > 4.5) return null;
  if (opts.bad.some((b) => b.start < end && b.end > start)) return null;
  return { start, end };
}

/**
 * Linha do tempo final de uma variante: (gancho) + trechos da EDL sem partes ruins, com
 * jump cuts e punch-in alternado.
 */
export function buildTimeline(opts: {
  segments: Interval[];
  words: TimedText[];
  bad: Interval[];
  hook: Interval | null;
  preset: VariantPreset;
}): Clip[] {
  const clean = subtractIntervals(opts.segments, opts.bad);
  const tight = capClips(tightenByWords(clean, opts.words, opts.preset.maxGap));
  const clips: Clip[] = [];
  // Gancho só vale se vier de mais adiante: se a melhor frase já está nos primeiros segundos,
  // o próprio começo é o gancho e repetir a fala logo em seguida soa como erro de edição.
  const hookUseful =
    opts.hook && tight.length > 0 && opts.hook.start - tight[0].start >= MIN_HOOK_DISTANCE;
  if (opts.preset.hook && opts.hook && hookUseful) {
    clips.push({ ...opts.hook, punch: true, flashIn: false, hook: true });
  }
  tight.forEach((c, i) => {
    clips.push({
      start: c.start,
      end: c.end,
      punch: opts.preset.punchIn && i % 2 === 1,
      flashIn: i === 0 && clips.length > 0,
      hook: false,
    });
  });
  return clips;
}

export function timelineDuration(clips: Interval[]): number {
  return clips.reduce((a, c) => a + (c.end - c.start), 0);
}
