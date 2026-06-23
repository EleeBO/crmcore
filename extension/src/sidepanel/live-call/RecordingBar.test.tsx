import { describe, it, expect, vi, beforeEach } from "vitest";
import { h } from "preact";
import { render } from "@testing-library/preact";
import { RecordingBar } from "./RecordingBar";
import { recordingSignal } from "./store";

describe("RecordingBar", () => {
  beforeEach(() => {
    recordingSignal.value = { isRecording: true, elapsedSeconds: 0, micLevel: 0 };
  });

  it("should render recording bar with stop button", () => {
    const onStop = vi.fn();
    const { container } = render(h(RecordingBar, { onStop }));
    const bar = container.querySelector(".lc-rec-bar");
    expect(bar).toBeTruthy();
    const button = container.querySelector(".lc-rec-stop");
    expect(button).toBeTruthy();
  });

  it("should display formatted time MM:SS", () => {
    recordingSignal.value = { isRecording: true, elapsedSeconds: 125, micLevel: 50 };
    const onStop = vi.fn();
    const { container } = render(h(RecordingBar, { onStop }));
    const timer = container.querySelector(".lc-rec-timer");
    expect(timer?.textContent).toBe("02:05");
  });

  it("should call onStop when button clicked", () => {
    const onStop = vi.fn();
    const { container } = render(h(RecordingBar, { onStop }));
    const button = container.querySelector(".lc-rec-stop") as HTMLButtonElement;
    button?.click();
    expect(onStop).toHaveBeenCalled();
  });

  it("should render mic bars", () => {
    const onStop = vi.fn();
    const { container } = render(h(RecordingBar, { onStop }));
    const bars = container.querySelectorAll(".lc-mic-bar");
    expect(bars.length).toBe(5);
  });
});
