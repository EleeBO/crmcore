/**
 * Service Worker — control plane for AI Sales Copilot (FEAT-007).
 *
 * Responsibilities:
 *  - Keepalive alarm (prevents SW unload after 30s)
 *  - Port-based message routing: Side Panel <-> Offscreen
 *  - Offscreen Document lifecycle management
 *  - Badge recording indicator
 *  - Hint buffering for panel reconnect
 *  - GET_SESSION_STATE handshake
 *  - Two-step tab capture via action.onClicked user gesture
 */

import {
  KEEPALIVE_ALARM,
  KEEPALIVE_PERIOD_MINUTES,
  OFFSCREEN_HTML,
} from "../shared/constants";
import type { ExtMessage, WsMessage } from "../shared/messages";

// ── Side panel behavior: open on icon click ──────────────────────────────

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(console.error);

// ── Keepalive ─────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(KEEPALIVE_ALARM, {
    periodInMinutes: KEEPALIVE_PERIOD_MINUTES,
  });
});

chrome.alarms.onAlarm.addListener((_alarm) => {
  // No-op: alarm handler presence keeps the SW alive.
});

// ── Session / capture state ──────────────────────────────────────────────

let captureInProgress = false;
let sessionTabId: number | null = null;
let currentSessionId = "";
let currentKbId = "";
let wsConnected = false;

// ── Pending capture (two-step flow) ──────────────────────────────────────
// Side panel sends PREPARE_CAPTURE -> SW stores pending here.
// User clicks extension icon -> action.onClicked fires with user gesture ->
// SW calls getMediaStreamId (requires user gesture) -> starts capture.

let pendingCapture: {
  sessionId: string;
  kbId: string;
  tabId: number;
} | null = null;

// ── Port references ──────────────────────────────────────────────────────

let offscreenPort: chrome.runtime.Port | null = null;
let sidePanelPort: chrome.runtime.Port | null = null;

// ── Hint buffer for panel reconnect ──────────────────────────────────────

let lastHintEnd: WsMessage | null = null;
let lastEvaluationResult: WsMessage | null = null;
let lastFollowUpReady: WsMessage | null = null;

// ── Helpers ───────────────────────────────────────────────────────────────

async function ensureOffscreenDocument(): Promise<void> {
  const existing = await chrome.runtime.getContexts({
    contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],
  });
  if (existing.length > 0) return;

  await chrome.offscreen.createDocument({
    url: chrome.runtime.getURL(OFFSCREEN_HTML),
    reasons: [
      chrome.offscreen.Reason.USER_MEDIA,
      chrome.offscreen.Reason.AUDIO_PLAYBACK,
    ],
    justification:
      "Captures mic/tab audio for real-time transcription; routes tab audio to speakers.",
  });
}

function setBadge(text: string, color?: string): void {
  chrome.action.setBadgeText({ text });
  if (text && color) {
    chrome.action.setBadgeBackgroundColor({ color });
  }
}

function clearPendingCapture(): void {
  pendingCapture = null;
  setBadge("");
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch(console.error);
}

// ── Hint buffer management ───────────────────────────────────────────────

function bufferHint(payload: WsMessage): void {
  if (payload.type === "hint_end") {
    lastHintEnd = payload;
  }
  if (payload.type === "evaluation_result") {
    lastEvaluationResult = payload;
  }
  if (payload.type === "follow_up_ready") {
    lastFollowUpReady = payload;
  }
  // hint_start and hint_chunk are no longer sent by backend (silent generation)
}

// ── Two-step capture: action.onClicked handler ──────────────────────────
// This fires when the user clicks the extension icon AND
// openPanelOnActionClick is false (set during PREPARE_CAPTURE).
// action.onClicked provides a valid user gesture for getMediaStreamId.

chrome.action.onClicked.addListener(async (tab) => {
  console.log("[SW] action.onClicked fired, pendingCapture=", !!pendingCapture);
  if (!pendingCapture) {
    // No pending capture — just open the side panel
    if (tab.id) {
      chrome.sidePanel.open({ tabId: tab.id }).catch(console.error);
    }
    return;
  }

  const { sessionId, kbId, tabId: targetTabId } = pendingCapture;
  pendingCapture = null;

  // Re-enable panel-on-click immediately
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch(console.error);

  try {
    // getMediaStreamId called inside action.onClicked = valid user gesture
    const streamId = await new Promise<string>((resolve, reject) => {
      chrome.tabCapture.getMediaStreamId({ targetTabId }, (id) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(id);
        }
      });
    });

    console.log("[SW] getMediaStreamId success, streamId length:", streamId.length);
    captureInProgress = true;
    sessionTabId = targetTabId;
    currentSessionId = sessionId;
    currentKbId = kbId;

    await ensureOffscreenDocument();

    // Wait for offscreen port to connect before sending START_SESSION.
    // The offscreen document was just created and needs time to register
    // its onMessage listener. We wait for the "offscreen" port to appear.
    if (!offscreenPort) {
      console.log("[SW] Waiting for offscreen port...");
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Offscreen port timeout")), 5000);
        const check = () => {
          if (offscreenPort) { clearTimeout(timeout); resolve(); return; }
          setTimeout(check, 50);
        };
        check();
      });
      console.log("[SW] Offscreen port ready");
    }

    // Read selected microphone device and STT provider from settings
    const localSettings = await chrome.storage.local.get([
      "selectedMicId",
      "sttProvider",
    ]) as { selectedMicId?: string; sttProvider?: string };
    const deviceId = localSettings.selectedMicId || undefined;
    const sttProvider = localSettings.sttProvider || undefined;

    // Forward to offscreen document
    const offscreenMsg = {
      type: "START_SESSION" as const,
      sessionId,
      kbId,
      tabId: targetTabId,
      streamId,
      deviceId,
      sttProvider,
    };
    const resp = await chrome.runtime.sendMessage(offscreenMsg);
    // resp is undefined if no listener handled the message — treat as failure
    if (!resp || !resp.ok) {
      throw new Error(resp?.error ?? "Offscreen did not respond to START_SESSION");
    }
    console.log("[SW] Offscreen responded ok, starting capture");

    setBadge("REC", "#dc2626");

    // Set side panel per-tab scope
    if (sessionTabId) {
      chrome.sidePanel
        .setOptions({ tabId: sessionTabId, enabled: true })
        .catch(console.error);
    }

    // Notify side panel that capture started
    sidePanelPort?.postMessage({ type: "CAPTURE_STARTED" });
  } catch (err) {
    captureInProgress = false;
    sessionTabId = null;
    currentSessionId = "";
    currentKbId = "";
    setBadge("");

    const errorMsg = err instanceof Error ? err.message : String(err);
    sidePanelPort?.postMessage({ type: "CAPTURE_FAILED", error: errorMsg });
  }
});

