import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { mkdir, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { env } from "./env.js";
import { isSafeJobId } from "./security.js";
import type { AiCaption, AiSegment, VariantId } from "./types.js";
import { writeAss, type CaptionStyle } from "./ass-caption-generator.js";

const FFMPEG = env.FFMPEG_PATH || "ffmpeg";
const FFPROBE =
  env.FFPROBE_PATH ||
  (env.FFMPEG_PATH ? env.FFMPEG_PATH.replace(/ffmpeg(\.exe)?$/, "ffprobe$1") : "ffprobe");

export const OUT_W = 1080;
export const OUT_H = 1920;
export const OUT_FPS = 30;

/** Executa um binário com timeout; mata o processo (SIGKILL) se estourar. */
export async function run(
  cmd: string,
  args: string[],
  opts: { timeoutMs?: number; captureStdout?: boolean } = {},
): Promise<string> {
  const timeoutMs = opts.timeoutMs ?? 10 * 60 * 1000;
  return await new Promise<string>((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      p.kill("SIGKILL");
      reject(
        new Error(
          `${path.basename(cmd)} excedeu ${Math.round(timeoutMs / 1000)}s e foi interrompido`,
        ),
      );
    }, timeoutMs);
    p.stdout.on("data", (d) => {
      if (opts.captureStdout) stdout += d.toString();
    });
    p.stderr.on("data", (d) => {
      stderr = (stderr + d.toString()).slice(-8000);
    });
    p.on("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
    p.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve(stdout);
      else
        reject(new Error(`${path.basename(cmd)} saiu com código ${code}: ${stderr.slice(-600)}`));
    });
  });
}

export interface ProbeReport {
  duration: number;
  width: number;
  height: number;
  v_codec: string;
  a_codec: string;
  has_video: boolean;
  has_audio: boolean;
  video_streams: number;
  /** Média real de quadros/s (celular/WhatsApp gravam com taxa variável). */
  fps_avg: number;
  fps_nominal: number;
  vfr: boolean;
  rotation: number;
  size: number;
  bit_rate: number;
}

function rate(v: string | undefined): number {
  const [n, d] = (v ?? "0/1").split("/").map(Number);
  return d ? n / d : 0;
}

/** ffprobe que FALHA de verdade (o original devolvia {} e seguia com duração 0). */
export async function probeMedia(inputPath: string): Promise<ProbeReport> {
  const out = await run(
    FFPROBE,
    ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", inputPath],
    { timeoutMs: 60_000, captureStdout: true },
  );
  let j: {
    format?: { duration?: string; size?: string; bit_rate?: string };
    streams?: Array<{
      codec_type?: string;
      codec_name?: string;
      width?: number;
      height?: number;
      r_frame_rate?: string;
      avg_frame_rate?: string;
      tags?: { rotate?: string };
      side_data_list?: Array<{ rotation?: number }>;
    }>;
  };
  try {
    j = JSON.parse(out);
  } catch {
    throw new Error("ffprobe devolveu JSON inválido");
  }
  const streams = j.streams ?? [];
  const videos = streams.filter(
    (s) => s.codec_type === "video" && s.codec_name !== "mjpeg" && s.codec_name !== "png",
  );
  const v = videos[0];
  const a = streams.find((s) => s.codec_type === "audio");
  const fpsNominal = rate(v?.r_frame_rate);
  const fpsAvg = rate(v?.avg_frame_rate) || fpsNominal;
  const rotation =
    Number(
      v?.tags?.rotate ?? v?.side_data_list?.find((d) => d.rotation !== undefined)?.rotation ?? 0,
    ) || 0;
  let width = v?.width ?? 0;
  let height = v?.height ?? 0;
  // Vídeo de celular gravado "deitado" com tag de rotação: o FFmpeg autorrotaciona,
  // então a geometria efetiva é a trocada.
  if (Math.abs(rotation) % 180 === 90) [width, height] = [height, width];
  return {
    duration: Number(j.format?.duration ?? 0) || 0,
    width,
    height,
    v_codec: v?.codec_name ?? "",
    a_codec: a?.codec_name ?? "",
    has_video: !!v,
    has_audio: !!a,
    video_streams: videos.length,
    fps_avg: Math.round(fpsAvg * 1000) / 1000,
    fps_nominal: Math.round(fpsNominal * 1000) / 1000,
    vfr: fpsNominal > 0 && fpsAvg > 0 && Math.abs(fpsNominal - fpsAvg) / fpsAvg > 0.05,
    rotation,
    size: Number(j.format?.size ?? 0) || 0,
    bit_rate: Number(j.format?.bit_rate ?? 0) || 0,
  };
}

