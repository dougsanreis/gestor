import { VARIANT_SPECS, type VariantId, type VariantResult } from "@/lib/video/job-contract";
import { VariantReviewCard } from "@/components/video/VariantReviewCard";

interface Props {
  variants: VariantResult[];
  title?: string | null;
  hook?: string | null;
  onApprove?: (variantId: VariantId, approved: boolean) => void | Promise<void>;
  onEditCaption?: (variantId: VariantId, text: string) => void | Promise<void>;
  onRerender?: (variantId: VariantId) => void | Promise<void>;
  approvingId?: VariantId | null;
  editingId?: VariantId | null;
  rerenderingId?: VariantId | null;
}

export function VariantCards({
  variants,
  title,
  hook,
  onApprove,
  onEditCaption,
  onRerender,
  approvingId,
  editingId,
  rerenderingId,
}: Props) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {VARIANT_SPECS.map((spec) => {
        const v = variants?.find((x) => x.id === spec.id);
        return (
          <VariantReviewCard
            key={spec.id}
            spec={spec}
            variant={v}
            title={title}
            hook={hook}
            onApprove={onApprove}
            onEditCaption={onEditCaption}
            onRerender={onRerender}
            approvingId={approvingId}
            editingId={editingId}
            rerenderingId={rerenderingId}
          />
        );
      })}
    </div>
  );
}
