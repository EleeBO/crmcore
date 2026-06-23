/**
 * Side Panel — FEAT-007 migration from popup + widget.
 * Core infrastructure: phase engine, Port, state, settings.
 */

import { API_BASE, BACKEND_WS_URL } from "../shared/constants";
import { WsClient } from "../lib/ws-client";
import type { ExtMessage, WsTranscript, WsError, WsMessage } from "../shared/messages";
import { mountLiveCall, unmountLiveCall, mountRecBarDone, unmountRecBarDone } from "./live-call/mount";
import {
  transcriptSignal, hintSignal, talkRatioSignal,
  recordingSignal, wsConnectedSignal, sttActiveSignal,
  activeTabSignal, briefDataSignal,
} from "./live-call/store";
import type { TranscriptItem } from "./live-call/types";
import type {
  CallAnalyticsWire,
  CallEvaluationResult,
  DiarizedUtterance,
  FollowUpEmail,
  CrmNote,
  WsEvaluationStarted,
  WsEvaluationResult,
  WsEvaluationError,
  WsFollowUpReady,
} from "../shared/evaluation-types";
import { VERDICT_LABELS, VERDICT_COLORS } from "../shared/evaluation-types";
import { isBriefDataV2, mountBriefPanel } from "./brief/mount";
import type { BriefData } from "./brief/types";

// ── Helpers ───────────────────────────────────────────────────────────────

const $ = <T extends HTMLElement>(id: string) =>
  document.getElementById(id) as T | null;

function show(el: HTMLElement | null): void {
  el?.removeAttribute("hidden");
}
function hide(el: HTMLElement | null): void {
  el?.setAttribute("hidden", "");
}

// ── Live-call state (module-level) ────────────────────────────────────────

let transcriptItems: TranscriptItem[] = [];
let recordingTimerInterval: ReturnType<typeof setInterval> | null = null;

function resetSignals(opts: {
  isRecording: boolean;
  wsConnected: boolean;
  briefData: BriefData | null;
}): void {
  transcriptItems = [];
  transcriptSignal.value = [];
  hintSignal.value = null;
  talkRatioSignal.value = { managerPercent: 0, clientPercent: 0, waveform: [] };
  recordingSignal.value = { isRecording: opts.isRecording, elapsedSeconds: 0, micLevel: 0 };
  wsConnectedSignal.value = opts.wsConnected;
  sttActiveSignal.value = true;
  activeTabSignal.value = "hints";
  briefDataSignal.value = opts.briefData;
}

// ── Phase engine ──────────────────────────────────────────────────────────

type Phase = 0 | 1 | 2 | 3 | 4;
let currentPhase: Phase = 0;

function setPhase(phase: Phase): void {
  currentPhase = phase;
  document.querySelectorAll(".phase").forEach((el) => {
    el.classList.toggle("active", el.id === `phase-${phase}`);
  });
  updateHeader(phase);

  // Clean up any leftover splitter inline styles on Phase 2 sections
  if (phase === 2) {
    void chrome.storage.local.remove("layout_phase2");
    const bc = $("briefing-content");
    if (bc) {
      for (const child of Array.from(bc.children)) {
        (child as HTMLElement).style.removeProperty("flex");
      }
    }
  }
}

function updateHeader(phase: Phase): void {
  const statusText = $("status-text");
  const recBtn = $<HTMLButtonElement>("rec-btn");
  const vuMeters = $("vu-meters");

  switch (phase) {
    case 0:
      if (statusText) statusText.textContent = "Готов";
      if (recBtn) recBtn.disabled = true;
      hide(vuMeters);
      break;
    case 1:
      if (statusText) statusText.textContent = "Загрузка...";
      if (recBtn) recBtn.disabled = true;
      hide(vuMeters);
      break;
    case 2:
      if (statusText) statusText.textContent = "Готов";
      void updateRecButtonState();
      hide(vuMeters);
      break;
    case 3:
      if (statusText) statusText.textContent = "Слушаю...";
      show(vuMeters);
      break;
    case 4:
      if (statusText) statusText.textContent = "Звонок завершён";
      hide(vuMeters);
      break;
  }
}

// ── State management (chrome.storage.session) ─────────────────────────────

interface PanelState {
  sessionId: string;
  kbId: string;
  capturing: boolean;
  chunksCount: number;
  briefing: BriefData | null;
  fileNames: string[];
}

const DEFAULT_STATE: PanelState = {
  sessionId: "",
  kbId: "",
  capturing: false,
  chunksCount: 0,
  briefing: null,
  fileNames: [],
};

// Module-level cached panel state (updated by loadState)
let panelState: PanelState = { ...DEFAULT_STATE };

async function loadState(): Promise<PanelState> {
  // Use chrome.storage.local so state survives extension reloads.
  // chrome.storage.session is wiped on every reload, losing the briefing.
  const result = (await chrome.storage.local.get("panel")) as {
    panel?: PanelState;
  };
  panelState = result.panel ?? { ...DEFAULT_STATE };
  return panelState;
}

async function saveState(state: Partial<PanelState>): Promise<void> {
  const current = await loadState();
  await chrome.storage.local.set({ panel: { ...current, ...state } });
}

// ── Port connection to Service Worker ─────────────────────────────────────

let swPort: chrome.runtime.Port | null = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;

function connectPort(): void {
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    updateStatusPill("error", "Расширение недоступно");
    return;
  }
  swPort = chrome.runtime.connect({ name: "sidepanel" });
  swPort.onMessage.addListener((msg) => {
    reconnectAttempts = 0;
    handlePortMessage(msg);
  });
  swPort.onDisconnect.addListener(() => {
    swPort = null;
    reconnectAttempts++;
    const delay = Math.min(1000 * 2 ** reconnectAttempts, 30_000);
    setTimeout(connectPort, delay);
  });
  // Request current state from SW
  swPort.postMessage({ type: "GET_SESSION_STATE" });
}

function updateStatusPill(variant: "ok" | "error" | "warn", text: string): void {
  const pill = $("status-pill");
  if (!pill) return;
  pill.className = `status-pill ${variant}`;
  pill.textContent = text;
  show(pill);
}

// ── Port message handler ──────────────────────────────────────────────────

function handlePortMessage(msg: Record<string, unknown>): void {
  switch (msg.type) {
    case "SESSION_STATE":
      restoreFromHandshake(
        msg as unknown as {
          capturing: boolean;
          sessionId: string;
          kbId: string;
          wsConnected: boolean;
        }
      );
      break;
    case "WS_MESSAGE":
      handleWsMessage(msg.payload as WsMessage);
      break;
    case "AUDIO_LEVEL":
      console.log("[Panel] AUDIO_LEVEL mic=", msg.mic, "tab=", msg.tab);
      scheduleVuUpdate(msg.mic as number, msg.tab as number);
      recordingSignal.value = { ...recordingSignal.value, micLevel: msg.mic as number };
      break;
    case "SESSION_ABORTED":
      handleSessionAborted(msg.reason as string);
      break;
    case "WS_RECONNECTED":
      showReconnectedBadge();
      break;
    case "WS_STATUS":
      updateWsStatus(msg.connected as boolean);
      break;
    case "CAPTURE_STARTED":
      console.log("[Panel] CAPTURE_STARTED received");
      handleCaptureStarted();
      break;
    case "CAPTURE_FAILED":
      handleCaptureFailed(msg.error as string);
      break;
  }
}

// ── State restore from SW handshake ───────────────────────────────────────

function restoreFromHandshake(state: {
  capturing: boolean;
  sessionId: string;
  kbId: string;
  wsConnected: boolean;
}): void {
  if (currentPhase === 3 || state.capturing) {
    setPhase(3);
    const recBtn = $<HTMLButtonElement>("rec-btn");
    const recLabel = $("rec-label");
    if (recBtn) {
      recBtn.classList.remove("rec-idle");
      recBtn.classList.add("rec-active");
      recBtn.disabled = false;
    }
    if (recLabel) recLabel.textContent = "СТОП";
    show($("vu-meters"));
    startCallTimer();
  } else if (state.kbId) {
    setPhase(2);
  }
  // If SW has no kbId, don't reset to phase 0 — local storage
  // may already have set phase 2 from cached briefing in init().
  updateWsStatus(state.wsConnected);
}