// ── Port listener ────────────────────────────────────────────────────────

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "offscreen") {
    console.log("[SW] Offscreen port connected");
    offscreenPort = port;

    port.onMessage.addListener((message) => {
      if (message.type === "WS_MESSAGE" && message.payload) {
        const payload = message.payload as WsMessage;

        // Buffer hints for panel reconnect
        bufferHint(payload);

        // Forward to side panel via Port
        sidePanelPort?.postMessage({ type: "WS_MESSAGE", payload });
      } else if (message.type === "AUDIO_LEVEL") {
        // Forward to side panel (first one logs) via Port only (no broadcast)
        sidePanelPort?.postMessage({
          type: "AUDIO_LEVEL",
          mic: message.mic as number,
          tab: message.tab as number,
        });
      } else if (message.type === "WS_RECONNECTED") {
        wsConnected = true;
        sidePanelPort?.postMessage({ type: "WS_RECONNECTED" });
      } else if (message.type === "WS_STATUS") {
        wsConnected = message.connected as boolean;
        sidePanelPort?.postMessage({
          type: "WS_STATUS",
          connected: wsConnected,
        });
      }
    });

    port.onDisconnect.addListener(() => {
      offscreenPort = null;
      wsConnected = false;

      // Offscreen was killed — notify side panel and reset
      if (captureInProgress) {
        sidePanelPort?.postMessage({
          type: "SESSION_ABORTED",
          reason: "Offscreen document killed",
        });
      }

      captureInProgress = false;
      sessionTabId = null;
      currentSessionId = "";
      currentKbId = "";
      lastHintEnd = null;
      lastEvaluationResult = null;
      lastFollowUpReady = null;
      setBadge("");
    });
  }

  if (port.name === "sidepanel") {
    console.log("[SW] Side panel port connected");
    sidePanelPort = port;

    port.onMessage.addListener((msg) => {
      if (msg.type === "GET_SESSION_STATE") {
        port.postMessage({
          type: "SESSION_STATE",
          capturing: captureInProgress,
          sessionId: currentSessionId,
          kbId: currentKbId,
          wsConnected,
        });

        // Replay last hint on panel reconnect
        if (lastHintEnd && captureInProgress) {
          port.postMessage({ type: "WS_MESSAGE", payload: lastHintEnd });
        }

        // Replay last follow-up on panel reconnect
        if (lastFollowUpReady) {
          port.postMessage({ type: "WS_MESSAGE", payload: lastFollowUpReady });
        }

        // Replay last evaluation result on panel reconnect
        if (lastEvaluationResult) {
          port.postMessage({ type: "WS_MESSAGE", payload: lastEvaluationResult });
        }
      }
    });

    port.onDisconnect.addListener(() => {
      sidePanelPort = null;
    });
  }
});

// ── Message routing ───────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener(
  (message: ExtMessage, _sender, sendResponse) => {
    if (message.type === "PREPARE_CAPTURE") {
      // If we think capture is in progress but port is dead, reset
      if (captureInProgress && offscreenPort === null) {
        captureInProgress = false;
      }

      if (captureInProgress) {
        sendResponse({ ok: false, error: "Capture already in progress" });
        return false;
      }

      console.log("[SW] PREPARE_CAPTURE received, tabId:", message.tabId);
      // Store pending capture for action.onClicked
      pendingCapture = {
        sessionId: message.sessionId,
        kbId: message.kbId,
        tabId: message.tabId,
      };

      // Disable panel-on-click so action.onClicked fires
      chrome.sidePanel
        .setPanelBehavior({ openPanelOnActionClick: false })
        .catch(console.error);

      // Show amber badge to prompt user to click icon
      setBadge("\u25B6", "#f59e0b");

      sendResponse({ ok: true });
      return false;
    }

    if (message.type === "STOP_SESSION") {
      const { sessionId } = message;

      // Also clear any pending capture
      if (pendingCapture) {
        clearPendingCapture();
      }

      const stopMsg = { type: "STOP_SESSION" as const, sessionId };
      chrome.runtime
        .sendMessage(stopMsg)
        .catch(() => {
          /* offscreen may already be closed */
        })
        .finally(() => {
          captureInProgress = false;
          sessionTabId = null;
          currentSessionId = "";
          currentKbId = "";
          lastHintEnd = null;
          lastEvaluationResult = null;
          setBadge("");
        });
      sendResponse({ ok: true });
      return false;
    }

    // Ignore unknown/unhandled message types silently
    return false;
  }
);
