import type { AiEditorialPlan, AiPipelineMode, VariantId } from "./job-contract";

/**
 * SYRA AIProviderRouter — Claude → Grok → Mistral → Local Heuristic.
 *
 * Hard contract:
 *  - NEVER throws. Always returns a valid AiEditorialPlan.
 *  - Schema-tolerant: missing fields become safe defaults (no Zod throw).
 *  - Structured logs (`[CLAUDE_OK]`, `[CLAUDE_FAIL]`, ...) for the pipeline.
 *  - Pipeline mode reflects degradation: FULL / PARTIAL / FALLBACK.
 */

const SYSTEM = `You are SYRA's editorial planner. Given a video transcript, produce a JSON editorial plan with:
- title (PT-BR, max 80 chars, magnetic)
- hooks: 3-5 opening lines (PT-BR)
- captions: [] if you can't time them precisely
- segments: keep/cut decisions with start/end seconds and reason
- variants: rationale for each of [viral_cut, clean_caption, speed_dynamic]
- virality_score 0-100
Return STRICT JSON only.`;

function buildUserPrompt(transcript: string): string {
  return `Transcript:\n"""\n${transcript.slice(0, 12000)}\n"""\n\nReturn the JSON object.`;
}

export interface RouterAttempt {
  provider: "anthropic" | "xai" | "mistral" | "local";
  status: "OK" | "FAIL";
  log: string;
  error?: string;
}

export interface RouterResult {
  plan: AiEditorialPlan;
  mode: AiPipelineMode;
  attempts: RouterAttempt[];
  degraded: boolean;
}

// ---------- Normalizer (universal) ----------

const ALLOWED_VARIANTS: VariantId[] = ["viral_cut", "clean_caption", "speed_dynamic"];

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asNumber(v: unknown, fallback = 0): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}
function asArray<T = unknown>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

/**
 * normalizeProviderResponse — accepts whatever Claude/Grok/Mistral returned
 * (possibly wrapped, partial, or differently-keyed) and produces a strict
 * AiEditorialPlan. Never throws.
 */
export function normalizeProviderResponse(
  raw: unknown,
  provider: AiEditorialPlan["provider"],
): AiEditorialPlan {
  const root = (raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {}) as Record<
    string,
    unknown
  >;
  const inner =
    (root.plan as Record<string, unknown> | undefined) ??
    (root.editorial_plan as Record<string, unknown> | undefined) ??
    root;

  const hooks = asArray(inner.hooks)
    .map((h) => asString(h))
    .filter(Boolean);
  const captions = asArray<Record<string, unknown>>(inner.captions)
    .map((c) => ({
      start: asNumber(c.start),
      end: asNumber(c.end),
      text: asString(c.text),
    }))
    .filter((c) => c.text);
  const segments = asArray<Record<string, unknown>>(inner.segments).map((s) => ({
    start: asNumber(s.start),
    end: asNumber(s.end),
    reason: asString(s.reason, "—"),
    keep: s.keep !== false,
  }));
  const variants = asArray<Record<string, unknown>>(inner.variants)
    .map((v) => ({
      id: (ALLOWED_VARIANTS.includes(v.id as VariantId) ? v.id : "viral_cut") as VariantId,
      rationale: asString(v.rationale, ""),
    }))
    .filter((v, i, arr) => arr.findIndex((x) => x.id === v.id) === i);

  return {
    title: asString(inner.title, "Vídeo analisado").slice(0, 140),
    hooks,
    captions,
    segments,
    variants,
    virality_score: Math.max(0, Math.min(100, Math.round(asNumber(inner.virality_score, 0)))),
    provider,
  };
}

// ---------- Local fallback factory ----------

/**
 * VideoAnalysisResultFactory — returns a valid plan even when no provider
 * answered. Heuristic uses transcript length to size virality / hooks.
 */
export function VideoAnalysisResultFactory(transcript = ""): AiEditorialPlan {
  const words = transcript.trim().split(/\s+/).filter(Boolean);
  const firstLine = transcript.split(/[.!?\n]/).find((s) => s.trim().length > 0)?.trim() ?? "";
  const hooks = firstLine ? [firstLine.slice(0, 120)] : [];
  return {
    title: firstLine ? firstLine.slice(0, 80) : "Vídeo analisado",
    hooks,
    captions: [],
    segments: [],
    variants: ALLOWED_VARIANTS.map((id) => ({
      id,
      rationale: "Heurística local — IA indisponível.",
    })),
    virality_score: Math.min(75, 40 + Math.floor(words.length / 50)),
    provider: "local",
  };
}