function updateWsStatus(connected: boolean): void {
  // Could show a WS indicator; for now just log
  console.log("[Copilot] WS connected:", connected);
  wsConnectedSignal.value = connected;
}

function handleSessionAborted(reason: string): void {
  const banner = $("session-error-banner");
  if (banner) {
    banner.textContent = `Сессия прервана: ${reason}`;
    show(banner);
    setTimeout(() => hide(banner), 5000);
  }
  stopCallTimer();
  setPhase(0);
  resetSessionState();
}

function showReconnectedBadge(): void {
  updateStatusPill("ok", "Переподключено");
  setTimeout(() => hide($("status-pill")), 3000);
}

async function resetSessionState(): Promise<void> {
  await saveState({
    capturing: false,
    briefing: null,
    kbId: "",
    sessionId: "",
    fileNames: [],
  });
}

// ── VU meters (rAF batching — Layer 2 throttling) ─────────────────────────

let pendingMic = 0;
let pendingTab = 0;
let vuRafPending = false;
const vuMicEl = () => $<HTMLDivElement>("vu-mic");
const vuTabEl = () => $<HTMLDivElement>("vu-tab");

function scheduleVuUpdate(mic: number, tab: number): void {
  pendingMic = mic;
  pendingTab = tab;
  if (!vuRafPending) {
    vuRafPending = true;
    requestAnimationFrame(() => {
      vuRafPending = false;
      const micPct = Math.min(100, pendingMic * 400);
      const tabPct = Math.min(100, pendingTab * 400);
      const vuMic = vuMicEl();
      const vuTab = vuTabEl();
      if (vuMic) vuMic.style.width = `${micPct}%`;
      if (vuTab) vuTab.style.width = `${tabPct}%`;
    });
  }
}

// ── Call timer ─────────────────────────────────────────────────────────────

let callTimerInterval: ReturnType<typeof setInterval> | null = null;
let callStartTime = 0;

function startCallTimer(): void {
  callStartTime = Date.now();
  callTimerInterval = setInterval(updateTimerDisplay, 1000);
  updateTimerDisplay();
}

function stopCallTimer(): void {
  if (callTimerInterval) {
    clearInterval(callTimerInterval);
    callTimerInterval = null;
  }
}

function updateTimerDisplay(): void {
  const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
  const mins = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const secs = String(elapsed % 60).padStart(2, "0");
  const statusText = $("status-text");
  if (statusText) statusText.textContent = `● ${mins}:${secs}`;
}

function getCallDuration(): string {
  const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
  const mins = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const secs = String(elapsed % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

// ── Capture prompt (two-step flow) ────────────────────────────────────────

let capturePromptTimeout: ReturnType<typeof setTimeout> | null = null;

function showCapturePrompt(): void {
  const statusText = $("status-text");
  if (statusText) {
    statusText.textContent = "\u25B6 \u041D\u0430\u0436\u043C\u0438\u0442\u0435 \u0438\u043A\u043E\u043D\u043A\u0443 \u0440\u0430\u0441\u0448\u0438\u0440\u0435\u043D\u0438\u044F \u0432 \u043F\u0430\u043D\u0435\u043B\u0438 Chrome";
    statusText.style.color = "#f59e0b";
    statusText.style.fontWeight = "700";
  }
}

function hideCapturePrompt(): void {
  const statusText = $("status-text");
  if (statusText) {
    statusText.style.color = "";
    statusText.style.fontWeight = "";
  }
  if (capturePromptTimeout) {
    clearTimeout(capturePromptTimeout);
    capturePromptTimeout = null;
  }
}

function handleCaptureStarted(): void {
  hideCapturePrompt();
  const recBtn = $<HTMLButtonElement>("rec-btn");
  const recLabel = $("rec-label");

  if (recBtn) {
    recBtn.disabled = false;
    recBtn.classList.remove("rec-idle");
    recBtn.classList.add("rec-active");
  }
  if (recLabel) recLabel.textContent = "СТОП";
  show($("vu-meters"));
  void saveState({ capturing: true });
  setPhase(3);
  startCallTimer();

  // Reset signals for new session
  resetSignals({
    isRecording: true,
    wsConnected: true,
    briefData: panelState.briefing ?? null,
  });

  // Start recording timer (updates recordingSignal.elapsedSeconds every 1s)
  if (recordingTimerInterval) clearInterval(recordingTimerInterval);
  const recStart = Date.now();
  recordingTimerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recStart) / 1000);
    recordingSignal.value = { ...recordingSignal.value, elapsedSeconds: elapsed };
  }, 1000);

  // Mount Preact tree
  const root = $("live-call-root");
  if (root) {
    mountLiveCall(root, {
      onStopRecording: () => { $<HTMLButtonElement>("rec-btn")?.click(); },
      onTabChange: () => {},
      onBriefingTabActive: (active) => {
        const bc = $("briefing-collapsed");
        if (bc) active ? show(bc) : hide(bc);
      },
    });
  }
}

function handleCaptureFailed(error: string): void {
  hideCapturePrompt();
  const recBtn = $<HTMLButtonElement>("rec-btn");
  const statusText = $("status-text");

  if (recBtn) recBtn.disabled = false;
  if (statusText) statusText.textContent = `\u041E\u0448\u0438\u0431\u043A\u0430: ${error}`;
}

const _ERROR_LABELS: Record<string, string> = {
  STT_BALANCE_EXHAUSTED:
    "Распознавание речи недоступно: закончился баланс. Обратитесь к администратору",
  STT_AUTH_FAILED:
    "Распознавание речи недоступно: ошибка доступа. Обратитесь к администратору",
  STT_UNAVAILABLE:
    "Распознавание речи временно недоступно. Попробуйте позже",
  SESSION_IDLE_TIMEOUT:
    "Сессия завершена: речь не обнаружена. Нажмите REC для новой сессии",
  SESSION_IDLE_WARNING:
    "Речь не обнаружена. Сессия завершится через 1 минуту",
};

// Cache STT balance error to prevent repeated connection attempts
let sttBalanceError = false;
let sttBalanceErrorTime = 0;
const BALANCE_ERROR_CACHE_MS = 30 * 60 * 1000; // 30 minutes

function handleBackendError(msg: WsError): void {
  const banner = $("session-error-banner");
  if (!banner) return;

  const label = _ERROR_LABELS[msg.code] ?? msg.message;
  banner.textContent = label;
  show(banner);

  // Fatal errors → terminate session in UI
  const fatal = [
    "STT_BALANCE_EXHAUSTED",
    "STT_AUTH_FAILED",
    "SESSION_IDLE_TIMEOUT",
  ];
  if (fatal.includes(msg.code)) {
    // Cache balance error to prevent re-connection attempts
    if (msg.code === "STT_BALANCE_EXHAUSTED") {
      sttBalanceError = true;
      sttBalanceErrorTime = Date.now();
    }
    stopCallTimer();
    setPhase(4);
    const recBarP4Fatal = $("rec-bar-phase4");
    if (recBarP4Fatal) mountRecBarDone(recBarP4Fatal);
    showFollowUpWithFallback();
    return; // banner stays visible
  }

  // Warning — show for 30s (not fatal)
  if (msg.code === "SESSION_IDLE_WARNING") {
    setTimeout(() => hide(banner), 30_000);
    return;
  }

  // Transient — hide after 10s
  setTimeout(() => hide(banner), 10_000);
}

// ── Evaluation display (Phase 4) ──────────────────────────────────────────

