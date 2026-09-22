// Thin wrapper around API Gateway endpoints.
// NOTE: no business_id parameters -- the backend derives it from the auth token,
// and rejects any request that tries to name its own (Foundation Rule 1).
//
// Point this at a deployed API with VITE_API_URL; it defaults to the
// application running locally (python3 backend/app.py).

import { clearSession, getToken } from "../auth/session.js";

const BASE = (import.meta.env?.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

function authHeaders(extra = {}) {
  const token = getToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

async function request(path, { method = "GET", body, anonymous = false } = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers: anonymous
        ? body
          ? { "Content-Type": "application/json" }
          : undefined
        : authHeaders(body ? { "Content-Type": "application/json" } : {}),
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (cause) {
    // A dead backend is the likeliest failure in development, and "failed to
    // fetch" tells nobody anything.
    throw new ApiError(
      `Could not reach the backend at ${BASE}. Start it with: python3 backend/app.py`,
      0
    );
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      throw new ApiError(`The backend returned something that isn't JSON.`, response.status);
    }
  }

  if (!response.ok) {
    // An expired or revoked token should drop the session rather than leave
    // the app retrying with a credential the server has already rejected.
    if (response.status === 401 && !anonymous) clearSession();
    throw new ApiError(payload?.error || `Request failed (${response.status}).`,
                       response.status, payload?.details);
  }
  return payload;
}

// --- accounts ---------------------------------------------------------------

export async function register(email, password, businessName) {
  return request("/api/auth/register", {
    method: "POST",
    anonymous: true,
    body: { email, password, business_name: businessName || null },
  });
}

export async function signIn(email, password) {
  return request("/api/auth/login", {
    method: "POST",
    anonymous: true,
    body: { email, password },
  });
}

export async function uploadCsv(file) {
  // One request. The old two-step presigned-URL dance existed only to get
  // large files past API Gateway's 10 MB body limit, which no longer applies.
  const form = new FormData();
  form.append("file", file);

  let response;
  try {
    response = await fetch(`${BASE}/api/uploads`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
  } catch {
    throw new ApiError(`Could not reach the backend at ${BASE}.`, 0);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(payload?.error || "That file could not be read.",
                       response.status, payload?.details);
  }
  return payload;
}

export async function getDashboard() {
  /* -> Module B (generate-dashboard) */
  return request("/api/dashboard");
}

export async function sendChatMessage(sessionId, message) {
  /* -> Module C (chat-agent) */
  return request("/api/chat", { method: "POST", body: { session_id: sessionId, message } });
}

export async function listScenarios() {
  /* -> read-only convenience over the Scenarios table */
  return request("/api/scenarios");
}

export async function saveScenario(sessionId, turn) {
  // The agent returns scenario_saved_id when it decides to save one itself;
  // this is the owner choosing to keep one after reading it.
  return request("/api/scenarios", {
    method: "POST",
    body: {
      session_id: sessionId,
      question: turn.question,
      summary: turn.reply,
      method: turn.method,
      confidence: turn.confidence,
      baseline: turn.summary?.metrics?.reduce((acc, m) => ({ ...acc, [m.label]: m.baseline }), {}),
      projected: turn.summary?.metrics?.reduce((acc, m) => ({ ...acc, [m.label]: m.projected }), {}),
    },
  });
}
