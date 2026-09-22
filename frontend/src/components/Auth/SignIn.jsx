// Sign in, or create a business.
//
// One form, two modes. Replaces the hosted Cognito UI, which is why the copy
// matters more than it would otherwise: this is the first thing an owner sees
// and it has to sound like the rest of the product, not like an auth vendor.
import { useState } from "react";
import { register, signIn } from "../../api/client.js";
import { setSession } from "../../auth/session.js";

export default function SignIn() {
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [failure, setFailure] = useState(null);
  const [busy, setBusy] = useState(false);

  const creating = mode === "register";

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setFailure(null);
    try {
      const session = creating
        ? await register(email, password, businessName)
        : await signIn(email, password);
      setSession(session);
    } catch (error) {
      setFailure(error.message);
      setBusy(false);
    }
  }

  return (
    <main className="gate">
      <div className="gate-panel">
        <p className="rail-mark">PlutusAI</p>
        <h1 className="gate-head">
          {creating ? "Set up your business" : "Welcome back"}
        </h1>
        <p className="gate-note">
          {creating
            ? "Upload a year of sales and PlutusAI builds a dashboard around what is actually in it."
            : "Sign in to pick up where you left off."}
        </p>

        <form className="gate-form" onSubmit={submit}>
          {creating && (
            <label className="field">
              <span className="field-label">Business name</span>
              <input
                className="field-input"
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                placeholder="Amba Bakehouse"
                autoComplete="organization"
              />
            </label>
          )}

          <label className="field">
            <span className="field-label">Email</span>
            <input
              className="field-input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </label>

          <label className="field">
            <span className="field-label">Password</span>
            <input
              className="field-input"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={creating ? "new-password" : "current-password"}
            />
            {creating && (
              <span className="field-hint">At least 10 characters.</span>
            )}
          </label>

          {failure && (
            <p className="field-error" role="alert">
              {failure}
            </p>
          )}

          <button className="composer-send gate-submit" type="submit" disabled={busy}>
            {busy ? "One moment" : creating ? "Create business" : "Sign in"}
          </button>
        </form>

        <p className="gate-switch">
          {creating ? "Already have an account?" : "First time here?"}{" "}
          <button
            className="linkish"
            type="button"
            onClick={() => {
              setMode(creating ? "signin" : "register");
              setFailure(null);
            }}
          >
            {creating ? "Sign in" : "Set up your business"}
          </button>
        </p>
      </div>
    </main>
  );
}
