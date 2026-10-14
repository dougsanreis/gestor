import { randomUUID } from "node:crypto";
import { createWriteStream } from "node:fs";
import { mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import express from "express";
import { z } from "zod";
import { env } from "./env.js";
import { enqueue, getJob, QueueFullError } from "./queue.js";
import { localPath, localUrl } from "./storage.js";
import { parseSubtitles } from "./srt.js";
import { DEV_PAGE } from "./dev-page.js";
import { ALL_VARIANTS } from "./types.js";

/** Servidor de teste: só existe com ALLOW_INSECURE_DEV=1 e STORAGE_PROVIDER=local. */
export function devEnabled(): boolean {
  return env.ALLOW_INSECURE_DEV && env.STORAGE_PROVIDER === "local";
}

const DEV_USER = "00000000-0000-4000-8000-000000000000";
const UPLOAD_RE = /^[0-9a-f-]{36}\.(mp4|mov|m4v|webm|mkv)$/;

const JobSchema = z.object({
  upload: z.string().regex(UPLOAD_RE),
  subtitles: z.string().max(2_000_000).optional(),
  variants: z.array(z.enum(["viral_cut", "clean_caption", "speed_dynamic"])).optional(),
  max_duration: z.number().positive().optional(),
});

export function mountDev(app: express.Express): void {
  app.get("/dev", (_req, res) => {
    res.type("html").send(DEV_PAGE);
  });

  // Upload do vídeo como corpo bruto (sem multipart), direto para o disco.
  app.post("/dev/upload", async (req, res) => {
    const ext = String(req.query.ext ?? "mp4").toLowerCase();
    const name = `${randomUUID()}.${ext}`;
    if (!UPLOAD_RE.test(name)) {
      res.status(400).json({ error: "formato não suportado (mp4, mov, m4v, webm, mkv)" });
      return;
    }
    const dest = localPath("uploads", name);
    await mkdir(path.dirname(dest), { recursive: true });
    let received = 0;
    req.on("data", (c: Buffer) => {
      received += c.length;
      if (received > env.MAX_INPUT_BYTES) req.destroy(new Error("arquivo grande demais"));
    });
    try {
      await pipeline(req, createWriteStream(dest));
      res.json({ upload: name, bytes: received });
    } catch (e) {
      res.status(400).json({ error: e instanceof Error ? e.message : String(e) });
    }
  });

  app.post("/dev/jobs", express.json({ limit: "3mb" }), async (req, res) => {
    const parsed = JobSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: "pedido inválido", details: parsed.error.flatten() });
      return;
    }
    const d = parsed.data;
    if (
      !(await stat(localPath("uploads", d.upload)).then(
        () => true,
        () => false,
      ))
    ) {
      res.status(404).json({ error: "upload não encontrado" });
      return;
    }
    const transcript = d.subtitles ? parseSubtitles(d.subtitles) : undefined;
    if (d.subtitles && !transcript?.segments.length) {
      res.status(400).json({ error: "legenda sem blocos válidos (use .srt ou .vtt)" });
      return;
    }
    try {
      const { job } = enqueue({
        job_id: randomUUID(),
        user_id: DEV_USER,
        input_url: localUrl("uploads", d.upload),
        callback_url: `${env.PUBLIC_BASE_URL}/dev/callback`,
        variants: d.variants?.length ? d.variants : ALL_VARIANTS,
        max_duration: d.max_duration,
        local_transcript: transcript,
      });
      res.status(202).json({ id: job.id });
    } catch (e) {
      res.status(e instanceof QueueFullError ? 429 : 500).json({ error: String(e) });
    }
  });

  // O worker manda o callback para si mesmo; a página lê o status em /dev/jobs/:id.
  app.post("/dev/callback", (_req, res) => {
    res.json({ ok: true });
  });

  app.get("/dev/jobs/:id", (req, res) => {
    const job = getJob(req.params.id);
    if (!job) {
      res.status(404).json({ error: "not found" });
      return;
    }
    res.json({
      id: job.id,
      status: job.status,
      progress: job.progress,
      title: job.title,
      transcript: job.transcript,
      error: job.error,
      logs: job.logs,
      variants: job.variants,
      report_url: job.report_path ? localUrl(env.REPORTS_BUCKET, job.report_path) : null,
    });
  });

  app.get(/^\/files\/([a-z-]+)\/(.+)$/, (req, res) => {
    const params = req.params as unknown as Record<string, string>;
    let file: string;
    try {
      file = localPath(params[0], decodeURIComponent(params[1]));
    } catch {
      res.status(400).end();
      return;
    }
    // `root` = pasta do storage: a regra de dotfiles vale só para o caminho dentro dela. Antes o
    // caminho absoluto incluía ".local-storage" e o Express recusava tudo com 404.
    const root = path.resolve(env.LOCAL_STORAGE_DIR);
    res.sendFile(path.relative(root, file), { root, dotfiles: "deny" }, (err) => {
      if (err && !res.headersSent) res.status(404).end();
    });
  });

  app.get("/favicon.ico", (_req, res) => {
    res.status(204).end();
  });
}
