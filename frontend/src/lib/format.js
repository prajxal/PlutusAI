// Value formatting. Indian digit grouping throughout -- the business is billed
// in rupees and reads in lakhs, so 4821000 must render as 48,21,000.

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const COUNT = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function formatValue(value, unit) {
  if (value === null || value === undefined) return "--";
  if (unit === "currency") return INR.format(value);
  if (unit === "percent") return `${value.toFixed(1)}%`;
  return COUNT.format(value);
}

export function formatDelta(value, unit) {
  if (unit === "percent") return `${Math.abs(value).toFixed(1)} points`;
  return `${Math.abs(value).toFixed(1)}%`;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Long form for prose, where "Sep 25" would read as a date rather than a month.
export function formatMonthLong(iso) {
  const [y, m] = iso.split("-");
  return `${MONTH_NAMES[Number(m) - 1]} ${y}`;
}

export function formatMonth(iso) {
  const [y, m] = iso.split("-");
  const names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");
  return `${names[Number(m) - 1]} ${y.slice(2)}`;
}

// Foundation Rule 4, made visible: any figure inside the agent's prose is set
// in the number face, so you can see at a glance which parts of a sentence
// were computed and which were written.
const FIGURE = /(₹\s?[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s?%|\b\d[\d,]*(?:\.\d+)?\b)/g;

export function splitFigures(text) {
  // One capture group in the pattern, so String.split alternates
  // plain text / figure / plain text ... and index parity tells us which.
  return String(text)
    .split(FIGURE)
    .map((part, i) => ({ text: part, isFigure: i % 2 === 1 }))
    .filter((part) => part.text !== "");
}

// Confidence maps to how the projected line is drawn, not to a coloured badge.
export const CONFIDENCE = {
  high: { dash: "0", band: 0.02, words: "high" },
  medium: { dash: "7 4", band: 0.06, words: "medium" },
  low: { dash: "2 5", band: 0.13, words: "low" },
};

export function confidenceOf(level) {
  return CONFIDENCE[level] || CONFIDENCE.medium;
}
