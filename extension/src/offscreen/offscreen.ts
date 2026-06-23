/**
 * Offscreen Document — audio capture + WebSocket pipeline (FEAT-007).
 *
 * Responsibilities:
 *  1. Receive { streamId, sessionId, kbId } from Service Worker
 *  2. Capture tab audio via getUserMedia (chromeMediaSource: 'tab')
 *  3. Capture mic audio via getUserMedia
 *  4. Mix both through ChannelMergerNode (L=mic, R=tab) → AudioWorklet
 *  5. AudioWorklet converts Float32 → Int16 PCM and posts buffers back
 *  6. Send binary audio frames to backend via WebSocket
 *  7. Route tab audio back to destination so user still hears it
 */

import { WsClient } from "../lib/ws-client";
import type { ExtMessage, WsMessage } from "../shared/messages";
import { BACKEND_WS_URL } from "../shared/constants";

const SAMPLE_RATE = 16_000;

// AUDIO_LEVEL throttle: ~15 Hz (Layer 1)
const AUDIO_LEVEL_MIN_INTERVAL_MS = 66;
let lastLevelSentAt = 0;

let wsClient: WsClient | null = null;
let audioCtx: AudioContext | null = null;
let workletNode: AudioWorkletNode | null = null;
let tabStream: MediaStream | null = null;
let micStream: MediaStream | null = null;
let capturing = false;

// Session params stored for WS reconnect replay
let currentSessionId = "";
let currentKbId = "";
let currentSttProvider = "";

// Port to Service Worker for bidirectional communication
const swPort = chrome.runtime.connect({ name: "offscreen" });
let swPortAlive = true;
swPort.onDisconnect.addListener(() => { swPortAlive = false; });

// Track whether we're waiting for evaluation result before closing WS
let awaitingEvalResult = false;
let evalCloseTimer: ReturnType<typeof setTimeout> | null = null;
const EVAL_CLOSE_TIMEOUT_MS = 180_000; // 3 min max wait for evaluation

/** Forward WebSocket messages to Service Worker (which relays to side panel). */
function handleWsMessage(msg: WsMessage): void {
  if (!swPortAlive) return;
  try {
    swPort.postMessage({ type: "WS_MESSAGE", payload: msg });
  } catch {
    swPortAlive = false;
  }

  // Auto-close WS after evaluation completes (or fails)
  if (
    awaitingEvalResult &&
    (msg.type === "evaluation_result" || msg.type === "evaluation_error")
  ) {
    awaitingEvalResult = false;
    if (evalCloseTimer) {
      clearTimeout(evalCloseTimer);
      evalCloseTimer = null;
    }
    // Small delay to let the message propagate
    setTimeout(() => {
      wsClient?.close();
      wsClient = null;
      notifyWsStatus(false);
    }, 500);
  }
}

/** Notify SW of WebSocket status changes. */
function notifyWsStatus(connected: boolean): void {
  if (!swPortAlive) return;
  try {
    swPort.postMessage({ type: "WS_STATUS", connected });
  } catch {
    swPortAlive = false;
  }
}

/**
 * Start audio capture pipeline.
 * @param streamId  Tab capture stream ID from chrome.tabCapture
 * @param sessionId Backend session ID
 * @param kbId      Knowledge base ID
 */
