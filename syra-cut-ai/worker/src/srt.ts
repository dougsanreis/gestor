import type { TimedText, Transcript } from "./types.js";

function toSeconds(ts: string): number {
  const m = ts.trim().match(/^(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})$/);
  if (!m) return NaN;
  return (
    Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4].padEnd(3, "0")) / 1000
  );
}

/**
 * Lê legenda SRT ou WebVTT (CapCut, YouTube, Premiere…) como transcrição de frases.
 * Sem tempo por palavra: o pipeline distribui o tempo da frase entre as palavras.
 */
export function parseSubtitles(raw: string): Transcript {
  const segments: TimedText[] = [];
  const blocks = raw
    .replace(/\r/g, "")
    .replace(/^WEBVTT[^\n]*\n/, "")
    .split(/\n\s*\n/);
  for (const block of blocks) {
    const lines = block
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const i = lines.findIndex((l) => l.includes("-->"));
    if (i < 0) continue;
    const [a, b] = lines[i].split("-->");
    const start = toSeconds(a);
    const end = toSeconds(b.trim().split(/\s+/)[0]);
    const text = lines
      .slice(i + 1)
      .join(" ")
      .replace(/<[^>]+>/g, "")
      .replace(/\{[^}]*\}/g, "")
      .trim();
    if (Number.isFinite(start) && Number.isFinite(end) && end > start && text)
      segments.push({ start, end, text });
  }
  segments.sort((x, y) => x.start - y.start);
  return { text: segments.map((s) => s.text).join(" "), segments, words: [], provider: "subtitle" };
}