let evalPollTimer: ReturnType<typeof setInterval> | null = null;
let evalReceived = false;
let evalStepTimer: ReturnType<typeof setInterval> | null = null;
let pendingFollowUpEmail: FollowUpEmail | null = null;
let pendingCrmNote: CrmNote | null = null;

function stopEvalPolling(): void {
  if (evalPollTimer) { clearInterval(evalPollTimer); evalPollTimer = null; }
  if (evalStepTimer) { clearInterval(evalStepTimer); evalStepTimer = null; }
}

function animateEvalProgress(): void {
  let step = 1;
  const steps = [
    document.getElementById("eval-step-1"),
    document.getElementById("eval-step-2"),
    document.getElementById("eval-step-3"),
  ];
  const fill = document.getElementById("eval-progress-fill");

  // Start step 1
  steps[0]?.classList.add("active");
  if (fill) fill.style.width = "15%";

  evalStepTimer = setInterval(() => {
    if (evalReceived) { stopEvalPolling(); return; }
    step++;
    if (step === 2) {
      steps[0]?.classList.remove("active");
      steps[0]?.classList.add("done");
      steps[1]?.classList.add("active");
      if (fill) fill.style.width = "50%";
    } else if (step === 3) {
      steps[1]?.classList.remove("active");
      steps[1]?.classList.add("done");
      steps[2]?.classList.add("active");
      if (fill) fill.style.width = "80%";
    } else if (step >= 4) {
      // Stay on step 3 spinning
      if (fill) fill.style.width = "90%";
      if (evalStepTimer) { clearInterval(evalStepTimer); evalStepTimer = null; }
    }
  }, 4000);
}

function handleEvaluationStarted(msg: WsEvaluationStarted): void {
  const loading = document.getElementById("eval-loading");
  const summary = document.getElementById("eval-summary");
  const error = document.getElementById("eval-error");
  if (loading) loading.hidden = false;
  if (summary) summary.hidden = true;
  if (error) error.hidden = true;

  // Reset follow-up state (keep buttons visible — email has fallback)
  pendingFollowUpEmail = null;
  pendingCrmNote = null;

  // Reset step states
  for (let i = 1; i <= 3; i++) {
    const el = document.getElementById(`eval-step-${i}`);
    el?.classList.remove("active", "done");
  }
  const fill = document.getElementById("eval-progress-fill");
  if (fill) fill.style.width = "0%";

  // Animate progress steps
  animateEvalProgress();

  // Store token so polling and report page can use it
  const sid = msg.session_id;
  const evalToken = msg.eval_token;
  if (evalToken) {
    chrome.storage.local.set({ [`eval_token_${sid}`]: evalToken });
  }

  // Start polling REST API as fallback (WS may close before result arrives)
  // LLM evaluation typically takes 30-120s, so poll for up to 3 minutes
  evalReceived = false;
  if (evalPollTimer) { clearInterval(evalPollTimer); evalPollTimer = null; }
  let attempts = 0;
  const MAX_POLL_ATTEMPTS = 36; // 36 * 5s = 180s (3 min)
  evalPollTimer = setInterval(async () => {
    if (evalReceived) { stopEvalPolling(); return; }
    attempts++;
    if (attempts > MAX_POLL_ATTEMPTS) { stopEvalPolling(); return; }
    if (!evalToken) return; // can't poll without token
    try {
      const url = `${API_BASE}/evaluation/${sid}?token=${evalToken}`;
      const resp = await fetch(url);
      if (resp.ok) {
        const raw = await resp.json();
        const { analytics, ...evalData } = raw as
          CallEvaluationResult & { analytics?: CallAnalyticsWire };
        evalReceived = true;
        stopEvalPolling();
        if (loading) loading.hidden = true;
        if (summary) summary.hidden = false;
        chrome.storage.local.set({
          [`eval_result_${sid}`]: evalData,
          [`eval_analytics_${sid}`]: analytics ?? null,
          last_eval_session_id: sid,
        });
        // Render diarized transcript if available
        if (raw.transcript && Array.isArray(raw.transcript) && raw.transcript.length > 0) {
          renderDiarizedTranscript(raw.transcript as DiarizedUtterance[]);
        }
        renderEvaluationSummary(evalData, sid);
        handleFollowUpActions(evalData as CallEvaluationResult);
      }
    } catch { /* retry next interval */ }
  }, 5000);
}

function handleEvaluationResult(msg: WsEvaluationResult): void {
  evalReceived = true;
  stopEvalPolling();

  const loading = document.getElementById("eval-loading");
  const summary = document.getElementById("eval-summary");
  if (loading) loading.hidden = true;
  if (summary) summary.hidden = false;

  const ev = msg.evaluation;

  // Save to chrome.storage.local for report page + recovery
  chrome.storage.local.set({
    [`eval_token_${msg.session_id}`]: msg.eval_token,
    [`eval_result_${msg.session_id}`]: ev,
    [`eval_analytics_${msg.session_id}`]: msg.analytics ?? null,
    last_eval_session_id: msg.session_id,
  });

  // Replace transcript with diarized version (includes timestamps)
  if (msg.transcript && msg.transcript.length > 0) {
    renderDiarizedTranscript(msg.transcript);
  }

  renderEvaluationSummary(ev, msg.session_id);
  handleFollowUpActions(ev);
}

function handleEvaluationError(msg: WsEvaluationError): void {
  evalReceived = true;
  stopEvalPolling();

  const loading = document.getElementById("eval-loading");
  const error = document.getElementById("eval-error");
  const errorText = document.getElementById("eval-error-text");
  if (loading) loading.hidden = true;
  if (error) error.hidden = false;
  if (errorText) errorText.textContent = msg.message || "Не удалось оценить звонок";
}

function renderEvaluationSummary(ev: CallEvaluationResult, sessionId: string): void {
  const color = VERDICT_COLORS[ev.verdict] || "#3b82f6";

  // Gauge arc
  const gaugeArc = document.getElementById("eval-gauge-arc");
  if (gaugeArc) {
    const pct = ev.overall_score / 10;
    const arcLen = 157; // approximate semicircle length
    gaugeArc.setAttribute("stroke-dasharray", `${pct * arcLen} ${arcLen}`);
    gaugeArc.setAttribute("stroke", color);
  }

  // Score text
  const scoreText = document.getElementById("eval-gauge-score");
  if (scoreText) scoreText.textContent = ev.overall_score.toFixed(1);

  // Verdict
  const verdictText = document.getElementById("eval-verdict-text");
  if (verdictText) {
    verdictText.textContent = VERDICT_LABELS[ev.verdict] || ev.verdict;
    verdictText.style.color = color;
  }

  // Summary brief
  const summaryBrief = document.getElementById("eval-summary-text");
  if (summaryBrief) {
    summaryBrief.textContent = ev.call_summary.slice(0, 120);
  }

  // Mini bars
  const barsContainer = document.getElementById("eval-mini-bars");
  if (barsContainer) {
    barsContainer.replaceChildren(); // clear
    for (const cr of ev.criteria_results) {
      const row = document.createElement("div");
      row.className = "eval-bar-row";

      const label = document.createElement("span");
      label.className = "eval-bar-label";
      label.textContent = cr.criterion_name;

      const track = document.createElement("div");
      track.className = "eval-bar-track";

      const fill = document.createElement("div");
      fill.className = "eval-bar-fill";
      fill.style.width = `${cr.score * 10}%`;
      fill.style.background = cr.score >= 7 ? "#22c55e" : cr.score >= 4 ? "#f59e0b" : "#ef4444";
      track.appendChild(fill);

      const score = document.createElement("span");
      score.className = "eval-bar-score";
      score.textContent = String(cr.score);

      row.appendChild(label);
      row.appendChild(track);
      row.appendChild(score);
      barsContainer.appendChild(row);
    }
  }

  // Detail button
  const detailBtn = document.getElementById("eval-detail-btn");
  if (detailBtn) {
    detailBtn.onclick = () => {
      const url = chrome.runtime.getURL(`src/report/report.html?session_id=${sessionId}`);
      chrome.tabs.create({ url });
    };
  }
}

