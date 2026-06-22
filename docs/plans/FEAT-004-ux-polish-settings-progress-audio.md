# FEAT-004: UX Polish — Settings Restructure, Upload Stepper, Audio Level Visualization

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve extension UX: move mic setup to Settings tab (non-blocking), replace frozen progress bar with multi-step stepper, add real-time audio level visualization driven by actual mic/tab signal.

**Architecture:** Three independent UI improvements sharing message plumbing. (1) Permission screen removed as blocker; mic config becomes a Settings section. (2) Upload flow gets a 3-phase stepper with indeterminate animation on LLM phase. (3) AudioWorklet computes RMS per channel, relays via port-SW-content/popup for VU-meter bars.

**Tech Stack:** TypeScript, Chrome Extension APIs, AudioWorklet, CSS animations, SVG

**Review fixes applied:** Architect, Backend, Product reviews (2026-03-07). See Review Fixes section below.

---

## Review Fixes Applied

| # | Source | Issue | Fix |
|---|--------|-------|-----|
| 1 | Architect, Backend | `fetchAndRenderBriefing` `finally` hides error before user sees it | Move `hide(loading)` to success path only; `catch` only cleans animation class and rethrows |
| 2 | Architect | Dual message type `AUDIO_LEVEL` vs `audio_level` | Standardize to `AUDIO_LEVEL` everywhere (SW, widget, popup) |
| 3 | Architect, Backend | `swPort` not guarded against SW restart in offscreen | Add `swPortAlive` flag + `onDisconnect` handler + try/catch |
| 4 | Backend | Unvalidated `data.buffer` in offscreen worklet handler | Add `instanceof ArrayBuffer` guard |
| 5 | Backend | DOM lookups on every AUDIO_LEVEL in popup | Cache VU refs at `initRecButton()` setup time |
| 6 | Product | VU labels "MIC"/"TAB" unclear for Russian users | Change to "МИК" / "ЗВУК" |
| 7 | Product | No explanation for disabled REC button | Add `title` attribute when disabled |
| 8 | Product | Tab flash too subtle (3 cycles then gone) | Add persistent red dot badge on Settings tab |
| 9 | Product | No ARIA roles on stepper | Add `role="status"`, `aria-live`, `aria-label` |
| 10 | Product | No upload fetch timeout | Add `AbortController` with 30s timeout |
| 11 | Product | Step labels may truncate | Add `white-space: nowrap` |
| 12 | Product | Error stepper timeout too short (3s) | Increase to 5s |
| 13 | Architect | `chrome.runtime.sendMessage` AUDIO_LEVEL hits offscreen | Add `AUDIO_LEVEL` to offscreen message handler, return false |

---

## Files to Modify

| File | Tasks |
|------|-------|
| `extension/src/popup/popup.html` | 1, 2, 3 |
| `extension/src/popup/popup.css` | 1, 2, 3 |
| `extension/src/popup/popup.ts` | 1, 2, 3 |
| `extension/src/audio-worklet.ts` | 4 |
| `extension/src/offscreen/offscreen.ts` | 5 |
| `extension/src/background/service-worker.ts` | 6 |
| `extension/src/shared/messages.ts` | 5, 6 |
| `extension/src/content/widget.ts` | 7 |

## Progress Tracking

- [x] Task 1: Move mic permission to Settings tab (non-blocking UI)
- [x] Task 2: Multi-step upload stepper (replace progress bar)
- [x] Task 3: Indeterminate animation for LLM generation phase
- [x] Task 4: AudioWorklet RMS computation
- [x] Task 5: Offscreen to Service Worker audio level relay
- [x] Task 6: Service Worker to Content Script + Popup audio level relay
- [x] Task 7: Widget VU-meter bars (real audio data)
- [x] Task 8: Popup VU-meter bars next to REC button

**Total Tasks:** 8 | **Completed:** 8 | **Remaining:** 0

---

### Task 1: Move mic permission to Settings tab (non-blocking UI)

**Goal:** Remove the blocking permission screen. Add mic status + setup button into the Settings tab. Briefing tab is always visible; REC stays disabled until mic is granted with a `title` tooltip explaining why.

**Files:**
- Modify: `extension/src/popup/popup.html:20-25` (remove `#permission-screen`)
- Modify: `extension/src/popup/popup.html:88-108` (add mic section to `#tab-settings`)
- Modify: `extension/src/popup/popup.css:49-55` (remove `#permission-screen` styles, add mic status styles)
- Modify: `extension/src/popup/popup.ts:84-91` (move permission logic into settings)
- Modify: `extension/src/popup/popup.ts:503-532` (remove UI-blocking logic from `init()`)

**Step 1: Modify popup.html — remove permission screen, add mic section to Settings**

