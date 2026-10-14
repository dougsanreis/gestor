import express from "express";
import { configProblems, env } from "./env.js";
import { enqueue, getJob, QueueFullError, retryJob } from "./queue.js";
import { getHealth } from "./health.js";
import { parseCreateJob } from "./contract.js";
import { bearerMatches, isSafeJobId } from "./security.js";

const problems = configProblems();
if (problems.length) {
  console.error(
    `[syra-worker] configuração insegura, não vou subir:\n - ${problems.join("\n - ")}`,
  );
  process.exit(1);
}
if (env.ALLOW_INSECURE_DEV)
  console.warn("[syra-worker] ALLOW_INSECURE_DEV=1: NÃO use em produção.");

const app = express();
app.disable("x-powered-by");
// Worker é servidor-para-servidor: sem CORS (o original liberava qualquer origem).
app.use(express.json({ limit: "256kb" }));

function auth(req: express.Request, res: express.Response, next: express.NextFunction) {
  if (env.ALLOW_INSECURE_DEV && !env.WORKER_API_KEY) return next();
  if (!bearerMatches(req.header("authorization"), env.WORKER_API_KEY)) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }
  next();
}

app.get("/health", async (_req, res) => {
  res.json(await getHealth());
});

const createJob: express.RequestHandler = (req, res) => {
  const parsed = parseCreateJob(req.body);
  if (!parsed.ok) {
    res.status(parsed.status).json({ error: parsed.error, details: parsed.details });
    return;
  }
  try {
    const { job, duplicate } = enqueue(parsed.payload);
    res.status(duplicate ? 200 : 202).json({ id: job.id, status: job.status, duplicate });
  } catch (e) {
    if (e instanceof QueueFullError) {
      res.status(429).json({ error: e.message });
      return;
    }
    throw e;
  }
};

app.post("/jobs", auth, createJob);
// O despachante do app usa /process.
app.post("/process", auth, createJob);

app.get("/jobs/:id", auth, (req, res) => {
  const job = isSafeJobId(req.params.id) ? getJob(req.params.id) : undefined;
  if (!job) {
    res.status(404).json({ error: "not found" });
    return;
  }
  res.json(job);
});

app.post("/jobs/:id/retry", auth, (req, res) => {
  const job = isSafeJobId(req.params.id) ? retryJob(req.params.id) : undefined;
  if (!job) {
    res.status(404).json({ error: "not found" });
    return;
  }
  res.json({ id: job.id, status: job.status });
});

app.use(
  (err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error("[syra-worker] erro não tratado", err);
    res.status(500).json({ error: "internal error" });
  },
);

app.listen(env.PORT, () => {
  console.log(`[syra-worker] ouvindo na porta ${env.PORT}`);
});