// ── Follow-up actions (FEAT-011) ──────────────────────────────────────────

/** Show follow-up buttons immediately on Phase 4 entry with email fallback. */
function showFollowUpWithFallback(): void {
  const container = $("follow-up-actions");
  show(container);

  const emailBtn = $("followup-email-btn") as HTMLButtonElement | null;
  const crmBtn = $("followup-crm-btn") as HTMLButtonElement | null;
  const hint = $("followup-hint");

  // Email always enabled (fallback text if evaluation hasn't arrived)
  if (emailBtn) {
    emailBtn.hidden = false;
    emailBtn.disabled = false;
    emailBtn.classList.remove("disabled");
  }

  // CRM disabled until evaluation
  if (crmBtn) {
    crmBtn.hidden = false;
    crmBtn.disabled = true;
    crmBtn.classList.add("disabled");
  }

  hide(hint);
}

function handleFollowUpActions(evaluation: CallEvaluationResult): void {
  const container = $("follow-up-actions");
  pendingFollowUpEmail = evaluation.follow_up_email ?? null;
  pendingCrmNote = evaluation.crm_note ?? null;

  // Always show the container after evaluation
  show(container);

  const emailBtn = $("followup-email-btn") as HTMLButtonElement | null;
  const crmBtn = $("followup-crm-btn") as HTMLButtonElement | null;
  const hint = $("followup-hint");

  if (emailBtn) {
    emailBtn.hidden = false;
    emailBtn.disabled = false;
    emailBtn.classList.remove("disabled");
  }
  if (crmBtn) {
    crmBtn.hidden = false;
    crmBtn.disabled = false;
    crmBtn.classList.remove("disabled");
  }
  hide(hint);
}

/** Handle early follow-up delivery (before full evaluation). */
function handleFollowUpReady(msg: WsFollowUpReady): void {
  console.log("[Copilot] follow_up_ready received");
  pendingFollowUpEmail = msg.follow_up_email;
  pendingCrmNote = msg.crm_note;

  // Show follow-up buttons immediately
  const container = $("follow-up-actions");
  show(container);

  const emailBtn = $("followup-email-btn") as HTMLButtonElement | null;
  const crmBtn = $("followup-crm-btn") as HTMLButtonElement | null;
  const hint = $("followup-hint");

  if (emailBtn) {
    emailBtn.hidden = false;
    emailBtn.disabled = false;
    emailBtn.classList.remove("disabled");
  }
  if (crmBtn) {
    crmBtn.hidden = false;
    crmBtn.disabled = false;
    crmBtn.classList.remove("disabled");
  }
  hide(hint);
}

function openGmailCompose(email: FollowUpEmail): void {
  const MAX_BODY = 1500;
  const MAX_SUBJECT = 128;
  let body = email.body;
  if (body.length > MAX_BODY) {
    body =
      body.slice(0, MAX_BODY) +
      "...\n\n(текст сокращён, дополните вручную)";
  }
  const subject = email.subject.slice(0, MAX_SUBJECT);
  const params = new URLSearchParams({
    view: "cm",
    fs: "1",
    su: subject,
    body,
  });
  const gmailUrl = `https://mail.google.com/mail/?${params.toString()}`;
  chrome.tabs.create({ url: gmailUrl }).catch(() => {
    const btn = $("followup-email-btn");
    if (btn) {
      btn.textContent = "Не удалось открыть Gmail";
      setTimeout(() => { btn.textContent = "Email follow-up"; }, 2000);
    }
  });
}

/** Try to recover follow-up email from storage or REST API. */
async function tryRecoverFollowUpEmail(): Promise<FollowUpEmail | null> {
  const storage = await chrome.storage.local.get("last_eval_session_id");
  const sid = storage.last_eval_session_id;
  if (!sid) return null;

  // Check storage cache first
  const cached = await chrome.storage.local.get(`eval_result_${sid}`);
  const evalData = cached[`eval_result_${sid}`] as CallEvaluationResult | undefined;
  if (evalData?.follow_up_email) {
    pendingFollowUpEmail = evalData.follow_up_email;
    return evalData.follow_up_email;
  }

  // Try REST API
  const tokenStorage = await chrome.storage.local.get(`eval_token_${sid}`);
  const token = tokenStorage[`eval_token_${sid}`];
  if (!token) return null;

  try {
    const resp = await fetch(`${API_BASE}/evaluation/${sid}?token=${token}`);
    if (resp.ok) {
      const raw = await resp.json();
      if (raw.follow_up_email) {
        pendingFollowUpEmail = raw.follow_up_email;
        if (raw.crm_note) pendingCrmNote = raw.crm_note;
        const { analytics, ...evalOnly } = raw as
          CallEvaluationResult & { analytics?: unknown };
        chrome.storage.local.set({
          [`eval_result_${sid}`]: evalOnly,
        });
        if (!evalReceived) {
          evalReceived = true;
          stopEvalPolling();
          const loading = document.getElementById("eval-loading");
          const summary = document.getElementById("eval-summary");
          if (loading) loading.hidden = true;
          if (summary) summary.hidden = false;
          renderEvaluationSummary(evalOnly, sid);
          handleFollowUpActions(evalOnly as CallEvaluationResult);
        }
        return raw.follow_up_email;
      }
    }
  } catch { /* ignore */ }
  return null;
}

function initFollowUpButtons(): void {
  // Email follow-up → opens Gmail compose
  $("followup-email-btn")?.addEventListener("click", async () => {
    if (pendingFollowUpEmail) {
      openGmailCompose(pendingFollowUpEmail);
      return;
    }
    const btn = $("followup-email-btn");
    if (btn) btn.textContent = "Загрузка...";
    const recovered = await tryRecoverFollowUpEmail();
    if (recovered) {
      openGmailCompose(recovered);
      if (btn) btn.textContent = "Email follow-up";
      return;
    }
    if (btn) {
      btn.textContent = "Оценка ещё не готова";
      setTimeout(() => { btn.textContent = "Email follow-up"; }, 3000);
    }
  });

  // CRM note → clipboard copy
  $("followup-crm-btn")?.addEventListener("click", async () => {
    if (!pendingCrmNote) {
      const btn = $("followup-crm-btn") as HTMLButtonElement | null;
      if (btn) btn.textContent = "Загрузка...";
      await tryRecoverFollowUpEmail(); // also recovers crm_note
      if (!pendingCrmNote) {
        if (btn) {
          btn.textContent = "Оценка ещё не готова";
          setTimeout(() => { btn.textContent = "Копировать в CRM"; }, 3000);
        }
        return;
      }
    }
    const btn = $("followup-crm-btn") as HTMLButtonElement | null;
    if (!btn || btn.disabled) return;
    btn.disabled = true;

    const text = `${pendingCrmNote.title}\n\n${pendingCrmNote.body}`;
    try {
      await navigator.clipboard.writeText(text);
      btn.classList.add("copied");
      btn.textContent = "Скопировано!";
      setTimeout(() => {
        btn.classList.remove("copied");
        btn.textContent = "Копировать в CRM";
        btn.disabled = false;
      }, 2000);
    } catch {
      btn.textContent = "Ошибка копирования";
      setTimeout(() => {
        btn.textContent = "Копировать в CRM";
        btn.disabled = false;
      }, 2000);
    }
  });
}

// ── WS message dispatch ───────────────────────────────────────────────────

