import { describe, it, expect, beforeEach } from "vitest";
import { h } from "preact";
import { render } from "@testing-library/preact";
import { ConnectionStatus } from "./ConnectionStatus";
import { wsConnectedSignal, sttActiveSignal } from "./store";

describe("ConnectionStatus", () => {
  beforeEach(() => {
    wsConnectedSignal.value = false;
    sttActiveSignal.value = false;
  });

  it("should render connection status indicators", () => {
    const { container } = render(h(ConnectionStatus, {}));
    const conn = container.querySelector(".lc-conn");
    expect(conn).toBeTruthy();
  });

  it("should show 2 connection dots", () => {
    const { container } = render(h(ConnectionStatus, {}));
    const dots = container.querySelectorAll(".lc-conn-dot");
    expect(dots.length).toBe(2);
  });

  it("should show off state when disconnected", () => {
    wsConnectedSignal.value = false;
    sttActiveSignal.value = false;
    const { container } = render(h(ConnectionStatus, {}));
    const dots = container.querySelectorAll(".lc-conn-dot--off");
    expect(dots.length).toBe(2);
  });

  it("should show on state when connected", () => {
    wsConnectedSignal.value = true;
    sttActiveSignal.value = true;
    const { container } = render(h(ConnectionStatus, {}));
    const dots = container.querySelectorAll(".lc-conn-dot--on");
    expect(dots.length).toBe(2);
  });

  it("should show mixed state when partially connected", () => {
    wsConnectedSignal.value = true;
    sttActiveSignal.value = false;
    const { container } = render(h(ConnectionStatus, {}));
    const onDots = container.querySelectorAll(".lc-conn-dot--on");
    const offDots = container.querySelectorAll(".lc-conn-dot--off");
    expect(onDots.length).toBe(1);
    expect(offDots.length).toBe(1);
  });
});
