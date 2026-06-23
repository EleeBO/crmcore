export function PainPoints({ points }: { points: string[] }) {
  if (points.length === 0) return null;

  return (
    <div class="brief-pains">
      {points.map((p, i) => (
        <div key={i} class="brief-pain-item">
          <span class="brief-pain-marker">!</span>
          <span class="brief-pain-text">{p}</span>
        </div>
      ))}
    </div>
  );
}
