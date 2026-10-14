import { writeFile } from "node:fs/promises";
import type { AiCaption } from "./types.js";

export type CaptionStyle = "kinetic" | "clean" | "dynamic";

/** Fonte com fallback: o libass usa fontconfig e cai na próxima disponível se Inter faltar. */
const FONT = process.env.CAPTION_FONT || "Inter";

/**
 * MarginV = distância da borda de baixo. TikTok/Reels/Shorts cobrem ~ os 20% inferiores
 * (legenda do post, botões); 420 px em 1920 mantém o texto acima dessa faixa.
 */
const SAFE_MARGIN_V = 420;
const SAFE_MARGIN_H = 90;

const STYLES: Record<
  CaptionStyle,
  { name: string; fontSize: number; primary: string; bold: number; outline: number; shadow: number }
> = {
  kinetic: {
    name: "Kinetic",
    fontSize: 84,
    primary: "&H00FFFFFF",
    bold: -1,
    outline: 5,
    shadow: 1,
  },
  clean: { name: "Clean", fontSize: 64, primary: "&H00FFFFFF", bold: 0, outline: 3, shadow: 0 },
  dynamic: {
    name: "Dynamic",
    fontSize: 76,
    primary: "&H0000F0FF",
    bold: -1,
    outline: 4,
    shadow: 1,
  },
};

const FX: Record<CaptionStyle, string> = {
  kinetic: "{\\fad(80,80)\\t(0,120,\\fscx115\\fscy115)\\t(120,260,\\fscx100\\fscy100)}",
  dynamic: "{\\fad(60,60)\\t(0,160,\\fscx108\\fscy108)\\t(160,300,\\fscx100\\fscy100)}",
  clean: "{\\fad(120,120)}",
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
Style: ${s.name},${FONT},${s.fontSize},${s.primary},&H000000FF,&H00000000,&H64000000,${s.bold},0,0,0,100,100,0,0,1,${s.outline},${s.shadow},2,${SAFE_MARGIN_H},${SAFE_MARGIN_H},${SAFE_MARGIN_V},1

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

/**
 * Remapeia as legendas (tempo da fonte) para a linha do tempo pós-corte (concatenação dos
 * trechos mantidos, na ordem da EDL).
 */
export function buildAssEvents(
  style: CaptionStyle,
  captions: AiCaption[],
  segments: { start: number; end: number }[],
): string[] {
  const name = STYLES[style].name;
  const events: string[] = [];
  let offset = 0;
  for (const seg of segments) {
    for (const c of captions) {
      const cs = Math.max(c.start, seg.start);
      const ce = Math.min(c.end, seg.end);
      if (ce - cs < 0.2) continue;
      const text = escapeText(c.text);
      if (!text) continue;
      events.push(
        `Dialogue: 0,${fmtTime(offset + (cs - seg.start))},${fmtTime(offset + (ce - seg.start))},${name},,0,0,0,,${FX[style]}${text}`,
      );
    }
    offset += seg.end - seg.start;
  }
  return events;
}

export async function writeAss(opts: {
  outPath: string;
  style: CaptionStyle;
  captions: AiCaption[];
  segments: { start: number; end: number }[];
}): Promise<number> {
  const events = buildAssEvents(opts.style, opts.captions, opts.segments);
  await writeFile(opts.outPath, header(opts.style) + events.join("\n") + "\n", "utf8");
  return events.length;
}
