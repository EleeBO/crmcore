// Permissions page: requests microphone access, saves flag, and closes the tab.
// Mic cannot be requested from Offscreen Document — must come from a
// visible extension page (popup or dedicated permissions page).

const btn = document.getElementById("grant-btn");
const errorEl = document.getElementById("error");

btn?.addEventListener("click", async () => {
  try {
    await navigator.mediaDevices.getUserMedia({ audio: true });
    // Store flag so popup knows mic was granted
    await chrome.storage.local.set({ micGranted: true });
    // Permission granted — close this page and return to popup
    window.close();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Ошибка доступа";
    if (errorEl) errorEl.textContent = `Не удалось получить доступ: ${msg}`;
  }
});
