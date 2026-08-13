import { useCallback, useEffect, useState } from "react";
import { api, type RiskView as RiskData, type Strategy } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Bar, Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";

export function RiskView({ subscribe }: { subscribe: Subscribe }) {
  const [risk, setRisk] = useState<RiskData | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);

  const load = useCallback(() => {
    api.risk().then(setRisk).catch(() => undefined);
    api.strategies().then(setStrategies).catch(() => undefined);
  }, []);

  useEffect(load, [load]);
  useStreamEvent(subscribe, "decision.created", load);

  const blocked = Object.entries(risk?.blocked_by_check ?? {}).sort((a, b) => b[1] - a[1]);
  const maxBlocked = blocked.length > 0 ? blocked[0][1] : 1;
  const limits = risk?.limits ?? {};

  return (
    <>
      <h1>Risk</h1>
      <p className="section-note">
        The risk engine is deterministic and has absolute veto. It is not a language model,
        it never asks one, and nothing downstream can override it. It may only ever
        <em> shrink</em> a requested size — an engine that could grow one would be a second,
        unreviewed sizing model.
      </p>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <Stat label="Mode" value={<Pill value={risk?.mode ?? "unknown"} />}
            sub={risk?.kill_switch_reason || "no halt in effect"} />
        </div>
        <div className="card">
          <Stat label="Gross exposure" value={`${(risk?.gross_exposure_pct ?? 0).toFixed(1)}%`}
            sub={`limit ${limits.max_gross_exposure_pct ?? "—"}%`} />
        </div>
        <div className="card">
          <Stat label="Approved" value={risk?.approved_total ?? 0}
            sub={`${risk?.rejected_total ?? 0} rejected`} />
        </div>
        <div className="card">
          <Stat label="Reconciliations" value={risk?.reconciliations ?? 0}
            tone={(risk?.reconciliation_breaks ?? 0) > 0 ? "warn" : "flat"}
            sub={`${risk?.reconciliation_breaks ?? 0} breaks`} />
        </div>
      </div>

      <div className="grid cols-2">
        <Card title="Which gate is binding">
          {blocked.length === 0 ? (
            <Empty message="Nothing has been blocked yet." />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {blocked.map(([name, count]) => (
                <div key={name}>
                  <div className="row" style={{ justifyContent: "space-between", fontSize: 12 }}>
                    <span>{name}</span>
                    <span className="mono faint">{count}</span>
                  </div>
                  <Bar value={count} max={maxBlocked} tone="warn" />
                </div>
              ))}
              <p className="footnote" style={{ marginTop: 6, paddingTop: 8 }}>
                Counted by failed check name rather than by message text — the messages
                embed the actual numbers, so counting those would produce one bucket per
                bar and identify nothing.
              </p>
            </div>
          )}
        </Card>

        <Card title="Limits (read-only)">
          <div className="scroll">
            <table>
              <thead><tr><th>Limit</th><th className="num">Value</th></tr></thead>
              <tbody>
                {Object.entries(limits).map(([key, value]) => (
                  <tr key={key}>
                    <td className="faint">{key}</td>
                    <td className="num">{String(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="footnote" style={{ marginTop: 10, paddingTop: 8 }}>
            These cannot be edited from this interface, and there is no API route that
            changes them. Altering a risk limit is a code change that goes through review
            and backtesting — a UI that could loosen them at runtime would make every
            limit advisory.
          </p>
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card title="Strategies">
          <table>
            <thead>
              <tr><th>Strategy</th><th>Version</th><th>Enabled</th><th>Applies in</th><th>Description</th></tr>
            </thead>
            <tbody>
              {strategies.map((strategy) => (
                <tr key={strategy.id}>
                  <td>{strategy.id}</td>
                  <td className="faint">{strategy.version}</td>
                  <td>{strategy.enabled ? <Pill value="enabled" tone="ok" /> : <Pill value="off" />}</td>
                  <td className="faint">{strategy.applicable_regimes.join(", ") || "—"}</td>
                  <td className="faint" style={{ maxWidth: 320, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {strategy.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="footnote" style={{ marginTop: 10, paddingTop: 8 }}>
            Strategies are chosen when a run starts. Toggling one mid-run would change the
            experiment while it is being measured, which makes the result uninterpretable.
          </p>
        </Card>
      </div>
      <SimulationFootnote />
    </>
  );
}
