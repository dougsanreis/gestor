import { test } from "node:test";
import assert from "node:assert/strict";
import { bearerMatches, isAllowedUrl, isSafeJobId, isUuid } from "../src/security.js";
import { parseCreateJob } from "../src/contract.js";
import { buildEdl, heuristicSegments } from "../src/edl-generator.js";
import {
  buildAssEvents,
  chunkWords,
  escapeText,
  fmtTime,
  remapWords,
} from "../src/ass-caption-generator.js";
import {
  buildTimeline,
  capClips,
  subtractIntervals,
  tightenByWords,
  validateHook,
} from "../src/timeline.js";
import { unstableIntervals } from "../src/scene-analysis.js";
import { PRESETS } from "../src/presets.js";
import { ensureWords } from "../src/pipeline.js";
import { parseSubtitles } from "../src/srt.js";
import { chooseFraming } from "../src/ffmpeg-renderer.js";
import { localHook, normalizePlan, timedTranscript } from "../src/ai-editorial-router.js";
import { storageKey } from "../src/storage.js";
import { clampMaxDuration } from "../src/pipeline.js";
import { env } from "../src/env.js";
import type { EditorialPlan, TimedText } from "../src/types.js";

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

test("legenda: blocos curtos, quebra em pontuação e pausa, nunca atravessa um corte", () => {
  assert.deepEqual(
    chunkWords(words, 3).map((c) => c.map((w) => w.text).join(" ")),
    ["Isso é um", "teste real.", "Depois", "da pausa"],
  );
  const clips = [
    { start: 0, end: 1.2, punch: false, flashIn: false, hook: false },
    { start: 4.5, end: 5.6, punch: true, flashIn: false, hook: false },
  ];
  const per = remapWords(words, clips);
  assert.equal(per.length, 2);
  assert.ok(
    per[1].every((w) => w.start >= 1.2 - 1e-9),
    "palavras do 2º trecho começam depois do 1º",
  );
});

test("legenda karaokê: um evento por palavra com destaque, maiúsculas, título no topo", () => {
  const clips = [{ start: 0, end: 1.8, punch: false, flashIn: false, hook: false }];
  const ev = buildAssEvents({ style: "karaoke", words, clips, title: "Um título de teste" });
  const dialog = ev.filter((e) => e.includes(",Karaoke,"));
  assert.equal(dialog.length, 6);
  assert.match(dialog[0], /\\c&H0000D7FF&.*ISSO/);
  assert.ok(ev.some((e) => e.includes(",Title,") && e.includes("UM TÍTULO DE TESTE")));
  const clean = buildAssEvents({ style: "clean", words, clips });
  assert.ok(
    clean.every((e) => !e.includes("\\c&H")),
    "estilo limpo sem destaque",
  );
});

test("ASS: escapa override tags e formata tempo", () => {
  assert.equal(escapeText("oi {\\b1}mundo\\N"), "oi b1mundoN");
  assert.equal(fmtTime(3661.239), "1:01:01.24");
});

test("borrão: detecta giro sustentado e ignora pico curto", () => {
  const series: Array<[number, number]> = [];
  for (let i = 0; i < 220; i++) {
    const t = i / 10;
    let b = 4.5;
    if (t >= 8.8 && t < 10.8) b = 7.5; // giro de 2 s
    if (t >= 5.0 && t < 5.3) b = 8.8; // pico de 0,3 s (movimento normal)
    if (t === 9.5) b = 5.0; // uma amostra baixa no meio do giro não quebra o trecho
    series.push([t, b]);
  }
  const out = unstableIntervals(series);
  assert.equal(out.length, 1);
  assert.ok(out[0].start < 8.8 && out[0].end > 10.7, JSON.stringify(out));
});

