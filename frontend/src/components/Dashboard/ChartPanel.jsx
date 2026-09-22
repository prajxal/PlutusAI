// Renders line/bar charts, including the before/after (baseline vs projected)
// series returned by what-if simulations.
//
// The one idea this file carries: confidence is drawn, not labelled. A
// high-confidence projection is a tight solid line with a narrow band; a
// low-confidence one is drawn loosely with a wide hatched band. You read how
// much to trust a number off the quality of the mark before you read a word.
import { useMemo } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { confidenceOf, formatMonth, formatValue } from "../../lib/format.js";

const METRIC_TITLE = {
  revenue: "Monthly revenue",
  profit: "Monthly profit",
  margin: "Monthly gross margin",
};

const INK = "#16251c";
const PENCIL = "#2e34a0";
const RULE = "#cbd6c4";
const SOFT = "#4e5e54";

const reduceMotion =
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function compactTick(unit) {
  return (value) => {
    if (unit === "currency") {
      if (Math.abs(value) >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
      if (Math.abs(value) >= 1000) return `₹${Math.round(value / 1000)}k`;
      return `₹${value}`;
    }
    if (unit === "percent") return `${value}%`;
    if (Math.abs(value) >= 1000) return `${Math.round(value / 1000)}k`;
    return String(value);
  };
}

const axis = {
  stroke: RULE,
  tick: { fill: SOFT, fontFamily: "Archivo, sans-serif", fontSize: 12 },
  tickLine: false,
};

function labelOf(x) {
  return /^\d{4}-\d{2}$/.test(x) ? formatMonth(x) : x;
}

function ChartTip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tip">
      <span className="tip-when">{label}</span>
      {payload
        .filter((row) => row.dataKey !== "band")
        .map((row) => (
          <span className="tip-row" key={row.dataKey}>
            <span>{row.dataKey === "projected" ? "Projected" : "What happened"}</span>
            <span className={row.dataKey === "projected" ? "fig projected" : "fig"}>
              {formatValue(row.value, unit)}
            </span>
          </span>
        ))}
    </div>
  );
}

export default function ChartPanel({ chart, projection, compact = false }) {
  const showProjection =
    !compact && projection?.chart && projection.chart.x.length === chart.x.length;
  const confidence = confidenceOf(projection?.confidence);

  // With a projection on screen both lines come from Module C, which returns
  // baseline_y and projected_y for the same metric. Mixing Module B's series
  // with Module C's would put two different measures on one axis.
  const data = useMemo(() => {
    const baseline = showProjection ? projection.chart.baseline_y : chart.series[0].y;
    return chart.x.map((x, i) => {
      const row = { x: labelOf(x), actual: baseline[i] };
      if (showProjection) {
        const value = projection.chart.projected_y[i];
        row.projected = value;
        // Band width is the confidence, expressed as a range rather than a word.
        row.band = [
          Math.round(value * (1 - confidence.band)),
          Math.round(value * (1 + confidence.band)),
        ];
      }
      return row;
    });
  }, [chart, projection, showProjection, confidence.band]);

  const unit = showProjection
    ? projection.chart.metric === "margin"
      ? "percent"
      : "currency"
    : chart.unit || "count";

  if (chart.type === "bar") {
    return (
      <section className="panel">
        <h3 className="panel-title">{chart.title}</h3>
        <div className={compact ? "panel-plot-sm" : "panel-plot"}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={RULE} vertical={false} />
              <XAxis dataKey="x" {...axis} interval={0} />
              <YAxis {...axis} tickFormatter={compactTick(unit)} width={52} />
              <Tooltip
                cursor={{ fill: "rgba(22,37,28,.06)" }}
                content={<ChartTip unit={unit} />}
              />
              <Bar dataKey="actual" fill={INK} maxBarSize={44} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <h3 className="panel-title">
        {showProjection
          ? `${METRIC_TITLE[projection.chart.metric] || chart.title}, with your change applied`
          : chart.title}
      </h3>
      <div className={compact ? "panel-plot-sm" : "panel-plot"}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <pattern
                id="plutus-hatch"
                width="6"
                height="6"
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)"
              >
                <line x1="0" y1="0" x2="0" y2="6" stroke={PENCIL} strokeWidth="1.4" opacity="0.3" />
              </pattern>
            </defs>
            <CartesianGrid stroke={RULE} vertical={false} />
            <XAxis dataKey="x" {...axis} />
            <YAxis {...axis} tickFormatter={compactTick(unit)} width={52} domain={["auto", "auto"]} />
            <Tooltip cursor={{ stroke: RULE }} content={<ChartTip unit={unit} />} />
            {showProjection && (
              <Area
                dataKey="band"
                stroke="none"
                fill="url(#plutus-hatch)"
                isAnimationActive={false}
              />
            )}
            <Line
              dataKey="actual"
              stroke={INK}
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
            />
            {showProjection && (
              <Line
                dataKey="projected"
                stroke={PENCIL}
                strokeWidth={2}
                strokeDasharray={confidence.dash}
                dot={false}
                // The single piece of non-user-triggered motion in the app: the
                // projection draws itself in, once, when a simulation lands.
                isAnimationActive={!reduceMotion}
                animationDuration={700}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {showProjection && (
        <p className="key">
          <span className="key-item">
            <svg width="26" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="26" y2="4" stroke={INK} strokeWidth="1.75" />
            </svg>
            What happened
          </span>
          <span className="key-item">
            <svg width="26" height="8" aria-hidden="true">
              <line
                x1="0"
                y1="4"
                x2="26"
                y2="4"
                stroke={PENCIL}
                strokeWidth="2"
                strokeDasharray={confidence.dash}
              />
            </svg>
            Projected, drawn {confidence.words === "high" ? "tight" : "loose"} because confidence is{" "}
            {confidence.words}
          </span>
        </p>
      )}
    </section>
  );
}
