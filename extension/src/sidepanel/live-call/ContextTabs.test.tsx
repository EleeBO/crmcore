import { describe, it, expect, vi, beforeEach } from "vitest";
import { h } from "preact";
import { render } from "@testing-library/preact";
import { ContextTabs } from "./ContextTabs";
import { activeTabSignal, briefDataSignal } from "./store";
import type { LiveCallCallbacks } from "./mount";

describe("ContextTabs", () => {
  beforeEach(() => {
    activeTabSignal.value = "hints";
    briefDataSignal.value = null;
  });

  it("should render tab buttons", () => {
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };
    const { container } = render(h(ContextTabs, { callbacks }));
    const tabs = container.querySelectorAll(".lc-tab");
    expect(tabs.length).toBe(4);
  });

  it("should set active class on selected tab", () => {
    activeTabSignal.value = "objections";
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };
    const { container } = render(h(ContextTabs, { callbacks }));
    const activeTab = container.querySelector(".lc-tab--active");
    expect(activeTab?.textContent).toContain("Возражения");
  });

  it("should show objections content when objections tab active", () => {
    activeTabSignal.value = "objections";
    briefDataSignal.value = {
      contact: { role: "Manager", company: "Corp", companyDetail: "", budgetNote: "" },
      profileTags: [],
      painPoints: [],
      focusPoints: [],
      objections: [{ question: "Why?", answer: "Because" }],
      fullBrief: "",
    };
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };
    const { container } = render(h(ContextTabs, { callbacks }));
    const objection = container.querySelector(".lc-objection");
    expect(objection).toBeTruthy();
    expect(objection?.textContent).toContain("Why?");
  });

  it("should show strategy content when strategy tab active", () => {
    activeTabSignal.value = "strategy";
    briefDataSignal.value = {
      contact: { role: "Manager", company: "Corp", companyDetail: "", budgetNote: "" },
      profileTags: [],
      painPoints: [],
      focusPoints: [{ headline: "Focus", detail: "Details" }],
      objections: [],
      fullBrief: "",
    };
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };
    const { container } = render(h(ContextTabs, { callbacks }));
    const focusPoint = container.querySelector(".lc-focus-point");
    expect(focusPoint).toBeTruthy();
    expect(focusPoint?.textContent).toContain("Focus");
  });

  it("should call onTabChange and onBriefingTabActive when tab clicked", () => {
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };
    const { container } = render(h(ContextTabs, { callbacks }));
    const tabs = container.querySelectorAll(".lc-tab");
    const briefingTab = tabs[2] as HTMLButtonElement;
    briefingTab?.click();
    expect(callbacks.onTabChange).toHaveBeenCalledWith("briefing");
    expect(callbacks.onBriefingTabActive).toHaveBeenCalledWith(true);
  });

  it("should show empty state for objections when no data", () => {
    activeTabSignal.value = "objections";
    briefDataSignal.value = {
      contact: { role: "Manager", company: "Corp", companyDetail: "", budgetNote: "" },
      profileTags: [],
      painPoints: [],
      focusPoints: [],
      objections: [],
      fullBrief: "",
    };
    const callbacks: LiveCallCallbacks = {
      onStopRecording: vi.fn(),
      onTabChange: vi.fn(),
      onBriefingTabActive: vi.fn(),
    };
    const { container } = render(h(ContextTabs, { callbacks }));
    const empty = container.querySelector(".lc-tab-empty");
    expect(empty).toBeTruthy();
    expect(empty?.textContent).toContain("Нет данных о возражениях");
  });
});
