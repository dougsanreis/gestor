import { generateObject } from "ai";
import { z } from "zod";
import { createLovableAiGatewayProvider } from "./ai-gateway.server";

/**
 * SYRA Viral Intelligence engine — server-only.
 *
 * Runs the Narrative → Emotion → Viral Moment → Identity → Retention → Share →
 * Viral Score V2 → Rhythm → Editorial layers over a REAL transcript using
 * Lovable AI. It never fabricates a transcript: callers must pass real text.
 */

const intelligenceSchema = z.object({
  narrative: z.object({
    hero: z.string(),
    problem: z.string(),
    pressure: z.string(),
    decision: z.string(),
    transformation: z.string(),
    proof: z.string(),
    legend: z.string(),
  }),
  emotion_timeline: z
    .array(
      z.object({
        emotion: z.enum([
          "curiosity",
          "interest",
          "tension",
          "escalation",
          "admiration",
          "impact",
          "identity",
        ]),
        start: z.number(),
        end: z.number(),
        note: z.string(),
      }),
    )
    .max(10),
  viral_moments: z
    .array(
      z.object({
        type: z.enum(["status_change", "expectation_break", "shareable_line"]),
        label: z.string(),
        quote: z.string(),
      }),
    )
    .max(8),
  identity: z.object({
    archetype: z.enum([
      "resilient",
      "disciplined",
      "leader",
      "believer",
      "visionary",
      "genius",
      "warrior",
      "entrepreneur",
    ]),
    rationale: z.string(),
  }),
  retention_hotspots: z
    .array(z.object({ second: z.number(), retention: z.number().min(0).max(100), reason: z.string() }))
    .max(8),
  share: z.object({
    reason: z.enum([
      "inspiration",
      "faith",
      "justice",
      "intelligence",
      "overcoming",
      "leadership",
      "discipline",
      "courage",
    ]),
    explanation: z.string(),
  }),
  rhythm: z
    .array(
      z.object({
        phase: z.string(),
        pace: z.enum(["slow", "medium", "fast", "explosive", "pause"]),
      }),
    )
    .max(6),
  editorial_plan: z.object({
    cuts: z.array(z.string()).max(8),
    zooms: z.array(z.string()).max(6),
    captions: z.array(z.string()).max(6),
    cta: z.array(z.string()).max(3),
  }),
  scores: z.object({
    curiosity: z.number().min(0).max(100),
    tension: z.number().min(0).max(100),
    transformation: z.number().min(0).max(100),
    identity: z.number().min(0).max(100),
    share: z.number().min(0).max(100),
    replay: z.number().min(0).max(100),
    viral_score: z.number().min(0).max(100),
  }),
});

export type ViralIntelligence = z.infer<typeof intelligenceSchema>;

const SYSTEM = `Você é o SYRA Viral Intelligence Engine — um sistema de engenharia narrativa, emocional e viral de nível big tech.
Você NÃO é um editor de vídeo. Você analisa o SIGNIFICADO de um conteúdo, não os frames.
Dado o transcript de um vídeo curto, produza a estrutura completa de inteligência viral.

Princípios:
- Narrativa primeiro: identifique herói, problema, pressão, decisão, transformação, prova e lenda.
- Mapeie a curva emocional (curiosity → tension → escalation → admiration → impact → identity) com janelas de tempo plausíveis.
- Detecte momentos virais reais: mudança de status, quebra de expectativa e frases replicáveis (cite a frase do transcript).
- Identidade: quem o espectador deseja SE TORNAR após assistir.
- Retenção: aponte segundos de maior retenção e por quê.
- Compartilhamento: por que alguém enviaria isso a outra pessoa.
- Ritmo: respira → acelera → explosão → silêncio, mapeado às emoções.
- Plano editorial: só agora descreva cortes, zooms, captions e CTA derivados das camadas acima.
- Scores V2 de 0 a 100. viral_score é a síntese ponderada dos demais.
Responda SEMPRE em português. Seja específico e baseado no transcript — nunca invente fatos fora do conteúdo.`;

export async function analyzeViralIntelligence(transcript: string): Promise<ViralIntelligence> {
  const key = process.env.LOVABLE_API_KEY;
  if (!key) throw new Error("LOVABLE_API_KEY ausente no servidor.");

  const gateway = createLovableAiGatewayProvider(key);

  try {
    const { object } = await generateObject({
      model: gateway("google/gemini-3-flash-preview"),
      schema: intelligenceSchema,
      system: SYSTEM,
      prompt: `Transcript do vídeo:\n"""\n${transcript.slice(0, 12000)}\n"""`,
    });
    return object;
  } catch (e) {
    const err = e as { statusCode?: number; status?: number; message?: string };
    const code = err.statusCode ?? err.status;
    if (code === 429) throw new Error("Limite de requisições da IA atingido. Tente novamente em instantes.");
    if (code === 402) throw new Error("Créditos de IA esgotados. Adicione créditos para continuar.");
    throw new Error(err.message ?? "Falha na análise de inteligência viral.");
  }
}
