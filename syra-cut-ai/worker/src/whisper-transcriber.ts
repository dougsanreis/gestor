import { readFile, stat } from "node:fs/promises";
import { env } from "./env.js";
import type { TimedText, Transcript } from "./types.js";

/** Limite do endpoint de transcrição da OpenAI. */
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

function timed(arr: unknown, key: "text" | "word"): TimedText[] {
  if (!Array.isArray(arr)) return [];
  return arr
    .map((x: Record<string, unknown>) => ({
      start: Number(x.start),
      end: Number(x.end),
      text: String(x[key] ?? "").trim(),
    }))
    .filter((x) => Number.isFinite(x.start) && Number.isFinite(x.end) && x.end > x.start && x.text);
}

/**
 * Transcreve com Whisper pedindo tempo por palavra e por frase (o original descartava os
 * tempos e mandava só o texto para a IA, que então inventava timecodes).
 * Nunca inventa texto: sem chave ou com erro, devolve transcrição vazia com o motivo.
 */
export async function transcribeAudio(audioPath: string): Promise<Transcript & { error?: string }> {
  const empty = (error: string): Transcript & { error: string } => ({
    text: "",
    segments: [],
    words: [],
    provider: "none",
    error,
  });
  if (!env.OPENAI_API_KEY)
    return empty("OPENAI_API_KEY ausente: configure o provedor de transcrição (STT).");
  const size = (await stat(audioPath)).size;
  if (size === 0) return empty("áudio extraído está vazio");
  if (size > MAX_UPLOAD_BYTES)
    return empty(`áudio de ${Math.round(size / 1e6)} MB excede 25 MB do Whisper; encurte o vídeo`);

  const form = new FormData();
  form.append("file", new Blob([await readFile(audioPath)], { type: "audio/mpeg" }), "audio.mp3");
  form.append("model", env.WHISPER_MODEL);
  form.append("response_format", "verbose_json");
  form.append("timestamp_granularities[]", "word");
  form.append("timestamp_granularities[]", "segment");
  if (env.WHISPER_LANGUAGE) form.append("language", env.WHISPER_LANGUAGE);

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), env.STT_TIMEOUT_MS);
  try {
    let lastErr = "";
    for (let attempt = 1; attempt <= 3; attempt++) {
      const res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
        method: "POST",
        headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}` },
        body: form,
        signal: ctrl.signal,
      });
      if (res.ok) {
        const j = (await res.json()) as {
          text?: string;
          language?: string;
          segments?: unknown;
          words?: unknown;
        };
        const segments = timed(j.segments, "text");
        const words = timed(j.words, "word");
        const text = (j.text ?? segments.map((s) => s.text).join(" ")).trim();
        if (!text) return empty("a transcrição voltou vazia (sem fala detectada)");
        return { text, language: j.language, segments, words, provider: "openai" };
      }
      lastErr = `HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`;
      // 4xx (exceto 429) não melhora tentando de novo.
      if (res.status < 500 && res.status !== 429) break;
      await new Promise((r) => setTimeout(r, 1500 * attempt));
    }
    return empty(`falha na transcrição (${lastErr})`);
  } catch (e) {
    return empty(
      ctrl.signal.aborted
        ? "transcrição excedeu o tempo limite"
        : `falha na transcrição: ${e instanceof Error ? e.message : e}`,
    );
  } finally {
    clearTimeout(timer);
  }
}
