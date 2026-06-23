/** Full evaluation report page (FEAT-004). Uses safe DOM methods only. */

interface CriterionResultWire {
  criterion_id: string;
  criterion_name: string;
  reasoning: string;
  score: number;
  comment: string;
  recommendations: string[];
}

interface CallEvaluationResult {
  call_summary: string;
  criteria_results: CriterionResultWire[];
  overall_score: number;
  verdict: "excellent" | "good" | "satisfactory" | "needs_improvement";
  strengths: string[];
  growth_areas: string[];
  action_plan: string[];
}

interface CallAnalyticsWire {
  total_duration_s: number;
  rep_talk_ratio: number;
  rep_talk_time_s: number;
  client_talk_time_s: number;
  rep_speech_rate_wpm: number;
  client_speech_rate_wpm: number;
  interruptions_by_rep: number;
  interruptions_by_client: number;
  avg_rep_pause_before_response_s: number;
  rep_word_count: number;
  client_word_count: number;
}

const VERDICT_LABELS: Record<string, string> = {
  excellent: "Отлично",
  good: "Хорошо",
  satisfactory: "Удовлетворительно",
  needs_improvement: "Требует внимания",
};

const VERDICT_COLORS: Record<string, string> = {
  excellent: "#22c55e",
  good: "#3b82f6",
  satisfactory: "#f59e0b",
  needs_improvement: "#ef4444",
};

function scoreColor(score: number): string {
  if (score >= 7) return "#22c55e";
  if (score >= 4) return "#f59e0b";
  return "#ef4444";
}

let currentAnalytics: CallAnalyticsWire | null = null;

const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS = 60_000;
const FETCH_TIMEOUT_MS = 10_000;

function updateLoadingText(msg: string): void {
  const loadingEl = document.getElementById("report-loading");
  if (!loadingEl) return;
  const span = loadingEl.querySelector("span");
  if (span) span.textContent = msg;
}

async function pollEvaluation(
  apiBase: string,
  sessionId: string,
  token: string,
): Promise<(CallEvaluationResult & { analytics?: CallAnalyticsWire }) | null> {
  const url = `${apiBase}/api/v1/evaluation/${sessionId}?token=${token}`;
  const start = Date.now();

  while (Date.now() - start < POLL_TIMEOUT_MS) {
    const elapsedS = Math.round((Date.now() - start) / 1000);
    updateLoadingText(`Оценка звонка... ${elapsedS}с`);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
      const resp = await fetch(url, { signal: controller.signal });
      clearTimeout(timeoutId);

      if (resp.ok) {
        return await resp.json();
      }

      if (resp.status === 404) {
        // Not ready yet — wait and retry
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        continue;
      }

      // Real error (403, 500, etc.) — stop polling
      showErrorReport(`Ошибка загрузки: HTTP ${resp.status}`);
      return null;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // Single fetch timed out — retry
        continue;
      }
      // Network error — stop polling
      showErrorReport(
        `Ошибка: ${String(err)}. Убедитесь, что бэкенд запущен.`,
      );
      return null;
    }
  }

  showErrorReport(
    "Время ожидания истекло. Оценка ещё не готова — попробуйте обновить страницу позже.",
  );
  return null;
}

async function initReport(): Promise<void> {
  const sessionId = new URLSearchParams(location.search).get("session_id");
  if (!sessionId) {
    showErrorReport("session_id не указан в URL");
    return;
  }

  const stored = await chrome.storage.local.get([
    "backendUrl",
    `eval_token_${sessionId}`,
    `eval_result_${sessionId}`,
    `eval_analytics_${sessionId}`,
  ]);

  // Load analytics from cache
  const cachedAnalytics = stored[`eval_analytics_${sessionId}`] as
    CallAnalyticsWire | null | undefined;
  if (cachedAnalytics) {
    currentAnalytics = cachedAnalytics;
  }

  // Try cache first
  const cached = stored[`eval_result_${sessionId}`] as CallEvaluationResult | undefined;
  if (cached) {
    renderReport(cached);
    return;
  }

  // Fetch from API
  const apiBase = stored.backendUrl || "http://localhost:8000";
  const token = stored[`eval_token_${sessionId}`] as string | undefined;
  if (!token) {
    showErrorReport("Токен доступа не найден. Попробуйте открыть отчёт из панели.");
    return;
  }

  const result = await pollEvaluation(apiBase, sessionId, token);
  if (result) {
    const { analytics, ...evalData } = result;
    if (analytics) {
      currentAnalytics = analytics;
    }
    renderReport(evalData);
  }
}

