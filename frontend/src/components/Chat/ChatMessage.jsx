// A single turn. The agent's reply and the working behind it are one block,
// because Module C returns them together and Foundation Rule 3 says the owner
// must see the method, the assumptions and the confidence alongside the claim
// they support -- not behind a tooltip.
import { confidenceOf, splitFigures } from "../../lib/format.js";

// Any figure in the prose is set in the number face. Sentences are written;
// numbers are computed. Foundation Rule 4, made visible at the glyph level.
function Prose({ text }) {
  return (
    <>
      {splitFigures(text).map((part, i) =>
        part.isFigure ? (
          <span className="fig" key={i}>
            {part.text}
          </span>
        ) : (
          <span key={i}>{part.text}</span>
        )
      )}
    </>
  );
}

export default function ChatMessage({
  role,
  content,
  reply,
  method_plain,
  confidence,
  assumptions,
  scenario_saved_id,
  question,
  saveError,
  onSave,
}) {
  if (role === "user") {
    return (
      <article className="turn-you">
        <p className="turn-who">You asked</p>
        <p className="turn-said-you">{content}</p>
      </article>
    );
  }

  const shape = confidenceOf(confidence);
  const hasWorking = Boolean(method_plain || assumptions?.length);

  return (
    <article>
      <p className="turn-who">PlutusAI</p>
      <p className="turn-said">
        <Prose text={reply || content} />
      </p>

      {hasWorking && (
        <div className="working">
          <p className="working-key">Method</p>
          <p className="working-val">{method_plain}</p>

          {assumptions?.length > 0 && (
            <>
              <p className="working-key">Assuming</p>
              <ul className="working-list">
                {assumptions.map((a) => (
                  <li className="working-val" key={a}>
                    <Prose text={a} />
                  </li>
                ))}
              </ul>
            </>
          )}

          <p className="working-key">Confidence</p>
          <p className="working-val">
            <span className="confidence">
              {/* The same mark the chart just drew, so the word and the line
                  are one piece of language. */}
              <svg width="26" height="8" aria-hidden="true">
                <line
                  x1="0"
                  y1="4"
                  x2="26"
                  y2="4"
                  stroke="#2e34a0"
                  strokeWidth="2"
                  strokeDasharray={shape.dash}
                />
              </svg>
              {shape.words}
            </span>
          </p>
        </div>
      )}

      {question &&
        (scenario_saved_id ? (
          <p className="save-done">Saved to your scenarios.</p>
        ) : (
          <>
            <button className="save" type="button" onClick={onSave}>
              Save this scenario
            </button>
            {saveError && <p className="save-done">{saveError}</p>}
          </>
        ))}
    </article>
  );
}