// ---------- Provider calls ----------

async function callAnthropic(transcript: string): Promise<unknown> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new Error("ANTHROPIC_API_KEY missing");
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      // claude-3-5-sonnet-latest foi aposentado; configurável por ANTHROPIC_MODEL.
      model: process.env.ANTHROPIC_MODEL || "claude-opus-5-5",
      max_tokens: 16000,
      system: SYSTEM,
      messages: [{ role: "user", content: buildUserPrompt(transcript) }],
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const json = (await res.json()) as { content?: { text?: string }[] };
  const text = json.content?.[0]?.text ?? "";
  return JSON.parse(extractJson(text));
}

async function callGrok(transcript: string): Promise<unknown> {
  const key = process.env.XAI_API_KEY;
  if (!key) throw new Error("XAI_API_KEY missing");
  const res = await fetch("https://api.x.ai/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: JSON.stringify({
      model: "grok-2-latest",
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: buildUserPrompt(transcript) },
      ],
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const json = (await res.json()) as { choices?: { message?: { content?: string } }[] };
  const text = json.choices?.[0]?.message?.content ?? "";
  return JSON.parse(extractJson(text));
}

async function callMistral(transcript: string): Promise<unknown> {
  const key = process.env.MISTRAL_API_KEY;
  if (!key) throw new Error("MISTRAL_API_KEY missing");
  const res = await fetch("https://api.mistral.ai/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: JSON.stringify({
      model: "mistral-large-latest",
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: buildUserPrompt(transcript) },
      ],
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const json = (await res.json()) as { choices?: { message?: { content?: string } }[] };
  const text = json.choices?.[0]?.message?.content ?? "";
  return JSON.parse(extractJson(text));
}

function extractJson(text: string): string {
  const trimmed = text.trim();
  if (trimmed.startsWith("{")) return trimmed;
  const m = trimmed.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("No JSON object in model response");
  return m[0];
}

// ---------- Cascade ----------

/**
 * Runs Claude → Grok → Mistral → Local. Never throws.
 * mode = FULL when primary (Claude) succeeded;
 *        PARTIAL when a secondary provider answered;
 *        FALLBACK when only the local heuristic answered.
 */
export async function planEditorial(transcript: string): Promise<RouterResult> {
  const attempts: RouterAttempt[] = [];
  const chain: Array<{
    name: "anthropic" | "xai" | "mistral";
    okTag: string;
    failTag: string;
    fn: (t: string) => Promise<unknown>;
  }> = [
    { name: "anthropic", okTag: "[CLAUDE_OK]", failTag: "[CLAUDE_FAIL]", fn: callAnthropic },
    { name: "xai", okTag: "[GROK_OK]", failTag: "[GROK_FAIL]", fn: callGrok },
    { name: "mistral", okTag: "[MISTRAL_OK]", failTag: "[MISTRAL_FAIL]", fn: callMistral },
  ];

  for (let i = 0; i < chain.length; i++) {
    const step = chain[i];
    try {
      const raw = await step.fn(transcript);
      const plan = normalizeProviderResponse(raw, step.name);
      attempts.push({ provider: step.name, status: "OK", log: step.okTag });
      console.log(`${step.okTag} provider=${step.name} virality=${plan.virality_score}`);
      const mode: AiPipelineMode = i === 0 ? "FULL" : "PARTIAL";
      return { plan, mode, attempts, degraded: mode !== "FULL" };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      attempts.push({ provider: step.name, status: "FAIL", log: step.failTag, error: msg });
      console.warn(`${step.failTag} provider=${step.name} error=${msg}`);
      // continue cascade
    }
  }

  // All providers failed → local heuristic. Never throw.
  const plan = VideoAnalysisResultFactory(transcript);
  attempts.push({ provider: "local", status: "OK", log: "[FALLBACK_LOCAL]" });
  console.warn("[FALLBACK_LOCAL] all AI providers failed; using local heuristic");
  return { plan, mode: "FALLBACK", attempts, degraded: true };
}