Remove the entire `#permission-screen` section (lines 20-25).

In `#tab-settings` (line 88), replace the entire settings section with grouped layout:

```html
<!-- Settings tab -->
<section id="tab-settings" role="tabpanel" class="tab-panel" hidden>
  <div id="mic-settings" class="settings-group">
    <div class="settings-group-header">Микрофон</div>
    <div id="mic-status" class="mic-status">
      <span id="mic-status-icon" class="mic-icon" aria-hidden="true">&#x1F3A4;</span>
      <span id="mic-status-text">Не настроен</span>
    </div>
    <button id="grant-mic-btn" type="button" class="btn-secondary">
      Настроить микрофон
    </button>
  </div>

  <div class="settings-group">
    <div class="settings-group-header">Подключение</div>
    <label for="backend-url-input">URL бэкенда</label>
    <input
      id="backend-url-input"
      type="text"
      placeholder="ws://localhost:8000/ws"
      autocomplete="off"
      spellcheck="false"
    />
    <label for="url-pattern-input">URL-паттерн Mizugate</label>
    <input
      id="url-pattern-input"
      type="text"
      placeholder="https://crm.example.com/*"
      autocomplete="off"
    />
    <button id="save-settings-btn" type="button" class="btn-primary">
      Сохранить
    </button>
    <div id="settings-saved" hidden aria-live="polite">&#x2713; Сохранено</div>
  </div>
</section>
```

**Step 2: Add CSS for mic status, settings groups, and persistent badge**

Remove `#permission-screen` styles (lines 49-55 of popup.css). Add new styles:

```css
/* Settings groups */
.settings-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e5e7eb;
}

.settings-group:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.settings-group-header {
  font-size: 11px;
  font-weight: 700;
  color: #374151;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Mic status */
.mic-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.mic-icon {
  font-size: 14px;
}

#mic-settings.mic-off #mic-status-text {
  color: #dc2626;
}

#mic-settings.mic-granted #mic-status-text {
  color: #16a34a;
}

#mic-settings.mic-granted #grant-mic-btn {
  display: none;
}

.btn-secondary {
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: background 0.15s;
}

.btn-secondary:hover { background: #e5e7eb; }

/* Persistent red dot badge on Settings tab when mic not configured [Review Fix #8] */
.tab-btn.has-badge {
  position: relative;
}

.tab-btn.has-badge::after {
  content: '';
  position: absolute;
  top: 2px;
  right: 2px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #dc2626;
}
```

**Step 3: Update popup.ts — remove blocking logic, integrate mic into settings**

Delete `initPermissionScreen()` function entirely (lines 84-91).