function handleWsMessage(msg: WsMessage): void {
  switch (msg.type) {
    case "hint_end": {
      console.log("[Panel] hint_end received", msg);
      if (msg.v !== 2) break;
      hintSignal.value = {
        id: crypto.randomUUID(),
        hintType: msg.hint_type,
        headline: msg.headline,
        detail: msg.detail,
        coaching: msg.coaching,
        source: msg.source,
        timestamp: Date.now(),
      };
      break;
    }
    case "talk_ratio": {
      console.log("[Panel] talk_ratio received", msg);
      talkRatioSignal.value = {
        managerPercent: msg.managerPercent,
        clientPercent: msg.clientPercent,
        waveform: msg.waveform,
      };
      break;
    }
    case "transcript":
      console.log("[Panel] transcript received", JSON.stringify(msg));
      handleTranscript(msg);
      break;
    case "error":
      console.error(`[Copilot] Backend error: ${msg.code} — ${msg.message}`);
      handleBackendError(msg);
      break;
    case "evaluation_started":
      handleEvaluationStarted(msg);
      break;
    case "evaluation_result":
      handleEvaluationResult(msg);
      break;
    case "evaluation_error":
      handleEvaluationError(msg);
      break;
    case "follow_up_ready":
      handleFollowUpReady(msg);
      break;
  }
}

// ── Transcript handler (Phase 3, signal-based) ───────────────────────────

function handleTranscript(msg: WsTranscript): void {
  console.log("[Panel] handleTranscript: speaker=%s text=%s is_final=%s", msg.speaker, JSON.stringify(msg.text), msg.is_final);
  const speaker = msg.speaker === "rep" ? "manager" as const : "client" as const;
  const timestamp = getCallDuration();

  // Find last interim from SAME speaker (not just the very last item).
  // This prevents duplicates when two STT channels interleave.
  function findLastInterimIdx(spk: typeof speaker): number {
    for (let i = transcriptItems.length - 1; i >= 0; i--) {
      if (transcriptItems[i].isInterim && transcriptItems[i].speaker === spk) return i;
      if (!transcriptItems[i].isInterim) break; // stop at first finalized item
    }
    return -1;
  }

  if (!msg.is_final) {
    const idx = findLastInterimIdx(speaker);
    if (idx !== -1) {
      transcriptItems[idx].text = msg.text;
    } else {
      transcriptItems.push({
        type: "message",
        id: `t-${Date.now()}`,
        speaker,
        text: msg.text,
        timestamp,
        isInterim: true,
      });
    }
  } else {
    // Dedup: Yandex sends final + final_refinement with same utterance_id.
    // If we already have a finalized entry with this id, just update its text.
    const existingIdx = msg.utterance_id
      ? transcriptItems.findIndex((item) => item.id === msg.utterance_id)
      : -1;

    if (existingIdx !== -1) {
      transcriptItems[existingIdx] = { ...transcriptItems[existingIdx], text: msg.text };
    } else {
      const idx = findLastInterimIdx(speaker);
      if (idx !== -1) {
        transcriptItems[idx] = {
          ...transcriptItems[idx],
          text: msg.text,
          isInterim: false,
          id: msg.utterance_id ?? transcriptItems[idx].id,
        };
      } else {
        transcriptItems.push({
          type: "message",
          id: msg.utterance_id ?? `t-${Date.now()}`,
          speaker,
          text: msg.text,
          timestamp,
          isInterim: false,
        });
      }
    }

    // Also append to Phase 4 transcript DOM for post-call display
    // Skip if this is a refinement update (existingIdx found)
    if (existingIdx !== -1) {
      // Update existing DOM entry text instead of appending
      const fullList = $("transcript-full-list");
      if (fullList?.children[existingIdx]) {
        const textSpan = fullList.children[existingIdx].querySelector(".transcript-text");
        if (textSpan) textSpan.textContent = ` ${msg.text}`;
      }
    } else {
      const fullList = $("transcript-full-list");
      if (fullList) {
        const entry = document.createElement("div");
        entry.className = `transcript-entry transcript-${speaker}`;
        const label = document.createElement("span");
        label.className = "transcript-speaker";
        label.textContent = speaker === "manager" ? "Менеджер" : "Клиент";
        const textSpan = document.createElement("span");
        textSpan.className = "transcript-text";
        textSpan.textContent = ` ${msg.text}`;
        entry.appendChild(label);
        entry.appendChild(textSpan);
        fullList.appendChild(entry);
      }
    }
  }

  transcriptSignal.value = [...transcriptItems];
  sttActiveSignal.value = true;
}

// ── Upload flow (Phase 0 → 1 → 2) ────────────────────────────────────────

const MAX_FILE_SIZE = 50 * 1024 * 1024;
const ALLOWED_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/markdown",
  "text/plain",
]);

function isAllowedExtension(name: string): boolean {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return ["pdf", "xlsx", "xls", "docx", "md", "txt"].includes(ext);
}

function validateFiles(
  files: FileList
): { valid: File[]; errors: string[] } {
  const valid: File[] = [];
  const errors: string[] = [];
  if (files.length > 10) {
    errors.push("Максимум 10 файлов за раз");
    return { valid: [], errors };
  }
  for (const file of files) {
    if (file.size > MAX_FILE_SIZE) {
      errors.push(`${file.name}: превышает 50 МБ`);
    } else if (!ALLOWED_TYPES.has(file.type) && !isAllowedExtension(file.name)) {
      errors.push(`${file.name}: неподдерживаемый формат`);
    } else {
      valid.push(file);
    }
  }
  return { valid, errors };
}

type StepPhase = "upload" | "process" | "briefing" | "done" | "error";

function setStep(phase: StepPhase, statusText?: string): void {
  const stepUpload = $("step-upload");
  const stepProcess = $("step-process");
  const stepBriefing = $("step-briefing");
  const line12 = $("line-1-2");
  const line23 = $("line-2-3");
  const stepperText = $("stepper-text");

  const steps = [stepUpload, stepProcess, stepBriefing];
  const lines = [line12, line23];

  for (const s of steps) {
    s?.classList.remove("active", "done");
    s?.removeAttribute("aria-current");
  }
  for (const l of lines) {
    l?.classList.remove("done");
  }

  const phaseIndex = { upload: 0, process: 1, briefing: 2, done: 3, error: -1 }[
    phase
  ];

  if (phase === "error") {
    if (stepperText) {
      stepperText.textContent = statusText ?? "Ошибка";
      stepperText.style.color = "#dc2626";
    }
    return;
  }

  for (let i = 0; i < phaseIndex && i < steps.length; i++) {
    steps[i]?.classList.add("done");
  }
  for (let i = 0; i < phaseIndex - 1 && i < lines.length; i++) {
    lines[i]?.classList.add("done");
  }
  if (phaseIndex < steps.length) {
    steps[phaseIndex]?.classList.add("active");
    steps[phaseIndex]?.setAttribute("aria-current", "step");
  }
  if (phase === "done") {
    for (const s of steps) s?.classList.add("done");
    for (const l of lines) l?.classList.add("done");
  }

  if (stepperText) {
    stepperText.textContent = statusText ?? "";
    stepperText.style.color = "#6b7280";
  }
}

