// Chat UI for both insight questions and what-if scenarios.
// Calls api/client.js#sendChatMessage and lifts any returned simulation up to
// the dashboard, which draws it onto the chart the owner is already reading.
import { useEffect, useRef, useState } from "react";
import ChatMessage from "./ChatMessage.jsx";
import { sendChatMessage, saveScenario } from "../../api/client.js";

const OPENERS = [
  "Why did margin drop in May?",
  "What if I raise the sourdough 10%?",
  "What if I make my own packaging?",
];

export default function ChatPanel({ sessionId, onProjection, onScenarioSaved }) {
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const streamRef = useRef(null);

  // Bring the newest turn to the TOP of the view, not the bottom -- a long
  // reply scrolled to its end hides the sentence that answers the question.
  useEffect(() => {
    const el = streamRef.current;
    if (!el) return;
    const last = el.querySelector("article:last-of-type");
    if (!last) return;
    el.scrollTop += last.getBoundingClientRect().top - el.getBoundingClientRect().top - 8;
  }, [turns, pending]);

  async function ask(message) {
    const text = message.trim();
    if (!text || pending) return;
    setDraft("");
    setTurns((prev) => [...prev, { id: `u${Date.now()}`, role: "user", content: text }]);
    setPending(true);

    try {
      const reply = await sendChatMessage(sessionId, text);
      setTurns((prev) => [...prev, { id: `a${Date.now()}`, role: "assistant", ...reply }]);
      if (reply.chart) onProjection(reply);
    } catch (error) {
      setTurns((prev) => [
        ...prev,
        { id: `e${Date.now()}`, role: "assistant", reply: error.message, failed: true },
      ]);
    } finally {
      setPending(false);
    }
  }

  async function keep(turn) {
    try {
      const saved = await saveScenario(sessionId, turn);
      setTurns((prev) =>
        prev.map((t) => (t.id === turn.id ? { ...t, scenario_saved_id: saved.scenario_id } : t))
      );
      onScenarioSaved({
        scenario_id: saved.scenario_id,
        question: turn.question,
        summary: "Saved just now",
      });
    } catch (error) {
      setTurns((prev) =>
        prev.map((t) => (t.id === turn.id ? { ...t, saveError: error.message } : t))
      );
    }
  }

  return (
    <>
      <header className="talk-head">
        <h2 className="talk-title">Ask about your numbers</h2>
        <p className="talk-note">
          Questions about what happened, or what-ifs. Every projection shows its working.
        </p>
      </header>

      <div className="stream" ref={streamRef}>
        {turns.length === 0 && (
          <div className="opening">
            <p className="opening-text">
              Ask in your own words. For a what-if, PlutusAI runs the maths against your own
              12 months of data and tells you which method it used, so you can decide whether
              to believe it.
            </p>
            <div className="chips">
              {OPENERS.map((q) => (
                <button className="chip" key={q} onClick={() => ask(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn) => (
          <ChatMessage key={turn.id} {...turn} onSave={() => keep(turn)} />
        ))}

        {pending && <p className="thinking">Checking your figures and running the numbers.</p>}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
        }}
      >
        <label className="skip-link" htmlFor="composer-field">
          Your question
        </label>
        <textarea
          id="composer-field"
          className="composer-field"
          rows={2}
          value={draft}
          placeholder="Ask about your numbers, or try a what-if."
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(draft);
            }
          }}
        />
        <button className="composer-send" type="submit" disabled={pending || !draft.trim()}>
          Ask
        </button>
      </form>
    </>
  );
}
