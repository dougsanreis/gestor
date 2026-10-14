import { VARIANT_SPECS, type VariantResult } from "./job-contract";

/**
 * Generates simulated variant results when no worker is configured. NEVER
 * produces a fake rendered MP4 — `output_url`/`preview_url` stay null. The UI
 * shows the SIM badge and disables download. Status uses the per-variant
 * READY_FOR_HUMAN_REVIEW so the review screen still renders 3 cards.
 */
export function buildSimulatedVariants(captionText?: string | null): VariantResult[] {
  const caption =
    (captionText && captionText.trim().slice(0, 800)) ||
    "Legenda simulada — conecte o worker real para gerar a transcrição editada.";
  return VARIANT_SPECS.map((spec) => ({
    id: spec.id,
    label: spec.label,
    status: "VARIANT_READY_FOR_HUMAN_REVIEW",
    output_path: null,
    output_url: null,
    preview_url: null,
    download_url: null,
    share_url: null,
    editable_caption_text: caption,
    render_logs: ["[SIM] worker ausente — variante registrada em modo simulado."],
    duration: 42.4,
    size: null,
    simulated: true,
    error: null,
  }));
}
