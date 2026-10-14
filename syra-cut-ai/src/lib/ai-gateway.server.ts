import { createOpenAICompatible } from "@ai-sdk/openai-compatible";

/**
 * Connects the AI SDK to the Lovable AI Gateway. Server-only.
 */
export function createLovableAiGatewayProvider(apiKey: string) {
  return createOpenAICompatible({
    name: "lovable",
    baseURL: "https://ai.gateway.lovable.dev/v1",
    headers: { "Lovable-API-Key": apiKey },
  });
}
