import { useState, type FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { Card } from "../components/ui";

export function Login({
  onAuthenticated,
}: {
  onAuthenticated: (user: { username: string; role: string }) => void;
}) {
  const [username, setUsername] = useState("operator");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onAuthenticated(await api.login(username, password));
    } catch (caught) {
      // The server returns one message for a wrong username and a wrong password, so it
      // is not a username oracle. Repeating it here keeps that property.
      setError(
        caught instanceof ApiError && caught.status === 429
          ? "Too many attempts. Wait five minutes."
          : "Invalid credentials.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card">
        <Card>
          <div className="row" style={{ gap: 12, alignItems: "center" }}>
            <img src="/icon-192.png" alt="" width={40} height={40} style={{ borderRadius: 10 }} />
            <div>
              <h1 style={{ margin: 0 }}>Trader-IA</h1>
              <span className="dim" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                Autonomous paper-trading research
              </span>
            </div>
          </div>
          <p className="dim" style={{ margin: "10px 0 0", fontSize: 13 }}>
            Simulation-only. No real money, no broker, no custody.
          </p>
          <form onSubmit={submit}>
            <label className="field">
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label className="field">
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            {error && <div className="banner error">{error}</div>}
            <button className="btn primary" disabled={busy} type="submit">
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <p className="footnote" style={{ marginTop: 18 }}>
            Credentials come from <code>TIA_DEMO_USER</code> and{" "}
            <code>TIA_DEMO_PASSWORD</code>. If neither is set, the server generates a
            password at startup and prints it once to its own log — it is never shown by
            any endpoint.
          </p>
        </Card>
      </div>
    </div>
  );
}
