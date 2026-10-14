import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { run } from "../src/ffmpeg-renderer.js";

/**
 * Sobe o servidor de teste como o usuário roda (npm run dev:local), com o storage padrão numa
 * pasta que começa com ponto. Regressão: o /files devolvia 404 para tudo dentro de ".local-…".
 */
const PORT = 8800 + Math.floor(Math.random() * 100);
const BASE = `http://localhost:${PORT}`;
const STORAGE = ".local-storage-test";
let server: ChildProcess;
let dir = "";

before(async () => {
  dir = await mkdtemp(path.join(tmpdir(), "syra-dev-test-"));
  server = spawn(process.execPath, ["--import", "tsx", "src/index.ts"], {
    env: {
      ...process.env,
      PORT: String(PORT),
      ALLOW_INSECURE_DEV: "1",
      STORAGE_PROVIDER: "local",
      LOCAL_STORAGE_DIR: STORAGE,
      STT_PROVIDER: "none",
      WORKER_API_KEY: "",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  await new Promise<void>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("servidor não subiu")), 20_000);
    server.stdout!.on("data", (d) => {
      if (String(d).includes("servidor de teste")) {
        clearTimeout(t);
        resolve();
      }
    });
    server.on("exit", (c) => reject(new Error(`servidor saiu com ${c}`)));
  });
});

after(async () => {
  server?.kill();
  await rm(STORAGE, { recursive: true, force: true });
  await rm(dir, { recursive: true, force: true });
});

test(
  "servidor de teste: upload → job com .srt → READY → download do MP4",
  { timeout: 180_000 },
  async () => {
    const src = path.join(dir, "v.mp4");
    await run("ffmpeg", [
      "-nostdin",
      "-y",
      "-v",
      "error",
      "-f",
      "lavfi",
      "-i",
      "testsrc2=size=640x360:rate=30",
      "-f",
      "lavfi",
      "-i",
      "sine=frequency=300",
      "-t",
      "8",
      "-c:v",
      "libx264",
      "-preset",
      "ultrafast",
      "-c:a",
      "aac",
      src,
    ]);
    assert.equal((await fetch(`${BASE}/dev`)).status, 200);
    const up = (await (
      await fetch(`${BASE}/dev/upload?ext=mp4`, { method: "POST", body: await readFile(src) })
    ).json()) as { upload: string };
    assert.match(up.upload, /\.mp4$/);
    assert.equal(
      (await fetch(`${BASE}/files/uploads/${up.upload}`)).status,
      200,
      "o worker precisa conseguir baixar o próprio upload",
    );

    const srt =
      "1\n00:00:00,300 --> 00:00:03,500\nPrimeira frase do teste.\n\n2\n00:00:03,700 --> 00:00:07,600\nSegunda frase continua aqui.\n";
    const job = (await (
      await fetch(`${BASE}/dev/jobs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          upload: up.upload,
          subtitles: srt,
          variants: ["clean_caption"],
          max_duration: 30,
        }),
      })
    ).json()) as { id: string };
    let state: {
      status: string;
      error?: string;
      variants: { status: string; download_url?: string }[];
    } = { status: "", variants: [] };
    for (let i = 0; i < 120 && !["READY", "FAILED"].includes(state.status); i++) {
      await new Promise((r) => setTimeout(r, 1000));
      state = await (await fetch(`${BASE}/dev/jobs/${job.id}`)).json();
    }
    assert.equal(state.status, "READY", state.error);
    const res = await fetch(state.variants[0].download_url!);
    assert.equal(res.status, 200);
    assert.ok((await res.arrayBuffer()).byteLength > 10_000);
    assert.equal((await fetch(`${BASE}/files/uploads/..%2F..%2Fpackage.json`)).status, 400);
    assert.equal((await fetch(`${BASE}/favicon.ico`)).status, 204);
  },
);
