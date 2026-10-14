export type VariantId = "viral_cut" | "clean_caption" | "speed_dynamic";

export const ALL_VARIANTS: VariantId[] = ["viral_cut", "clean_caption", "speed_dynamic"];

export interface CreateJobPayload {
  job_id: string;
  user_id?: string;
  input_url: string;
  callback_url: string;
  variants?: VariantId[];
  ai_mode?: string;
  /** Duração máxima do corte final em segundos (já considerando a aceleração). */
  max_duration?: number;
  /**
   * Só o servidor de teste preenche (nunca vem do payload HTTP): transcrição já pronta, por
   * exemplo de um .srt enviado na página /dev.
   */
  local_transcript?: Transcript;
}

export type JobStatus =
  | "QUEUED"
  | "DOWNLOADING"
  | "TRANSCRIBING"
  | "ANALYZING"
  | "RENDERING"
  | "UPLOADING"
  | "VALIDATING"
  | "READY"
  | "FAILED";

export interface VariantOutput {
  id: VariantId;
  name: string;
  status: "PENDING" | "RENDERING" | "VALIDATING" | "READY" | "FAILED";
  preview_url?: string;
  download_url?: string;
  share_url?: string;
  storage_path?: string;
  duration?: number;
  size?: number;
  width?: number;
  height?: number;
  v_codec?: string;
  a_codec?: string;
  sha256?: string;
  virality_score?: number;
  error?: string;
}

export interface JobRecord {
  id: string;
  payload: CreateJobPayload;
  status: JobStatus;
  progress: number;
  logs: string[];
  variants: VariantOutput[];
  ai_mode: "FULL" | "PARTIAL" | "FALLBACK";
  ai_provider: "anthropic" | "xai" | "mistral" | "local" | null;
  transcript?: string;
  title?: string;
  virality_score?: number;
  cuts?: number;
  subtitle_words?: number;
  framing?: string;
  report_path?: string;
  error?: string;
  created_at: number;
  updated_at: number;
  attempts: number;
}

/** Palavra/frase com tempo vindos da transcrição (fonte da verdade para legenda e corte). */
export interface TimedText {
  start: number;
  end: number;
  text: string;
}

export interface Transcript {
  text: string;
  language?: string;
  segments: TimedText[];
  words: TimedText[];
  provider: "openai" | "command" | "subtitle" | "none";
}

export interface AiSegment {
  start: number;
  end: number;
  reason: string;
  keep: boolean;
}

export type AiCaption = TimedText;

export interface EditorialPlan {
  title: string;
  hooks: string[];
  segments: AiSegment[];
  /** Frase mais forte (1,5–4 s) repetida no começo como gancho; validada na timeline. */
  hook?: { start: number; end: number } | null;
  virality_score: number;
  provider: "anthropic" | "xai" | "mistral" | "local";
}
