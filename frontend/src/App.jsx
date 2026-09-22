// Top-level app shell.
// Renders the sheet (the dashboard) beside the conversation. Numbers live in
// the sheet; the reasoning behind them lives in the conversation -- that split
// is the whole layout.
import { useCallback, useEffect, useState } from "react";
import Dashboard from "./components/Dashboard/Dashboard.jsx";
import ChatPanel from "./components/Chat/ChatPanel.jsx";
import SignIn from "./components/Auth/SignIn.jsx";
import { getDashboard, listScenarios } from "./api/client.js";
import { clearSession, getSession, onSessionChange } from "./auth/session.js";
import { formatMonthLong } from "./lib/format.js";

export default function App() {
  const [session, setSession] = useState(getSession);
  const [dashboard, setDashboard] = useState(null);
  const [failure, setFailure] = useState(null);
  const [projection, setProjection] = useState(null);
  const [scenarios, setScenarios] = useState([]);

  useEffect(() => onSessionChange(setSession), []);

  const load = useCallback(() => {
    setFailure(null);
    getDashboard().then(setDashboard).catch(setFailure);
    // A failure here is not worth showing -- an empty scenario list and a
    // missing one look the same to the owner.
    listScenarios()
      .then((data) => setScenarios(data.scenarios || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!session) {
      setDashboard(null);
      setProjection(null);
      return;
    }
    load();
  }, [session, load]);

  if (!session) return <SignIn />;

  const source = dashboard?.source;

  return (
    <div className="app">
      <a className="skip-link" href="#sheet">
        Skip to the dashboard
      </a>

      <aside className="rail">
        <div>
          <p className="rail-mark">PlutusAI</p>
          <h1 className="rail-biz">
            {source?.business_name || session.user?.business_name || "Your business"}
          </h1>
          {source && (
            <p className="rail-source">
              Reading <span className="fig">{source.rows.toLocaleString("en-IN")}</span> rows
              from {source.file}, {formatMonthLong(source.from.slice(0, 7))} to{" "}
              {formatMonthLong(source.to.slice(0, 7))}.{" "}
              {source.rejected_rows > 0 && (
                <>
                  <span className="fig">{source.rejected_rows}</span> rows were skipped because
                  their dates could not be read.
                </>
              )}
            </p>
          )}
        </div>

        <div>
          <h2 className="rail-heading">Saved scenarios</h2>
          {scenarios.length === 0 ? (
            <p className="rail-empty">
              Nothing saved yet. Ask a what-if question and keep the ones worth coming back to.
            </p>
          ) : (
            <ul className="rail-list">
              {scenarios.map((s) => (
                <li className="scenario" key={s.scenario_id}>
                  {s.question}
                  <span className="scenario-when">{s.summary}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rail-foot">
          <p className="rail-empty">{session.user?.email}</p>
          <button className="linkish" type="button" onClick={clearSession}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="sheet" id="sheet">
        <Dashboard
          dashboard={dashboard}
          projection={projection}
          failure={failure}
          onDataLoaded={load}
        />
      </main>

      <section className="talk" aria-label="Ask about your numbers">
        <ChatPanel
          sessionId="default"
          onProjection={setProjection}
          onScenarioSaved={(s) => setScenarios((prev) => [s, ...prev])}
        />
      </section>
    </div>
  );
}
