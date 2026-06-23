import type { BriefObjection } from "./types";

export function ObjectionCards({
  objections,
}: {
  objections: BriefObjection[];
}) {
  const capped = objections.slice(0, 3);
  if (capped.length === 0) return null;

  return (
    <div class="brief-objections">
      <div class="brief-section-label">
        ГОТОВЫЕ ОТВЕТЫ НА ВОЗРАЖЕНИЯ
      </div>
      {capped.map((obj, i) => (
        <div key={i} class="brief-objection-item">
          <div class="brief-objection-q">{obj.question}</div>
          <div class="brief-objection-a">
            {"\u2192 "}
            {obj.answer}
          </div>
        </div>
      ))}
    </div>
  );
}
