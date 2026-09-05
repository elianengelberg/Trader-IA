import { useEffect, useState } from "react";
import { api, type Health, type RuntimeSnapshot, type SecurityPosture } from "../lib/api";
import { Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";

/**
 * What protects this deployment, as facts with remedies. The server judges; this page
 * only reads. Nothing here is a secret — the password appears as a strength verdict.
 */
function SecurityPanel() {
  const [posture, setPosture] = useState<SecurityPosture | null>(null);
  useEffect(() => {
    api.securityPosture().then(setPosture).catch(() => undefined);
  }, []);
  if (!posture) return null;
  return (
    <Card
      title="Security posture"
      actions={<Pill value={`${posture.passed}/${posture.total}`} tone={posture.passed === posture.total ? "ok" : "warn"} />}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {posture.checks.map((check) => (
          <div key={check.key} className="row" style={{ alignItems: "flex-start", gap: 12 }}>
            <Pill value={check.ok ? "ok" : "fix"} tone={check.ok ? "ok" : "warn"} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{check.title}</div>
              <div className="faint" style={{ fontSize: 12, lineHeight: 1.5 }}>{check.detail}</div>
              {check.remedy && (
                <div style={{ fontSize: 12, color: "var(--warn, #c90)", marginTop: 2 }}>→ {check.remedy}</div>
              )}
            </div>
          </div>
        ))}
      </div>
      <p className="footnote" style={{ marginTop: 12 }}>
        Sessions last {posture.session_hours} hours. This page was served over {posture.scheme.toUpperCase()}.
      </p>
    </Card>
  );
}

const DESCRIPTIONS: Record<string, string> = {
  database: "SQLite by default; stores every decision, order, fill and equity point.",
  market_data: "The scenario generator. Seeded, offline, reproducible.",
  paper_execution: "Bar-based matching engine. The only execution provider that exists.",
  risk_engine: "Deterministic gate with absolute veto. Degraded means halted or in safe mode.",
  llm: "Context layer. Offline means its circuit breaker is open — trading continues without it.",
  backtest_engine: "Runs on demand against the committed fixtures.",
  event_stream: "Server-sent events to this browser.",
  news: "Scenario-generated headlines, not a news provider.",
};

export function SystemView({
  health,
  runtime,
}: {
  health: Health | null;
  runtime: RuntimeSnapshot | null;
}) {
  const counters = runtime?.counters ?? {};

  return (
    <>
      <h1>System</h1>
      <p className="section-note">
        Component health, as reported by the server rather than inferred by this page. An
        &ldquo;unknown&rdquo; means no run has exercised that component yet — it is not an
        error, and it is not shown as one.
      </p>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        {Object.entries(health?.components ?? {}).map(([name, state]) => (
          <div className="card" key={name}>
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
              <strong style={{ fontSize: 13 }}>{name.replace(/_/g, " ")}</strong>
              <Pill value={state} />
            </div>
            <p className="faint" style={{ fontSize: 11.5, margin: 0, lineHeight: 1.5 }}>
              {DESCRIPTIONS[name] ?? ""}
            </p>
          </div>
        ))}
      </div>

      <div className="grid cols-2">
        <SecurityPanel />
        <Card title="Runtime counters">
          {Object.keys(counters).length === 0 ? (
            <Empty message="No run active." />
          ) : (
            <div className="grid cols-3" style={{ gap: 12 }}>
              {Object.entries(counters).map(([name, value]) => (
                <Stat key={name} label={name.replace(/_/g, " ")} value={value} />
              ))}
            </div>
          )}
        </Card>

        <Card title="Process">
          <div className="grid cols-2" style={{ gap: 12 }}>
            <Stat label="Version" value={health?.version ?? "—"} />
            <Stat label="Uptime" value={`${Math.floor((health?.uptime_seconds ?? 0) / 60)}m`} />
            <Stat label="Status" value={<Pill value={health?.status ?? "unknown"} />} />
            <Stat label="Mode" value="paper (simulated)" />
          </div>
          {health?.degraded && health.degraded.length > 0 && (
            <div className="banner warn" style={{ marginTop: 14, marginBottom: 0 }}>
              Degraded: {health.degraded.join(", ")}
            </div>
          )}
          {runtime?.run_id && (
            <p className="footnote" style={{ marginTop: 14, paddingTop: 10 }}>
              Run <span className="mono">{runtime.run_id}</span> · scenario{" "}
              {runtime.scenario?.id} · seed is fixed, so this run can be reproduced exactly.
            </p>
          )}
        </Card>
      </div>
      <SimulationFootnote />
    </>
  );
}
