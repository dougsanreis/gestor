import { env } from "./env.js";
import { ffmpegVersion } from "./ffmpeg-renderer.js";

export async function getHealth() {
  const ffmpeg = await ffmpegVersion();
  const storage = env.SUPABASE_URL && env.SUPABASE_SERVICE_ROLE_KEY ? "ONLINE" : "OFFLINE";
  const stt = env.OPENAI_API_KEY ? "ONLINE" : "OFFLINE";
  // Sem FFmpeg, storage ou STT nenhum job consegue terminar READY: o worker está degradado.
  const status = ffmpeg && storage === "ONLINE" && stt === "ONLINE" ? "ok" : "degraded";
  return {
    status,
    ffmpeg: ffmpeg ? "ONLINE" : "OFFLINE",
    providers: {
      anthropic: env.ANTHROPIC_API_KEY ? "ONLINE" : "OFFLINE",
      xai: env.XAI_API_KEY ? "ONLINE" : "OFFLINE",
      mistral: env.MISTRAL_API_KEY ? "ONLINE" : "OFFLINE",
      whisper: stt,
    },
    storage,
    uptime_s: Math.round(process.uptime()),
  };
}
