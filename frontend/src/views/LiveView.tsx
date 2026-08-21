/**
 * The live activation page.
 *
 * The most important thing on this screen is the list of things that are wrong. A gate
 * that only showed a green button when everything passed would leave someone staring at a
 * disabled control with no idea what to do; this shows every check, its verdict, why it
 * exists, and the exact command that would fix it.
 *
 * The second most important thing is the custody statement, which is at the top rather
 * than in a footnote: someone about to connect their exchange account needs to know what
 * this system can and cannot do with it before they read anything else.
 */
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type ActivationAttempt, type GateReport, type Health } from "../lib/api";
import { Card, Empty, Pill, Stat } from "../components/ui";

type LiveSnapshot = Record<string, unknown> & { active: boolean; state: string };

export function LiveView({ role }: { role: string }) {
  const [report, setReport] = useState<GateReport | null>(null);
  const [history, setHistory] = useState<ActivationAttempt[]>([]);
  const [session, setSession] = useState<LiveSnapshot | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [sessionError, setSessionError] = useState("");

  const load = useCallback(() => {
    api.liveGate().then(setReport).catch(() => undefined);
    api.liveHistory().then(setHistory).catch(() => undefined);
    api.liveSnapshot().then(setSession).catch(() => undefined);
    api.health().then((h) => { setHealth(h); setOffline(false); }).catch(() => setOffline(true));
  }, []);

  useEffect(load, [load]);
  useEffect(() => {
    // The heartbeat is only meaningful if it visibly moves — and if the server stops
    // answering, this is what turns the banner red instead of leaving stale numbers up.
    const timer = setInterval(() => {
      api.liveSnapshot().then(setSession).catch(() => undefined);
      api.health().then((h) => { setHealth(h); setOffline(false); }).catch(() => setOffline(true));
    }, 10_000);
    return () => clearInterval(timer);
  }, []);

  const paperSession = async (action: "start" | "stop" | "resume") => {
    setSessionBusy(true);
    setSessionError("");
    try {
      if (action === "start") await api.paperStart();
      else if (action === "resume") await api.liveResume();
      else await api.liveStop();
    } catch (error) {
      setSessionError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setSessionBusy(false);
      load();
    }
  };

  const arm = async () => {
    setBusy(true);
    setResult(null);
    try {
      await api.armLive(confirmation);
      setResult({ ok: true, message: "Live trading armed." });
    } catch (error) {
      setResult({
        ok: false,
        message: error instanceof ApiError ? error.message : String(error),
      });
    } finally {
      setBusy(false);
      setConfirmation("");
      load();
    }
  };

  if (!report) {
    return (
      <>
        <h1>Live trading</h1>
        <Card>
          <Empty message="Loading…" />
        </Card>
      </>
    );
  }

  const failures = report.checks.filter((check) => !check.passed);
  const sessionActive = Boolean(session && session.active);
  // A session that stopped taking entries needs a way back that is not "restart the
  // process". The stop ladder had every rung except this one.
  const halted = sessionActive && ["halt_new_orders", "paused"].includes(String(session?.state));
  const armed = sessionActive && session?.mode === "live";
  const environment = armed
    ? report.environment.toUpperCase()
    : sessionActive
      ? "PAPER"
      : "PAPER (idle)";
  const riskState = health?.components?.risk_engine ?? "unknown";
  const reconCheck = report.checks.find((c) => c.name === "reconciliation_healthy");

  return (
    <>
      <h1>Live trading</h1>

      <div
        className="card"
        style={{
          marginBottom: 16,
          borderLeft: `4px solid ${offline ? "var(--bad, #c44)" : armed ? "var(--warn, #ca4)" : "var(--ok, #4a4)"}`,
        }}
      >
        <div className="grid cols-4" style={{ gap: 12 }}>
          <Stat label="Environment" value={<Pill value={environment} tone={armed ? "warn" : "ok"} />}
            sub={armed ? "REAL EXECUTION PATH" : "simulated fills only"} />
          <Stat label="System"
            value={<Pill value={offline ? "OFFLINE" : health?.status === "ok" ? "ONLINE" : "DEGRADED"}
              tone={offline ? "bad" : health?.status === "ok" ? "ok" : "warn"} />}
            sub={offline ? "the API stopped answering" : `uptime ${Math.floor((health?.uptime_seconds ?? 0) / 3600)}h`} />
          <Stat label="Readiness" value={`${report.total - report.failed} / ${report.total}`}
            tone={report.passed ? "flat" : "warn"} sub="activation checks passing" />
          <Stat label="Status"
            value={<Pill value={armed ? "ARMED" : "DISARMED"} tone={armed ? "warn" : "ok"} />}
            sub={armed ? "live session running" : "no real order can exist"} />
        </div>
        <div className="grid cols-3" style={{ gap: 12, marginTop: 10 }}>
          <Stat label="Risk"
            value={<Pill value={riskState === "online" ? "HEALTHY" : riskState.toUpperCase()}
              tone={riskState === "online" ? "ok" : riskState === "unknown" ? "" : "bad"} />}
            sub="absolute veto, not a suggestion" />
          <Stat label="Reconciliation"
            value={<Pill value={reconCheck ? (reconCheck.passed ? "HEALTHY" : "FAILED") : "UNKNOWN"}
              tone={reconCheck?.passed ? "ok" : "warn"} />}
            sub="our books vs the venue's" />
          <Stat label="Live capital" value={report.max_live_capital.toLocaleString()}
            tone={report.max_live_capital > 0 ? "warn" : "flat"}
            sub={report.max_live_capital > 0 ? "ceiling configured — still gated" : "0 — fails closed"} />
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16, borderLeft: "3px solid var(--accent, #58a)" }}>
        <strong>Your money stays at the exchange.</strong>
        <p style={{ margin: "8px 0 0", color: "var(--muted)" }}>{report.custody_note}</p>
        <ul style={{ margin: "10px 0 0", color: "var(--muted)" }}>
          <li>This application has no wallet and never receives a deposit.</li>
          <li>
            There is no withdrawal or transfer code path anywhere in it — a test fails the
            build if one is added.
          </li>
          <li>
            The API key you create must have withdrawals and transfers <em>disabled</em>.
            The system checks this against the exchange and refuses to trade with a key
            that can move funds.
          </li>
          <li>
            Nothing here guarantees a profit. A system in perfect health can lose money
            steadily, and passing every check below says only that the machinery works.
          </li>
        </ul>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <Stat
            label="Gate"
            value={<Pill value={report.passed ? "ready" : "refused"} tone={report.passed ? "ok" : "bad"} />}
            sub={`${report.total - report.failed} of ${report.total} checks pass`}
          />
        </div>
        <div className="card">
          <Stat
            label="Live path"
            value={<Pill value={report.live_enabled_in_config ? "enabled" : "disabled"} tone={report.live_enabled_in_config ? "warn" : ""} />}
            sub="in configuration"
          />
        </div>
        <div className="card">
          <Stat
            label="Capital ceiling"
            value={report.max_live_capital > 0 ? report.max_live_capital.toLocaleString() : "not set"}
            tone={report.max_live_capital > 0 ? "flat" : "warn"}
            sub="the most that may ever be at work"
          />
        </div>
        <div className="card">
          <Stat
            label="Activation lifetime"
            value={`${Math.round(report.ttl_seconds / 60)} min`}
            sub="then the gate runs again"
          />
        </div>
      </div>

      <Card title="24/7 paper session">
        <p style={{ marginTop: 0, color: "var(--muted)" }}>
          Real market data, simulated fills, no credentials — this is the session the
          paper track record accrues on. It resumes by itself after a crash or redeploy;
          an operator stop (or an engaged kill switch) stays stopped.
        </p>
        {session && session.active ? (
          <>
            <div className="grid cols-4" style={{ marginBottom: 12 }}>
              <Stat
                label="Mode"
                value={<Pill value={String(session.mode ?? "?")} tone={session.mode === "paper-live" ? "ok" : "warn"} />}
                sub={session.simulated ? "simulated fills" : "REAL EXECUTION"}
              />
              <Stat
                label="State"
                value={<Pill value={String(session.state)} tone={session.state === "running" ? "ok" : "warn"} />}
                sub="the state machine's word"
              />
              <Stat
                label="Engine heartbeat"
                value={`${Number(session.heartbeat_age_seconds ?? 0).toFixed(0)} s ago`}
                tone={Number(session.heartbeat_age_seconds ?? 0) > 120 ? "warn" : "flat"}
                sub="HTTP answering is not this"
              />
              <Stat
                label="Last market data"
                value={`${Number(session.market_data_age_seconds ?? 0).toFixed(0)} s ago`}
                tone={Number(session.market_data_age_seconds ?? 0) > 300 ? "warn" : "flat"}
                sub="stale data halts new entries"
              />
            </div>
            {role === "operator" && halted && (
              <button
                onClick={() => paperSession("resume")}
                disabled={sessionBusy}
                title="Lifts the halt and lets the session take entries again"
                style={{
                  marginRight: 10,
                  background: "var(--ok, #1e8e4e)",
                  color: "#fff",
                  fontWeight: 600,
                  border: "none",
                  padding: "10px 18px",
                  borderRadius: 6,
                }}
              >
                {sessionBusy ? "Resuming…" : "▶  Resume entries"}
              </button>
            )}
            {role === "operator" && (
              <button
                onClick={() => {
                  if (window.confirm(
                    "Stop the 24/7 paper session?\n\nIt will STAY stopped across restarts " +
                    "until you start it again, and it stops accruing the paper track record " +
                    "while stopped."
                  )) paperSession("stop");
                }}
                disabled={sessionBusy}
                style={{
                  background: "var(--bad, #c0392b)",
                  color: "#fff",
                  fontWeight: 600,
                  border: "none",
                  padding: "10px 18px",
                  borderRadius: 6,
                }}
              >
                {sessionBusy ? "Stopping…" : "⏹  Stop the 24/7 session"}
              </button>
            )}
          </>
        ) : (
          <>
            <Empty message="No realtime session is running." />
            {role === "operator" && (
              <button
                onClick={() => paperSession("start")}
                disabled={sessionBusy}
                style={{
                  marginTop: 8,
                  background: "var(--ok, #1e8e4e)",
                  color: "#fff",
                  fontWeight: 600,
                  border: "none",
                  padding: "10px 18px",
                  borderRadius: 6,
                }}
              >
                {sessionBusy ? "Starting…" : "▶  Start the 24/7 paper session"}
              </button>
            )}
          </>
        )}
        {sessionError && (
          <div className="card" style={{ marginTop: 12, borderLeft: "3px solid var(--bad, #c44)" }}>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{sessionError}</pre>
          </div>
        )}
      </Card>

      <Card title={`Activation checks — ${failures.length} blocking`}>
        <p style={{ marginTop: 0, color: "var(--muted)" }}>
          Every check must pass. A check that reports nothing counts as failed, never as
          neutral — the most dangerous check is the one nobody wired up.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {report.checks.map((check) => (
            <div
              key={check.name}
              className="card"
              style={{ padding: 12, borderLeft: `3px solid ${check.passed ? "var(--ok, #4a4)" : "var(--bad, #c44)"}` }}
            >
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                <strong className="mono">{check.name}</strong>
                <Pill
                  value={check.passed ? "pass" : check.reported ? "fail" : "not reported"}
                  tone={check.passed ? "ok" : "bad"}
                />
              </div>
              <div style={{ color: check.passed ? "var(--muted)" : "inherit" }}>{check.detail}</div>
              {check.remedy && (
                <div className="mono" style={{ marginTop: 6, fontSize: "0.9em" }}>
                  → {check.remedy}
                </div>
              )}
              <p className="footnote" style={{ margin: "6px 0 0" }}>{check.rationale}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Arm live trading">
        {!report.passed ? (
          <Empty message="Blocked. Resolve every failing check above first — this control does nothing until they all pass." />
        ) : role !== "operator" ? (
          <Empty message="Only an operator may arm live trading." />
        ) : (
          <>
            <p style={{ marginTop: 0 }}>
              Type the phrase below exactly. It is long on purpose: a confirmation that can
              be produced by hitting Enter is not a confirmation.
            </p>
            <p className="mono" style={{ userSelect: "all" }}>{report.confirmation_phrase}</p>
            <div className="row" style={{ gap: 8, marginTop: 12 }}>
              <input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder="Type the confirmation phrase"
                style={{ flex: 1 }}
                aria-label="Confirmation phrase"
              />
              <button onClick={arm} disabled={busy || !confirmation.trim()}>
                {busy ? "Checking…" : "Arm"}
              </button>
            </div>
          </>
        )}
        {result && (
          <div
            className="card"
            style={{
              marginTop: 12,
              borderLeft: `3px solid ${result.ok ? "var(--ok, #4a4)" : "var(--bad, #c44)"}`,
            }}
          >
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{result.message}</pre>
          </div>
        )}
      </Card>

      <Card title="Connecting your exchange account">
        <p style={{ marginTop: 0 }}>
          Credentials are never entered here. There is no field for them on this page and no
          endpoint that accepts them — a secret sent through a browser passes through a
          request log, a proxy and the page&rsquo;s memory on the way. They are read from
          the server&rsquo;s own environment.
        </p>
        <ol style={{ color: "var(--muted)" }}>
          <li>
            In Binance, open <strong>Account → API Management</strong> and create an API key.
          </li>
          <li>
            Enable only <strong>Reading</strong> and <strong>Spot &amp; Margin Trading</strong>.
            Leave <strong>Withdrawals</strong>, <strong>Internal Transfer</strong>,{" "}
            <strong>Universal Transfer</strong>, <strong>Futures</strong> and{" "}
            <strong>Margin</strong> disabled.
          </li>
          <li>Restrict the key to this server&rsquo;s IP address.</li>
          <li>
            Put the key and secret in the server&rsquo;s <span className="mono">.env</span> as{" "}
            <span className="mono">TIA_LIVE__BINANCE_API_KEY</span> and{" "}
            <span className="mono">TIA_LIVE__BINANCE_API_SECRET</span>, then restart.
          </li>
          <li>
            Run <span className="mono">python scripts/validate_binance.py --account</span> to
            confirm the adapter&rsquo;s assumptions against the real exchange.
          </li>
        </ol>
        <p className="footnote">
          Never share the secret with anyone, including an AI assistant. If you paste it
          somewhere by accident, delete the key in Binance immediately and create a new one —
          that is the whole remedy and it takes thirty seconds.
        </p>
      </Card>

      <Card title="Activation history">
        {history.length === 0 ? (
          <Empty message="No arming attempt has ever been made. When one happens — pass or fail — it appears here with what decided it." />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Operator</th>
                <th>Gate</th>
                <th>Runtime</th>
                <th>Blocking checks</th>
              </tr>
            </thead>
            <tbody>
              {history.map((attempt) => (
                <tr key={attempt.attempt_id}>
                  <td className="mono">{new Date(attempt.attempted_at).toLocaleString()}</td>
                  <td>{attempt.operator}</td>
                  <td>
                    <Pill value={attempt.passed ? "passed" : "refused"}
                      tone={attempt.passed ? "ok" : "bad"} />
                  </td>
                  <td>
                    <Pill
                      value={attempt.runtime_started ? "running" : attempt.runtime_state || "not started"}
                      tone={attempt.runtime_started ? "ok" : ""}
                    />
                  </td>
                  <td className="mono" style={{ fontSize: "0.85em" }}>
                    {attempt.failed_checks.slice(0, 4).join(", ")}
                    {attempt.failed_checks.length > 4 && ` +${attempt.failed_checks.length - 4}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="footnote">
          Every attempt is recorded, pass or fail — the audit question this answers is
          &ldquo;who tried to turn it on, when, and what stopped them?&rdquo;, which matters
          most exactly when the answer is embarrassing.
        </p>
      </Card>

      {report.venue_validation && (
        <Card title="Last validated against the exchange">
          <pre style={{ margin: 0, overflowX: "auto" }}>
            {JSON.stringify(report.venue_validation, null, 2)}
          </pre>
        </Card>
      )}
    </>
  );
}
