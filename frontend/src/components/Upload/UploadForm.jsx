// CSV upload.
//
// One request: pick a file, it goes straight to the backend and comes back
// with what loaded and what did not. Rejected rows are shown rather than
// swallowed -- an owner should never be left wondering why a total looks low.
import { useRef, useState } from "react";
import { uploadCsv } from "../../api/client.js";

export default function UploadForm({ onLoaded }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState(null);
  const [result, setResult] = useState(null);
  const input = useRef(null);

  async function send(file) {
    if (!file || busy) return;
    setBusy(true);
    setFailure(null);
    try {
      const loaded = await uploadCsv(file);
      setResult(loaded);
      onLoaded?.(loaded);
    } catch (error) {
      setFailure(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upload">
      <input
        ref={input}
        className="skip-link"
        type="file"
        accept=".csv,text/csv"
        id="csv-input"
        onChange={(e) => send(e.target.files?.[0])}
      />
      <label className="upload-drop" htmlFor="csv-input">
        <span className="upload-action">
          {busy ? "Reading your file" : "Choose a CSV"}
        </span>
        <span className="upload-hint">
          Sales rows with a date, a product, how many you sold, your price and
          your cost. Column names do not have to match ours.
        </span>
      </label>

      {failure && (
        <p className="field-error" role="alert">
          {failure}
        </p>
      )}

      {result && (
        <div className="upload-result">
          <p>
            Loaded <span className="fig">{result.records.toLocaleString("en-IN")}</span> rows
            {result.rejected.length > 0 && (
              <>
                {" "}and skipped <span className="fig">{result.rejected.length}</span>.
              </>
            )}
          </p>
          {result.rejected.length > 0 && (
            <ul className="upload-rejects">
              {result.rejected.slice(0, 5).map((row) => (
                <li key={row.line}>
                  Line <span className="fig">{row.line}</span>: {row.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
