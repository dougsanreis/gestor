import { useState } from "react";
import {
  Check,
  Download,
  FlaskConical,
  Gauge,
  Link as LinkIcon,
  Loader2,
  MessageCircle,
  Pencil,
  RotateCcw,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  isVariantReady,
  type VariantId,
  type VariantResult,
  type VariantSpec,
} from "@/lib/video/job-contract";
import { buildShareMessage, buildWhatsAppUrl, copyToClipboard } from "@/lib/video/share";

interface Props {
  spec: VariantSpec;
  variant: VariantResult | undefined;
  title?: string | null;
  hook?: string | null;
  onApprove?: (variantId: VariantId, approved: boolean) => void | Promise<void>;
  onEditCaption?: (variantId: VariantId, text: string) => void | Promise<void>;
  onRerender?: (variantId: VariantId) => void | Promise<void>;
  approvingId?: VariantId | null;
  editingId?: VariantId | null;
  rerenderingId?: VariantId | null;
}

export function VariantReviewCard({
  spec,
  variant: v,
  title,
  hook,
  onApprove,
  onEditCaption,
  onRerender,
  approvingId,
  editingId,
  rerenderingId,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(v?.editable_caption_text ?? "");

  const ready = isVariantReady(v?.status);
  const simulated = v?.simulated;
  const url = v?.preview_url ?? v?.output_url ?? null;
  const downloadUrl = v?.download_url ?? v?.output_url ?? url;
  const shareUrl = v?.share_url ?? downloadUrl ?? url;
  const message = shareUrl ? buildShareMessage({ title, hook, url: shareUrl }) : null;
  const approved = !!v?.approved;
  const isApproving = approvingId === spec.id;
  const isEditingSave = editingId === spec.id;
  const isRerendering = rerenderingId === spec.id;
  const rendering = v?.status === "RENDERING" || v?.status === "VARIANT_RENDERING";
  const failed = v?.status === "FAILED" || v?.status === "VARIANT_FAILED";
  const noData = !v;
  if (import.meta.env.DEV) {
    // Diagnóstico solicitado: imprime payload bruto de cada variante.
    // eslint-disable-next-line no-console
    console.debug("[variant]", spec.id, v);
  }

  return (
    <div
      className={`glass-panel flex flex-col rounded-2xl p-4 ${approved ? "ring-1 ring-success/60" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-display text-sm font-semibold">{spec.label}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{spec.description}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {simulated && (
            <span className="flex items-center gap-1 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
              <FlaskConical className="size-3" /> SIM
            </span>
          )}
          {approved && (
            <span className="flex items-center gap-1 rounded bg-success/15 px-1.5 py-0.5 text-[10px] font-semibold text-success">
              <Check className="size-3" /> APROVADA
            </span>
          )}
          {typeof v?.virality_score === "number" && (
            <span className="flex items-center gap-1 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
              <Gauge className="size-3" /> {v.virality_score}
            </span>
          )}
        </div>
      </div>

      <div className="mt-3 flex aspect-[9/16] items-center justify-center overflow-hidden rounded-lg bg-black/40 text-center text-xs text-muted-foreground">
        {url ? (
          <video
            src={url}
            controls
            playsInline
            preload="metadata"
            className="size-full rounded-lg object-contain"
            onError={() => toast.error(`Preview URL inválida para ${spec.label}.`)}
          />
        ) : rendering ? (
          <div className="flex flex-col items-center gap-1">
            <Loader2 className="size-4 animate-spin" /> Renderizando…
          </div>
        ) : simulated ? (
          <div className="px-3">
            <FlaskConical className="mx-auto mb-1 size-4 text-accent" />
            Modo simulado — worker real ainda não configurado.
          </div>
        ) : failed ? (
          <span className="text-destructive">{v?.error ?? "Falhou"}</span>
        ) : noData ? (
          <div className="px-3">
            Variante ainda não foi criada. Gere o plano editorial ou use o modo simulado.
          </div>
        ) : (
          <div className="px-3">
            Aguardando worker · status <code>{v?.status ?? "—"}</code>
          </div>
        )}
      </div>
      {v && !url && !rendering && (
        <div className="mt-2 grid grid-cols-2 gap-1 text-[10px] text-muted-foreground">
          <span>status: <code>{v.status}</code></span>
          <span>sim: <code>{String(!!v.simulated)}</code></span>
          <span>preview: <code>{v.preview_url ? "ok" : "—"}</code></span>
          <span>download: <code>{v.download_url ? "ok" : "—"}</code></span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          className="flex-1"
          disabled={!ready || !downloadUrl}
          asChild={ready && !!downloadUrl}
        >
          {ready && downloadUrl ? (
            <a href={downloadUrl} download>
              <Download className="size-3.5" /> Baixar
            </a>
          ) : (
            <span>
              <Download className="size-3.5" /> Baixar
            </span>
          )}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!ready || !message}
          onClick={async () => {
            if (!message) return;
            const ok = await copyToClipboard(message);
            toast[ok ? "success" : "error"](ok ? "Link copiado." : "Falha ao copiar.");
          }}
          title="Copiar link"
        >
          <LinkIcon className="size-3.5" />
        </Button>
        <Button
          size="sm"
          disabled={!ready || !message}
          asChild={ready && !!message}
          className="glow-border"
        >
          {ready && message ? (
            <a href={buildWhatsAppUrl(message)} target="_blank" rel="noopener noreferrer">
              <MessageCircle className="size-3.5" /> WhatsApp
            </a>
          ) : (
            <span>
              <MessageCircle className="size-3.5" /> WhatsApp
            </span>
          )}
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {onEditCaption && (
          <Button
            size="sm"
            variant="outline"
            className="flex-1"
            onClick={() => {
              setDraft(v?.editable_caption_text ?? "");
              setEditing((e) => !e);
            }}
          >
            <Pencil className="size-3.5" /> {editing ? "Fechar" : "Editar legenda"}
          </Button>
        )}
        {onRerender && (
          <Button
            size="sm"
            variant="outline"
            className="flex-1"
            disabled={isRerendering}
            onClick={() => onRerender(spec.id)}
          >
            {isRerendering ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RotateCcw className="size-3.5" />
            )}
            Re-renderizar
          </Button>
        )}
      </div>

      {editing && onEditCaption && (
        <div className="mt-2 space-y-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={4}
            placeholder="Legenda final exibida no vídeo"
            className="text-xs"
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancelar
            </Button>
            <Button
              size="sm"
              disabled={isEditingSave}
              onClick={async () => {
                await onEditCaption(spec.id, draft);
                setEditing(false);
              }}
            >
              {isEditingSave ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
              Salvar
            </Button>
          </div>
        </div>
      )}

      {onApprove && (
        <Button
          size="sm"
          variant={approved ? "outline" : "default"}
          className="mt-2 w-full"
          disabled={!ready || isApproving}
          onClick={() => onApprove(spec.id, !approved)}
        >
          {isApproving ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
          {approved ? "Desaprovar" : "Aprovar"}
        </Button>
      )}
    </div>
  );
}
