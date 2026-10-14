import { test } from "node:test";
import assert from "node:assert/strict";
import { bearerMatches, isAllowedUrl, isSafeJobId, isUuid } from "../src/security.js";
import { parseCreateJob } from "../src/contract.js";
import { buildEdl, heuristicSegments } from "../src/edl-generator.js";
import { buildCaptions, countWordsInSegments } from "../src/captions.js";
import { buildAssEvents, escapeText, fmtTime } from "../src/ass-caption-generator.js";
import { chooseFraming } from "../src/ffmpeg-renderer.js";
import { normalizePlan, timedTranscript } from "../src/ai-editorial-router.js";
import { storageKey } from "../src/storage.js";
import { clampMaxDuration } from "../src/pipeline.js";
import { env } from "../src/env.js";
import type { EditorialPlan, TimedText, Transcript } from "../src/types.js";

const E = {
  ...env,
  INPUT_ALLOWED_HOSTS: ["abc.supabase.co"],
  CALLBACK_ALLOWED_HOSTS: ["syra.lovable.app"],
  ALLOW_INSECURE_DEV: false,
};
const JOB = "3f1c2a8e-1b2c-4d5e-8f90-123456789abc";

test("job_id: aceita UUID/slug e recusa path traversal e caracteres de filtro", () => {
  assert.ok(isSafeJobId(JOB));
  assert.ok(isSafeJobId("job_01-a"));
  for (const bad of [
    "../../etc",
    "a/../../home",
    "",
    "a:b",
    "a,b",
    "a'b",
    ".hidden",
    "x".repeat(65),
  ]) {
    assert.equal(isSafeJobId(bad), false, bad);
  }
  assert.ok(isUuid(JOB));
  assert.equal(isUuid("job_01"), false);
});

test("bearer: compara em tempo constante e recusa vazio/errado", () => {
  assert.ok(bearerMatches("Bearer segredo-123", "segredo-123"));
  assert.equal(bearerMatches("Bearer errado", "segredo-123"), false);
  assert.equal(bearerMatches(undefined, "segredo-123"), false);
  assert.equal(bearerMatches("Bearer ", ""), false);
});

test("allowlist de URL: só https e hosts listados (subdomínio ok)", () => {
  assert.ok(isAllowedUrl("https://abc.supabase.co/storage/v1/x", ["abc.supabase.co"]));
  assert.ok(isAllowedUrl("https://cdn.abc.supabase.co/x", ["abc.supabase.co"]));
  assert.equal(isAllowedUrl("http://abc.supabase.co/x", ["abc.supabase.co"]), false);
  assert.equal(isAllowedUrl("https://abc.supabase.co.evil.com/x", ["abc.supabase.co"]), false);
  assert.equal(isAllowedUrl("https://user:pw@abc.supabase.co/x", ["abc.supabase.co"]), false);
  assert.equal(isAllowedUrl("https://169.254.169.254/latest", ["abc.supabase.co"]), false);
  assert.equal(isAllowedUrl("nota url", ["abc.supabase.co"]), false);
});

test("contrato: aceita o payload de video-jobs.functions.ts (output_profiles, max 75)", () => {
  const r = parseCreateJob(
    {
      job_id: JOB,
      user_id: JOB,
      source_file_url: "https://abc.supabase.co/storage/v1/object/sign/source-videos/x.mp4?token=t",
      target_format: "9:16",
      max_duration: 75,
      output_profiles: ["tiktok_viral", "reels_premium", "shorts_clean"],
      callback_url: "https://syra.lovable.app/api/public/update-video-job",
    },
    E,
  );
  assert.ok(r.ok, JSON.stringify(r));
  if (r.ok) {
    assert.equal(r.payload.max_duration, 75);
    assert.equal(r.payload.variants, undefined);
  }
});

