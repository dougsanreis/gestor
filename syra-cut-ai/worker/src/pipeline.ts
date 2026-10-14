import { writeFile } from "node:fs/promises";
import path from "node:path";
import { buildEdl, type Edl } from "./edl-generator.js";
import {
  chooseFraming,
  ffmpegVersion,
  renderVariant,
  sha256File,
  validateRender,
  type Framing,
  type ProbeReport,
} from "./ffmpeg-renderer.js";
import type { RouterResult } from "./ai-editorial-router.js";
import { PRESETS } from "./presets.js";
import type { Interval } from "./scene-analysis.js";
import { buildTimeline, timelineDuration, validateHook, type Clip } from "./timeline.js";
import type { TimedText, Transcript, VariantId } from "./types.js";

export interface RenderedVariant {
  id: VariantId;
  ok: boolean;
  outputPath?: string;
  duration?: number;
  width?: number;
  height?: number;
  v_codec?: string;
  a_codec?: string;
  size?: number;
  sha256?: string;
  captionEvents?: number;
  error?: string;
}

export interface PlanResult {
  edl: Edl;
  framing: Framing;
  lowRes: boolean;
  /** Trechos com giro/borrão removidos automaticamente. */
  unstable: Interval[];
  hook: Interval | null;
  timelines: Partial<Record<VariantId, Clip[]>>;
  words: TimedText[];
  subtitleWords: number;
}

/**
 * Duração máxima do corte final. O app manda max_duration (75 ou 90); a variante acelerada
 * fica mais curta, então o limite vale para o tempo da fonte.
 */
export function clampMaxDuration(v: number | undefined): number {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return 90;
  return Math.max(5, Math.min(180, n));
}

/**
 * Palavras com tempo. Se o STT só devolveu frases, distribui o tempo de cada frase entre as
 * palavras proporcionalmente ao tamanho (aproximação; o normal é vir palavra a palavra).
 */
export function ensureWords(t: Transcript): TimedText[] {
  const words = t.words.filter((w) => w.text.trim() && w.end > w.start);
  if (words.length) return words;
  return t.segments.flatMap((s) => {
    const parts = s.text.split(/\s+/).filter(Boolean);
    const total = parts.reduce((a, p) => a + p.length + 1, 0);
    let cursor = s.start;
    return parts.map((p) => {
      const len = ((p.length + 1) / total) * (s.end - s.start);
      const w = { start: cursor, end: cursor + len * 0.92, text: p };
      cursor += len;
      return w;
    });
  });
}

export function planCut(opts: {
  probe: ProbeReport;
  transcript: Transcript;
  router: RouterResult;
  maxTotal: number;
  unstable: Interval[];
  variants: VariantId[];
}): PlanResult {
  const words = ensureWords(opts.transcript);
  const edl = buildEdl(opts.router.plan, {
    sourceDuration: opts.probe.duration,
    maxTotal: opts.maxTotal,
    speech: opts.transcript.segments,
  });
  const hook = validateHook(opts.router.plan.hook, {
    duration: opts.probe.duration,
    words,
    bad: opts.unstable,
  });
  const timelines: PlanResult["timelines"] = {};
  for (const id of opts.variants) {
    timelines[id] = buildTimeline({
      segments: edl.segments,
      words,
      bad: opts.unstable,
      hook,
      preset: PRESETS[id],
    });
  }
  const main = timelines[opts.variants[0]] ?? [];
  const subtitleWords = words.filter((w) =>
    main.some((c) => (w.start + w.end) / 2 >= c.start && (w.start + w.end) / 2 <= c.end),
  ).length;
  return {
    edl,
    framing: chooseFraming(opts.probe.width, opts.probe.height),
    lowRes: Math.min(opts.probe.width, opts.probe.height) < 720,
    unstable: opts.unstable,
    hook,
    timelines,
    words,
    subtitleWords,
  };
}

/**
 * Renderiza e valida cada variante. Uma variante que falha não derruba as outras; o
 * chamador decide (o job só falha se nenhuma passar no QA).
 */
export async function renderAndValidate(opts: {
  inputPath: string;
  workDir: string;
  variants: VariantId[];
  plan: PlanResult;
  title: string | null;
  onVariant?: (id: VariantId, phase: "RENDERING" | "VALIDATING") => Promise<void> | void;
}): Promise<RenderedVariant[]> {
  const out: RenderedVariant[] = [];
  for (const id of opts.variants) {
    try {
      const clips = opts.plan.timelines[id] ?? [];
      if (timelineDuration(clips) < 3)
        throw new Error("linha do tempo com menos de 3 s após os cortes");
      await opts.onVariant?.(id, "RENDERING");
      const res = await renderVariant({
        inputPath: opts.inputPath,
        workDir: opts.workDir,
        variant: id,
        clips,
        words: opts.plan.words,
        title: opts.title,
        framing: opts.plan.framing,
        lowRes: opts.plan.lowRes,
      });
      await opts.onVariant?.(id, "VALIDATING");
      const { probe, failures } = await validateRender(res.outputPath, res.expectedDuration);
      if (failures.length) throw new Error(`QA reprovou: ${failures.join("; ")}`);
      out.push({
        id,
        ok: true,
        outputPath: res.outputPath,
        duration: probe.duration,
        width: probe.width,
        height: probe.height,
        v_codec: probe.v_codec,
        a_codec: probe.a_codec,
        size: probe.size,
        sha256: await sha256File(res.outputPath),
        captionEvents: res.captionEvents,
      });
    } catch (e) {
      out.push({ id, ok: false, error: e instanceof Error ? e.message : String(e) });
    }
  }
  return out;
}

/** mission_report.json: tudo o que é preciso para auditar/reproduzir o job. */
export async function writeMissionReport(opts: {
  workDir: string;
  jobId: string;
  attempt: number;
  probe: ProbeReport;
  warnings: string[];
  transcript: Transcript;
  router: RouterResult;
  plan: PlanResult;
  rendered: RenderedVariant[];
}): Promise<string> {
  const report = {
    job_id: opts.jobId,
    attempt: opts.attempt,
    created_at: new Date().toISOString(),
    ffmpeg: await ffmpegVersion(),
    source: opts.probe,
    warnings: opts.warnings,
    transcript: {
      provider: opts.transcript.provider,
      language: opts.transcript.language,
      words: opts.transcript.words.length,
      segments: opts.transcript.segments.length,
    },
    ai: {
      mode: opts.router.mode,
      provider: opts.router.plan.provider,
      attempts: opts.router.attempts,
      title: opts.router.plan.title,
      hooks: opts.router.plan.hooks,
      virality_score: opts.router.plan.virality_score,
    },
    edl: opts.plan.edl,
    unstable_removed: opts.plan.unstable,
    hook: opts.plan.hook,
    framing: opts.plan.framing,
    subtitle_words: opts.plan.subtitleWords,
    variants: opts.rendered.map((r) => ({
      ...r,
      outputPath: r.outputPath ? path.basename(r.outputPath) : undefined,
      preset: PRESETS[r.id],
      clips: opts.plan.timelines[r.id],
    })),
    human_review_required: true,
  };
  const p = path.join(opts.workDir, "mission_report.json");
  await writeFile(p, JSON.stringify(report, null, 2) + "\n", "utf8");
  return p;
}