function showErrorReport(msg: string): void {
  const loadingEl = document.getElementById("report-loading");
  const errorEl = document.getElementById("report-error");
  if (loadingEl) loadingEl.hidden = true;
  if (errorEl) {
    errorEl.hidden = false;
    errorEl.textContent = msg;
  }
}

function renderReport(ev: CallEvaluationResult): void {
  const loadingEl = document.getElementById("report-loading");
  const contentEl = document.getElementById("report-content");
  if (loadingEl) loadingEl.hidden = true;
  if (contentEl) contentEl.hidden = false;

  const color = VERDICT_COLORS[ev.verdict] || "#3b82f6";

  // Date
  const dateEl = document.getElementById("report-date");
  if (dateEl) dateEl.textContent = new Date().toLocaleString("ru-RU");

  // Score
  const scoreEl = document.getElementById("report-score");
  if (scoreEl) {
    scoreEl.textContent = ev.overall_score.toFixed(1);
    scoreEl.style.color = color;
  }

  // Verdict badge
  const verdictEl = document.getElementById("report-verdict-badge");
  if (verdictEl) {
    verdictEl.textContent = VERDICT_LABELS[ev.verdict] || ev.verdict;
    verdictEl.style.background = color + "20";
    verdictEl.style.color = color;
  }

  // Summary
  const summaryEl = document.getElementById("report-summary");
  if (summaryEl) summaryEl.textContent = ev.call_summary;

  // Scorecard
  const scorecardEl = document.getElementById("report-scorecard");
  if (scorecardEl) {
    scorecardEl.replaceChildren();
    for (const cr of ev.criteria_results) {
      scorecardEl.appendChild(createCriterionCardReport(cr));
    }
  }

  // Strengths
  renderListReport("report-strengths", ev.strengths);

  // Growth areas
  renderListReport("report-growth", ev.growth_areas);

  // Action plan
  renderListReport("report-action-plan", ev.action_plan);

  // Analytics
  if (currentAnalytics) {
    renderAnalytics(currentAnalytics);
  }

  // Copy button
  document.getElementById("copy-btn")?.addEventListener("click", () => {
    const text = buildPlainText(ev);
    navigator.clipboard.writeText(text).then(() => {
      const btn = document.getElementById("copy-btn");
      if (btn) {
        btn.textContent = "Скопировано!";
        setTimeout(() => { btn.textContent = "Скопировать как текст"; }, 2000);
      }
    });
  });
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins} мин ${String(secs).padStart(2, "0")} сек`;
}

function renderAnalytics(a: CallAnalyticsWire): void {
  const section = document.getElementById("report-analytics");
  if (!section) return;
  section.hidden = false;

  // Duration
  const durVal = document.getElementById("analytics-duration-val");
  if (durVal) durVal.textContent = formatDuration(a.total_duration_s);

  // Talk ratio bar
  const ratioBar = document.getElementById("analytics-ratio-bar");
  if (ratioBar) {
    const repPct = Math.round(a.rep_talk_ratio * 100);
    const clientPct = 100 - repPct;
    const inRange = repPct >= 35 && repPct <= 50;
    const repColor = inRange ? "#22c55e" : "#f59e0b";
    ratioBar.innerHTML = "";
    const repDiv = document.createElement("div");
    repDiv.className = "ratio-segment ratio-rep";
    repDiv.style.width = `${repPct}%`;
    repDiv.style.background = repColor;
    repDiv.textContent = `${repPct}%`;
    const clientDiv = document.createElement("div");
    clientDiv.className = "ratio-segment ratio-client";
    clientDiv.style.width = `${clientPct}%`;
    clientDiv.textContent = `${clientPct}%`;
    ratioBar.appendChild(repDiv);
    ratioBar.appendChild(clientDiv);
  }
  const ratioVal = document.getElementById("analytics-ratio-val");
  if (ratioVal) {
    const repPct = Math.round(a.rep_talk_ratio * 100);
    ratioVal.textContent = `Менеджер ${repPct}% / Клиент ${100 - repPct}%`;
  }

  // Speech rate
  const rateVal = document.getElementById("analytics-speech-rate-val");
  if (rateVal) {
    rateVal.textContent =
      `${Math.round(a.rep_speech_rate_wpm)} сл/мин (менеджер) / ` +
      `${Math.round(a.client_speech_rate_wpm)} сл/мин (клиент)`;
  }

  // Interruptions
  const intVal = document.getElementById("analytics-interruptions-val");
  if (intVal) {
    intVal.textContent =
      `${a.interruptions_by_rep} (менеджер) / ${a.interruptions_by_client} (клиент)`;
  }

  // Pause
  const pauseVal = document.getElementById("analytics-pause-val");
  if (pauseVal) {
    pauseVal.textContent = `${a.avg_rep_pause_before_response_s.toFixed(1)} сек`;
  }
}

function createCriterionCardReport(cr: CriterionResultWire): HTMLElement {
  const card = document.createElement("div");
  card.className = "criterion-card";

  // Header
  const header = document.createElement("div");
  header.className = "criterion-header";

  const name = document.createElement("span");
  name.className = "criterion-name";
  name.textContent = cr.criterion_name;

  const scoreBadge = document.createElement("span");
  scoreBadge.className = "criterion-score-badge";
  scoreBadge.textContent = `${cr.score}/10`;
  scoreBadge.style.color = scoreColor(cr.score);

  header.appendChild(name);
  header.appendChild(scoreBadge);
  card.appendChild(header);

  // Bar
  const bar = document.createElement("div");
  bar.className = "criterion-bar";
  const fill = document.createElement("div");
  fill.className = "criterion-bar-fill";
  fill.style.width = `${cr.score * 10}%`;
  fill.style.background = scoreColor(cr.score);
  bar.appendChild(fill);
  card.appendChild(bar);

  // Comment
  const comment = document.createElement("p");
  comment.className = "criterion-comment";
  comment.textContent = cr.comment;
  card.appendChild(comment);

  // Recommendations
  if (cr.recommendations.length > 0) {
    const recList = document.createElement("ul");
    recList.className = "criterion-recs";
    for (const rec of cr.recommendations) {
      const li = document.createElement("li");
      li.textContent = rec;
      recList.appendChild(li);
    }
    card.appendChild(recList);
  }

  return card;
}

function renderListReport(elementId: string, items: string[]): void {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.replaceChildren();
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  }
}

function buildPlainText(ev: CallEvaluationResult): string {
  const lines: string[] = [
    `ОЦЕНКА ЗВОНКА: ${ev.overall_score.toFixed(1)}/10 (${VERDICT_LABELS[ev.verdict]})`,
    "",
  ];

  if (currentAnalytics) {
    const a = currentAnalytics;
    const repPct = Math.round(a.rep_talk_ratio * 100);
    lines.push(
      "АНАЛИТИКА ЗВОНКА:",
      `  Длительность: ${formatDuration(a.total_duration_s)}`,
      `  Соотношение речи: Менеджер ${repPct}% / Клиент ${100 - repPct}%`,
      `  Темп речи: ${Math.round(a.rep_speech_rate_wpm)} сл/мин (менеджер) / ${Math.round(a.client_speech_rate_wpm)} сл/мин (клиент)`,
      `  Перебивания: ${a.interruptions_by_rep} (менеджер) / ${a.interruptions_by_client} (клиент)`,
      `  Пауза перед ответом: ${a.avg_rep_pause_before_response_s.toFixed(1)} сек`,
      "",
    );
  }

  lines.push(
    `Резюме: ${ev.call_summary}`,
    "",
    "КРИТЕРИИ:",
  );
  for (const cr of ev.criteria_results) {
    lines.push(`  ${cr.criterion_name}: ${cr.score}/10 — ${cr.comment}`);
    for (const rec of cr.recommendations) {
      lines.push(`    - ${rec}`);
    }
  }
  lines.push("", "Сильные стороны:");
  for (const s of ev.strengths) lines.push(`  + ${s}`);
  lines.push("", "Зоны роста:");
  for (const g of ev.growth_areas) lines.push(`  ^ ${g}`);
  lines.push("", "План действий:");
  ev.action_plan.forEach((item, i) => lines.push(`  ${i + 1}. ${item}`));
  return lines.join("\n");
}

document.addEventListener("DOMContentLoaded", initReport);
