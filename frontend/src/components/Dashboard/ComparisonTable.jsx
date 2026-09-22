// The change, in figures. Sits under the chart because the chart shows the
// shape of the change and this shows its size.
// Digits are tabular and right-aligned so the before and after columns can be
// read down; the alternating stripe is green-bar accounting paper doing the
// job it was invented for, which is keeping your eye on one row.
import { formatValue } from "../../lib/format.js";

export default function ComparisonTable({ metrics, question }) {
  return (
    <section className="compare">
      <table className="compare-table">
        <caption className="compare-caption">{question}</caption>
        <thead>
          <tr>
            <th className="compare-head compare-head-first" scope="col">
              Measure
            </th>
            <th className="compare-head" scope="col">
              Now
            </th>
            <th className="compare-arrow" aria-hidden="true"></th>
            <th className="compare-head" scope="col">
              Projected
            </th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr className="compare-row" key={m.label}>
              <th className="compare-name" scope="row">
                {m.label}
              </th>
              <td className="compare-cell">{formatValue(m.baseline, m.unit)}</td>
              <td className="compare-arrow" aria-hidden="true">
                →
              </td>
              <td className="compare-cell-to">{formatValue(m.projected, m.unit)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