/** Pré-checagem da fonte antes de gastar transcrição/IA/render. */
export function preflightProblems(p: ProbeReport): string[] {
  const problems: string[] = [];
  if (!p.has_video) problems.push("arquivo sem stream de vídeo");
  if (p.duration <= 1) problems.push(`duração inválida (${p.duration.toFixed(2)}s)`);
  if (p.duration > env.MAX_SOURCE_SECONDS)
    problems.push(
      `vídeo de ${Math.round(p.duration)}s excede o limite de ${env.MAX_SOURCE_SECONDS}s`,
    );
  if (!p.has_audio)
    problems.push("vídeo sem áudio: não há fala para transcrever nem legenda real a gerar");
  if (p.width < 2 || p.height < 2) problems.push("dimensões de vídeo inválidas");
  return problems;
}

export function preflightWarnings(p: ProbeReport): string[] {
  const w: string[] = [];
  if (p.vfr)
    w.push(
      `taxa variável (nominal ${p.fps_nominal}, média ${p.fps_avg}); normalizando para ${OUT_FPS} fps`,
    );
  if (Math.min(p.width, p.height) < 720)
    w.push(
      `resolução baixa (${p.width}x${p.height}); o 1080x1920 será uma ampliação e pode ficar suave`,
    );
  if (p.video_streams > 1) w.push("mais de um stream de vídeo; usando o primeiro");
  return w;
}

/** Áudio para STT: mono 16 kHz em MP3 32 kbps (~14 MB/h, abaixo do limite de 25 MB do Whisper até ~100 min). */
export async function extractAudio(inputPath: string, outPath: string): Promise<void> {
  await run(
    FFMPEG,
    [
      "-nostdin",
      "-y",
      "-v",
      "error",
      "-i",
      inputPath,
      "-vn",
      "-ac",
      "1",
      "-ar",
      "16000",
      "-c:a",
      "libmp3lame",
      "-b:a",
      "32k",
      outPath,
    ],
    { timeoutMs: 5 * 60 * 1000 },
  );
}

export type Framing = "cover" | "blur_fill";

/**
 * Enquadramento automático: se a proporção da fonte é parecida com 9:16, corta pelo centro
 * (cover). Se é bem diferente (ex.: 16:9 deitado), o cover cortaria ~68% da largura; então
 * mantemos o quadro inteiro sobre um fundo desfocado da própria imagem (blur_fill).
 */
export function chooseFraming(width: number, height: number): Framing {
  if (!width || !height) return "cover";
  const target = OUT_W / OUT_H;
  const ratio = width / height;
  return Math.abs(ratio - target) / target <= 0.25 ? "cover" : "blur_fill";
}

export interface VariantSpec {
  style: CaptionStyle;
  speed: number;
  zoom: boolean;
}

export const VARIANT_SPECS: Record<VariantId, VariantSpec> = {
  viral_cut: { style: "kinetic", speed: 1.0, zoom: true },
  clean_caption: { style: "clean", speed: 1.0, zoom: false },
  speed_dynamic: { style: "dynamic", speed: 1.08, zoom: true },
};

