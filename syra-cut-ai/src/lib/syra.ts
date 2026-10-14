import type { Database } from "@/integrations/supabase/types";

export type VideoJob = Database["public"]["Tables"]["video_jobs"]["Row"];
export type VideoJobEvent = Database["public"]["Tables"]["video_job_events"]["Row"];
export type VideoAsset = Database["public"]["Tables"]["video_assets"]["Row"];
export type VideoJobStatus = Database["public"]["Enums"]["video_job_status"];

export type StatusTone = "neutral" | "info" | "accent" | "success" | "danger";

export interface StatusMeta {
  label: string;
  description: string;
  tone: StatusTone;
}

/** Ordered pipeline stages (FAILED is handled separately). */
export const PIPELINE_ORDER: VideoJobStatus[] = [
  "UPLOADED",
  "QUEUED",
  "PROCESSING",
  "TRANSCRIBING",
  "ANALYZING",
  "CUTTING",
  "RENDERING",
  "VALIDATING",
  "READY_FOR_HUMAN_REVIEW",
];

export const STATUS_META: Record<VideoJobStatus, StatusMeta> = {
  UPLOADED: { label: "Enviado", description: "Arquivo recebido no storage.", tone: "neutral" },
  QUEUED: { label: "Na fila", description: "Aguardando o worker externo.", tone: "info" },
  PROCESSING: { label: "Processando", description: "Worker iniciou o pipeline.", tone: "info" },
  TRANSCRIBING: { label: "Transcrevendo", description: "Gerando transcrição real (STT).", tone: "info" },
  ANALYZING: { label: "Analisando", description: "Hook detection e ranking de segmentos.", tone: "accent" },
  CUTTING: { label: "Cortando", description: "Silence removal e smart cut.", tone: "accent" },
  RENDERING: { label: "Renderizando", description: "FFmpeg gerando 9:16.", tone: "accent" },
  VALIDATING: { label: "Validando", description: "ffprobe conferindo o MP4 final.", tone: "info" },
  READY_FOR_HUMAN_REVIEW: { label: "Pronto p/ revisão", description: "Aguardando revisão humana.", tone: "success" },
  FAILED: { label: "Falhou", description: "O pipeline reportou um erro.", tone: "danger" },
};

export function statusMeta(status: VideoJobStatus): StatusMeta {
  return STATUS_META[status] ?? STATUS_META.UPLOADED;
}

export function stageIndex(status: VideoJobStatus): number {
  return PIPELINE_ORDER.indexOf(status);
}

export function isTerminal(status: VideoJobStatus): boolean {
  return status === "READY_FOR_HUMAN_REVIEW" || status === "FAILED";
}

export function isProcessing(status: VideoJobStatus): boolean {
  return !isTerminal(status) && status !== "UPLOADED";
}

// ---- Capability Matrix ----
export type CapabilityStatus = "ACTIVE" | "CONFIG_REQUIRED" | "PLANNED" | "FAILED";

export interface Capability {
  name: string;
  status: CapabilityStatus;
  evidence: string;
  artifact: string;
  priority: "P0" | "P1" | "P2";
  roi: "Alto" | "Médio" | "Baixo";
}

