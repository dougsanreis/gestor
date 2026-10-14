/**
 * SYRA Worker Contract v1 — shared types between the app and the external
 * FFmpeg/Whisper worker. Safe to import from client and server.
 */

export type VariantId = "viral_cut" | "clean_caption" | "speed_dynamic";

export interface VariantSpec {
  id: VariantId;
  label: string;
  description: string;
  speed: number;
  zoom: boolean;
  captions: boolean;
}

export const VARIANT_SPECS: VariantSpec[] = [
  {
    id: "viral_cut",
    label: "Viral Cut",
    description: "Smart cut + zoom dinâmico + legenda kinetic. Máxima retenção.",
    speed: 1.0,
    zoom: true,
    captions: true,
  },
  {
    id: "clean_caption",
    label: "Clean Caption",
    description: "Sem zoom, legenda limpa, ritmo natural. Versão broadcast.",
    speed: 1.0,
    zoom: false,
    captions: true,
  },
  {
    id: "speed_dynamic",
    label: "Speed Dynamic 1.08x",
    description: "Aceleração sutil + zoom + legendas. Reels/Shorts.",
    speed: 1.08,
    zoom: true,
    captions: true,
  },
];

export type VariantStatus =
  | "VARIANT_QUEUED"
  | "VARIANT_RENDERING"
  | "VARIANT_READY_FOR_HUMAN_REVIEW"
  | "VARIANT_FAILED"
  // legacy aliases tolerated by the UI
  | "PENDING"
  | "RENDERING"
  | "READY"
  | "READY_FOR_HUMAN_REVIEW"
  | "FAILED";

/** Stored on `video_jobs.variants` — one per generated profile. */
export interface VariantResult {
  id: VariantId;
  label: string;
  status: VariantStatus;
  output_path?: string | null;
  output_url?: string | null;
  preview_url?: string | null;
  download_url?: string | null;
  share_url?: string | null;
  editable_caption_text?: string | null;
  render_logs?: string[] | null;
  duration?: number | null;
  size?: number | null;
  simulated?: boolean;
  error?: string | null;
  virality_score?: number | null;
  approved?: boolean;
  approved_at?: string | null;
}

export function isVariantReady(status: VariantStatus | undefined | null): boolean {
  return (
    status === "READY" ||
    status === "READY_FOR_HUMAN_REVIEW" ||
    status === "VARIANT_READY_FOR_HUMAN_REVIEW"
  );
}

/** Payload sent to `POST {WORKER_API_URL}/process`. */
export interface WorkerDispatchPayload {
  job_id: string;
  user_id: string;
  source_file_url: string;
  target_ratio: "9:16";
  max_duration: number;
  callback_url: string;
  variants: { id: VariantId; speed: number; zoom: boolean; captions: boolean }[];
  ai_plan?: AiEditorialPlan | null;
}

/** Pipeline AI degradation level surfaced in the UI badge. */
export type AiPipelineMode = "FULL" | "PARTIAL" | "FALLBACK";

/** Schema returned by the AI Provider Router (Claude → Grok → Mistral → Local). */
export interface AiEditorialPlan {
  title: string;
  hooks: string[];
  captions: { start: number; end: number; text: string }[];
  segments: { start: number; end: number; reason: string; keep: boolean }[];
  variants: { id: VariantId; rationale: string }[];
  virality_score: number;
  provider: "anthropic" | "xai" | "mistral" | "local";
}

export const JOB_STATES = [
  "UPLOADED",
  "QUEUED",
  "PROCESSING",
  "TRANSCRIBING",
  "ANALYZING",
  "CUTTING",
  "RENDERING",
  "VALIDATING",
  "READY_FOR_HUMAN_REVIEW",
  "FAILED",
] as const;