function initUpload(): void {
  const dropZone = $("drop-zone");
  const fileInput = $<HTMLInputElement>("file-input");
  const failedFiles = $<HTMLUListElement>("failed-files");

  dropZone?.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });
  dropZone?.addEventListener("dragleave", () =>
    dropZone.classList.remove("drag-over")
  );
  dropZone?.addEventListener("drop", async (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const files = e.dataTransfer?.files;
    if (files) await doUpload(files);
  });

  dropZone?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") fileInput?.click();
  });

  fileInput?.addEventListener("change", async () => {
    const files = fileInput.files;
    if (files) await doUpload(files);
  });

  async function doUpload(files: FileList): Promise<void> {
    const { valid, errors } = validateFiles(files);

    // Clear cached briefing on new upload
    await saveState({ briefing: null });

    if (failedFiles) {
      failedFiles.textContent = "";
      for (const err of errors) {
        const li = document.createElement("li");
        li.textContent = err;
        failedFiles.appendChild(li);
      }
      errors.length > 0 ? show(failedFiles) : hide(failedFiles);
    }

    if (valid.length === 0) return;

    setPhase(1);
    setStep("upload", "Загружаем файлы...");

    const sessionId = crypto.randomUUID();
    const formData = new FormData();
    formData.append("session_id", sessionId);
    const fileNames: string[] = [];
    for (const file of valid) {
      formData.append("files", file);
      fileNames.push(file.name);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30_000);

    try {
      const resp = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      setStep("process", "Обрабатываем документы...");

      if (resp.ok || resp.status === 207) {
        const data = (await resp.json()) as {
          knowledge_base_id: string;
          chunks_count: number;
          scenario_generated?: boolean;
          failed_files?: { name: string; error: string }[];
        };

        await saveState({
          sessionId,
          kbId: data.knowledge_base_id,
          chunksCount: data.chunks_count,
          fileNames,
        });

        if (data.failed_files?.length && failedFiles) {
          for (const f of data.failed_files) {
            const li = document.createElement("li");
            li.textContent = `${f.name}: ${f.error}`;
            failedFiles.appendChild(li);
          }
          show(failedFiles);
        }

        if (data.scenario_generated !== false) {
          setStep("briefing", "Генерируем брифинг...");
          await fetchAndRenderBriefing();
        }

        setStep("done", `Загружено ${data.chunks_count} фрагментов`);

        // Transition to Phase 2 after short delay
        setTimeout(() => setPhase(2), 1500);
      } else {
        throw new Error(`HTTP ${resp.status}`);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      const msg =
        err instanceof DOMException && err.name === "AbortError"
          ? "Превышено время ожидания (30с)"
          : String(err);
      setStep("error", `Ошибка: ${msg}`);
      // Return to Phase 0 after delay so user can retry
      setTimeout(() => setPhase(0), 5000);
    }
  }
}

// ── Briefing rendering ────────────────────────────────────────────────────

function renderBriefToAllPhases(data: BriefData): void {
  const phase2 = $("briefing-content");
  if (phase2) mountBriefPanel(phase2, data);

  const phase3 = $("briefing-collapsed");
  if (phase3) mountBriefPanel(phase3, data, true);  // compact

  const phase4 = $("briefing-collapsed-done");
  if (phase4) mountBriefPanel(phase4, data);
}

