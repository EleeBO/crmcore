/**
 * Binary WebSocket client for AI Sales Copilot.
 *
 * Frame format: 5-byte header + payload
 *   - Bytes 0–3: sequence number (uint32, little-endian)
 *   - Byte  4:   channel (0 = audio PCM16, 1 = control JSON)
 */

import type { WsMessage } from "../shared/messages";
import { BACKEND_WS_URL } from "../shared/constants";

type MessageHandler = (msg: WsMessage) => void;

const CHANNEL_AUDIO = 0;
const CHANNEL_CONTROL = 1;

const BACKOFF_INITIAL_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;
const HEADER_BYTES = 5;

export class WsClient {
  private ws: WebSocket | null = null;
  private seq = 0;
  private backoffMs = BACKOFF_INITIAL_MS;
  private stopped = false;
  private onMessage: MessageHandler;
  private url: string;
  private onReconnect: (() => void) | null;
  private hasConnectedOnce = false;

  constructor(
    onMessage: MessageHandler,
    url = BACKEND_WS_URL,
    onReconnect?: () => void,
  ) {
    this.onMessage = onMessage;
    this.url = url;
    this.onReconnect = onReconnect ?? null;
    this.connect();
  }

  private connect(): void {
    if (this.stopped) return;
    this.ws = new WebSocket(this.url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.backoffMs = BACKOFF_INITIAL_MS;
      if (this.hasConnectedOnce) {
        this.onReconnect?.();
      }
      this.hasConnectedOnce = true;
    };

    this.ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === "string") {
        try {
          const msg = JSON.parse(event.data) as WsMessage;
          this.onMessage(msg);
        } catch {
          // ignore malformed JSON
        }
      }
    };

    this.ws.onclose = () => {
      if (!this.stopped) this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private scheduleReconnect(): void {
    const delay = this.backoffMs;
    this.backoffMs = Math.min(this.backoffMs * 2, BACKOFF_MAX_MS);
    setTimeout(() => this.connect(), delay);
  }

  /** Wait for the WebSocket connection to open. */
  waitForOpen(timeoutMs = 5000): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }
      const timer = setTimeout(
        () => reject(new Error("WS open timeout")),
        timeoutMs,
      );
      const ws = this.ws;
      const origOnOpen = ws?.onopen;
      if (ws) {
        ws.onopen = (ev: Event) => {
          clearTimeout(timer);
          this.backoffMs = BACKOFF_INITIAL_MS;
          if (typeof origOnOpen === "function") origOnOpen.call(ws, ev);
          resolve();
        };
      } else {
        clearTimeout(timer);
        reject(new Error("No WebSocket instance"));
      }
    });
  }

  /** Send raw PCM16 audio bytes as a binary audio frame. */
  sendAudio(pcm16: ArrayBuffer): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const header = new ArrayBuffer(HEADER_BYTES);
    const view = new DataView(header);
    view.setUint32(0, this.seq++, /*littleEndian=*/ true);
    view.setUint8(4, CHANNEL_AUDIO);

    // Concatenate header + payload
    const frame = new Uint8Array(HEADER_BYTES + pcm16.byteLength);
    frame.set(new Uint8Array(header), 0);
    frame.set(new Uint8Array(pcm16), HEADER_BYTES);
    this.ws.send(frame.buffer);
  }

  /** Send a JSON control message as a binary control frame. */
  sendControl(payload: Record<string, unknown>): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const json = JSON.stringify(payload);
    const encoded = new TextEncoder().encode(json);

    const header = new ArrayBuffer(HEADER_BYTES);
    const view = new DataView(header);
    view.setUint32(0, this.seq++, /*littleEndian=*/ true);
    view.setUint8(4, CHANNEL_CONTROL);

    const frame = new Uint8Array(HEADER_BYTES + encoded.byteLength);
    frame.set(new Uint8Array(header), 0);
    frame.set(encoded, HEADER_BYTES);
    this.ws.send(frame.buffer);
  }

  close(): void {
    this.stopped = true;
    this.ws?.close();
    this.ws = null;
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