async function startCapture(
  streamId: string,
  sessionId: string,
  kbId: string,
  deviceId?: string,
  sttProvider?: string,
): Promise<void> {
  // If already capturing, stop first to allow clean restart
  if (capturing) {
    await stopCapture(currentSessionId);
  }
  // Clear any pending eval close timer from a previous session
  if (evalCloseTimer) {
    clearTimeout(evalCloseTimer);
    evalCloseTimer = null;
  }
  awaitingEvalResult = false;
  capturing = true;
  console.log("[Offscreen] startCapture: beginning pipeline setup, swPortAlive=", swPortAlive);

  // Create AudioContext at 16 kHz for STT compatibility
  audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
  if (audioCtx.state === "suspended") {
    await audioCtx.resume();
  }

  // Acquire tab audio stream using the streamId from tabCapture
  tabStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      // @ts-expect-error — Chrome-specific constraint
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
    video: false,
  });

  console.log("[Offscreen] Tab stream acquired, tracks:", tabStream.getAudioTracks().length);

  // Acquire mic audio stream (use selected device or system default)
  const micConstraints: MediaStreamConstraints = {
    audio: deviceId ? { deviceId: { exact: deviceId } } : true,
    video: false,
  };
  try {
    micStream = await navigator.mediaDevices.getUserMedia(micConstraints);
  } catch (err) {
    // If selected device is unavailable, fall back to default
    if (deviceId) {
      console.warn("[Offscreen] Selected mic unavailable, falling back to default:", err);
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } else {
      throw err;
    }
  }

  // Route tab audio back to speakers so the user still hears the call
  const tabSource = audioCtx.createMediaStreamSource(tabStream);
  tabSource.connect(audioCtx.destination);

  const micSource = audioCtx.createMediaStreamSource(micStream);

  // Merge mic (L=ch0) and tab (R=ch1) into stereo
  const merger = audioCtx.createChannelMerger(2);
  micSource.connect(merger, 0, 0);
  tabSource.connect(merger, 0, 1);

  // Load AudioWorklet (IIFE bundle compiled separately)
  await audioCtx.audioWorklet.addModule(
    chrome.runtime.getURL("audio-worklet.js")
  );

  workletNode = new AudioWorkletNode(audioCtx, "pcm-processor");

  // Receive PCM16 chunks and audio levels from worklet
  workletNode.port.onmessage = (
    event: MessageEvent<{ type: string; buffer?: ArrayBuffer; mic?: number; tab?: number }>
  ) => {
    const data = event.data;
    if (data.type === "pcm" && data.buffer instanceof ArrayBuffer) {
      wsClient?.sendAudio(data.buffer);
    } else if (data.type === "level") {
      if (!swPortAlive) { console.warn("[Offscreen] swPort dead, dropping level"); return; }
      // Throttle AUDIO_LEVEL to ~15 Hz (Layer 1)
      const now = performance.now();
      if (now - lastLevelSentAt < AUDIO_LEVEL_MIN_INTERVAL_MS) return;
      lastLevelSentAt = now;
      try {
        swPort.postMessage({
          type: "AUDIO_LEVEL",
          mic: data.mic ?? 0,
          tab: data.tab ?? 0,
        });
      } catch {
        swPortAlive = false;
      }
    }
  };

  merger.connect(workletNode);
  console.log("[Offscreen] Audio pipeline connected: merger -> worklet");
  // Do NOT connect workletNode to destination — we don't want double audio

  // Store session params for reconnect replay
  currentSessionId = sessionId;
  currentKbId = kbId;
  currentSttProvider = sttProvider ?? "";

  // Open WebSocket with reconnect handler
  wsClient = new WsClient(handleWsMessage, BACKEND_WS_URL, () => {
    // On reconnect: re-send session_start so backend creates a new orchestrator
    const reconnectCtrl: Record<string, string> = {
      type: "session_start",
      session_id: currentSessionId,
      kb_id: currentKbId,
    };
    if (currentSttProvider) reconnectCtrl.stt_provider = currentSttProvider;
    wsClient?.sendControl(reconnectCtrl);
    // Notify SW of reconnection (for side panel status)
    if (swPortAlive) {
      try {
        swPort.postMessage({ type: "WS_RECONNECTED" });
      } catch {
        swPortAlive = false;
      }
    }
  });
  await wsClient.waitForOpen();
  console.log("[Offscreen] WebSocket connected");

  // Notify SW that WS is connected
  notifyWsStatus(true);

  const startCtrl: Record<string, string> = {
    type: "session_start",
    session_id: sessionId,
    kb_id: kbId,
  };
  if (sttProvider) startCtrl.stt_provider = sttProvider;
  wsClient.sendControl(startCtrl);
}

/** Stop capture; keep WebSocket open for evaluation messages. */
async function stopCapture(sessionId: string): Promise<void> {
  if (!capturing && !audioCtx) return; // nothing to stop
  capturing = false;

  wsClient?.sendControl({ type: "session_end", session_id: sessionId });

  // Stop audio pipeline but keep WS open for evaluation_started / evaluation_result
  workletNode?.disconnect();
  workletNode = null;

  // Stop all MediaStream tracks so Chrome releases the tab capture
  tabStream?.getTracks().forEach((t) => t.stop());
  tabStream = null;
  micStream?.getTracks().forEach((t) => t.stop());
  micStream = null;

  if (audioCtx) {
    await audioCtx.close();
    audioCtx = null;
  }

  // Keep WS alive until evaluation completes (or timeout)
  awaitingEvalResult = true;
  evalCloseTimer = setTimeout(() => {
    console.warn("[Offscreen] Eval timeout — closing WS");
    awaitingEvalResult = false;
    wsClient?.close();
    wsClient = null;
    notifyWsStatus(false);
  }, EVAL_CLOSE_TIMEOUT_MS);
}

// Listen for messages from Service Worker.
// Only START_SESSION and STOP_SESSION are handled here.
// Side panel sends PREPARE_CAPTURE (handled by SW), not START_SESSION,
// so there is no risk of the side panel accidentally triggering capture.
chrome.runtime.onMessage.addListener(
  (message: ExtMessage, _sender, sendResponse) => {
    if (message.type === "START_SESSION") {
      const msg = message as {
        streamId?: string;
        deviceId?: string;
        sttProvider?: string;
        sessionId: string;
        kbId: string;
      };
      const streamId = msg.streamId;
      if (!streamId) return false;

      const { sessionId, kbId, deviceId, sttProvider } = msg;
      startCapture(streamId, sessionId, kbId, deviceId, sttProvider)
        .then(() => sendResponse({ ok: true }))
        .catch((err: Error) => {
          capturing = false;
          sendResponse({ ok: false, error: err.message });
        });
      return true; // async
    }

    if (message.type === "STOP_SESSION") {
      // Ignore if not currently capturing
      if (!capturing && !audioCtx) return false;

      const { sessionId } = message;
      stopCapture(sessionId)
        .then(() => sendResponse({ ok: true }))
        .catch((err: Error) =>
          sendResponse({ ok: false, error: err.message })
        );
      return true;
    }

    // Ignore unknown messages silently
    return false;
  }
);
