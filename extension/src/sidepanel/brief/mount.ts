import { render, h } from "preact";
import { BriefPanel } from "./BriefPanel";
import type { BriefData } from "./types";
import "./brief.css";

/**
 * Mount/update brief panel into a DOM container.
 * Call with data=null to unmount (clear container).
 */
export function mountBriefPanel(
  container: HTMLElement,
  data: BriefData | null,
  compact = false,
): void {
  if (!data) {
    render(null, container);
    return;
  }
  render(h(BriefPanel, { data, compact }), container);
}

/**
 * Type guard: checks if cached data is v2 BriefData format.
 */
export function isBriefDataV2(data: unknown): data is BriefData {
  return (
    typeof data === "object" &&
    data !== null &&
    "contact" in data &&
    "focusPoints" in data
  );
}
