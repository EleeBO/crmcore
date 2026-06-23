import type { BriefFocusPoint } from "./types";

export function FocusPoints({ points }: { points: BriefFocusPoint[] }) {
  const capped = points.slice(0, 3);
  if (capped.length === 0) return null;

  return (
    <div class="brief-focus">
      <div class="brief-section-label">ФОКУС РАЗГОВОРА</div>
      <div class="brief-focus-list">
        {capped.map((fp, i) => (
          <div key={i} class="brief-focus-item">
            <span class="brief-focus-num">{i + 1}</span>
            <div class="brief-focus-text">
              <span class="brief-focus-headline">{fp.headline}</span>
              {fp.detail && (
                <>
                  {" \u2014 "}
                  <span class="brief-focus-detail">{fp.detail}</span>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
