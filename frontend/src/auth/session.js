// The signed-in session, held in the browser.
//
// Replaces Amplify/Cognito. The token is opaque to this code: it is attached
// to requests and otherwise not inspected, because the server decides what it
// means. In particular the business it belongs to is resolved server-side on
// every request and is deliberately not a claim we could read here.

const KEY = "plutusai.session";

let listeners = [];

export function getSession() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    // Private browsing, cleared storage, or a corrupt value: no session.
    return null;
  }
}

export function setSession(session) {
  try {
    if (session) localStorage.setItem(KEY, JSON.stringify(session));
    else localStorage.removeItem(KEY);
  } catch {
    // Storage being unavailable must not stop someone signing in; the session
    // simply lasts until they close the tab.
  }
  listeners.forEach((fn) => fn(session));
}

export function clearSession() {
  setSession(null);
}

export function onSessionChange(fn) {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((l) => l !== fn);
  };
}

export function getToken() {
  return getSession()?.token || null;
}
