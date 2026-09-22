// Renders KPI cards + charts from Module B's output.
// When the chat returns a simulation, its projection is drawn onto the primary
// chart rather than opening a second view -- the owner compares in one place.
import { formatMonthLong } from "../../lib/format.js";
import UploadForm from "../Upload/UploadForm.jsx";
import KpiCard from "./KpiCard.jsx";
import ChartPanel from "./ChartPanel.jsx";
import ComparisonTable from "./ComparisonTable.jsx";

export default function Dashboard({ dashboard, projection, failure, onDataLoaded }) {
  if (failure) {
    // 404 means the account is real but has no data yet, which is an
    // invitation to act rather than an error to apologise for.
    const empty = failure.status === 404;
    if (empty) {
      return (
        <div className="empty">
          <h2 className="empty-head">Start with a year of sales</h2>
          <p className="empty-note">
            Upload a CSV and PlutusAI builds the dashboard around whatever is in it. No
            template to fill in, and rows it cannot read are reported rather than dropped
            in silence.
          </p>
          <UploadForm onLoaded={onDataLoaded} />
          <p className="empty-note">
            Nothing to hand? Run <code className="code">python3 scripts/seed_sample_data.py</code>{" "}
            for a year of realistic bakery data.
          </p>
        </div>
      );
    }
    return (
      <div className="empty">
        <h2 className="empty-head">The dashboard could not load</h2>
        <p className="empty-note">{failure.message}</p>
      </div>
    );
  }
  if (!dashboard) {
    return <p className="loading">Building your dashboard from the file you uploaded.</p>;
  }

  const [primary, ...rest] = dashboard.charts;

  return (
    <>
      <header className="masthead">
        <h2 className="masthead-title">
          {projection ? "What the change does" : "What happened"}
        </h2>
        <p className="masthead-note">
          {projection
            ? "Projected figures are in indigo, here and in the chart. Your actual figures stay in black."
            : `${formatMonthLong(dashboard.source.from.slice(0, 7))} to ${formatMonthLong(
                dashboard.source.to.slice(0, 7)
              )}, from the file in the sidebar.`}
        </p>
      </header>

      <div className="band-figures">
        {dashboard.kpis.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>

      <ChartPanel chart={primary} projection={projection} />

      {projection?.summary && (
        <ComparisonTable
          metrics={projection.summary.metrics}
          question={projection.question}
        />
      )}

      {rest.length > 0 && (
        <div className="panel-row">
          {rest.map((chart) => (
            <ChartPanel key={chart.title} chart={chart} compact />
          ))}
        </div>
      )}

      {dashboard.anomalies.length > 0 && (
        <section className="noticed">
          <h3 className="panel-title">Worth a look</h3>
          <ul className="noticed-list">
            {dashboard.anomalies.map((note) => (
              <li className="noticed-item" key={note}>
                {note}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