async function fetchAndRenderBriefing(): Promise<void> {
  const loading = $("briefing-loading");
  const content = $("briefing-content");

  const state = await loadState();
  if (!state.kbId) return;

  hide(content);
  show(loading);
  if (loading) {
    loading.textContent = "Генерация брифинга";
    loading.classList.add("loading-dots");
  }

  try {
    const resp = await fetch(`${API_BASE}/briefing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        kb_id: state.kbId,
      }),
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const data = (await resp.json()) as BriefData;

    renderBriefToAllPhases(data);

    if (loading) loading.classList.remove("loading-dots");
    hide(loading);
    show(content);

    // Update file strip
    updateFileStrip(state.fileNames);

    // Cache briefing
    await saveState({ briefing: data });

    // Run preflight
    void runPreflight();
  } catch (err) {
    if (loading) loading.classList.remove("loading-dots");
    throw err;
  }
}

function updateFileStrip(fileNames: string[]): void {
  const strip = $("file-strip");
  const namesEl = $("file-strip-names");
  if (strip && namesEl && fileNames.length > 0) {
    namesEl.textContent = fileNames.join(", ");
    show(strip);
  }
}

function initBriefing(): void {
  const refreshBtn = $<HTMLAnchorElement>("refresh-briefing-btn");
  const reloadBtn = $<HTMLAnchorElement>("reload-files-btn");

  refreshBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    void fetchAndRenderBriefing().catch((err) => {
      const loading = $("briefing-loading");
      if (loading) {
        loading.textContent = `Ошибка: ${String(err)}`;
        show(loading);
      }
    });
  });

  reloadBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    void resetSessionState().then(() => setPhase(0));
  });
}

// ── Preflight status ──────────────────────────────────────────────────────

interface PreflightResult {
  stt: { status: string; detail?: string };
  llm: { status: string; detail?: string };
  redis: { status: string; detail?: string };
}

const _PROVIDER_LABELS: Record<string, string> = {
  salutespeech: "SaluteSpeech",
  yandex: "Yandex STT",
  deepgram: "Deepgram",
};

async function getSavedProvider(): Promise<string> {
  const result = (await chrome.storage.local.get("sttProvider")) as {
    sttProvider?: string;
  };
  return result.sttProvider ?? "salutespeech";
}

async function runPreflight(): Promise<void> {
  const container = $("preflight-status");
  const pfStt = $("pf-stt");
  const pfLlm = $("pf-llm");
  const pfRedis = $("pf-redis");

  if (!container) return;
  show(container);

  for (const chip of [pfStt, pfLlm, pfRedis]) {
    chip?.setAttribute("data-status", "checking");
  }

  // Task 4.5: send provider in preflight query
  const provider = await getSavedProvider();

  try {
    const resp = await fetch(
      `${API_BASE}/preflight?provider=${encodeURIComponent(provider)}`,
      { method: "GET" },
    );
    const data = (await resp.json()) as PreflightResult;

    if (pfStt) {
      pfStt.setAttribute("data-status", data.stt.status);
      const label = _PROVIDER_LABELS[provider] ?? provider;
      const dot = document.createElement("span");
      dot.className = "pf-dot";
      pfStt.replaceChildren(dot, document.createTextNode(` ${label}`));
      if (data.stt.detail) pfStt.title = data.stt.detail;
    }
    if (pfLlm) {
      pfLlm.setAttribute("data-status", data.llm.status);
      if (data.llm.detail) pfLlm.title = data.llm.detail;
    }
    if (pfRedis) {
      pfRedis.setAttribute("data-status", data.redis.status);
      if (data.redis.detail) pfRedis.title = data.redis.detail;
    }
  } catch (err) {
    for (const chip of [pfStt, pfLlm, pfRedis]) {
      chip?.setAttribute("data-status", "error");
      if (chip) chip.title = String(err);
    }
  }
}

function initPreflight(): void {
  const container = $("preflight-status");
  container?.addEventListener("click", () => {
    void runPreflight();
  });
}

// ── REC button (start/stop session) ───────────────────────────────────────

function initRecButton(): void {
  const recBtn = $<HTMLButtonElement>("rec-btn");
  const recLabel = $("rec-label");
  const statusText = $("status-text");

  recBtn?.addEventListener("click", async () => {
    const state = await loadState();

    if (currentPhase === 3 || state.capturing) {
      // Stop session
      if (testWsClient) {
        // Test mode: close direct WS
        stopTestSession();
      } else {
        // Normal mode: notify service worker
        const msg: ExtMessage = {
          type: "STOP_SESSION",
          sessionId: state.sessionId,
        };
        chrome.runtime.sendMessage(msg);
      }
      recBtn.classList.remove("rec-active");
      recBtn.classList.add("rec-idle");
      if (recLabel) recLabel.textContent = "REC";
      hide($("vu-meters"));
      const vuMic = vuMicEl();
      const vuTab = vuTabEl();
      if (vuMic) vuMic.style.width = "0%";
      if (vuTab) vuTab.style.width = "0%";
      await saveState({ capturing: false });
      stopCallTimer();

      // Transition to Phase 4
      const duration = getCallDuration();
      const completionText = $("completion-text");
      if (completionText) completionText.textContent = `Звонок завершён — ${duration}`;
      setPhase(4);

      // Mount grey "● REC" pill in Phase 4
      const recBarP4 = $("rec-bar-phase4");
      if (recBarP4) mountRecBarDone(recBarP4);

      // Show follow-up actions immediately with email fallback
      showFollowUpWithFallback();
    } else if (testModeEnabled) {
      // Test mode: direct WS, no audio capture needed
      if (!state.kbId) return;

      // Activate recording UI
      recBtn.classList.remove("rec-idle");
      recBtn.classList.add("rec-active");
      if (recLabel) recLabel.textContent = "СТОП";
      hide($("vu-meters")); // No audio in test mode
      handleCaptureStarted();
      if (statusText) statusText.textContent = "Тест";

      // Start test session via direct WebSocket
      startTestSession();
    } else {
      // Start session — two-step capture flow
      if (!state.kbId) return;

      // Task 5.3: check cached balance error
      if (sttBalanceError) {
        const elapsed = Date.now() - sttBalanceErrorTime;
        if (elapsed < BALANCE_ERROR_CACHE_MS) {
          const banner = $("session-error-banner");
          if (banner) {
            banner.textContent =
              _ERROR_LABELS.STT_BALANCE_EXHAUSTED;
            show(banner);
          }
          return;
        }
        // Cache expired — allow retry
        sttBalanceError = false;
      }

      const [tab] = await chrome.tabs.query({
        active: true,
        currentWindow: true,
      });
      if (!tab?.id) {
        if (statusText) {
          statusText.textContent =
            "Ошибка: откройте вкладку с CRM";
        }
        return;
      }

      // Check if the tab URL can be captured
      const tabUrl = tab.url ?? "";
      if (
        tabUrl.startsWith("chrome://") ||
        tabUrl.startsWith("chrome-extension://") ||
        tabUrl.startsWith("about:") ||
        tabUrl.startsWith("chrome-search://") ||
        tabUrl === ""
      ) {
        if (statusText) {
          statusText.textContent =
            "Откройте страницу с CRM или конференцией";
        }
        return;
      }

      recBtn.disabled = true;

      const msg: ExtMessage = {
        type: "PREPARE_CAPTURE",
        sessionId: state.sessionId || crypto.randomUUID(),
        kbId: state.kbId,
        tabId: tab.id,
      };

      chrome.runtime.sendMessage(msg, (resp) => {
        if (resp?.ok) {
          // Show prompt to click extension icon
          showCapturePrompt();
          // 30s timeout — cancel if icon not clicked
          capturePromptTimeout = setTimeout(() => {
            hideCapturePrompt();
            if (recBtn) recBtn.disabled = false;
            if (statusText) {
              statusText.textContent = "Время ожидания истекло";
            }
          }, 30_000);
        } else {
          recBtn.disabled = false;
          if (statusText) {
            statusText.textContent =
              `Ошибка: ${resp?.error ?? "неизвестно"}`;
          }
        }
      });
    }
  });
}

async function updateRecButtonState(): Promise<void> {
  const hasMic = await checkMicPermission();
  const state = await loadState();
  const recBtn = $<HTMLButtonElement>("rec-btn");

  if (recBtn) {
    // Test mode doesn't need mic permission
    const needsMic = !testModeEnabled && !hasMic;
    const disabled = needsMic || !state.kbId;
    recBtn.disabled = disabled;
    if (disabled && needsMic) {
      recBtn.title = "Настройте микрофон в Настройках";
    } else if (disabled && !state.kbId) {
      recBtn.title = "Сначала загрузите файлы";
    } else {
      recBtn.title = testModeEnabled ? "Тестовый режим" : "";
    }
  }
}

// ── Mic permission ────────────────────────────────────────────────────────

async function checkMicPermission(): Promise<boolean> {
  const result = (await chrome.storage.local.get("micGranted")) as {
    micGranted?: boolean;
  };
  return result.micGranted === true;
}

async function updateMicStatus(
  container: HTMLElement | null,
  textEl: HTMLElement | null
): Promise<void> {
  const hasMic = await checkMicPermission();
  if (container) {
    container.classList.toggle("mic-granted", hasMic);
    container.classList.toggle("mic-off", !hasMic);
  }
  if (textEl) {
    textEl.textContent = hasMic ? "Подключён" : "Не настроен";
  }
}

// ── Mic device selection ──────────────────────────────────────────────────

async function populateMicList(): Promise<void> {
  const select = $<HTMLSelectElement>("mic-select");
  const grantBtn = $("grant-mic-btn");
  if (!select) return;

  const hasMic = await checkMicPermission();
  if (!hasMic) {
    hide(select);
    show(grantBtn);
    return;
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  const audioInputs = devices.filter((d) => d.kind === "audioinput");

  // Preserve current selection
  const saved = (
    await chrome.storage.local.get("selectedMicId")
  ) as { selectedMicId?: string };
  const savedId = saved.selectedMicId ?? "";

  // Rebuild options
  select.textContent = "";
  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "По умолчанию (системный)";
  select.appendChild(defaultOpt);

  for (const dev of audioInputs) {
    // Skip "default" pseudo-device that duplicates real device
    if (dev.deviceId === "default") continue;
    const opt = document.createElement("option");
    opt.value = dev.deviceId;
    opt.textContent = dev.label || `Микрофон (${dev.deviceId.slice(0, 8)})`;
    select.appendChild(opt);
  }

  // Restore saved selection (fallback to default if device gone)
  const ids = audioInputs.map((d) => d.deviceId);
  select.value = ids.includes(savedId) ? savedId : "";

  show(select);
  // Hide grant button once permission is given — select replaces it
  hide(grantBtn);
}

function initMicSelect(): void {
  const select = $<HTMLSelectElement>("mic-select");
  select?.addEventListener("change", () => {
    void chrome.storage.local.set({ selectedMicId: select.value });
  });

  // Refresh list when devices change (plug/unplug)
  navigator.mediaDevices.addEventListener("devicechange", () => {
    void populateMicList();
  });
}

// ── Settings overlay ──────────────────────────────────────────────────────

function initSettingsOverlay(): void {
  const gearBtn = $("gear-btn");
  const overlay = $("settings-overlay");
  const backBtn = $("settings-back-btn");
  const backendInput = $<HTMLInputElement>("backend-url-input");
  const patternInput = $<HTMLInputElement>("url-pattern-input");
  const saveBtn = $("save-settings-btn");
  const savedNotice = $("settings-saved");
  const micSettings = $("mic-settings");
  const micStatusText = $("mic-status-text");
  const grantMicBtn = $("grant-mic-btn");
  const providerSelect = $<HTMLSelectElement>("stt-provider-select");

  gearBtn?.addEventListener("click", () => show(overlay));
  backBtn?.addEventListener("click", () => hide(overlay));

  // Load saved settings
  void chrome.storage.local
    .get(["backendUrl", "urlPattern", "sttProvider"])
    .then((result) => {
      const r = result as {
        backendUrl?: string;
        urlPattern?: string;
        sttProvider?: string;
      };
      if (backendInput && r.backendUrl) backendInput.value = r.backendUrl;
      if (patternInput && r.urlPattern) patternInput.value = r.urlPattern;
      if (providerSelect && r.sttProvider)
        providerSelect.value = r.sttProvider;
    });

  // Provider change → re-run preflight, clear balance error cache
  providerSelect?.addEventListener("change", async () => {
    await chrome.storage.local.set({ sttProvider: providerSelect.value });
    sttBalanceError = false; // reset on provider change
    void runPreflight();
  });

  saveBtn?.addEventListener("click", async () => {
    await chrome.storage.local.set({
      backendUrl: backendInput?.value ?? "",
      urlPattern: patternInput?.value ?? "",
      sttProvider: providerSelect?.value ?? "salutespeech",
    });
    show(savedNotice);
    setTimeout(() => hide(savedNotice), 2000);
  });

  grantMicBtn?.addEventListener("click", () => {
    chrome.tabs.create({
      url: chrome.runtime.getURL("src/permissions/permissions.html"),
    });
  });

  const evalBtn = $("eval-settings-btn");
  evalBtn?.addEventListener("click", () => {
    chrome.tabs.create({
      url: chrome.runtime.getURL("src/settings/evaluation-settings.html"),
    });
  });

  void updateMicStatus(micSettings, micStatusText);
  initMicSelect();
  void populateMicList();

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.micGranted) {
      void updateMicStatus(micSettings, micStatusText);
      void updateRecButtonState();
      void populateMicList();
    }
  });

  // ── Test mode toggle ─────────────────────────────────────────────────────
  initTestModeToggle();
}

// ── Test mode (synthetic conversation without microphone) ─────────────────

let testWsClient: WsClient | null = null;
let testModeEnabled = false;

function initTestModeToggle(): void {
  const testBtn = $<HTMLButtonElement>("test-mode-btn");
  const testStatus = $("test-mode-status");
  if (!testBtn) return;

  // Load saved state
  void chrome.storage.local.get("testMode").then((result) => {
    testModeEnabled = !!(result as { testMode?: boolean }).testMode;
    updateTestModeUI(testBtn, testStatus);
  });

  testBtn.addEventListener("click", async () => {
    testModeEnabled = !testModeEnabled;
    await chrome.storage.local.set({ testMode: testModeEnabled });
    updateTestModeUI(testBtn, testStatus);
    void updateRecButtonState();
  });
}

function updateTestModeUI(
  btn: HTMLButtonElement,
  statusEl: HTMLElement | null,
): void {
  if (testModeEnabled) {
    btn.textContent = "Тест: ВКЛ";
    btn.classList.add("active");
    if (statusEl) {
      statusEl.textContent = "Нажмите REC для запуска теста";
      statusEl.className = "test-status running";
      statusEl.hidden = false;
    }
  } else {
    btn.textContent = "Тест: ВЫКЛ";
    btn.classList.remove("active");
    if (statusEl) statusEl.hidden = true;
  }
}

/** Start a test-mode session: direct WS, no audio capture. */
function startTestSession(): void {
  const sessionId = `test-${crypto.randomUUID().slice(0, 8)}`;
  const testStatus = $("test-mode-status");

  // Open direct WebSocket for test mode
  testWsClient = new WsClient(
    (msg) => {
      handleWsMessage(msg);
      if (msg.type === "evaluation_started") {
        if (testStatus) {
          testStatus.textContent = "Тест завершён";
          testStatus.className = "test-status";
        }
      }
    },
    BACKEND_WS_URL,
  );

  void testWsClient.waitForOpen(5000).then(() => {
    if (testStatus) {
      testStatus.textContent = "Синтетический разговор...";
      testStatus.className = "test-status running";
      testStatus.hidden = false;
    }
    void chrome.storage.local
      .get("panel")
      .then((result) => {
        const panel = (result as { panel?: PanelState }).panel;
        const kbId = panel?.kbId ?? "";
        testWsClient?.sendControl({
          type: "session_start",
          session_id: sessionId,
          kb_id: kbId,
          test_mode: true,
        });
      });
  }).catch(() => {
    if (testStatus) {
      testStatus.textContent = "Не удалось подключиться";
      testStatus.className = "test-status error";
      testStatus.hidden = false;
    }
    stopTestSession();
  });
}

/** Stop a test-mode session. */
function stopTestSession(): void {
  if (testWsClient) {
    testWsClient.close();
    testWsClient = null;
  }
}

// ── Diarized transcript rendering ─────────────────────────────────────────

function formatTimestamp(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function renderDiarizedTranscript(utterances: DiarizedUtterance[]): void {
  const fullList = $("transcript-full-list");
  if (!fullList) return;

  fullList.replaceChildren();

  for (const u of utterances) {
    const entry = document.createElement("div");
    entry.className = `transcript-entry ${
      u.speaker === "rep" ? "speaker-you" : "speaker-client"
    }`;
    entry.dataset.speaker = u.speaker;
    if (u.start_ms != null) entry.dataset.startMs = String(u.start_ms);
    if (u.end_ms != null) entry.dataset.endMs = String(u.end_ms);

    if (u.start_ms != null) {
      const timeSpan = document.createElement("span");
      timeSpan.className = "transcript-time";
      timeSpan.textContent = formatTimestamp(u.start_ms);
      entry.appendChild(timeSpan);
    }

    const speakerSpan = document.createElement("span");
    speakerSpan.className = "transcript-speaker";
    speakerSpan.textContent = u.speaker === "rep" ? "Вы" : "Клиент";

    const textSpan = document.createElement("span");
    textSpan.className = "transcript-text";
    textSpan.textContent = u.text;

    entry.appendChild(speakerSpan);
    entry.appendChild(textSpan);
    fullList.appendChild(entry);
  }
}

// ── Download transcript (Phase 4) ─────────────────────────────────────────

function downloadTranscript(): void {
  const list = $("transcript-full-list");
  if (!list) return;

  const entries = list.querySelectorAll(".transcript-entry");
  const lines: string[] = [];
  for (const entry of entries) {
    const el = entry as HTMLElement;
    const time = el.querySelector(".transcript-time")?.textContent ?? "";
    const speaker = el.querySelector(".transcript-speaker")?.textContent ?? "";
    const text = el.querySelector(".transcript-text")?.textContent ?? "";
    const prefix = time ? `[${time}] ` : "";
    lines.push(`${prefix}${speaker}: ${text}`);
  }

  if (lines.length === 0) return;

  const content = lines.join("\n");
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `transcript-${new Date().toISOString().slice(0, 10)}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

function initDownloadButton(): void {
  const btn = $("download-transcript-btn");
  btn?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation(); // Prevent toggling the <details>
    downloadTranscript();
  });
}

// ── New Call: centralized per-call state reset ───────────────────────────

function resetForNewCall(): void {
  void saveState({ sessionId: crypto.randomUUID(), briefing: null });

  // Unmount Preact brief panels
  const bc = $("briefing-content");
  if (bc) mountBriefPanel(bc, null);
  hide(bc);
  const bcc = $("briefing-collapsed");
  if (bcc) mountBriefPanel(bcc, null);
  const bcd = $("briefing-collapsed-done");
  if (bcd) mountBriefPanel(bcd, null);

  stopEvalPolling();
  evalReceived = false;
  pendingFollowUpEmail = null;
  pendingCrmNote = null;
  hide($("follow-up-actions"));

  // Clear transcript DOM (Phase 4 full list)
  const fullList = $("transcript-full-list");
  if (fullList) fullList.textContent = "";

  // Stop recording timer
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }

  // Reset live-call signals
  resetSignals({
    isRecording: false,
    wsConnected: false,
    briefData: null,
  });

  // Unmount live-call Preact tree and Phase 4 rec bar
  unmountLiveCall();
  unmountRecBarDone();
}

