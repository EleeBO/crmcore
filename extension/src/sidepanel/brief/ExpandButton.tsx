import { useState } from "preact/hooks";

export function ExpandButton({ text }: { text?: string }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;

  return (
    <div class="brief-expand-wrapper">
      <button
        class="brief-expand-btn"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {open ? "Скрыть полный бриф \u2191" : "Открыть полный бриф \u2192"}
      </button>
      {open && <pre class="brief-expand-content">{text}</pre>}
    </div>
  );
}