export const CAPABILITY_MATRIX: Capability[] = [
  { name: "Upload de vídeo", status: "ACTIVE", evidence: "Drag & drop + storage", artifact: "source.mp4", priority: "P0", roi: "Alto" },
  { name: "Storage seguro", status: "ACTIVE", evidence: "Buckets por user_id/job_id", artifact: "source-videos/*", priority: "P0", roi: "Alto" },
  { name: "Job tracking", status: "ACTIVE", evidence: "Tabela video_jobs + status", artifact: "video_jobs", priority: "P0", roi: "Alto" },
  { name: "Logs técnicos", status: "ACTIVE", evidence: "Tabela video_job_events", artifact: "video_job_events", priority: "P0", roi: "Médio" },
  { name: "Worker externo", status: "CONFIG_REQUIRED", evidence: "Requer WORKER_API_URL/KEY", artifact: "POST /process", priority: "P0", roi: "Alto" },
  { name: "Transcrição (STT)", status: "CONFIG_REQUIRED", evidence: "Whisper/WhisperX no worker", artifact: "transcript", priority: "P0", roi: "Alto" },
  { name: "Legendas sincronizadas", status: "CONFIG_REQUIRED", evidence: "ASS gerado do transcript", artifact: "captions.ass", priority: "P0", roi: "Alto" },
  { name: "Cortes (silence/smart)", status: "CONFIG_REQUIRED", evidence: "Silence + smart cut", artifact: "cut_plan.json", priority: "P1", roi: "Alto" },
  { name: "Render final 9:16", status: "CONFIG_REQUIRED", evidence: "FFmpeg no worker", artifact: "final_*.mp4", priority: "P0", roi: "Alto" },
  { name: "Validação ffprobe", status: "CONFIG_REQUIRED", evidence: "1080x1920 h264 >3s", artifact: "mission_report.json", priority: "P0", roi: "Alto" },
];

/** Viral Intelligence engines — the strategic core (analysis before render). */
export const INTELLIGENCE_MATRIX: Capability[] = [
  { name: "Narrative Intelligence", status: "ACTIVE", evidence: "Lovable AI sobre transcript real", artifact: "narrative graph", priority: "P0", roi: "Alto" },
  { name: "Emotion Graph", status: "ACTIVE", evidence: "Curva emocional por tempo", artifact: "emotion_timeline", priority: "P0", roi: "Alto" },
  { name: "Viral Moment Detector", status: "ACTIVE", evidence: "Status change / quebra / frase", artifact: "viral_moments", priority: "P0", roi: "Alto" },
  { name: "Identity Engine", status: "ACTIVE", evidence: "Arquétipo do espectador", artifact: "identity", priority: "P0", roi: "Alto" },
  { name: "Retention Engine", status: "ACTIVE", evidence: "Score por segundo", artifact: "retention_hotspots", priority: "P1", roi: "Alto" },
  { name: "Share Engine", status: "ACTIVE", evidence: "Motivo de compartilhamento", artifact: "share", priority: "P1", roi: "Alto" },
  { name: "Viral Score V2", status: "ACTIVE", evidence: "6 eixos + síntese", artifact: "scores", priority: "P1", roi: "Alto" },
  { name: "Rhythm Engine", status: "ACTIVE", evidence: "respira → explode → silêncio", artifact: "rhythm", priority: "P2", roi: "Médio" },
  { name: "Editorial Master Plan", status: "ACTIVE", evidence: "Plano derivado das camadas", artifact: "editorial_plan", priority: "P2", roi: "Alto" },
  { name: "Visual Intelligence", status: "CONFIG_REQUIRED", evidence: "YOLO/MediaPipe no worker", artifact: "reframe/zoom", priority: "P2", roi: "Médio" },
  { name: "Caption Intelligence", status: "CONFIG_REQUIRED", evidence: "WhisperX word align", artifact: "words[]", priority: "P1", roi: "Alto" },
  { name: "Learning Engine", status: "PLANNED", evidence: "Pós-publicação (watch/share)", artifact: "learning", priority: "P2", roi: "Médio" },
];

// ---- Viral Intelligence output (mirror of intelligence.server schema) ----
export type EmotionKind =
  | "curiosity"
  | "interest"
  | "tension"
  | "escalation"
  | "admiration"
  | "impact"
  | "identity";

export const EMOTION_META: Record<EmotionKind, { label: string; color: string }> = {
  curiosity: { label: "Curiosidade", color: "oklch(0.82 0.13 195)" },
  interest: { label: "Interesse", color: "oklch(0.74 0.13 175)" },
  tension: { label: "Tensão", color: "oklch(0.8 0.14 75)" },
  escalation: { label: "Escalada", color: "oklch(0.7 0.18 45)" },
  admiration: { label: "Admiração", color: "oklch(0.7 0.16 295)" },
  impact: { label: "Impacto", color: "oklch(0.64 0.21 18)" },
  identity: { label: "Identidade", color: "oklch(0.74 0.16 155)" },
};

