import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mountLiveCall, unmountLiveCall, type LiveCallCallbacks } from "./mount";

describe("mount", () => {
  let container: HTMLElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    unmountLiveCall();
    document.body.removeChild(container);
  });

  it("should mount LiveCallPanel with callbacks", () => {
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };

    expect(() => mountLiveCall(container, callbacks)).not.toThrow();
    expect(container.childElementCount).toBeGreaterThan(0);
  });

  it("should guard against double-mount", () => {
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };

    mountLiveCall(container, callbacks);
    const firstChild = container.firstChild;

    mountLiveCall(container, callbacks);
    const secondChild = container.firstChild;

    // Should have re-mounted (cleared old, rendered new)
    expect(firstChild).not.toBe(secondChild);
  });

  it("should unmount and clear container", () => {
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };

    mountLiveCall(container, callbacks);
    expect(container.childElementCount).toBeGreaterThan(0);

    unmountLiveCall();
    expect(container.childElementCount).toBe(0);
  });
});