test("contrato: aceita o payload de video-worker-client.server.ts (variants como objetos) — antes dava 400", () => {
  const r = parseCreateJob(
    {
      job_id: JOB,
      user_id: JOB,
      source_file_url: "https://abc.supabase.co/storage/v1/object/sign/source-videos/x.mp4?token=t",
      target_ratio: "9:16",
      max_duration: 90,
      callback_url: "https://syra.lovable.app/api/public/update-video-job",
      variants: [
        { id: "viral_cut", speed: 1, zoom: true, captions: true },
        { id: "speed_dynamic", speed: 1.08, zoom: true, captions: true },
      ],
      ai_plan: null,
    },
    E,
  );
  assert.ok(r.ok, JSON.stringify(r));
  if (r.ok) assert.deepEqual(r.payload.variants, ["viral_cut", "speed_dynamic"]);
});

test("contrato: recusa job_id perigoso, host fora da lista e proporção não suportada", () => {
  const base = {
    job_id: JOB,
    source_file_url: "https://abc.supabase.co/x.mp4",
    callback_url: "https://syra.lovable.app/api/public/update-video-job",
  };
  assert.equal(parseCreateJob({ ...base, job_id: "../../tmp" }, E).ok, false);
  assert.equal(parseCreateJob({ ...base, source_file_url: "https://evil.com/x.mp4" }, E).ok, false);
  assert.equal(
    parseCreateJob({ ...base, callback_url: "https://evil.com/steal-key" }, E).ok,
    false,
  );
  assert.equal(parseCreateJob({ ...base, target_ratio: "16:9" }, E).ok, false);
  assert.equal(parseCreateJob({ ...base, variants: ["nao_existe"] }, E).ok, false);
});

const speech: TimedText[] = [
  { start: 0.4, end: 3.2, text: "Olá, hoje eu vou mostrar." },
  { start: 3.4, end: 7.9, text: "O primeiro ponto é simples." },
  { start: 10.5, end: 15.0, text: "Depois de uma pausa longa, o segundo." },
  { start: 15.2, end: 30.0, text: "E aqui um trecho comprido." },
];
const plan = (segments: EditorialPlan["segments"]): EditorialPlan => ({
  title: "t",
  hooks: [],
  segments,
  virality_score: 70,
  provider: "anthropic",
});

test("EDL: encaixa timecodes da IA nos limites de fala e ordena", () => {
  const edl = buildEdl(
    plan([
      { start: 10.6, end: 14.7, keep: true, reason: "b" },
      { start: 0.5, end: 7.5, keep: true, reason: "a" },
    ]),
    { sourceDuration: 30, maxTotal: 90, speech },
  );
  assert.equal(edl.segments.length, 2);
  assert.ok(Math.abs(edl.segments[0].start - 0.28) < 1e-9);
  assert.ok(Math.abs(edl.segments[0].end - 8.02) < 1e-9);
  assert.ok(Math.abs(edl.segments[1].end - 15.12) < 1e-9);
});

test("EDL: fim nunca encaixa no início da frase seguinte (frases coladas)", () => {
  const glued: TimedText[] = [
    { start: 0, end: 5.0, text: "a" },
    { start: 5.05, end: 9, text: "b" },
  ];
  const edl = buildEdl(plan([{ start: 0, end: 4.9, keep: true, reason: "a" }]), {
    sourceDuration: 9,
    maxTotal: 90,
    speech: glued,
  });
  assert.ok(edl.segments[0].end >= 5.0, String(edl.segments[0].end));
});

test("EDL: plano inválido da IA (fora da duração, invertido, curto) cai na heurística de fala", () => {
  const edl = buildEdl(
    plan([
      { start: 50, end: 80, keep: true, reason: "fora" },
      { start: 5, end: 2, keep: true, reason: "invertido" },
      { start: 1, end: 1.4, keep: true, reason: "curto" },
    ]),
    { sourceDuration: 30, maxTotal: 90, speech },
  );
  assert.ok(edl.notes.some((n) => n.includes("heurística")));
  assert.equal(edl.segments.length, 2); // pausa de 2,6 s entre 7,9 e 10,5 vira corte
});

