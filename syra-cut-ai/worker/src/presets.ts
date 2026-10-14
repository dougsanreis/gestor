import type { VariantId } from "./types.js";

export type CaptionStyle = "karaoke" | "clean" | "dynamic";

/**
 * Formato de cada variante. Os ids continuam os do app (contrato), o que muda é a edição.
 *
 * - viral_cut: gancho no início (cold open), jump cuts nas pausas, punch-in alternado a cada
 *   corte, legenda palavra a palavra com destaque, título do gancho, barra de progresso.
 * - clean_caption: ritmo natural (só pausas longas saem), sem zoom, legenda limpa e pequena.
 *   Para conteúdo de autoridade/explicação, onde corte agressivo atrapalha.
 * - speed_dynamic: o viral_cut mais rápido (1,1×) e com cortes ainda mais secos.
 */
export interface VariantPreset {
  captions: CaptionStyle;
  speed: number;
  /** Repete a melhor frase no começo (2–4 s) antes do vídeo, com flash de transição. */
  hook: boolean;
  /** Pausa entre palavras acima disso vira corte (jump cut). */
  maxGap: number;
  /** Alterna enquadramento 1,00×/1,12× a cada corte para esconder o pulo. */
  punchIn: boolean;
  titleCard: boolean;
  progressBar: boolean;
  /** Contraste/saturação leves e nitidez quando a fonte é de baixa resolução. */
  grade: boolean;
}

export const PRESETS: Record<VariantId, VariantPreset> = {
  viral_cut: {
    captions: "karaoke",
    speed: 1.0,
    hook: true,
    maxGap: 0.3,
    punchIn: true,
    titleCard: true,
    progressBar: true,
    grade: true,
  },
  clean_caption: {
    captions: "clean",
    speed: 1.0,
    hook: false,
    maxGap: 0.8,
    punchIn: false,
    titleCard: false,
    progressBar: false,
    grade: true,
  },
  speed_dynamic: {
    captions: "dynamic",
    speed: 1.1,
    hook: true,
    maxGap: 0.22,
    punchIn: true,
    titleCard: true,
    progressBar: true,
    grade: true,
  },
};

/** Escala do punch-in nos cortes ímpares. */
export const PUNCH_SCALE = 1.12;
/** Limite de trechos por render (cada um é uma entrada do FFmpeg). */
export const MAX_CLIPS = 48;
