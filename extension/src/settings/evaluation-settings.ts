/** Evaluation criteria settings page (FEAT-004). */

interface CriterionData {
  id: string;
  name: string;
  description: string;
  weight: number;
}

interface ConfigPayload {
  criteria: CriterionData[];
  model: string;
}

let criteria: CriterionData[] = [];
let API_BASE = "http://localhost:8000";

async function init(): Promise<void> {
  const stored = await chrome.storage.local.get(["backendUrl"]);
  API_BASE = stored.backendUrl || API_BASE;

  await loadConfig();
  renderAll();
  bindGlobalEvents();
}

async function loadConfig(): Promise<void> {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/evaluation-config`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data: ConfigPayload = await resp.json();
    criteria = data.criteria;
  } catch (err) {
    console.error("Failed to load config:", err);
  }
}

function renderAll(): void {
  const list = document.getElementById("criteria-list");
  if (!list) return;
  list.replaceChildren();

  for (let i = 0; i < criteria.length; i++) {
    list.appendChild(createCard(criteria[i], i));
  }
  updateWeightStatus();
}

function createCard(c: CriterionData, index: number): HTMLElement {
  const card = document.createElement("div");
  card.className = "criterion-card";
  card.dataset.index = String(index);

  // Top row: drag + name + delete
  const topRow = document.createElement("div");
  topRow.className = "criterion-top-row";

  const drag = document.createElement("span");
  drag.className = "criterion-drag";
  drag.textContent = "\u2801\u2801\u2801";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.className = "criterion-name-input";
  nameInput.value = c.name;
  nameInput.placeholder = "Название критерия";
  nameInput.addEventListener("input", () => {
    criteria[index].name = nameInput.value;
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "criterion-delete-btn";
  deleteBtn.textContent = "\ud83d\uddd1";
  deleteBtn.addEventListener("click", () => {
    if (criteria.length <= 1) return;
    criteria.splice(index, 1);
    renderAll();
  });

  topRow.appendChild(drag);
  topRow.appendChild(nameInput);
  topRow.appendChild(deleteBtn);
  card.appendChild(topRow);

  // Description textarea
  const desc = document.createElement("textarea");
  desc.className = "criterion-desc-textarea";
  desc.value = c.description;
  desc.placeholder = "Описание критерия";
  desc.addEventListener("input", () => {
    criteria[index].description = desc.value;
  });
  card.appendChild(desc);

  // Weight row
  const weightRow = document.createElement("div");
  weightRow.className = "criterion-weight-row";

  const weightLabel = document.createElement("span");
  weightLabel.className = "criterion-weight-label";
  weightLabel.textContent = "Вес:";

  const slider = document.createElement("input");
  slider.type = "range";
  slider.className = "criterion-weight-slider";
  slider.min = "0";
  slider.max = "50";
  slider.value = String(Math.round(c.weight * 100));

  const weightInput = document.createElement("input");
  weightInput.type = "number";
  weightInput.className = "criterion-weight-input";
  weightInput.min = "0";
  weightInput.max = "50";
  weightInput.value = String(Math.round(c.weight * 100));

  const pctSign = document.createElement("span");
  pctSign.className = "criterion-weight-label";
  pctSign.textContent = "%";

  slider.addEventListener("input", () => {
    const val = Number(slider.value);
    weightInput.value = String(val);
    criteria[index].weight = val / 100;
    updateWeightStatus();
  });

  weightInput.addEventListener("input", () => {
    const val = Math.min(50, Math.max(0, Number(weightInput.value)));
    slider.value = String(val);
    criteria[index].weight = val / 100;
    updateWeightStatus();
  });

  weightRow.appendChild(weightLabel);
  weightRow.appendChild(slider);
  weightRow.appendChild(weightInput);
  weightRow.appendChild(pctSign);
  card.appendChild(weightRow);

  return card;
}

function updateWeightStatus(): void {
  const total = criteria.reduce((sum, c) => sum + c.weight, 0);
  const pct = Math.round(total * 100);
  const sumEl = document.getElementById("weight-sum");
  const statusEl = document.querySelector(".weight-status");
  const saveBtn = document.getElementById("save-btn") as HTMLButtonElement | null;

  if (sumEl) sumEl.textContent = `${pct}%`;

  const isValid = Math.abs(total - 1.0) <= 0.01;
  if (statusEl) {
    statusEl.classList.toggle("error", !isValid);
  }
  if (saveBtn) saveBtn.disabled = !isValid;
}

function bindGlobalEvents(): void {
  document.getElementById("add-criterion-btn")?.addEventListener("click", () => {
    if (criteria.length >= 10) return;
    criteria.push({
      id: `custom_${Date.now()}`,
      name: "",
      description: "",
      weight: 0,
    });
    renderAll();
  });

  document.getElementById("reset-btn")?.addEventListener("click", async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/evaluation-config/reset`, {
        method: "POST",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: ConfigPayload = await resp.json();
      criteria = data.criteria;
      renderAll();
    } catch (err) {
      console.error("Reset failed:", err);
    }
  });

  document.getElementById("save-btn")?.addEventListener("click", async () => {
    const total = criteria.reduce((sum, c) => sum + c.weight, 0);
    if (Math.abs(total - 1.0) > 0.01) return;

    const errEl = document.getElementById("validation-error");
    try {
      const resp = await fetch(`${API_BASE}/api/v1/evaluation-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ criteria, model: "google/gemini-2.5-flash" }),
      });
      if (!resp.ok) {
        const detail = await resp.text();
        if (errEl) {
          errEl.textContent = `Ошибка сохранения: ${detail}`;
          errEl.hidden = false;
        }
        return;
      }
      if (errEl) errEl.hidden = true;
      // Visual feedback
      const btn = document.getElementById("save-btn");
      if (btn) {
        btn.textContent = "Сохранено \u2713";
        setTimeout(() => { btn.textContent = "Сохранить"; }, 2000);
      }
    } catch (err) {
      if (errEl) {
        errEl.textContent = `Ошибка: ${String(err)}`;
        errEl.hidden = false;
      }
    }
  });
}

document.addEventListener("DOMContentLoaded", init);