test("timeline: remove trechos ruins, faz jump cuts e alterna punch-in", () => {
  const ws = [
    { start: 0.2, end: 0.6, text: "a" },
    { start: 0.7, end: 1.1, text: "b" },
    { start: 2.5, end: 2.9, text: "c" }, // pausa de 1,4 s antes
    { start: 3.0, end: 3.4, text: "d" },
    { start: 6.5, end: 7.0, text: "e" },
    { start: 7.1, end: 7.6, text: "f" },
  ];
  assert.deepEqual(subtractIntervals([{ start: 0, end: 8 }], [{ start: 4, end: 6 }]), [
    { start: 0, end: 4 },
    { start: 6, end: 8 },
  ]);
  assert.equal(tightenByWords([{ start: 0, end: 8 }], ws, 0.3).length, 3);
  assert.equal(tightenByWords([{ start: 0, end: 8 }], ws, 0.8).length, 3);
  const tl = buildTimeline({
    segments: [{ start: 0, end: 8 }],
    words: ws,
    bad: [{ start: 4, end: 6 }],
    hook: { start: 6.44, end: 7.66 },
    preset: PRESETS.viral_cut,
  });
  assert.equal(tl[0].hook, true);
  assert.equal(tl[1].flashIn, true);
  assert.deepEqual(
    tl.slice(1).map((c) => c.punch),
    [false, true, false],
  );
  const near = buildTimeline({
    segments: [{ start: 0, end: 8 }],
    words: ws,
    bad: [],
    hook: { start: 2.44, end: 3.46 },
    preset: PRESETS.viral_cut,
  });
  assert.ok(!near[0].hook, "gancho perto do início não é repetido");
  assert.ok(
    tl.every((c) => !(c.start < 6 && c.end > 4)),
    "nada do trecho ruim entra",
  );
  const clean = buildTimeline({
    segments: [{ start: 0, end: 8 }],
    words: ws,
    bad: [],
    hook: { start: 2.44, end: 3.46 },
    preset: PRESETS.clean_caption,
  });
  assert.ok(clean.every((c) => !c.hook && !c.punch));
  assert.equal(
    capClips(
      Array.from({ length: 60 }, (_, i) => ({ start: i, end: i + 0.5 })),
      48,
    ).length,
    48,
  );
});

test("gancho: encaixa em palavras, recusa curto/longo e trecho ruim", () => {
  const ws = Array.from({ length: 20 }, (_, i) => ({
    start: i * 0.5,
    end: i * 0.5 + 0.4,
    text: `w${i}`,
  }));
  const ok = validateHook({ start: 1.1, end: 3.3 }, { duration: 10, words: ws, bad: [] });
  assert.ok(ok && ok.start <= 1.0 + 1e-9 && ok.end >= 3.4 - 1e-9, JSON.stringify(ok));
  assert.equal(validateHook({ start: 1, end: 1.4 }, { duration: 10, words: ws, bad: [] }), null);
  assert.equal(validateHook({ start: 1, end: 8 }, { duration: 10, words: ws, bad: [] }), null);
  assert.equal(
    validateHook({ start: 1, end: 3 }, { duration: 10, words: ws, bad: [{ start: 2, end: 2.5 }] }),
    null,
  );
  assert.equal(validateHook(null, { duration: 10, words: ws, bad: [] }), null);
});

test("palavras: sem tempo por palavra, distribui pelo tempo da frase", () => {
  const w = ensureWords({
    text: "",
    words: [],
    provider: "openai",
    segments: [{ start: 0, end: 2, text: "uma frase curta" }],
  });
  assert.equal(w.length, 3);
  assert.ok(w[2].end <= 2 && w[0].start === 0);
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
  assert.equal(p.hook, null);
  assert.deepEqual(
    normalizePlan(
      { title: "x", segments: [{ start: 1, end: 3 }], hook: { start: 2, end: 4 } },
      "xai",
    ).hook,
    { start: 2, end: 4 },
  );
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

test("gancho local (sem IA): prefere pergunta/curiosidade depois dos primeiros segundos", () => {
  const segs = [
    { start: 0.3, end: 3.0, text: "Ninguém te conta isso." },
    { start: 7.0, end: 9.5, text: "Sabe por que seu anúncio não vende?" },
    { start: 10.0, end: 12.0, text: "Então vamos lá." },
  ];
  assert.deepEqual(localHook(segs), { start: 7.0, end: 9.5 });
  assert.equal(localHook([{ start: 8, end: 10, text: "frase comum sem gancho" }]), null);
});

test("legenda SRT/VTT vira transcrição de frases (servidor de teste)", () => {
  const srt =
    "1\n00:00:01,500 --> 00:00:03,250\nOlá <b>mundo</b>\n\n2\n00:00:04,000 --> 00:00:05,000\nSegunda {\\an8}linha\n";
  const t = parseSubtitles(srt);
  assert.deepEqual(t.segments, [
    { start: 1.5, end: 3.25, text: "Olá mundo" },
    { start: 4, end: 5, text: "Segunda linha" },
  ]);
  assert.equal(t.provider, "subtitle");
  const vtt = parseSubtitles("WEBVTT\n\n00:00:00.500 --> 00:00:02.000 align:start\nTeste vtt\n");
  assert.deepEqual(vtt.segments, [{ start: 0.5, end: 2, text: "Teste vtt" }]);
  assert.equal(parseSubtitles("lixo sem tempo").segments.length, 0);
});
