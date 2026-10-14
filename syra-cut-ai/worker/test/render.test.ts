import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { run, probeMedia, preflightProblems, preflightWarnings } from "../src/ffmpeg-renderer.js";
import { planCut, renderAndValidate } from "../src/pipeline.js";
import type { RouterResult } from "../src/ai-editorial-router.js";
import type { TimedText, Transcript } from "../src/types.js";

let dir = "";
before(async () => {
  dir = await mkdtemp(path.join(tmpdir(), "syra-render-test-"));
});
after(async () => {
  await rm(dir, { recursive: true, force: true });
});

async function synth(
  name: string,
  size: string,
  opts: { audio: boolean; seconds: number; rate?: number },
): Promise<string> {
  const out = path.join(dir, name);
  const args = [
    "-nostdin",
    "-y",
    "-v",
    "error",
    "-f",
    "lavfi",
    "-i",
    `testsrc2=size=${size}:rate=${opts.rate ?? 30}`,
  ];
  if (opts.audio) args.push("-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100");
  args.push(
    "-t",
    String(opts.seconds),
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-pix_fmt",
    "yuv420p",
  );
  if (opts.audio) args.push("-c:a", "aac", "-ac", "1");
  args.push(out);
  await run("ffmpeg", args);
  return out;
}

function fakeTranscript(): Transcript {
  const segments: TimedText[] = [
    { start: 0.3, end: 3.0, text: "Primeira frase do teste." },
    { start: 3.2, end: 6.4, text: "Segunda frase continua." },
    { start: 9.0, end: 12.5, text: "Depois da pausa vem a terceira." },
  ];
  const words: TimedText[] = segments.flatMap((s) => {
    const ws = s.text.split(" ");
    const step = (s.end - s.start) / ws.length;
    return ws.map((w, i) => ({
      start: s.start + i * step,
      end: s.start + (i + 1) * step - 0.02,
      text: w,
    }));
  });
  return { text: segments.map((s) => s.text).join(" "), segments, words, provider: "openai" };
}

const router = (segments: { start: number; end: number }[]): RouterResult => ({
  plan: {
    title: "t",
    hooks: [],
    segments: segments.map((s) => ({ ...s, keep: true, reason: "teste" })),
    virality_score: 60,
    provider: "anthropic",
  },
  mode: "FULL",
  attempts: [],
});

for (const c of [
  { name: "horizontal 16:9 → fundo desfocado", size: "1280x720", framing: "blur_fill" },
  { name: "vertical baixa resolução → corte central", size: "474x850", framing: "cover" },
]) {
  test(`render das 3 variantes: ${c.name}`, { timeout: 300_000 }, async () => {
    const src = await synth(`${c.framing}.mp4`, c.size, { audio: true, seconds: 14 });
    const probe = await probeMedia(src);
    assert.deepEqual(preflightProblems(probe), []);
    const transcript = fakeTranscript();
    // IA propõe trechos fora de ordem e com timecodes aproximados.
    const plan = planCut({
      probe,
      transcript,
      router: router([
        { start: 9.1, end: 12.3 },
        { start: 0.4, end: 6.2 },
      ]),
      maxTotal: 90,
    });
    assert.equal(plan.framing, c.framing);
    assert.equal(plan.edl.segments.length, 2);
    const work = path.join(dir, `work-${c.framing}`);
    const rendered = await renderAndValidate({
      inputPath: src,
      workDir: work,
      variants: ["viral_cut", "clean_caption", "speed_dynamic"],
      transcript,
      plan,
    });
    for (const r of rendered) {
      assert.ok(r.ok, `${r.id}: ${r.error}`);
      assert.equal(r.width, 1080);
      assert.equal(r.height, 1920);
      assert.equal(r.v_codec, "h264");
      assert.equal(r.a_codec, "aac");
      assert.match(r.sha256 ?? "", /^[0-9a-f]{64}$/);
    }
    const speed = rendered.find((r) => r.id === "speed_dynamic")!;
    const viral = rendered.find((r) => r.id === "viral_cut")!;
    assert.ok(
      Math.abs(speed.duration! - viral.duration! / 1.08) < 0.4,
      `${speed.duration} vs ${viral.duration}`,
    );
  });
}

test("preflight: vídeo sem áudio é recusado antes de gastar STT/IA/render", async () => {
  const src = await synth("mudo.mp4", "640x360", { audio: false, seconds: 3 });
  const problems = preflightProblems(await probeMedia(src));
  assert.ok(
    problems.some((p) => p.includes("sem áudio")),
    problems.join("; "),
  );
});

test("preflight: arquivo que não é vídeo falha com erro (não segue com duração 0)", async () => {
  await assert.rejects(() => probeMedia(path.join(dir, "nao-existe.mp4")));
});

test("preflight: avisa resolução baixa", async () => {
  const src = await synth("baixa.mp4", "474x850", { audio: true, seconds: 2 });
  assert.ok(preflightWarnings(await probeMedia(src)).some((w) => w.includes("resolução baixa")));
});
