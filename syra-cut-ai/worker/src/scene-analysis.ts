import { run } from "./ffmpeg-renderer.js";
import { env } from "./env.js";

export interface Interval {
  start: number;
  end: number;
}

const SAMPLE_FPS = 10;

/**
 * Mede o borrão por quadro (blurdetect, 10 amostras/s em baixa resolução: rápido).
 * Devolve [tempo, borrão].
 */
export async function blurSeries(inputPath: string): Promise<Array<[number, number]>> {
  const out = await run(
    env.FFMPEG_PATH || "ffmpeg",
    [
      "-nostdin",
      "-v",
      "error",
      "-i",
      inputPath,
      "-an",
      "-vf",
      `fps=${SAMPLE_FPS},scale=270:-2,blurdetect=block_width=32:block_height=32,metadata=print:file=-`,
      "-f",
      "null",
      "-",
    ],
    { timeoutMs: 5 * 60 * 1000, captureStdout: true },
  );
  const rows: Array<[number, number]> = [];
  let t: number | null = null;
  for (const line of out.split("\n")) {
    const pts = line.match(/pts_time:([\d.]+)/);
    if (pts) t = Number(pts[1]);
    const b = line.match(/blur=([\d.]+)/);
    if (b && t !== null) rows.push([t, Number(b[1])]);
  }
  return rows;
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : 0;
}

/**
 * Trechos inutilizáveis: borrão bem acima do normal DESTE vídeo (limiar relativo à mediana)
 * por pelo menos `minRun` segundos. Pega giro de câmera (whip pan), câmera tremendo e foco
 * perdido; ignora pico curto de movimento normal. Tolera 1 amostra abaixo no meio do trecho.
 */
export function unstableIntervals(
  series: Array<[number, number]>,
  opts = { ratio: 1.35, floor: 6.0, minRun: 0.6, pad: 0.12 },
): Interval[] {
  if (series.length < 3) return [];
  const threshold = Math.max(opts.floor, median(series.map(([, b]) => b)) * opts.ratio);
  const step = 1 / SAMPLE_FPS;
  const out: Interval[] = [];
  let start: number | null = null;
  let lastHigh = 0;
  let misses = 0;
  const close = () => {
    if (start !== null && lastHigh + step - start >= opts.minRun) {
      out.push({ start: Math.max(0, start - opts.pad), end: lastHigh + step + opts.pad });
    }
    start = null;
    misses = 0;
  };
  for (const [t, b] of series) {
    if (b >= threshold) {
      if (start === null) start = t;
      lastHigh = t;
      misses = 0;
    } else if (start !== null && ++misses > 1) {
      close();
    }
  }
  close();
  return out;
}

export async function detectUnstable(inputPath: string): Promise<Interval[]> {
  try {
    return unstableIntervals(await blurSeries(inputPath));
  } catch (e) {
    // Análise é melhoria, não requisito: sem ela o corte segue só pela fala.
    console.warn(`[scene] análise de borrão falhou: ${e instanceof Error ? e.message : e}`);
    return [];
  }
}
