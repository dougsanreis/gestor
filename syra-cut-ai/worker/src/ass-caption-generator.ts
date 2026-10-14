import { writeFile } from "node:fs/promises";
import type { CaptionStyle } from "./presets.js";
import type { Clip } from "./timeline.js";
import type { TimedText } from "./types.js";

export type { CaptionStyle };

/** Fonte com fallback: o libass usa fontconfig e cai na próxima disponível se Inter faltar. */
const FONT = process.env.CAPTION_FONT || "Inter";

/**
 * Posição: MarginV a partir de baixo. A UI do TikTok/Reels/Shorts cobre ~25% inferiores
 * (descrição, botões); 560 px em 1920 coloca a legenda no terço inferior, acima dela.
 */
const MARGIN_V = 560;
const MARGIN_H = 110;

interface StyleDef {
  name: string;
  size: number;
  bold: number;
  outline: number;
  shadow: number;
  upper: boolean;
  maxWords: number;
  /** Cor da palavra falada no momento (ASS = &HBBGGRR&). null = sem destaque. */
  highlight: string | null;
}

const STYLES: Record<CaptionStyle, StyleDef> = {
  karaoke: {
    name: "Karaoke",
    size: 58,
    bold: -1,
    outline: 5,
    shadow: 0,
    upper: true,
    maxWords: 3,
    highlight: "&H0000D7FF&",
  },
  dynamic: {
    name: "Dynamic",
    size: 58,
    bold: -1,
    outline: 5,
    shadow: 0,
    upper: true,
    maxWords: 2,
    highlight: "&H006EFF3C&",
  },
  clean: {
    name: "Clean",
    size: 48,
    bold: 0,
    outline: 3,
    shadow: 1,
    upper: false,
    maxWords: 5,
    highlight: null,
  },
};

function header(style: CaptionStyle): string {
  const s = STYLES[style];
  return `[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ${s.name},${FONT},${s.size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,${s.bold},0,0,0,100,100,1,0,1,${s.outline},${s.shadow},2,${MARGIN_H},${MARGIN_H},${MARGIN_V},1
Style: Title,${FONT},60,&H00FFFFFF,&H000000FF,&H00000000,&H28000000,-1,0,0,0,100,100,0,0,3,18,0,8,90,90,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
`;
}

export function fmtTime(s: number): string {
  const totalCs = Math.max(0, Math.round(s * 100));
  const h = Math.floor(totalCs / 360000);
  const m = Math.floor((totalCs % 360000) / 6000);
  const sec = Math.floor((totalCs % 6000) / 100);
  const cs = totalCs % 100;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
}

/**
 * Texto vem da fala transcrita (dado não confiável): remove quebras, chaves e barras
 * invertidas para não virar tag de override do ASS.
 */
export function escapeText(t: string): string {
  return t
    .replace(/\r?\n/g, " ")
    .replace(/[{}]/g, "")
    .replace(/\\/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Palavras da transcrição remapeadas para o tempo do vídeo final, trecho a trecho. */
export function remapWords(words: TimedText[], clips: Clip[]): TimedText[][] {
  const perClip: TimedText[][] = [];
  let offset = 0;
  for (const c of clips) {
    const inside = words
      .filter((w) => {
        const mid = (w.start + w.end) / 2;
        return mid >= c.start && mid <= c.end;
      })
      .map((w) => ({
        start: offset + Math.max(0, w.start - c.start),
        end: offset + Math.min(c.end - c.start, w.end - c.start),
        text: escapeText(w.text),
      }))
      .filter((w) => w.text && w.end > w.start);
    perClip.push(inside);
    offset += c.end - c.start;
  }
  return perClip;
}

/** Blocos curtos (2–5 palavras), quebrando em pausa e pontuação; nunca atravessam um corte. */
export function chunkWords(words: TimedText[], maxWords: number, gap = 0.4): TimedText[][] {
  const chunks: TimedText[][] = [];
  let cur: TimedText[] = [];
  for (const w of words) {
    const last = cur[cur.length - 1];
    if (
      cur.length &&
      (cur.length >= maxWords || w.start - last.end > gap || /[.!?…,;:]$/.test(last.text))
    ) {
      chunks.push(cur);
      cur = [];
    }
    cur.push(w);
  }
  if (cur.length) chunks.push(cur);
  return chunks;
}

function wrapTitle(t: string, perLine = 20): string {
  const words = escapeText(t).toUpperCase().split(" ");
  const lines: string[] = [];
  let line = "";
  for (const w of words) {
    if (line && (line + " " + w).length > perLine) {
      lines.push(line);
      line = w;
    } else line = line ? `${line} ${w}` : w;
  }
  if (line) lines.push(line);
  return lines.slice(0, 3).join("\\N");
}

export function buildAssEvents(opts: {
  style: CaptionStyle;
  words: TimedText[];
  clips: Clip[];
  title?: string | null;
}): string[] {
  const s = STYLES[opts.style];
  const events: string[] = [];
  const fmt = (w: string) => (s.upper ? w.toUpperCase() : w);
  for (const clipWords of remapWords(opts.words, opts.clips)) {
    const chunks = chunkWords(clipWords, s.maxWords);
    chunks.forEach((chunk, ci) => {
      const next = chunks[ci + 1];
      // Segura o bloco até o próximo começar (se perto) para a legenda não piscar.
      const chunkEnd =
        next && next[0].start - chunk[chunk.length - 1].end < 0.3
          ? next[0].start
          : chunk[chunk.length - 1].end + 0.08;
      if (!s.highlight) {
        events.push(
          `Dialogue: 0,${fmtTime(chunk[0].start)},${fmtTime(chunkEnd)},${s.name},,0,0,0,,{\\fad(60,40)}${chunk.map((w) => fmt(w.text)).join(" ")}`,
        );
        return;
      }
      chunk.forEach((w, wi) => {
        const end = wi < chunk.length - 1 ? chunk[wi + 1].start : chunkEnd;
        if (end - w.start < 0.04) return;
        const text = chunk
          .map((x, xi) =>
            xi === wi ? `{\\c${s.highlight}\\fscx108\\fscy108}${fmt(x.text)}{\\r}` : fmt(x.text),
          )
          .join(" ");
        const pop = wi === 0 ? "{\\fscx92\\fscy92\\t(0,90,\\fscx100\\fscy100)}" : "";
        events.push(
          `Dialogue: 0,${fmtTime(w.start)},${fmtTime(end)},${s.name},,0,0,0,,${pop}${text}`,
        );
      });
    });
  }
  if (opts.title) {
    const hook = opts.clips[0]?.hook ? opts.clips[0].end - opts.clips[0].start : 0;
    const end = Math.max(2.4, Math.min(3.5, hook + 0.4));
    events.push(
      `Dialogue: 1,${fmtTime(0.1)},${fmtTime(end)},Title,,0,0,0,,{\\fad(90,160)\\fscx85\\fscy85\\t(0,140,\\fscx100\\fscy100)}${wrapTitle(opts.title)}`,
    );
  }
  return events;
}

export async function writeAss(opts: {
  outPath: string;
  style: CaptionStyle;
  words: TimedText[];
  clips: Clip[];
  title?: string | null;
}): Promise<number> {
  const events = buildAssEvents(opts);
  await writeFile(opts.outPath, header(opts.style) + events.join("\n") + "\n", "utf8");
  return events.length;
}
