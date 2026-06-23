import { describe, it, expect, vi } from "vitest";
import { h } from "preact";
import { render } from "@testing-library/preact";
import { LiveCallPanel } from "./LiveCallPanel";
import type { LiveCallCallbacks } from "./mount";

describe("LiveCallPanel", () => {
  it("should render the panel with placeholder text", () => {
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };

    const { container } = render(h(LiveCallPanel, { callbacks }));
    const panel = container.querySelector(".lc-panel");
    expect(panel).toBeTruthy();
  });

  it("should render child components", () => {
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };

    const { container } = render(h(LiveCallPanel, { callbacks }));
    // RecordingBar renders СТОП button
    expect(container.querySelector(".lc-rec-bar")).toBeTruthy();
    // ConnectionStatus renders WS/STT dots
    expect(container.querySelector(".lc-conn")).toBeTruthy();
    // TranscriptFeed renders transcript section
    expect(container.querySelector(".lc-transcript")).toBeTruthy();
  });
});