function escapeFilterPath(p: string): string {
  // Dentro de filter_complex: escapa \ ' : , [ ] ; para o parser de filtros e de opções.
  return p.replace(/\\/g, "/").replace(/([':,[\];])/g, "\\$1");
}

/**
 * Monta o filtro. Cada trecho é uma entrada própria (-ss/-t antes de -i), então o FFmpeg não
 * decodifica a fonte inteira nem acumula quadros na memória; cada trecho é normalizado para
 * 30 fps (fontes VFR) antes do concat.
 */
export function buildFilterGraph(opts: {
  segments: { start: number; end: number }[];
  framing: Framing;
  spec: VariantSpec;
  assPath: string | null;
  totalDuration: number;
}): string {
  const parts: string[] = [];
  opts.segments.forEach((s, i) => {
    const d = (s.end - s.start).toFixed(3);
    parts.push(`[${i}:v:0]trim=duration=${d},setpts=PTS-STARTPTS,fps=${OUT_FPS},setsar=1[v${i}]`);
    parts.push(
      `[${i}:a:0]atrim=duration=${d},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a${i}]`,
    );
  });
  const n = opts.segments.length;
  parts.push(
    `${opts.segments.map((_, i) => `[v${i}][a${i}]`).join("")}concat=n=${n}:v=1:a=1[vc][ac]`,
  );

  let v = "[vc]";
  if (opts.framing === "cover") {
    parts.push(
      `${v}scale=${OUT_W}:${OUT_H}:force_original_aspect_ratio=increase,crop=${OUT_W}:${OUT_H}[vf]`,
    );
  } else {
    parts.push(`${v}split=2[bg0][fg0]`);
    parts.push(
      `[bg0]scale=${OUT_W}:${OUT_H}:force_original_aspect_ratio=increase,crop=${OUT_W}:${OUT_H},boxblur=24:2,eq=brightness=-0.08[bg]`,
    );
    parts.push(`[fg0]scale=${OUT_W}:${OUT_H}:force_original_aspect_ratio=decrease[fg]`);
    parts.push(`[bg][fg]overlay=(W-w)/2:(H-h)/2[vf]`);
  }
  v = "[vf]";

  const chain: string[] = [];
  if (opts.spec.zoom) {
    // Push-in suave e contínuo de 1.00 → 1.06 ao longo do vídeo (o zoompan original resetava
    // por quadro e tremia). Dimensões pares para o x264.
    const T = Math.max(opts.totalDuration, 1).toFixed(3);
    chain.push(
      `scale=w='2*trunc(${OUT_W}*(1+0.06*min(t/${T}\\,1))/2)':h='2*trunc(${OUT_H}*(1+0.06*min(t/${T}\\,1))/2)':eval=frame`,
      `crop=${OUT_W}:${OUT_H}`,
    );
  }
  if (opts.assPath) chain.push(`ass='${escapeFilterPath(opts.assPath)}'`);
  if (opts.spec.speed !== 1) chain.push(`setpts=PTS/${opts.spec.speed}`, `fps=${OUT_FPS}`);
  chain.push("format=yuv420p");
  parts.push(`${v}${chain.join(",")}[vo]`);

  const aChain = ["loudnorm=I=-16:TP=-1.5:LRA=11"];
  if (opts.spec.speed !== 1) aChain.push(`atempo=${opts.spec.speed}`);
  aChain.push("aresample=48000"); // loudnorm sobe para 192 kHz; volta para 48 kHz.
  parts.push(`[ac]${aChain.join(",")}[ao]`);
  return parts.join(";");
}

export interface RenderInput {
  inputPath: string;
  workDir: string;
  variant: VariantId;
  segments: AiSegment[];
  captions: AiCaption[];
  framing: Framing;
}

export interface RenderResult {
  outputPath: string;
  expectedDuration: number;
}

export async function renderVariant(input: RenderInput): Promise<RenderResult> {
  if (input.segments.length === 0) throw new Error("EDL vazia");
  await mkdir(input.workDir, { recursive: true });
  const spec = VARIANT_SPECS[input.variant];
  let assPath: string | null = null;
  if (input.captions.length > 0) {
    assPath = path.join(input.workDir, `captions-${input.variant}.ass`);
    await writeAss({
      outPath: assPath,
      style: spec.style,
      captions: input.captions,
      segments: input.segments,
    });
  }
  const sourceTotal = input.segments.reduce((acc, s) => acc + (s.end - s.start), 0);
  const expectedDuration = sourceTotal / spec.speed;
  const outPath = path.join(input.workDir, `${input.variant}.mp4`);

  const inputs: string[] = [];
  for (const s of input.segments) {
    inputs.push(
      "-ss",
      s.start.toFixed(3),
      "-t",
      (s.end - s.start).toFixed(3),
      "-i",
      input.inputPath,
    );
  }
  const filter = buildFilterGraph({
    segments: input.segments,
    framing: input.framing,
    spec,
    assPath,
    totalDuration: sourceTotal,
  });
  await run(
    FFMPEG,
    [
      "-nostdin",
      "-y",
      "-v",
      "error",
      ...inputs,
      "-filter_complex",
      filter,
      "-map",
      "[vo]",
      "-map",
      "[ao]",
      "-map_metadata",
      "-1",
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "21",
      "-pix_fmt",
      "yuv420p",
      "-r",
      String(OUT_FPS),
      "-c:a",
      "aac",
      "-b:a",
      "160k",
      "-ar",
      "48000",
      "-movflags",
      "+faststart",
      outPath,
    ],
    { timeoutMs: Math.max(5 * 60 * 1000, Math.round(sourceTotal * 30_000)) },
  );
  return { outputPath: outPath, expectedDuration };
}

/**
 * QA bloqueante antes do upload: dimensões, codecs, áudio, duração contra o esperado e
 * decodificação integral (pega arquivo truncado/corrompido que o ffprobe sozinho não vê).
 */
export async function validateRender(
  outputPath: string,
  expectedDuration: number,
): Promise<{ probe: ProbeReport; failures: string[] }> {
  const probe = await probeMedia(outputPath);
  const failures: string[] = [];
  if (!probe.has_video) failures.push("sem stream de vídeo");
  if (!probe.has_audio) failures.push("sem stream de áudio");
  if (probe.v_codec !== "h264") failures.push(`codec ${probe.v_codec || "?"} != h264`);
  if (probe.has_audio && probe.a_codec !== "aac") failures.push(`áudio ${probe.a_codec} != aac`);
  if (probe.width !== OUT_W || probe.height !== OUT_H)
    failures.push(`dimensões ${probe.width}x${probe.height} != ${OUT_W}x${OUT_H}`);
  if (probe.duration <= 3) failures.push(`duração ${probe.duration.toFixed(2)}s <= 3s`);
  const tolerance = Math.max(0.5, expectedDuration * 0.03);
  if (Math.abs(probe.duration - expectedDuration) > tolerance)
    failures.push(
      `duração ${probe.duration.toFixed(2)}s difere do plano (${expectedDuration.toFixed(2)}s)`,
    );
  if (failures.length === 0) {
    try {
      await run(
        FFMPEG,
        ["-nostdin", "-v", "error", "-xerror", "-i", outputPath, "-f", "null", "-"],
        {
          timeoutMs: Math.max(120_000, Math.round(expectedDuration * 10_000)),
        },
      );
    } catch (e) {
      failures.push(`decodificação integral falhou: ${e instanceof Error ? e.message : e}`);
    }
  }
  return { probe, failures };
}

export async function sha256File(p: string): Promise<string> {
  const h = createHash("sha256");
  for await (const chunk of createReadStream(p)) h.update(chunk as Buffer);
  return h.digest("hex");
}

export async function ffmpegVersion(): Promise<string> {
  try {
    const out = await run(FFMPEG, ["-version"], { timeoutMs: 10_000, captureStdout: true });
    return out.split("\n")[0] ?? "";
  } catch {
    return "";
  }
}

export async function makeWorkDir(jobId: string): Promise<string> {
  if (!isSafeJobId(jobId)) throw new Error("job_id inválido para pasta de trabalho");
  const root = path.join(tmpdir(), "syra-worker");
  const dir = path.join(root, `job-${jobId}`);
  if (path.dirname(dir) !== root) throw new Error("pasta de trabalho fora da raiz");
  await mkdir(dir, { recursive: true });
  return dir;
}

export async function cleanupWorkDir(dir: string): Promise<void> {
  const root = path.join(tmpdir(), "syra-worker");
  if (path.dirname(path.resolve(dir)) !== root) return; // nunca apaga fora da raiz do worker
  await rm(dir, { recursive: true, force: true }).catch(() => undefined);
}

/** Download em stream para o disco, com limite de bytes e timeout (o original carregava tudo na RAM). */
export async function downloadToFile(
  url: string,
  destPath: string,
  maxBytes: number,
): Promise<number> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), env.DOWNLOAD_TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: ctrl.signal, redirect: "error" });
    if (!res.ok || !res.body) throw new Error(`download falhou: HTTP ${res.status}`);
    const declared = Number(res.headers.get("content-length") || 0);
    if (declared && declared > maxBytes)
      throw new Error(`arquivo de ${declared} bytes excede o limite de ${maxBytes}`);
    let received = 0;
    const limited = Readable.fromWeb(res.body as import("node:stream/web").ReadableStream).on(
      "data",
      (chunk: Buffer) => {
        received += chunk.length;
        if (received > maxBytes)
          limited.destroy(new Error(`arquivo excede o limite de ${maxBytes} bytes`));
      },
    );
    await pipeline(limited, createWriteStream(destPath));
    const size = (await stat(destPath)).size;
    if (size === 0) throw new Error("download vazio");
    return size;
  } catch (e) {
    if (ctrl.signal.aborted)
      throw new Error(`download excedeu ${Math.round(env.DOWNLOAD_TIMEOUT_MS / 1000)}s`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
