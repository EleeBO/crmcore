import { describe, it, expect, beforeEach } from "vitest";
import { h } from "preact";
import { render } from "@testing-library/preact";
import { TalkRatioBar } from "./TalkRatioBar";
import { talkRatioSignal } from "./store";

describe("TalkRatioBar", () => {
  beforeEach(() => {
    talkRatioSignal.value = {
      managerPercent: 50,
      clientPercent: 50,
      waveform: [],
    };
  });

  it("should render the talk ratio bar with manager and client percentages", () => {
    const { container } = render(h(TalkRatioBar, {}));
    const ratioDiv = container.querySelector(".lc-ratio");
    expect(ratioDiv).toBeTruthy();

    const labels = container.querySelectorAll(".lc-ratio-label");
    expect(labels.length).toBe(2);
    expect(labels[0].textContent).toContain("Вы");
    expect(labels[0].textContent).toContain("50%");
    expect(labels[1].textContent).toContain("Клиент");
    expect(labels[1].textContent).toContain("50%");
  });

  it("should render a fill bar with correct width based on manager percent", () => {
    talkRatioSignal.value = {
      managerPercent: 65,
      clientPercent: 35,
      waveform: [],
    };

    const { container } = render(h(TalkRatioBar, {}));
    const fill = container.querySelector(".lc-ratio-fill");
    expect(fill?.getAttribute("style")).toContain("width: 65%");
  });

  it("should render a hint when manager talks more than 65%", () => {
    talkRatioSignal.value = {
      managerPercent: 70,
      clientPercent: 30,
      waveform: [],
    };

    const { container } = render(h(TalkRatioBar, {}));
    const hint = container.querySelector(".lc-ratio-hint");
    expect(hint?.textContent).toBe("Дайте клиенту больше говорить");
    // CSS color values are converted to rgb by the browser
    expect(hint?.getAttribute("style")).toMatch(/color:\s*(#854F0B|rgb\(133,\s*79,\s*11\))/);
  });

  it("should render a hint when manager talks less than 35%", () => {
    talkRatioSignal.value = {
      managerPercent: 30,
      clientPercent: 70,
      waveform: [],
    };

    const { container } = render(h(TalkRatioBar, {}));
    const hint = container.querySelector(".lc-ratio-hint");
    expect(hint?.textContent).toBe("Перехватите инициативу");
    // CSS color values are converted to rgb by the browser
    expect(hint?.getAttribute("style")).toMatch(/color:\s*(#854F0B|rgb\(133,\s*79,\s*11\))/);
  });

  it("should render a hint when talk ratio is balanced (35-65%)", () => {
    talkRatioSignal.value = {
      managerPercent: 50,
      clientPercent: 50,
      waveform: [],
    };

    const { container } = render(h(TalkRatioBar, {}));
    const hint = container.querySelector(".lc-ratio-hint");
    expect(hint?.textContent).toBe("Отличный баланс");
    // CSS color values are converted to rgb by the browser
    expect(hint?.getAttribute("style")).toMatch(/color:\s*(#3B6D11|rgb\(59,\s*109,\s*17\))/);
  });

  it("should render waveform bars when waveform data is present", () => {
    talkRatioSignal.value = {
      managerPercent: 50,
      clientPercent: 50,
      waveform: [
        { speaker: "manager", amplitude: 0.5 },
        { speaker: "client", amplitude: 0.8 },
      ],
    };

    const { container } = render(h(TalkRatioBar, {}));
    const waveform = container.querySelector(".lc-waveform");
    expect(waveform).toBeTruthy();

    const bars = container.querySelectorAll(".lc-wave-bar");
    expect(bars.length).toBe(2);

    expect(bars[0]?.className).toContain("lc-wave-manager");
    expect(bars[1]?.className).toContain("lc-wave-client");
  });

  it("should calculate correct waveform bar heights", () => {
    talkRatioSignal.value = {
      managerPercent: 50,
      clientPercent: 50,
      waveform: [
        { speaker: "manager", amplitude: 0.5 },
        { speaker: "client", amplitude: 1.0 },
      ],
    };

    const { container } = render(h(TalkRatioBar, {}));
    const bars = container.querySelectorAll(".lc-wave-bar");

    // height = 3 + amplitude * 13
    // For amplitude 0.5: 3 + 0.5 * 13 = 9.5px
    expect(bars[0].getAttribute("style")).toContain("height: 9.5px");

    // For amplitude 1.0: 3 + 1.0 * 13 = 16px
    expect(bars[1].getAttribute("style")).toContain("height: 16px");
  });

  it("should not render waveform when waveform array is empty", () => {
    talkRatioSignal.value = {
      managerPercent: 50,
      clientPercent: 50,
      waveform: [],
    };

    const { container } = render(h(TalkRatioBar, {}));
    const waveform = container.querySelector(".lc-waveform");
    expect(waveform).toBeFalsy();
  });
});
