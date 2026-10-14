import type { AiCaption, TimedText, Transcript } from "./types.js";

/**
 * Legenda só vem da transcrição real (contrato do app). Agrupa as palavras do Whisper em
 * blocos curtos para leitura no celular: até 4 palavras, até 1,8 s, quebrando em pausa > 0,45 s
 * ou pontuação final. Sem palavras com tempo, usa os segmentos do Whisper como estão.
 */
export function buildCaptions(
  t: Transcript,
  opts = { maxWords: 4, maxSeconds: 1.8, gap: 0.45 },
): AiCaption[] {
  const words = t.words.filter((w) => w.text.trim() && w.end > w.start);
  if (words.length === 0) {
    return t.segments
      .filter((s) => s.text.trim() && s.end > s.start)
      .map((s) => ({ start: s.start, end: s.end, text: s.text.trim() }));
  }
  const out: AiCaption[] = [];
  let cur: TimedText[] = [];
  const flush = () => {
    if (cur.length === 0) return;
    out.push({
      start: cur[0].start,
      end: cur[cur.length - 1].end,
      text: cur.map((w) => w.text.trim()).join(" "),
    });
    cur = [];
  };
  for (const w of words) {
    if (cur.length > 0) {
      const first = cur[0];
      const last = cur[cur.length - 1];
      const breakHere =
        cur.length >= opts.maxWords ||
        w.end - first.start > opts.maxSeconds ||
        w.start - last.end > opts.gap ||
        /[.!?…]$/.test(last.text.trim());
      if (breakHere) flush();
    }
    cur.push(w);
  }
  flush();
  return out;
}

/** Quantas palavras de legenda caem dentro dos trechos mantidos (para o technical_report). */
export function countWordsInSegments(
  words: TimedText[],
  segments: { start: number; end: number }[],
): number {
  return words.filter((w) =>
    segments.some((s) => w.start >= s.start - 0.05 && w.end <= s.end + 0.05),
  ).length;
}