export interface ViralIntelligence {
  narrative: {
    hero: string;
    problem: string;
    pressure: string;
    decision: string;
    transformation: string;
    proof: string;
    legend: string;
  };
  emotion_timeline: { emotion: EmotionKind; start: number; end: number; note: string }[];
  viral_moments: {
    type: "status_change" | "expectation_break" | "shareable_line";
    label: string;
    quote: string;
  }[];
  identity: { archetype: string; rationale: string };
  retention_hotspots: { second: number; retention: number; reason: string }[];
  share: { reason: string; explanation: string };
  rhythm: { phase: string; pace: "slow" | "medium" | "fast" | "explosive" | "pause" }[];
  editorial_plan: { cuts: string[]; zooms: string[]; captions: string[]; cta: string[] };
  scores: {
    curiosity: number;
    tension: number;
    transformation: number;
    identity: number;
    share: number;
    replay: number;
    viral_score: number;
  };
}

export type IntelligenceStatus = "PENDING" | "ANALYZING" | "ACTIVE" | "SIMULATED" | "FAILED";

/** The strategic architecture flow, narrative-first. */
export const ARCH_FLOW = [
  "Narrativa",
  "Emoção",
  "Retenção",
  "Identidade",
  "Editorial",
  "Render",
  "Aprendizado",
];

export const INTELLIGENCE_LAYERS = [
  { n: "01", name: "Narrative Intelligence", desc: "Herói, problema, pressão, decisão, transformação, prova, lenda." },
  { n: "02", name: "Emotion Graph", desc: "Curiosidade → tensão → escalada → admiração → identidade." },
  { n: "03", name: "Viral Moment Detector", desc: "Mudança de status, quebra de expectativa, frases replicáveis." },
  { n: "04", name: "Identity Engine", desc: "Quem o espectador deseja se tornar após assistir." },
  { n: "05", name: "Retention & Share", desc: "Score por segundo e o motivo real do compartilhamento." },
  { n: "06", name: "Editorial Master", desc: "Cortes, zooms, captions e CTA derivados das camadas acima." },
];


// ---- Editorial intelligence flags (SYRA) ----
export interface EditorialCapability {
  name: string;
  reportKey: string;
}

export const EDITORIAL_CAPABILITIES: EditorialCapability[] = [
  { name: "Auto Caption", reportKey: "subtitle_words" },
  { name: "Word-by-word captions", reportKey: "word_timestamps" },
  { name: "Dynamic Highlight", reportKey: "highlights" },
  { name: "Silence Removal", reportKey: "silence_cuts" },
  { name: "Smart Cut", reportKey: "cuts" },
  { name: "Kinetic Captions", reportKey: "kinetic" },
  { name: "Auto Reframe", reportKey: "reframe" },
  { name: "Auto Zoom", reportKey: "zoom" },
  { name: "Hook Detection", reportKey: "hook" },
  { name: "Segment Ranking", reportKey: "segment_ranking" },
  { name: "Virality Score", reportKey: "virality_score" },
];

/** Resolve an editorial feature state from real worker evidence. */
export function editorialState(
  job: Pick<VideoJob, "status" | "technical_report" | "virality_score">,
  cap: EditorialCapability,
): CapabilityStatus {
  if (job.status === "FAILED") return "FAILED";
  const report = (job.technical_report ?? {}) as Record<string, unknown>;
  if (cap.reportKey === "virality_score") {
    return typeof job.virality_score === "number" ? "ACTIVE" : "PLANNED";
  }
  const value = report[cap.reportKey];
  if (value !== undefined && value !== null) return "ACTIVE";
  return "PLANNED";
}

export const UPLOAD_LIMITS = {
  maxSizeBytes: 250 * 1024 * 1024,
  maxSizeLabel: "250MB",
  maxDurationSeconds: 180,
  acceptedTypes: ["video/mp4", "video/quicktime", "video/webm"],
  acceptedExtensions: [".mp4", ".mov", ".webm"],
};

export function formatBytes(bytes?: number | null): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(value < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export function formatDuration(seconds?: number | null): string {
  if (!seconds && seconds !== 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
