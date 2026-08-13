/**
 * The control bar: start, stop, pause, halt, reset.
 *
 * Two things it does deliberately.
 *
 * Destructive actions ask first. Reset destroys the run's entire history, and a button
 * that silently deletes a session's work is a button people learn to fear rather than
 * use. Same for the kill switch, which is the one control that stops everything.
 *
 * Leaving safe mode asks for a name. That name is recorded in the log. Halting is a
 * decision a machine may take; un-halting is not.
 */
import { useEffect, useState } from "react";
import { ApiError, api, type RuntimeSnapshot, type Scenario } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";

const CAPITAL_PRESETS = [10_000, 50_000, 100_000, 250_000];

export function Controls({
  runtime,
  onChanged,
  subscribe,
}: {
  runtime: RuntimeSnapshot | null;
  onChanged: () => void;
  subscribe: Subscribe;
}) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState("trend_up");
  const [capital, setCapital] = useState(100_000);
  const [speed, setSpeed] = useState(0.35);
  const [llmEnabled, setLlmEnabled] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState<"reset" | "kill" | null>(null);
  const [approver, setApprover] = useState("");

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => undefined);
  }, []);

  useStreamEvent(subscribe, "runtime.finished", onChanged);
  useStreamEvent(subscribe, "runtime.error", onChanged);
  useStreamEvent(subscribe, "runtime.kill_switch", onChanged);

  const state = runtime?.state ?? "stopped";
  const active = state === "running" || state === "paused";
  const halted = state === "halted" || runtime?.risk?.mode === "halted" ||
    runtime?.risk?.mode === "safe_mode";

  async function act(name: string, action: () => Promise<unknown>) {
    setBusy(name);
    setError("");
    try {
      await action();
      onChanged();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy("");
      setConfirming(null);
    }
  }

  const selected = scenarios.find((s) => s.id === scenario);

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {error && <div className="banner error">{error}</div>}

      {runtime?.last_error && (
        <div className="banner error">Runtime halted: {runtime.last_error}</div>
      )}

      {halted && (
        <div className="banner warn">
          <strong>Trading halted.</strong>{" "}
          {runtime?.risk?.kill_switch_reason || "The risk engine stopped new risk."}{" "}
          Releasing it requires naming who approved the release; the name is recorded.
          <div className="row" style={{ marginTop: 10 }}>
            <input
              className="mono"
              placeholder="your name or email"
              value={approver}
              onChange={(e) => setApprover(e.target.value)}
              style={{
                background: "var(--bg-input)",
                border: "1px solid var(--border-strong)",
                borderRadius: 7,
                padding: "6px 10px",
              }}
            />
            <button
              className="btn"
              disabled={!approver.trim() || busy !== ""}
              onClick={() => act("release", () => api.releaseKillSwitch(approver.trim()))}
            >
              Release halt
            </button>
          </div>
        </div>
      )}

      {!active ? (
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field" style={{ minWidth: 210 }}>
            Scenario
            <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </label>

          <label className="field" style={{ minWidth: 160 }}>
            Simulated capital
            <select value={capital} onChange={(e) => setCapital(Number(e.target.value))}>
              {CAPITAL_PRESETS.map((value) => (
                <option key={value} value={value}>
                  ${value.toLocaleString("en-US")}
                </option>
              ))}
            </select>
          </label>

          <label className="field" style={{ minWidth: 120 }}>
            Speed
            <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
              <option value={1}>1 bar / s</option>
              <option value={0.35}>3 bars / s</option>
              <option value={0.12}>8 bars / s</option>
              <option value={0.02}>Fast</option>
            </select>
          </label>

          <label className="checkbox">
            <input
              type="checkbox"
              checked={llmEnabled}
              onChange={(e) => setLlmEnabled(e.target.checked)}
            />
            AI context layer
          </label>

          <button
            className="btn primary"
            disabled={busy !== ""}
            onClick={() =>
              act("start", () =>
                api.start({
                  scenario,
                  symbols: ["BTC-USD"],
                  initial_capital: capital,
                  seed: 20260812,
                  bar_interval_seconds: speed,
                  strategies: ["trend_following", "mean_reversion", "breakout"],
                  llm_enabled: llmEnabled,
                  news_enabled: true,
                }),
              )
            }
          >
            {busy === "start" ? "Starting…" : "Start paper trading"}
          </button>

          {runtime?.run_id && (
            <button
              className="btn danger"
              disabled={busy !== ""}
              onClick={() => setConfirming("reset")}
            >
              Reset account
            </button>
          )}
        </div>
      ) : (
        <div className="row">
          <button
            className="btn"
            disabled={busy !== ""}
            onClick={() =>
              act("pause", () => (state === "paused" ? api.resume() : api.pause()))
            }
          >
            {state === "paused" ? "Resume strategies" : "Pause strategies"}
          </button>
          <button
            className="btn"
            disabled={busy !== "" || runtime?.risk?.new_trades_allowed === false}
            onClick={() => act("stopnew", () => api.stopNewTrades())}
          >
            Stop new trades
          </button>
          <button className="btn" disabled={busy !== ""} onClick={() => act("stop", () => api.stop())}>
            Stop run
          </button>
          <button className="btn danger" disabled={busy !== ""} onClick={() => setConfirming("kill")}>
            Kill switch
          </button>

          {runtime?.progress && (
            <div style={{ flex: 1, minWidth: 180 }}>
              <div className="row" style={{ justifyContent: "space-between", fontSize: 11 }}>
                <span className="faint">
                  {runtime.progress.bars_done} / {runtime.progress.bars_total} bars
                </span>
                <span className="faint">{runtime.progress.percent}%</span>
              </div>
              <div className="bar">
                <div style={{ width: `${runtime.progress.percent}%` }} />
              </div>
            </div>
          )}
        </div>
      )}

      {selected && !active && (
        <p className="section-note" style={{ marginTop: 12, marginBottom: 0 }}>
          <strong>{selected.title}.</strong> {selected.demonstrates}{" "}
          <span className="faint">Expected: {selected.expected_outcome}.</span>
          {(selected.injects_data_faults ||
            selected.injects_llm_failure ||
            selected.tightens_risk_limits) && (
            <span className="warn">
              {" "}
              This scenario injects a fault — producing few or no trades is the correct
              outcome, not a failure.
            </span>
          )}
        </p>
      )}

      {confirming && (
        <div className="drawer-backdrop" onClick={() => setConfirming(null)}>
          <div
            className="card"
            style={{ margin: "auto", maxWidth: 460 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2>{confirming === "reset" ? "Reset simulated account?" : "Engage kill switch?"}</h2>
            <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
              {confirming === "reset"
                ? "This deletes the current run and everything recorded for it — decisions, orders, fills, equity history. It cannot be undone. The simulated capital resets to the amount you select when you start the next run."
                : "This halts all new risk immediately. Open positions stay open and continue to be managed, but nothing new will be opened. Releasing it afterwards requires naming who approved the release."}
            </p>
            <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
              <button className="btn" onClick={() => setConfirming(null)}>
                Cancel
              </button>
              <button
                className="btn danger"
                disabled={busy !== ""}
                onClick={() =>
                  confirming === "reset"
                    ? act("reset", () => api.reset(capital))
                    : act("kill", () => api.killSwitch("operator engaged from dashboard"))
                }
              >
                {confirming === "reset" ? "Delete and reset" : "Halt trading"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
