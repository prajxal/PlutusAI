// Single KPI display: { label, value, unit, trend, change }
// Not a card. A figure with its label set beneath it as a footing, separated
// from its neighbours by a hairline -- card chrome is reserved for things that
// are actually discrete objects.
import { formatValue, formatDelta } from "../../lib/format.js";

// Direction is carried by the shape of the mark, not by hue. Colour in this
// interface means actual vs projected and nothing else, which also makes the
// dashboard readable without colour vision.
function TrendMark({ trend }) {
  if (trend === "flat") {
    return (
      <svg className="trend-mark" width="10" height="9" aria-hidden="true">
        <line x1="0" y1="4.5" x2="10" y2="4.5" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    );
  }
  const up = trend === "up";
  return (
    <svg className="trend-mark" width="10" height="9" aria-hidden="true">
      <polygon
        points={up ? "5,0.5 9.5,8.5 0.5,8.5" : "5,8.5 0.5,0.5 9.5,0.5"}
        fill={up ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const WORD = { up: "up", down: "down", flat: "flat" };

export default function KpiCard({ label, value, unit, trend, change, change_label }) {
  // The period compared against is Module B's to decide, not ours to assume.
  const period = change_label || "on the previous period";
  return (
    <div className="figure">
      <span className="figure-value">{formatValue(value, unit)}</span>
      <span className="figure-label">{label}</span>
      <span className="figure-trend">
        <TrendMark trend={trend} />
        {trend === "flat"
          ? `flat ${period}`
          : `${WORD[trend]} ${formatDelta(change ?? 0, unit)} ${period}`}
      </span>
    </div>
  );
}
