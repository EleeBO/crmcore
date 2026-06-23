/** Backend URLs — must match manifest.json host_permissions. */
export const BACKEND_HTTP_URL = "http://localhost:8000";
export const BACKEND_WS_URL = "ws://localhost:8000/ws";
export const API_BASE = `${BACKEND_HTTP_URL}/api/v1`;

/** Chrome extension alarm name for Service Worker keepalive. */
export const KEEPALIVE_ALARM = "keepalive";
export const KEEPALIVE_PERIOD_MINUTES = 0.4; // 24 seconds

/** Extension offscreen document path. */
export const OFFSCREEN_HTML = "src/offscreen/offscreen.html";
