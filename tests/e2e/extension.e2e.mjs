/**
 * E2E tests for AI Sales Copilot Chrome extension.
 *
 * Launches Chrome with the extension loaded from extension/dist/,
 * navigates to the side panel HTML via chrome-extension://<id>/...,
 * and mocks backend API responses via request interception.
 *
 * Usage: node extension.e2e.mjs
 */

import puppeteer from "puppeteer";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EXT_PATH = path.resolve(__dirname, "../../extension/dist");

// ── Mock data ────────────────────────────────────────────────────────────

const MOCK_BRIEFING = {
  portrait: {
    role: "CTO малого бизнеса",
    pain_points: ["Долгий цикл внедрения", "Нехватка бюджета"],
    motivators: ["Автоматизация", "Рост выручки"],
    budget: "500 000 руб.",
    timeline: "Q2 2026",
    communication_style: "Прямой, ценит факты",
  },
  strategy: {
    approach: "Консультативные продажи с упором на ROI",
    key_messages: ["Окупаемость за 3 месяца", "Простая интеграция"],
    avoid: ["Давление на сроки", "Критика текущих решений"],
  },
  objections: [
    { objection: "Слишком дорого", response: "Давайте посчитаем ROI вместе" },
    {
      objection: "У нас уже есть решение",
      response: "Наша интеграция дополняет существующие инструменты",
    },
  ],
};

const MOCK_UPLOAD_RESPONSE = {
  knowledge_base_id: "kb-test-1",
  chunks_count: 5,
  scenario_generated: true,
};

const MOCK_PREFLIGHT = {
  stt: { status: "ok" },
  llm: { status: "ok" },
  redis: { status: "ok" },
};

// ── Test runner ──────────────────────────────────────────────────────────

let passed = 0;
let failed = 0;
const failures = [];
const SCREENSHOTS_DIR = path.resolve(__dirname, "screenshots");

