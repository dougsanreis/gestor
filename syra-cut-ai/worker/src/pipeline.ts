import { writeFile } from "node:fs/promises";
import path from "node:path";
import { buildCaptions, countWordsInSegments } from "./captions.js";
import { buildEdl, type Edl } from "./edl-generator.js";
import {
  chooseFraming,
  ffmpegVersion,
  renderVariant,
  sha256File,
  validateRender,
  VARIANT_SPECS,
  type Framing,
  type ProbeReport,
} from "./ffmpeg-renderer.js";
import type { RouterResult } from "./ai-editorial-router.js";
import type { Transcript, VariantId } from "./types.js";

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
  error?: string;
}

export interface PlanResult {
  edl: Edl;
  framing: Framing;
  captionsCount: number;
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

export function planCut(opts: {
  probe: ProbeReport;
  transcript: Transcript;
  router: RouterResult;
  maxTotal: number;
}): PlanResult {
  const edl = buildEdl(opts.router.plan, {
    sourceDuration: opts.probe.duration,
    maxTotal: opts.maxTotal,
    speech: opts.transcript.segments,
  });
  return {
    edl,
    framing: chooseFraming(opts.probe.width, opts.probe.height),
    captionsCount: buildCaptions(opts.transcript).length,
    subtitleWords: countWordsInSegments(opts.transcript.words, edl.segments),
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
  transcript: Transcript;
  plan: PlanResult;
  onVariant?: (id: VariantId, phase: "RENDERING" | "VALIDATING") => Promise<void> | void;
}): Promise<RenderedVariant[]> {
  const captions = buildCaptions(opts.transcript);
  const out: RenderedVariant[] = [];
  for (const id of opts.variants) {
    try {
      await opts.onVariant?.(id, "RENDERING");
      const res = await renderVariant({
        inputPath: opts.inputPath,
        workDir: opts.workDir,
        variant: id,
        segments: opts.plan.edl.segments,
        captions,
        framing: opts.plan.framing,
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
    framing: opts.plan.framing,
    captions: opts.plan.captionsCount,
    subtitle_words: opts.plan.subtitleWords,
    variants: opts.rendered.map((r) => ({
      ...r,
      outputPath: r.outputPath ? path.basename(r.outputPath) : undefined,
      spec: VARIANT_SPECS[r.id],
    })),
    human_review_required: true,
  };
  const p = path.join(opts.workDir, "mission_report.json");
  await writeFile(p, JSON.stringify(report, null, 2) + "\n", "utf8");
  return p;
}
