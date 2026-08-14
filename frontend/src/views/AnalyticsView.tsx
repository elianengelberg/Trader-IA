/**
 * Probability of ruin, and the sizing that follows from it.
 *
 * This page exists because a positive expectancy is not protection. Betting too much of a
 * winning edge goes bankrupt with probability approaching one, and nothing on a P&L chart
 * warns about it. The number here is the one that does.
 *
 * It refuses to show anything below two closed trades, and warns below thirty. A ruin
 * probability computed from four round trips is a precise-looking figure in front of
 * someone deciding how much to risk, which is worse than no figure at all.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type Analytics } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Bar, Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";

export function AnalyticsView({ subscribe }: { subscribe: Subscribe }) {
  const [data, setData] = useState<Analytics | null>(null);

  const load = useCallback(() => {
    api.analytics().then(setData).catch(() => undefined);
  }, []);

  useEffect(load, [load]);
  useStreamEvent(subscribe, "trade.closed", load);

  if (!data?.available) {
    return (
      <>
        <h1>Analytics</h1>
        <p className="section-note">
          A strategy with a positive expectancy still goes bankrupt if it bets too much.
          That is the single most common way a correct edge produces a zero balance, and no
          Sharpe ratio warns about it.
        </p>
        <Card>
          <Empty message={data?.reason ?? "Loading…"} />
        </Card>
      </>
    );
  }

  const ruin = data.ruin!;
  const safe = data.max_safe_risk_fraction;

  return (
    <>
      <h1>Analytics</h1>
      <p className="section-note">
        Two estimates, deliberately both: a closed form for fixed-fractional betting, and a
        Monte Carlo that resamples the actual trade distribution. When they disagree, trust
        the simulation — real trade returns are neither normal nor independent enough for
        the closed form to be exact. Every run is seeded, because a risk number that changes
        each time you look at it is not a risk number.
      </p>

      {data.sample_warning && (
        <div className="card" style={{ marginBottom: 16, borderLeft: "3px solid var(--warn, #c90)" }}>
          <strong>Too few samples to mean much.</strong>
          <p style={{ margin: "8px 0 0", color: "var(--muted)" }}>{data.sample_warning}</p>
        </div>
      )}

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <Stat
            label="Probability of ruin"
            value={`${(ruin.probability_of_ruin * 100).toFixed(2)}%`}
            tone={ruin.acceptable ? "pos" : "neg"}
            sub={`equity below ${(ruin.ruin_threshold * 100).toFixed(0)}% of start`}
          />
        </div>
        <div className="card">
          <Stat
            label="Analytic cross-check"
            value={
              ruin.analytic_probability === null
                ? "n/a"
                : `${(ruin.analytic_probability * 100).toFixed(2)}%`
            }
            sub="closed form, fixed-fractional"
          />
        </div>
        <div className="card">
          <Stat
            label="Max safe risk / trade"
            value={safe === null || safe === undefined ? "none" : `${safe.toFixed(2)}%`}
            tone={safe === null || safe === undefined ? "neg" : "flat"}
            sub="ruin stays under 1%"
          />
        </div>
        <div className="card">
          <Stat
            label="Verdict"
            value={<Pill value={ruin.acceptable ? "acceptable" : "too risky"} tone={ruin.acceptable ? "ok" : "bad"} />}
            sub={`${data.closed_trades} closed trades`}
          />
        </div>
      </div>

      <div className="grid cols-2">
        <Card title="What the simulation produced">
          <p style={{ marginTop: 0 }}>{data.explanation}</p>
          <div className="grid cols-2" style={{ marginTop: 12 }}>
            <Stat
              label="Median worst drawdown"
              value={`${ruin.median_max_drawdown_pct.toFixed(1)}%`}
            />
            <Stat
              label="Worst observed"
              value={`${ruin.worst_max_drawdown_pct.toFixed(1)}%`}
              tone="warn"
            />
            <Stat
              label="5th-percentile outcome"
              value={`${ruin.equity_5th_percentile.toFixed(2)}×`}
              sub="of starting equity"
            />
            <Stat
              label="Median outcome"
              value={`${ruin.median_final_equity.toFixed(2)}×`}
              sub="of starting equity"
            />
          </div>
          <p className="footnote" style={{ marginTop: 12 }}>
            {ruin.paths.toLocaleString()} paths over {ruin.horizon_trades} trades, seed{" "}
            {ruin.seed}. Same inputs and same seed give the same answer every time.
          </p>
        </Card>

        <Card title="Where this estimate is optimistic">
          <p style={{ marginTop: 0 }}>
            The bootstrap samples past trades <em>with replacement</em>, which assumes they
            are exchangeable. That assumption is wrong when returns are autocorrelated, and
            it is wrong in the flattering direction: resampling breaks up losing streaks,
            and losing streaks are what actually empty accounts.
          </p>
          <div className="grid cols-2" style={{ marginTop: 12 }}>
            <Stat
              label="Longest simulated losing streak"
              value={ruin.longest_losing_streak}
              sub="across all paths"
            />
            <Stat label="Ruin threshold" value={`${(ruin.ruin_threshold * 100).toFixed(0)}%`}
              sub="not zero — a halved account needs a 100% gain to recover" />
          </div>
          <p className="footnote" style={{ marginTop: 12 }}>
            Reported rather than hidden, so the optimism is visible instead of living in a
            docstring. If the real strategy strings losses together more tightly than the
            bootstrap does, the true ruin probability is higher than the number above.
          </p>
        </Card>
      </div>

      {data.profile && (
        <Card title="Active risk profile">
          <div className="grid cols-4">
            {Object.entries(data.profile)
              .filter(([key]) => key !== "name")
              .map(([key, value]) => (
                <Stat
                  key={key}
                  label={key.replace(/_/g, " ")}
                  value={typeof value === "number" ? value.toString() : String(value)}
                />
              ))}
          </div>
          <p className="footnote">
            Profiles scale every parameter together. A &ldquo;conservative&rdquo; profile
            with a conservative position size and an aggressive drawdown tolerance is a
            labelling bug, and labelling bugs in risk parameters are the expensive kind —
            so the three profiles are asserted to be ordered on every dimension.
          </p>
        </Card>
      )}

      <div style={{ marginTop: 16 }}>
        <Bar value={ruin.probability_of_ruin * 100} max={100} tone={ruin.acceptable ? "" : "warn"} />
      </div>

      <SimulationFootnote />
    </>
  );
}