test("EDL: respeita max_duration terminando num limite de fala", () => {
  const edl = buildEdl(plan([{ start: 0, end: 30, keep: true, reason: "tudo" }]), {
    sourceDuration: 30,
    maxTotal: 12,
    speech,
  });
  assert.ok(edl.total_duration <= 12 + 1e-9);
  assert.ok(edl.segments.at(-1)!.end <= 12);
});

test("heurística: sem frases, usa o início até o limite", () => {
  assert.deepEqual(
    heuristicSegments([], 200, 60).map((s) => [s.start, s.end]),
    [[0, 60]],
  );
  assert.equal(clampMaxDuration(undefined), 90);
  assert.equal(clampMaxDuration(1000), 180);
  assert.equal(clampMaxDuration(2), 5);
});

const words: TimedText[] = ["Isso", "é", "um", "teste", "real.", "Depois", "da", "pausa"].map(
  (w, i) => ({
    start: i < 6 ? i * 0.3 : 3 + i * 0.3,
    end: (i < 6 ? i * 0.3 : 3 + i * 0.3) + 0.25,
    text: w,
  }),
);
const transcript: Transcript = {
  text: words.map((w) => w.text).join(" "),
  segments: [],
  words,
  provider: "openai",
};

test("legenda: só palavras reais, blocos de até 4 palavras, quebra em pontuação e pausa", () => {
  const caps = buildCaptions(transcript);
  assert.deepEqual(
    caps.map((c) => c.text),
    ["Isso é um teste", "real.", "Depois", "da pausa"],
  );
  assert.equal(countWordsInSegments(words, [{ start: 0, end: 1.6 }]), 5); // 6ª palavra termina em 1,75 s
});

test("ASS: escapa override tags e remapeia para a linha do tempo do corte", () => {
  assert.equal(escapeText("oi {\\b1}mundo\\N"), "oi b1mundoN");
  assert.equal(fmtTime(3661.239), "1:01:01.24");
  const ev = buildAssEvents(
    "clean",
    [{ start: 10, end: 11, text: "x" }],
    [
      { start: 0, end: 2 },
      { start: 9.5, end: 12 },
    ],
  );
  assert.equal(ev.length, 1);
  assert.match(ev[0], /Dialogue: 0,0:00:02\.50,0:00:03\.50,Clean/);
});

test("enquadramento: 9:16 parecido corta; 16:9 usa fundo desfocado", () => {
  assert.equal(chooseFraming(474, 850), "cover");
  assert.equal(chooseFraming(1080, 1920), "cover");
  assert.equal(chooseFraming(1920, 1080), "blur_fill");
  assert.equal(chooseFraming(1080, 1080), "blur_fill");
});

test("IA: normaliza resposta e transcrição com tempos limita tamanho", () => {
  const p = normalizePlan(
    {
      plan: {
        title: " T ",
        hooks: ["a", 3],
        segments: [{ start: "1", end: 4, reason: "r" }],
        virality_score: 140,
      },
    },
    "xai",
  );
  assert.equal(p.title, "T");
  assert.equal(p.virality_score, 100);
  assert.deepEqual(p.segments, [{ start: 1, end: 4, reason: "r", keep: true }]);
  assert.throws(() => normalizePlan({ title: "x", segments: [] }, "xai"));
  assert.match(timedTranscript(speech, ""), /^\[0\.40-3\.20\] Olá/);
  assert.ok(timedTranscript(speech, "", 40).length <= 40);
});

test("storage: caminho {user}/{job}/ com sufixo de retentativa, sem sobrescrever", () => {
  assert.equal(
    storageKey({ userId: JOB, jobId: "j1", file: "final_viral_cut.mp4", attempt: 1 }),
    `${JOB}/j1/final_viral_cut.mp4`,
  );
  assert.equal(
    storageKey({ userId: JOB, jobId: "j1", file: "final_viral_cut.mp4", attempt: 3 }),
    `${JOB}/j1/final_viral_cut_r3.mp4`,
  );
  assert.equal(
    storageKey({ userId: "x/../y", jobId: "j1", file: "a.json", attempt: 1 }),
    "_sem-usuario/j1/a.json",
  );
});
