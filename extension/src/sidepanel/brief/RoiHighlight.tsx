import type { BriefRoi } from "./types";

export function RoiHighlight({ roi }: { roi?: BriefRoi | null }) {
  if (!roi) return null;

  return (
    <div class="brief-roi">
      <div class="brief-roi-value">{roi.value}</div>
      <div class="brief-roi-desc brief-text-clamp">{roi.description}</div>
    </div>
  );
}