// ── New Call button (Phase 4) ─────────────────────────────────────────────

function initNewCallButton(): void {
  const btn = $("new-call-btn");
  btn?.addEventListener("click", () => {
    resetForNewCall();
    setPhase(2);
  });
}

// ── Init ──────────────────────────────────────────────────────────────────

async function init(): Promise<void> {
  // Show version from manifest
  const verEl = $("app-version");
  if (verEl) verEl.textContent = `v${chrome.runtime.getManifest().version}`;

  connectPort();
  initSettingsOverlay();
  initUpload();
  initRecButton();
  initBriefing();
  initPreflight();
  initDownloadButton();
  initNewCallButton();
  initFollowUpButtons();

  // Always restore briefing from cached state (session storage survives
  // side-panel close/reopen). The SW handshake only knows about capture
  // state, not about upload/briefing data, so we must render from storage.
  const state = await loadState();
  if (state.briefing) {
    if (isBriefDataV2(state.briefing)) {
      renderBriefToAllPhases(state.briefing);
    } else {
      await saveState({ briefing: null });
    }
    updateFileStrip(state.fileNames);
  }
  // Restore phase from local state if we're still at the default phase.
  // The SW handshake may have arrived during loadState() and set a phase
  // (e.g. phase 3 if capturing), so only override if phase is still 0.
  if (currentPhase === 0 && state.kbId && state.briefing) {
    setPhase(2);
  }

  // Always run preflight so the user sees backend status on open
  void runPreflight();
}

document.addEventListener("DOMContentLoaded", () => {
  void init();
});