Add `updateMicStatus` helper function with `title` tooltip on REC [Review Fix #7]:

```typescript
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
  // Enable/disable REC based on mic + kbId; set title tooltip [Review Fix #7]
  const state = await loadState();
  const recBtn = $<HTMLButtonElement>("rec-btn");
  if (recBtn) {
    const disabled = !hasMic || !state.kbId;
    recBtn.disabled = disabled;
    if (disabled && !hasMic) {
      recBtn.title = "Настройте микрофон в Настройках";
    } else if (disabled && !state.kbId) {
      recBtn.title = "Сначала загрузите файлы";
    } else {
      recBtn.title = "";
    }
  }
  // Update settings tab badge [Review Fix #8]
  const settingsTabBtn = document.querySelector<HTMLButtonElement>('[data-tab="settings"]');
  if (settingsTabBtn) {
    settingsTabBtn.classList.toggle("has-badge", !hasMic);
  }
}
```

Replace `initSettings()` (lines 468-491) to include mic handling:

```typescript
function initSettings(): void {
  const backendInput = $<HTMLInputElement>("backend-url-input");
  const patternInput = $<HTMLInputElement>("url-pattern-input");
  const saveBtn = $("save-settings-btn");
  const savedNotice = $("settings-saved");
  const micSettings = $("mic-settings");
  const micStatusText = $("mic-status-text");
  const grantBtn = $("grant-mic-btn");

  // Load existing settings
  void chrome.storage.local.get(["backendUrl", "urlPattern"]).then(
    (result) => {
      const r = result as { backendUrl?: string; urlPattern?: string };
      if (backendInput && r.backendUrl) backendInput.value = r.backendUrl;
      if (patternInput && r.urlPattern) patternInput.value = r.urlPattern;
    }
  );

  saveBtn?.addEventListener("click", async () => {
    await chrome.storage.local.set({
      backendUrl: backendInput?.value ?? "",
      urlPattern: patternInput?.value ?? "",
    });
    show(savedNotice);
    setTimeout(() => hide(savedNotice), 2000);
  });

  // Mic permission button opens permissions page
  grantBtn?.addEventListener("click", () => {
    chrome.tabs.create({ url: chrome.runtime.getURL("src/permissions/permissions.html") });
    window.close();
  });

  // Update mic status display
  void updateMicStatus(micSettings, micStatusText);

  // Listen for mic status changes
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.micGranted) {
      void updateMicStatus(micSettings, micStatusText);
    }
  });
}
```

Replace `init()` (lines 495-542) — remove all permission-blocking logic:

```typescript
async function init(): Promise<void> {
  initTabs();
  initUpload();
  initRecButton();
  initBriefing();
  initSettings();

  // Restore capture state
  const hasMic = await checkMicPermission();
  const state = await loadState();
  const recBtn = $<HTMLButtonElement>("rec-btn");
  const recLabel = $("rec-label");
  const statusText = $("status-text");

  if (state.kbId && hasMic && recBtn) {
    recBtn.disabled = false;
    recBtn.title = "";
  }
  if (state.capturing) {
    if (recBtn) {
      recBtn.classList.remove("rec-idle");
      recBtn.classList.add("rec-active");
    }
    if (recLabel) recLabel.textContent = "СТОП";
    if (statusText) statusText.textContent = "Слушаю...";
  }
}
```

Remove the old `initPermissionScreen()` call, `permScreen`/`tabNav`/`tabBriefing` variables, the `if (!hasMic)` block that hides UI, and the `chrome.storage.onChanged` listener at the bottom of `init()`.

**Step 4: Commit**

```bash
git add extension/src/popup/popup.html extension/src/popup/popup.css extension/src/popup/popup.ts
git commit -m "feat(ext): move mic permission to Settings tab, non-blocking UI (FEAT-004 Task 1)"
```

---

### Task 2: Multi-step upload stepper (replace progress bar)

**Goal:** Replace the single progress bar with a 3-step visual stepper: Upload - Processing - Briefing. Each step has an icon, label, and connecting line. Active step shows animated SVG spinner. Includes ARIA roles [Review Fix #9], `white-space: nowrap` [Review Fix #11], `AbortController` timeout [Review Fix #10], error timeout 5s [Review Fix #12].

**Files:**
- Modify: `extension/src/popup/popup.html:48-53` (replace `#upload-progress`)
- Modify: `extension/src/popup/popup.css:89-106` (replace progress styles with stepper styles)
- Modify: `extension/src/popup/popup.ts:128-133` (replace `setProgress` with `setStep`)

**Step 1: Replace progress HTML in popup.html**

Replace lines 48-53 (`#upload-progress` div) with stepper markup with ARIA [Review Fix #9]:

```html
<div id="upload-stepper" role="group" aria-label="Прогресс загрузки" hidden>
  <div class="stepper">
    <div class="step" id="step-upload" data-step="1" aria-label="Шаг 1: Загрузка">
      <div class="step-icon">
        <svg class="step-check" viewBox="0 0 16 16" width="14" height="14" hidden aria-hidden="true">
          <path d="M13.5 4.5l-7 7L3 8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <svg class="step-spinner" viewBox="0 0 16 16" width="14" height="14" hidden aria-hidden="true">
          <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="28 10" stroke-linecap="round">
            <animateTransform attributeName="transform" type="rotate" from="0 8 8" to="360 8 8" dur="0.8s" repeatCount="indefinite"/>
          </circle>
        </svg>
        <span class="step-number">1</span>
      </div>
      <span class="step-label">Загрузка</span>
    </div>
    <div class="step-line" id="line-1-2"></div>
    <div class="step" id="step-process" data-step="2" aria-label="Шаг 2: Обработка">
      <div class="step-icon">
        <svg class="step-check" viewBox="0 0 16 16" width="14" height="14" hidden aria-hidden="true">
          <path d="M13.5 4.5l-7 7L3 8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <svg class="step-spinner" viewBox="0 0 16 16" width="14" height="14" hidden aria-hidden="true">
          <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="28 10" stroke-linecap="round">
            <animateTransform attributeName="transform" type="rotate" from="0 8 8" to="360 8 8" dur="0.8s" repeatCount="indefinite"/>
          </circle>
        </svg>
        <span class="step-number">2</span>
      </div>
      <span class="step-label">Обработка</span>
    </div>
    <div class="step-line" id="line-2-3"></div>
    <div class="step" id="step-briefing" data-step="3" aria-label="Шаг 3: Брифинг">
      <div class="step-icon">
        <svg class="step-check" viewBox="0 0 16 16" width="14" height="14" hidden aria-hidden="true">
          <path d="M13.5 4.5l-7 7L3 8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <svg class="step-spinner" viewBox="0 0 16 16" width="14" height="14" hidden aria-hidden="true">
          <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="28 10" stroke-linecap="round">
            <animateTransform attributeName="transform" type="rotate" from="0 8 8" to="360 8 8" dur="0.8s" repeatCount="indefinite"/>
          </circle>
        </svg>
        <span class="step-number">3</span>
      </div>
      <span class="step-label">Брифинг</span>
    </div>
  </div>
  <span id="stepper-text" class="stepper-status-text" aria-live="polite">Загружаем файлы...</span>
</div>
```

**Step 2: Replace progress CSS with stepper CSS**

Remove old `#upload-progress`, `#progress-bar`, `#progress-fill`, `#progress-text` styles (lines 89-106). Add:

```css
/* Stepper */
#upload-stepper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stepper {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
}

.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  min-width: 60px;
}

.step-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid #d1d5db;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  color: #9ca3af;
  transition: all 0.3s;
}

.step-number {
  font-size: 10px;
  font-weight: 700;
}

.step-label {
  font-size: 10px;
  color: #9ca3af;
  font-weight: 500;
  white-space: nowrap; /* [Review Fix #11] */
  transition: color 0.3s;
}

.step-line {
  width: 32px;
  height: 2px;
  background: #d1d5db;
  margin-bottom: 16px;
  transition: background 0.3s;
}

/* Step states */
.step.active .step-icon {
  border-color: #2563eb;
  color: #2563eb;
  background: #eff6ff;
}

.step.active .step-number { display: none; }
.step.active .step-spinner { display: block !important; }

.step.active .step-label {
  color: #2563eb;
  font-weight: 600;
}

.step.done .step-icon {
  border-color: #16a34a;
  color: #16a34a;
  background: #f0fdf4;
}

.step.done .step-number { display: none; }
.step.done .step-check { display: block !important; }

.step.done .step-label {
  color: #16a34a;
}

.step-line.done {
  background: #16a34a;
}

.stepper-status-text {
  font-size: 11px;
  color: #6b7280;
  text-align: center;
}
```

**Step 3: Replace setProgress with setStep in popup.ts**

Remove `setProgress()` function (lines 128-133). Add `setStep()` with `aria-current` [Review Fix #9]:

```typescript
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

  // Reset all
  for (const s of steps) {
    s?.classList.remove("active", "done");
    s?.removeAttribute("aria-current");
  }
  for (const l of lines) {
    l?.classList.remove("done");
  }

  const phaseIndex = { upload: 0, process: 1, briefing: 2, done: 3, error: -1 }[phase];

  if (phase === "error") {
    if (stepperText) {
      stepperText.textContent = statusText ?? "Ошибка";
      stepperText.style.color = "#dc2626";
    }
    return;
  }

  // Mark completed steps
  for (let i = 0; i < phaseIndex && i < steps.length; i++) {
    steps[i]?.classList.add("done");
  }
  // Mark completed lines
  for (let i = 0; i < phaseIndex - 1 && i < lines.length; i++) {
    lines[i]?.classList.add("done");
  }
  // Mark active step
  if (phaseIndex < steps.length) {
    steps[phaseIndex]?.classList.add("active");
    steps[phaseIndex]?.setAttribute("aria-current", "step");
  }
  // All done
  if (phase === "done") {
    for (const s of steps) s?.classList.add("done");
    for (const l of lines) l?.classList.add("done");
  }

  if (stepperText) {
    stepperText.textContent = statusText ?? "";
    stepperText.style.color = "#6b7280";
  }
}
```

**Step 4: Update doUpload() with setStep, AbortController [Review Fix #10], error timeout 5s [Review Fix #12]**

Inside `initUpload()`, change `const uploadProgress = $("upload-progress");` to `const uploadStepper = $("upload-stepper");`

Replace the `doUpload` function body:

```typescript
async function doUpload(files: FileList): Promise<void> {
  const { valid, errors } = validateFiles(files);

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

  hide(uploadResult);
  show(uploadStepper);
  setStep("upload", "Загружаем файлы...");

  const sessionId = crypto.randomUUID();
  const formData = new FormData();
  formData.append("session_id", sessionId);
  for (const file of valid) {
    formData.append("files", file);
  }

  // [Review Fix #10] AbortController with 30s timeout
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
      });

      if (data.failed_files?.length && failedFiles) {
        for (const f of data.failed_files) {
          const li = document.createElement("li");
          li.textContent = `${f.name}: ${f.error}`;
          failedFiles.appendChild(li);
        }
        show(failedFiles);
      }

      // Use updateMicStatus to properly enable/disable REC with tooltip
      void updateMicStatus($("mic-settings"), $("mic-status-text"));

      if (data.scenario_generated !== false) {
        setStep("briefing", "Генерируем брифинг...");
        await fetchAndRenderBriefing();
      }

      setStep("done", `Загружено ${data.chunks_count} фрагментов`);

      if (resultText) {
        resultText.className = "success";
        resultText.textContent = `Загружено ${data.chunks_count} фрагментов`;
      }
      show(uploadResult);
      setTimeout(() => hide(uploadStepper), 2000);
    } else {
      throw new Error(`HTTP ${resp.status}`);
    }
  } catch (err) {
    clearTimeout(timeoutId);
    const msg = err instanceof DOMException && err.name === "AbortError"
      ? "Превышено время ожидания (30с)"
      : String(err);
    setStep("error", `Ошибка: ${msg}`);
    if (resultText) {
      resultText.className = "error";
      resultText.textContent = `Ошибка загрузки: ${msg}`;
    }
    show(uploadResult);
    setTimeout(() => hide(uploadStepper), 5000); // [Review Fix #12] 5s for errors
  }
}
```

**Step 5: Commit**

```bash
git add extension/src/popup/popup.html extension/src/popup/popup.css extension/src/popup/popup.ts
git commit -m "feat(ext): replace progress bar with 3-step upload stepper (FEAT-004 Task 2)"
```

---

### Task 3: Indeterminate animation for LLM generation phase

**Goal:** Enhance briefing loading text with an animated dots CSS effect. Fix error handling: `hide(loading)` only on success path [Review Fix #1].

**Files:**
- Modify: `extension/src/popup/popup.css` (add loading-dots animation)
- Modify: `extension/src/popup/popup.ts:418-455` (update `fetchAndRenderBriefing`)

**Step 1: Add animated dots CSS**

```css
/* Chrome-only: content is not officially animatable per CSS spec */
.loading-dots::after {
  content: '';
  animation: dots 1.5s steps(4, end) infinite;
}

@keyframes dots {
  0%   { content: ''; }
  25%  { content: '.'; }
  50%  { content: '..'; }
  75%  { content: '...'; }
  100% { content: ''; }
}
```

**Step 2: Update fetchAndRenderBriefing — fixed error handling [Review Fix #1]**

```typescript
async function fetchAndRenderBriefing(): Promise<void> {
  const loading = $("briefing-loading");
  const content = $("briefing-content");
  const portraitEl = $("portrait-text");
  const strategyEl = $("strategy-text");
  const objList = $("objections-list");
  const refreshBtn = $("refresh-briefing-btn");

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
      body: JSON.stringify({ session_id: state.sessionId, kb_id: state.kbId }),
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const data = (await resp.json()) as BriefingData;

    if (portraitEl) renderPortrait(data.portrait, portraitEl);
    if (strategyEl) renderStrategy(data.strategy, strategyEl);
    if (objList) renderObjections(data.objections, objList);

    // [Review Fix #1] hide loading only on success
    if (loading) loading.classList.remove("loading-dots");
    hide(loading);
    show(content);
    show(refreshBtn);
  } catch (err) {
    // [Review Fix #1] clean up animation, rethrow — doUpload handles error display
    if (loading) loading.classList.remove("loading-dots");
    throw err;
  }
}
```

Also update `initBriefing()` to handle the new rethrow when called from refresh button:

```typescript
function initBriefing(): void {
  const refreshBtn = $<HTMLAnchorElement>("refresh-briefing-btn");

  refreshBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    // Wrap in catch since fetchAndRenderBriefing now rethrows on error
    void fetchAndRenderBriefing().catch((err) => {
      const loading = $("briefing-loading");
      if (loading) {
        loading.textContent = `Ошибка: ${String(err)}`;
        show(loading);
      }
    });
  });
}
```

**Step 3: Commit**

```bash
git add extension/src/popup/popup.css extension/src/popup/popup.ts
git commit -m "feat(ext): add animated dots during briefing LLM generation (FEAT-004 Task 3)"
```

---

### Task 4: AudioWorklet RMS computation

**Goal:** Compute RMS audio level per channel inside the AudioWorklet. Throttled to ~10 fps.

**Files:**
- Modify: `extension/src/audio-worklet.ts`

**Step 1: Replace entire audio-worklet.ts**

```typescript
// AudioWorklet Processor — compiled as IIFE (see vite.worklet.config.ts).
// AudioWorklet scope does NOT support ES module `import` statements.
// This file runs inside AudioWorkletGlobalScope, not the browser window.

class PCMProcessor extends AudioWorkletProcessor {
  // Throttle level messages: send every ~12 blocks (~96ms at 16kHz, 128 samples/block)
  private frameCounter = 0;
  private static readonly LEVEL_INTERVAL = 12;

  process(
    inputs: Float32Array[][],
    _outputs: Float32Array[][],
    _params: Record<string, Float32Array>
  ): boolean {
    const ch0 = inputs[0]?.[0]; // mic (L)
    const ch1 = inputs[0]?.[1]; // tab (R)
    if (!ch0 || ch0.length === 0) return true;

    // If only one channel available, duplicate it
    const right = ch1 && ch1.length > 0 ? ch1 : ch0;

    // Interleave L,R,L,R,... as Int16 — matches backend deinterleave_stereo()
    const interleaved = new Int16Array(ch0.length * 2);
    for (let i = 0; i < ch0.length; i++) {
      interleaved[i * 2] = Math.max(-32768, Math.min(32767, (ch0[i] ?? 0) * 32768));
      interleaved[i * 2 + 1] = Math.max(-32768, Math.min(32767, (right[i] ?? 0) * 32768));
    }

    // Transfer PCM buffer to main thread (zero-copy)
    this.port.postMessage(
      { type: "pcm", buffer: interleaved.buffer },
      [interleaved.buffer]
    );

    // Compute and send audio levels at throttled rate
    this.frameCounter++;
    if (this.frameCounter >= PCMProcessor.LEVEL_INTERVAL) {
      this.frameCounter = 0;
      const micRms = rms(ch0);
      const tabRms = rms(right);
      this.port.postMessage({ type: "level", mic: micRms, tab: tabRms });
    }

    return true;
  }
}

/** Compute RMS of a Float32 buffer, returns 0..1 range. */
function rms(buf: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) {
    const s = buf[i] ?? 0;
    sum += s * s;
  }
  return Math.sqrt(sum / buf.length);
}

registerProcessor("pcm-processor", PCMProcessor);
```

**Step 2: Commit**

```bash
git add extension/src/audio-worklet.ts
git commit -m "feat(ext): compute per-channel RMS in AudioWorklet (FEAT-004 Task 4)"
```

---

### Task 5: Offscreen to Service Worker audio level relay

**Goal:** Handle new worklet message format. Add `swPort` disconnect guard [Review Fix #3]. Validate `data.buffer` [Review Fix #4]. Handle `AUDIO_LEVEL` in offscreen message listener to avoid "Unknown message type" [Review Fix #13].

**Files:**
- Modify: `extension/src/offscreen/offscreen.ts:89-92` (worklet message handler)
- Modify: `extension/src/offscreen/offscreen.ts:132-158` (message listener — add AUDIO_LEVEL case)
- Modify: `extension/src/shared/messages.ts` (add AUDIO_LEVEL to ExtMessage)

**Step 1: Add AUDIO_LEVEL to ExtMessage in messages.ts**

Replace the `ExtMessage` type (lines 42-47):

```typescript
export type ExtMessage =
  | { type: "START_SESSION"; sessionId: string; kbId: string; tabId: number }
  | { type: "STOP_SESSION"; sessionId: string }
  | { type: "WIDGET_STATE"; state: WidgetState }
  | { type: "HINT"; hint: WsHintEnd }
  | { type: "TRANSCRIPT"; transcript: WsTranscript }
  | { type: "AUDIO_LEVEL"; mic: number; tab: number };
```

**Step 2: Add swPort disconnect guard [Review Fix #3] and update worklet handler [Review Fix #4]**

At the top of offscreen.ts, after `const swPort = chrome.runtime.connect(...)` (line 29), add:

```typescript
let swPortAlive = true;
swPort.onDisconnect.addListener(() => { swPortAlive = false; });
```

Replace lines 89-92 (the `workletNode.port.onmessage` handler):

```typescript
workletNode.port.onmessage = (
  event: MessageEvent<{ type: string; buffer?: ArrayBuffer; mic?: number; tab?: number }>
) => {
  const data = event.data;
  if (data.type === "pcm" && data.buffer instanceof ArrayBuffer) { // [Review Fix #4]
    wsClient?.sendAudio(data.buffer);
  } else if (data.type === "level" && swPortAlive) { // [Review Fix #3]
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
```

**Step 3: Handle AUDIO_LEVEL in offscreen message listener [Review Fix #13]**

In the `chrome.runtime.onMessage.addListener` at the bottom of offscreen.ts (line 132), add a case before the final `sendResponse`:

```typescript
// [Review Fix #13] Ignore AUDIO_LEVEL broadcast from SW — prevent "Unknown message type" response
if (message.type === "AUDIO_LEVEL") {
  return false; // not handled here, no response needed
}
```

**Step 4: Commit**

```bash
git add extension/src/offscreen/offscreen.ts extension/src/shared/messages.ts
git commit -m "feat(ext): relay audio levels from offscreen to SW with guards (FEAT-004 Task 5)"
```

---

### Task 6: Service Worker to Content Script + Popup audio level relay

**Goal:** Forward AUDIO_LEVEL to session tab and popup. Use consistent `AUDIO_LEVEL` type everywhere [Review Fix #2].

**Files:**
- Modify: `extension/src/background/service-worker.ts:71-77` (port message listener)

**Step 1: Update port listener to forward AUDIO_LEVEL**

Replace the `port.onMessage.addListener` callback (lines 71-77):

```typescript
port.onMessage.addListener((message) => {
  if (message.type === "WS_MESSAGE" && message.payload) {
    if (sessionTabId != null) {
      chrome.tabs.sendMessage(sessionTabId, message.payload).catch(() => {});
    }
  } else if (message.type === "AUDIO_LEVEL") {
    // [Review Fix #2] Use AUDIO_LEVEL consistently everywhere
    const levelMsg = {
      type: "AUDIO_LEVEL" as const,
      mic: message.mic as number,
      tab: message.tab as number,
    };
    // Forward to session tab (for widget VU meters)
    if (sessionTabId != null) {
      chrome.tabs.sendMessage(sessionTabId, levelMsg).catch(() => {});
    }
    // Broadcast for popup (if open)
    chrome.runtime.sendMessage(levelMsg).catch(() => {
      // popup may not be open — ignore
    });
  }
});
```

**Step 2: Commit**

```bash
git add extension/src/background/service-worker.ts
git commit -m "feat(ext): service worker relays audio levels to widget and popup (FEAT-004 Task 6)"
```

---

### Task 7: Widget VU-meter bars (real audio data)

**Goal:** Replace CSS-only `eq-bounce` animation with JS-driven bars. Use `AUDIO_LEVEL` type [Review Fix #2].

**Files:**
- Modify: `extension/src/content/widget.ts` (CSS string + CopilotWidget class + boot listener)

**Step 1: Update WIDGET_CSS — remove CSS animation, add transition**

In the `WIDGET_CSS` template string, find the equalizer bar rules. Remove:
```css
.eq-bar {
  width: 3px;
  background: #2E75B6;
  border-radius: 1px;
  transform-origin: bottom;
  animation: eq-bounce 0.8s ease-in-out infinite;
}

.eq-bar:nth-child(1) { animation-delay: 0s; }
.eq-bar:nth-child(2) { animation-delay: 0.15s; }
.eq-bar:nth-child(3) { animation-delay: 0.3s; }
.eq-bar:nth-child(4) { animation-delay: 0.45s; }

@keyframes eq-bounce {
  0%, 100% { transform: scaleY(0.3); }
  50%      { transform: scaleY(1); }
}
```

Replace with:
```css
.eq-bar {
  width: 3px;
  background: #2E75B6;
  border-radius: 1px;
  transform-origin: bottom;
  transition: transform 0.08s ease-out;
  transform: scaleY(0.15);
}
```

Update `prefers-reduced-motion`:
```css
@media (prefers-reduced-motion: reduce) {
  .state-LISTENING #panel { animation: none; }
  .state-WARNING #panel  { animation: none; }
  .eq-bar { transition: none; }
}
```

**Step 2: Add eqBars property and handleAudioLevel method**

Add property: `private eqBars: HTMLElement[] = [];`

In constructor, after `this.sm.onStateChange(...)`:
```typescript
this.eqBars = Array.from(
  this.shadow.querySelectorAll<HTMLElement>(".eq-bar")
);
```

Add method:
```typescript
handleAudioLevel(mic: number, _tab: number): void {
  const state = this.sm.current();
  if (state !== "LISTENING" && state !== "HINT_ACTIVE") return;

  const level = Math.min(mic * 4, 1);

  for (let i = 0; i < this.eqBars.length; i++) {
    const bar = this.eqBars[i];
    if (!bar) continue;
    const variation = 0.7 + Math.random() * 0.6;
    const barLevel = Math.max(0.15, Math.min(1, level * variation));
    bar.style.transform = `scaleY(${barLevel})`;
  }
}
```

**Step 3: Handle AUDIO_LEVEL in message listener [Review Fix #2]**

In the switch in `boot()`:
```typescript
case "AUDIO_LEVEL": {
  const a = msg as unknown as { mic: number; tab: number };
  widget.handleAudioLevel(a.mic ?? 0, a.tab ?? 0);
  break;
}
```

**Step 4: Commit**

```bash
git add extension/src/content/widget.ts
git commit -m "feat(ext): widget equalizer driven by real audio RMS levels (FEAT-004 Task 7)"
```

---

### Task 8: Popup VU-meter bars next to REC button

**Goal:** Add VU-meter bars with Russian labels [Review Fix #6], cached DOM refs [Review Fix #5].

**Files:**
- Modify: `extension/src/popup/popup.html:61-67` (add VU meter markup)
- Modify: `extension/src/popup/popup.css` (add VU meter styles)
- Modify: `extension/src/popup/popup.ts` (listen for AUDIO_LEVEL, show/hide VU, animate bars)

**Step 1: Add VU meter HTML with Russian labels [Review Fix #6]**

Replace `#session-section` (lines 61-67):

```html
<div id="session-section">
  <button id="rec-btn" class="rec-btn rec-idle" type="button" disabled>
    <span class="rec-dot"></span>
    <span id="rec-label">REC</span>
  </button>
  <div id="vu-meters" hidden aria-hidden="true">
    <div class="vu-row">
      <span class="vu-label">МИК</span>
      <div class="vu-track"><div class="vu-fill" id="vu-mic"></div></div>
    </div>
    <div class="vu-row">
      <span class="vu-label">ЗВУК</span>
      <div class="vu-track"><div class="vu-fill" id="vu-tab"></div></div>
    </div>
  </div>
  <span id="status-text" class="status-text">Готов</span>
</div>
```

**Step 2: Add VU meter CSS**

```css
/* VU meters */
#vu-meters {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  max-width: 100px;
}

.vu-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.vu-label {
  font-size: 8px;
  font-weight: 700;
  color: #9ca3af;
  width: 24px;
  text-align: right;
  letter-spacing: 0.5px;
}

.vu-track {
  flex: 1;
  height: 4px;
  background: #e5e7eb;
  border-radius: 2px;
  overflow: hidden;
}

.vu-fill {
  height: 100%;
  width: 0%;
  border-radius: 2px;
  background: linear-gradient(90deg, #22c55e 0%, #22c55e 60%, #eab308 75%, #dc2626 100%);
  transition: width 0.08s ease-out;
}
```

**Step 3: Add cached audio level listener in popup.ts [Review Fix #5]**

At the end of `initRecButton()`, capture refs once and add listener:

```typescript
// [Review Fix #5] Cache VU DOM refs at setup time
const vuMeters = $("vu-meters");
const vuMic = $<HTMLDivElement>("vu-mic");
const vuTab = $<HTMLDivElement>("vu-tab");

chrome.runtime.onMessage.addListener((message: { type: string; mic?: number; tab?: number }) => {
  if (message.type === "AUDIO_LEVEL") {
    if (!vuMeters || vuMeters.hidden) return;

    const micPct = Math.min(100, (message.mic ?? 0) * 400);
    const tabPct = Math.min(100, (message.tab ?? 0) * 400);

    if (vuMic) vuMic.style.width = `${micPct}%`;
    if (vuTab) vuTab.style.width = `${tabPct}%`;
  }
});
```

**Step 4: Show/hide VU meters on REC toggle**

When starting session (after `statusText.textContent = "Слушаю..."`):
```typescript
show(vuMeters);
```

When stopping session (after `statusText.textContent = "Готов"`):
```typescript
hide(vuMeters);
if (vuMic) vuMic.style.width = "0%";
if (vuTab) vuTab.style.width = "0%";
```

In `init()`, when restoring capture state:
```typescript
if (state.capturing) {
  // ... existing button state restore ...
  show($("vu-meters"));
}
```

**Step 5: Commit**

```bash
git add extension/src/popup/popup.html extension/src/popup/popup.css extension/src/popup/popup.ts
git commit -m "feat(ext): add VU meter bars in popup for mic/tab audio levels (FEAT-004 Task 8)"
```

---

## Dependency Graph

```
Task 1 (Settings restructure) ── independent
Task 2 (Stepper HTML+CSS) ─┐
Task 3 (Animated dots)  ────┘ sequential (3 depends on 2)
Task 4 (Worklet RMS) ─────────┐
Task 5 (Offscreen relay) ─────┤ sequential chain (4 -> 5 -> 6 -> 7, 8)
Task 6 (SW relay) ────────────┤
Task 7 (Widget VU) ───────────┤
Task 8 (Popup VU) ────────────┘
```

Tasks 1, 2-3, and 4-8 can be done in **3 parallel streams**.

## Final Verification

After all tasks, run:

```bash
cd extension && npm run build
```

Then load unpacked extension in Chrome and verify:
1. Settings tab shows mic status + connection fields grouped; red dot badge if mic not configured
2. Briefing tab visible even without mic; REC disabled with tooltip explaining why
3. File upload shows 3-step stepper with ARIA roles and animated spinner per phase
4. Upload timeout at 30s; error stepper stays visible 5s
5. Briefing generation phase shows spinning + animated dots; error visible if LLM fails
6. During recording, popup shows МИК/ЗВУК VU meters responding to real audio
7. Widget equalizer bars respond to actual audio signal (not CSS-only animation)
8. AUDIO_LEVEL message type consistent everywhere (no lowercase variant)
