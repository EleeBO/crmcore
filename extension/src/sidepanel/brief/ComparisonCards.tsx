import type { BriefComparison } from "./types";

export function ComparisonCards({
  comparison,
}: {
  comparison?: BriefComparison | null;
}) {
  if (!comparison) return null;

  return (
    <div class="brief-comparison">
      <div class="brief-comparison-card brief-comparison-card--current">
        <div class="brief-comparison-name">{comparison.current.name}</div>
        <div class="brief-comparison-price">{comparison.current.price}</div>
        {comparison.current.cons && (
          <div class="brief-comparison-info">{comparison.current.cons}</div>
        )}
      </div>
      <div class="brief-comparison-card brief-comparison-card--proposed">
        <div class="brief-comparison-name">{comparison.proposed.name}</div>
        <div class="brief-comparison-price">{comparison.proposed.price}</div>
        {comparison.proposed.pros && (
          <div class="brief-comparison-info">{comparison.proposed.pros}</div>
        )}
      </div>
    </div>
  );
}