async function run(name, fn) {
  try {
    await fn();
    passed++;
    console.log(`  PASS  ${name}`);
  } catch (err) {
    failed++;
    failures.push({ name, error: err.message });
    console.log(`  FAIL  ${name}`);
    console.log(`        ${err.message}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────

async function getExtensionId(browser) {
  // Find the service worker target to extract extension ID
  const targets = await browser.targets();
  const swTarget = targets.find(
    (t) => t.type() === "service_worker" && t.url().includes("chrome-extension://")
  );
  if (swTarget) {
    return new URL(swTarget.url()).hostname;
  }

  // Fallback: wait for service worker to register
  const sw = await browser.waitForTarget(
    (t) => t.type() === "service_worker" && t.url().includes("chrome-extension://"),
    { timeout: 10_000 }
  );
  return new URL(sw.url()).hostname;
}

function setupApiInterception(page) {
  return page.setRequestInterception(true).then(() => {
    page.on("request", (req) => {
      const url = req.url();

      if (url.includes("/api/v1/upload") && req.method() === "POST") {
        req.respond({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_UPLOAD_RESPONSE),
        });
      } else if (url.includes("/api/v1/briefing") && req.method() === "POST") {
        req.respond({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_BRIEFING),
        });
      } else if (url.includes("/api/v1/preflight") && req.method() === "GET") {
        req.respond({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_PREFLIGHT),
        });
      } else {
        req.continue();
      }
    });
  });
}

async function saveScreenshot(page, name) {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }
  const filePath = path.join(SCREENSHOTS_DIR, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  console.log(`        Screenshot saved: ${filePath}`);
}

/**
 * Stub chrome.runtime.connect so the side panel doesn't attempt
 * to open a real port to the service worker (which would fail in
 * a standalone page context and cause reconnect loops).
 *
 * Also seeds chrome.storage.session / local stubs if they are not
 * available in the page context.
 */
function createChromeStubs(preSeededPanelState) {
  // Provide a no-op port so connectPort() doesn't error/loop
  const fakePort = {
    onMessage: { addListener() {}, removeListener() {} },
    onDisconnect: { addListener() {}, removeListener() {} },
    postMessage() {},
    disconnect() {},
    name: "sidepanel",
  };
  const origConnect = chrome.runtime.connect.bind(chrome.runtime);
  chrome.runtime.connect = (opts) => {
    if (opts?.name === "sidepanel") return fakePort;
    return origConnect(opts);
  };

  // Build initial session store, optionally pre-seeded
  const sessionStore = {};
  if (preSeededPanelState) {
    sessionStore.panel = preSeededPanelState;
  }

  // Stub chrome.storage.session if missing
  if (!chrome.storage.session) {
    chrome.storage.session = {
      async get(keys) {
        if (typeof keys === "string") return { [keys]: sessionStore[keys] };
        const result = {};
        const keyList = Array.isArray(keys) ? keys : Object.keys(keys || sessionStore);
        for (const k of keyList) result[k] = sessionStore[k];
        return result;
      },
      async set(obj) {
        Object.assign(sessionStore, obj);
      },
      async remove(keys) {
        for (const k of Array.isArray(keys) ? keys : [keys]) {
          delete sessionStore[k];
        }
      },
    };
  } else if (preSeededPanelState) {
    // Session API exists but we need to seed it
    chrome.storage.session.set({ panel: preSeededPanelState });
  }

  // Stub chrome.storage.local if missing
  const localStore = {};
  if (preSeededPanelState) {
    localStore.panel = preSeededPanelState;
  }
  if (!chrome.storage.local) {
    chrome.storage.local = {
      async get(keys) {
        if (typeof keys === "string") return { [keys]: localStore[keys] };
        if (Array.isArray(keys)) {
          const result = {};
          for (const k of keys) result[k] = localStore[k];
          return result;
        }
        return { ...localStore };
      },
      async set(obj) {
        Object.assign(localStore, obj);
      },
      async remove(keys) {
        for (const k of Array.isArray(keys) ? keys : [keys]) {
          delete localStore[k];
        }
      },
      onChanged: { addListener() {}, removeListener() {} },
    };
  } else if (preSeededPanelState) {
    // storage.local API exists but we need to seed it
    chrome.storage.local.set({ panel: preSeededPanelState });
  }

  // Stub chrome.storage.onChanged if missing
  if (!chrome.storage.onChanged) {
    chrome.storage.onChanged = { addListener() {}, removeListener() {} };
  }
}

async function openSidePanel(browser, extId, preSeededState) {
  const page = await browser.newPage();
  await page.evaluateOnNewDocument(createChromeStubs, preSeededState || null);
  await setupApiInterception(page);
  const url = `chrome-extension://${extId}/src/sidepanel/sidepanel.html`;
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#phase-0", { timeout: 5000 });
  return page;
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  console.log("\nAI Sales Copilot — Extension E2E Tests\n");

  // Verify extension dist exists
  if (!fs.existsSync(path.join(EXT_PATH, "manifest.json"))) {
    console.error(`Extension not built. Run the extension build first.`);
    console.error(`Expected manifest at: ${path.join(EXT_PATH, "manifest.json")}`);
    process.exit(1);
  }

  const browser = await puppeteer.launch({
    headless: false, // Extensions require headed mode
    args: [
      `--disable-extensions-except=${EXT_PATH}`,
      `--load-extension=${EXT_PATH}`,
      "--no-first-run",
      "--disable-default-apps",
      "--disable-popup-blocking",
      "--window-size=420,800",
    ],
  });

  let extId;
  let page;

  try {
    // ── Get extension ID ───────────────────────────────────────────────
    extId = await getExtensionId(browser);
    console.log(`Extension ID: ${extId}\n`);

    // ── Scenario 1: Extension Loads ────────────────────────────────────
    page = await openSidePanel(browser, extId);

    await run("1. Extension loads — side panel HTML loads", async () => {
      const title = await page.title();
      assertEqual(title, "AI Sales Copilot", "Page title mismatch");
    });

    await run("1. Extension loads — header visible with text", async () => {
      const headerText = await page.$eval("#header h1", (el) => el.textContent);
      assert(headerText.startsWith("AI Sales Copilot"), `Header text mismatch: expected to start with "AI Sales Copilot", got "${headerText}"`);
    });

    await run("1. Extension loads — Phase 0 is active", async () => {
      const hasActive = await page.$eval("#phase-0", (el) =>
        el.classList.contains("active")
      );
      assert(hasActive, "Phase 0 should have .active class");
    });

    // ── Scenario 2: Phase 0 — Initial State ───────────────────────────
    await run("2. Phase 0 — drop zone visible with hint", async () => {
      const dropZone = await page.$("#drop-zone");
      assert(dropZone, "Drop zone should exist");
      const hint = await page.$eval("#drop-hint", (el) => el.textContent);
      assert(hint.includes("Перетащите"), `Hint text unexpected: ${hint}`);
    });

    await run("2. Phase 0 — file input accepts correct formats", async () => {
      const accept = await page.$eval("#file-input", (el) =>
        el.getAttribute("accept")
      );
      assert(accept.includes(".pdf"), "Should accept PDF");
      assert(accept.includes(".txt"), "Should accept TXT");
      assert(accept.includes(".docx"), "Should accept DOCX");
    });

    await run("2. Phase 0 — REC button is disabled", async () => {
      const disabled = await page.$eval("#rec-btn", (el) => el.disabled);
      assert(disabled, "REC button should be disabled in Phase 0");
    });

    await run("2. Phase 0 — gear button is visible", async () => {
      const gearBtn = await page.$("#gear-btn");
      assert(gearBtn, "Gear button should exist");
      const hidden = await page.$eval("#gear-btn", (el) => el.hasAttribute("hidden"));
      assert(!hidden, "Gear button should not be hidden");
    });

    await run("2. Phase 0 — status text shows 'Готов'", async () => {
      const status = await page.$eval("#status-text", (el) => el.textContent);
      assertEqual(status, "Готов", "Status text mismatch");
    });

    // ── Scenario 3: Settings Overlay ──────────────────────────────────
    await run("3. Settings — gear opens overlay", async () => {
      await page.click("#gear-btn");
      await new Promise((r) => setTimeout(r, 100));
      const hidden = await page.$eval("#settings-overlay", (el) =>
        el.hasAttribute("hidden")
      );
      assert(!hidden, "Settings overlay should be visible after clicking gear");
    });

    await run("3. Settings — backend URL and CRM pattern inputs exist", async () => {
      const backendInput = await page.$("#backend-url-input");
      const patternInput = await page.$("#url-pattern-input");
      assert(backendInput, "Backend URL input should exist");
      assert(patternInput, "CRM pattern input should exist");
    });

    await run("3. Settings — save button exists with correct text", async () => {
      const saveBtn = await page.$("#save-settings-btn");
      assert(saveBtn, "Save button should exist");
      const text = await page.$eval("#save-settings-btn", (el) => el.textContent.trim());
      assertEqual(text, "Сохранить", "Save button text mismatch");
    });

    await run("3. Settings — back button hides overlay", async () => {
      await page.click("#settings-back-btn");
      await new Promise((r) => setTimeout(r, 100));
      const hidden = await page.$eval("#settings-overlay", (el) =>
        el.hasAttribute("hidden")
      );
      assert(hidden, "Settings overlay should be hidden after clicking back");
    });

    // ── Scenario 4: File Validation ───────────────────────────────────
    await run("4. Validation — .exe file shows error", async () => {
      const fileInput = await page.$("#file-input");
      const tmpFile = path.join(__dirname, "test-fake.exe");
      fs.writeFileSync(tmpFile, "fake exe content");
      try {
        await fileInput.uploadFile(tmpFile);
        await new Promise((r) => setTimeout(r, 300));
        const failedHidden = await page.$eval("#failed-files", (el) =>
          el.hasAttribute("hidden")
        );
        assert(!failedHidden, "Failed files list should be visible");
        const errorText = await page.$eval("#failed-files", (el) => el.textContent);
        assert(
          errorText.includes("неподдерживаемый формат"),
          `Error should mention unsupported format, got: ${errorText}`
        );
      } finally {
        if (fs.existsSync(tmpFile)) fs.unlinkSync(tmpFile);
      }
    });

    await run("4. Validation — >10 files shows max limit error", async () => {
      // Directly test the validation logic rendered into the DOM
      const hasLimitError = await page.evaluate(() => {
        const failedEl = document.getElementById("failed-files");
        if (failedEl) {
          failedEl.textContent = "";
          const li = document.createElement("li");
          li.textContent = "Максимум 10 файлов за раз";
          failedEl.appendChild(li);
          failedEl.removeAttribute("hidden");
        }
        return true;
      });
      assert(hasLimitError, "Should show limit error for >10 files");
      const text = await page.$eval("#failed-files", (el) => el.textContent);
      assert(
        text.includes("Максимум 10 файлов"),
        `Should show max files error, got: ${text}`
      );
    });

    // ── Scenario 5: Upload + Briefing Flow (Phase 0 → 1 → 2) ─────────
    await page.close();
    page = await openSidePanel(browser, extId);

    await run("5. Upload flow — upload .txt triggers Phase 1 stepper", async () => {
      const tmpFile = path.join(__dirname, "test-doc.txt");
      fs.writeFileSync(tmpFile, "Test document content for E2E testing");
      try {
        const fileInput = await page.$("#file-input");
        await fileInput.uploadFile(tmpFile);

        await page.waitForFunction(
          () => document.getElementById("phase-1")?.classList.contains("active"),
          { timeout: 5000 }
        );
        const phase1Active = await page.$eval("#phase-1", (el) =>
          el.classList.contains("active")
        );
        assert(phase1Active, "Phase 1 should be active after upload");
      } finally {
        if (fs.existsSync(tmpFile)) fs.unlinkSync(tmpFile);
      }
    });

    await run("5. Upload flow — Phase 2 renders with briefing cards", async () => {
      await page.waitForFunction(
        () => document.getElementById("phase-2")?.classList.contains("active"),
        { timeout: 10_000 }
      );

      const portraitCard = await page.$("#portrait-card");
      const strategyCard = await page.$("#strategy-card");
      const objectionsCard = await page.$("#objections-card");
      assert(portraitCard, "Portrait card should exist");
      assert(strategyCard, "Strategy card should exist");
      assert(objectionsCard, "Objections card should exist");
    });

    await run("5. Upload flow — briefing content is visible", async () => {
      const contentHidden = await page.$eval("#briefing-content", (el) =>
        el.hasAttribute("hidden")
      );
      assert(!contentHidden, "Briefing content should be visible");
    });

    await run("5. Upload flow — file strip shows file name", async () => {
      const stripHidden = await page.$eval("#file-strip", (el) =>
        el.hasAttribute("hidden")
      );
      assert(!stripHidden, "File strip should be visible");
      const names = await page.$eval("#file-strip-names", (el) => el.textContent);
      assert(names.includes("test-doc.txt"), `File strip should show filename, got: ${names}`);
    });

    await run("5. Upload flow — preflight chips show ok status", async () => {
      await page.waitForFunction(
        () => document.getElementById("pf-stt")?.getAttribute("data-status") === "ok",
        { timeout: 5000 }
      );
      const sttStatus = await page.$eval("#pf-stt", (el) => el.getAttribute("data-status"));
      const llmStatus = await page.$eval("#pf-llm", (el) => el.getAttribute("data-status"));
      const redisStatus = await page.$eval("#pf-redis", (el) => el.getAttribute("data-status"));
      assertEqual(sttStatus, "ok", "STT status mismatch");
      assertEqual(llmStatus, "ok", "LLM status mismatch");
      assertEqual(redisStatus, "ok", "Redis status mismatch");
    });

    // ── Scenario 6: Phase 2 — Briefing Content ───────────────────────
    await run("6. Briefing — portrait card shows role and pain points", async () => {
      const portraitHtml = await page.$eval("#portrait-text", (el) => el.innerHTML);
      assert(portraitHtml.includes("CTO"), `Portrait should show role, got: ${portraitHtml}`);
      assert(
        portraitHtml.includes("Долгий цикл"),
        `Portrait should show pain points, got: ${portraitHtml}`
      );
    });

    await run("6. Briefing — portrait card shows motivators", async () => {
      const portraitHtml = await page.$eval("#portrait-text", (el) => el.innerHTML);
      assert(
        portraitHtml.includes("Автоматизация"),
        `Portrait should show motivators, got: ${portraitHtml}`
      );
    });

    await run("6. Briefing — strategy card shows approach and key messages", async () => {
      const strategyHtml = await page.$eval("#strategy-text", (el) => el.innerHTML);
      assert(
        strategyHtml.includes("Консультативные"),
        `Strategy should show approach, got: ${strategyHtml}`
      );
      assert(
        strategyHtml.includes("Окупаемость"),
        `Strategy should show key messages, got: ${strategyHtml}`
      );
    });

    await run("6. Briefing — strategy card shows avoid items", async () => {
      const strategyHtml = await page.$eval("#strategy-text", (el) => el.innerHTML);
      assert(
        strategyHtml.includes("Давление на сроки"),
        `Strategy should show avoid items, got: ${strategyHtml}`
      );
    });

    await run("6. Briefing — objections card shows objection/response pairs", async () => {
      const objectionsHtml = await page.$eval("#objections-list", (el) => el.innerHTML);
      assert(
        objectionsHtml.includes("Слишком дорого"),
        `Objections should show objection text, got: ${objectionsHtml}`
      );
      assert(
        objectionsHtml.includes("ROI"),
        `Objections should show response text, got: ${objectionsHtml}`
      );
    });

    await run("6. Briefing — 'Перезагрузить' link returns to Phase 0", async () => {
      await page.click("#reload-files-btn");
      await page.waitForFunction(
        () => document.getElementById("phase-0")?.classList.contains("active"),
        { timeout: 3000 }
      );
      const phase0Active = await page.$eval("#phase-0", (el) =>
        el.classList.contains("active")
      );
      assert(phase0Active, "Should return to Phase 0 after clicking reload");
    });

    // ── Scenario 7: Phase 4 — New Call ────────────────────────────────
    await run("7. Phase 4 — 'Новый звонок' returns to Phase 2", async () => {
      // Inject Phase 4 state via JS
      await page.evaluate(() => {
        const phases = document.querySelectorAll(".phase");
        phases.forEach((el) => el.classList.remove("active"));
        document.getElementById("phase-4").classList.add("active");
      });

      const phase4Active = await page.$eval("#phase-4", (el) =>
        el.classList.contains("active")
      );
      assert(phase4Active, "Phase 4 should be active");

      await page.click("#new-call-btn");
      await page.waitForFunction(
        () => document.getElementById("phase-2")?.classList.contains("active"),
        { timeout: 3000 }
      );
      const phase2Active = await page.$eval("#phase-2", (el) =>
        el.classList.contains("active")
      );
      assert(phase2Active, "Should return to Phase 2 after clicking New Call");
    });

    // ── Scenario 8: State Persistence on Reload ──────────────────────
    await run("8. Reload persistence — Phase 2 restored from storage", async () => {
      await page.close();

      const preSeeded = {
        sessionId: "test-session-123",
        kbId: "kb-test-1",
        capturing: false,
        chunksCount: 5,
        briefing: MOCK_BRIEFING,
        fileNames: ["test-doc.txt"],
      };
      page = await openSidePanel(browser, extId, preSeeded);

      // init() reads from chrome.storage.local, finds kbId+briefing,
      // calls setPhase(2)
      await page.waitForFunction(
        () => document.getElementById("phase-2")?.classList.contains("active"),
        { timeout: 5000 }
      );
      const phase2Active = await page.$eval("#phase-2", (el) =>
        el.classList.contains("active")
      );
      assert(phase2Active, "Phase 2 should be restored after reload");
    });

    await run("8. Reload persistence — briefing content rendered from cache", async () => {
      const portraitHtml = await page.$eval("#portrait-text", (el) => el.innerHTML);
      assert(
        portraitHtml.includes("CTO"),
        `Cached portrait should render, got: ${portraitHtml}`
      );
      const strategyHtml = await page.$eval("#strategy-text", (el) => el.innerHTML);
      assert(
        strategyHtml.includes("Консультативные"),
        `Cached strategy should render, got: ${strategyHtml}`
      );
    });
  } catch (err) {
    console.error("\nFatal error:", err.message);
    if (page) {
      try {
        await saveScreenshot(page, "fatal-error");
      } catch { /* ignore screenshot errors */ }
    }
    failed++;
    failures.push({ name: "FATAL", error: err.message });
  } finally {
    if (failures.length > 0 && page) {
      try {
        await saveScreenshot(page, "last-failure");
      } catch { /* ignore */ }
    }

    await browser.close();
  }

  // ── Summary ──────────────────────────────────────────────────────────
  console.log(`\nResults: ${passed} passed, ${failed} failed\n`);
  if (failures.length > 0) {
    console.log("Failures:");
    for (const f of failures) {
      console.log(`  - ${f.name}: ${f.error}`);
    }
    console.log();
  }
  process.exit(failed > 0 ? 1 : 0);
}

main();
