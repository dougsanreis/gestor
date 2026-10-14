/** Share utilities. Safe for client + server. */

export function buildWhatsAppUrl(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

export function buildShareMessage(opts: {
  title?: string | null;
  url: string;
  hook?: string | null;
}): string {
  const parts: string[] = [];
  if (opts.hook) parts.push(opts.hook);
  else if (opts.title) parts.push(opts.title);
  parts.push(opts.url);
  parts.push("— editado com SYRA VideoOS");
  return parts.join("\n\n");
}

export async function copyToClipboard(text: string): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.clipboard) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
