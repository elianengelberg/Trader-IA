/**
 * What the system has learned from its own closed trades.
 *
 * The Expected Value engine already learns silently — it revises a bucket's edge down after
 * a bad trade and refuses buckets it has no evidence for. This page makes that legible: for
 * every closed round trip it shows what the system *expected* against what it *got*, files
 * the gap as a categorised lesson, and — on the live session — raises the bar for exactly
 * the patterns that have recently disappointed. It can only ever make the system more
 * cautious; nothing here talks it into a trade.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type LearningReport, type MentorReport } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";
import { bpsUsd, clock, money, titleCase } from "../lib/format";

const CATEGORY: Record<string, { label: string; tone: string }> = {
  edge_confirmed: { label: "Confirmed", tone: "ok" },
  unexpected_loss: { label: "Unexpected loss", tone: "bad" },
  edge_overestimated: { label: "Overestimated", tone: "warn" },
  edge_underestimated: { label: "Underestimated", tone: "info" },
  exploration: { label: "Exploration", tone: "info" },
};


export function Learning({ subscribe }: { subscribe: Subscribe }) {
  const [data, setData] = useState<LearningReport | null>(null);
  const [mentor, setMentor] = useState<MentorReport | null>(null);
  const [applying, setApplying] = useState("");
  const [applyError, setApplyError] = useState("");

  const load = useCallback(() => {
    api.learning().then(setData).catch(() => undefined);
    api.mentor().then(setMentor).catch(() => undefined);
  }, []);

  useEffect(load, [load]);
  useStreamEvent(subscribe, "trade.closed", load);
  useStreamEvent(subscribe, "live.evidence_absorbed", load);

  // The learning record also grows without browser events — training simulations write
  // straight to the database and load on an engine restart — so the page keeps itself
  // current instead of waiting for a manual reload. Hidden tabs skip the fetch.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (!document.hidden) load();
    }, 10_000);
    return () => window.clearInterval(id);
  }, [load]);

  const applyProposal = useCallback(
    async (proposalId: string) => {
      setApplying(proposalId);
      setApplyError("");
      try {
        await api.mentorApply(proposalId);
        load();
      } catch (error) {
        setApplyError(error instanceof Error ? error.message : "could not apply");
      } finally {
        setApplying("");
      }
    },
    [load],
  );

  if (!data?.available) {
    return (
      <>
        <h1>Learning</h1>
        <p className="section-note">
          The system learns from its own closed trades: every round trip is scored against
          the edge it was taken on, and recurring disappointments make it warier of that
          exact setup. Nothing here is an opinion scraped from the internet — it is the
          system&apos;s own track record, read back to it.
        </p>
        <Card>
          <Empty message={data?.reason ?? "Loading…"} />
        </Card>
      </>
    );
  }

  const acts = Boolean(data.applies_guardrails);
  const meanErr = data.mean_calibration_error_bps ?? 0;
  // The engine learns in basis points (they compare trades of any size); the page speaks
  // dollars, converted at this session's typical trade size — or per row where the trade's
  // own size is on record.
  const notional = data.typical_notional_usd ?? 0;
  const rowUsd = (bps: number, rowNotional?: number) =>
    bpsUsd(bps, rowNotional && rowNotional > 0 ? rowNotional : notional);
  const evidence = data.evidence;
  const categories = data.category_counts ?? {};
  const guardrails = data.active_guardrails ?? [];
  const patterns = data.patterns ?? [];
  const lessons = data.recent_lessons ?? [];

  return (
    <>
      <h1>Learning</h1>
      <p className="section-note">
        Every closed trade is judged against the edge it was taken on. On the 24/7 paper
        session the lessons <strong>act</strong>: a pattern that has recently lost money or
        overstated its edge must clear a higher threshold before the system re-enters it —
        and the penalty eases on its own as the pattern comes back in line. The system only
        ever grows more cautious from what it learns; it never talks itself into a trade.
      </p>

      <div
        className="card"
        style={{
          marginBottom: 16,
          borderLeft: `3px solid var(--${acts ? "accent" : "border-strong"})`,
        }}
      >
        <div className="row" style={{ justifyContent: "space-between" }}>
          <strong>
            {acts
              ? "Live session — the lessons are tightening risk."
              : "Demo run — lessons are being read, but not acted on."}
          </strong>
          <Pill value={data.source ?? "unknown"} tone={acts ? "ok" : ""} />
        </div>
        <p style={{ margin: "8px 0 0", color: "var(--text-dim)", fontSize: 13 }}>
          {acts
            ? `The guardrails below have refused ${data.guardrail_rejected ?? 0} trade(s) so far in this session.`
            : "The demo explores every bucket to produce evidence; the live session is where these lessons actually gate trades."}
        </p>
        {acts && (
          <p style={{ margin: "6px 0 0", color: "var(--text-faint)", fontSize: 12 }}>
            {evidence && evidence.absorbed_since_start > 0
              ? `Evidence is current: ${evidence.absorbed_since_start.toLocaleString("en-US")} ` +
                `trades from finished training runs were folded in without a restart` +
                (evidence.last_absorbed_at ? `, most recently at ${clock(evidence.last_absorbed_at)}` : "") +
                `. ${evidence.buckets_ready} bucket(s) are at the evidence floor.`
              : "The session checks the trade store every minute and folds in anything new " +
                "on its own — a training batch that finishes overnight appears here without " +
                "a restart."}
          </p>
        )}
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <Stat label="Trades reviewed" value={String(data.reviews ?? 0)}
            sub={`${data.wins ?? 0} up · ${data.losses ?? 0} down`} />
        </div>
        <div className="card">
          <Stat label="Win rate" value={`${((data.win_rate ?? 0) * 100).toFixed(0)}%`}
            tone={(data.win_rate ?? 0) >= 0.5 ? "pos" : "neg"} sub="of closed round trips" />
        </div>
        <div className="card">
          <Stat
            label="Mean calibration error"
            value={bpsUsd(meanErr, notional)}
            tone={meanErr >= -3 ? "flat" : "neg"}
            sub="got minus expected, per trade"
          />
        </div>
        <div className="card">
          <Stat label="Patterns being guarded" value={String(guardrails.length)}
            tone={guardrails.length > 0 ? "warn" : "flat"}
            sub={`${data.concerns ?? 0} concerning trades`} />
        </div>
      </div>

      {notional > 0 && (
        <p className="footnote" style={{ marginTop: -6, marginBottom: 16 }}>
          Dollar figures are per trade, at this session&apos;s typical trade size of ≈$
          {money(notional, 0)} (simulated money).
        </p>
      )}

      {Object.keys(categories).length > 0 && (
        <Card title="What the lessons were">
          <div className="grid cols-4">
            {Object.entries(categories).map(([key, count]) => (
              <Stat
                key={key}
                label={CATEGORY[key]?.label ?? titleCase(key)}
                value={String(count)}
                tone={
                  key === "unexpected_loss"
                    ? "neg"
                    : key === "edge_confirmed"
                      ? "pos"
                      : "flat"
                }
              />
            ))}
          </div>
        </Card>
      )}

      {guardrails.length > 0 && (
        <Card title="Active guardrails — where the system is now warier">
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Pattern</th>
                  <th className="num">Extra profit demanded</th>
                  <th className="num">Size</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {guardrails.map((g) => (
                  <tr key={g.pattern}>
                    <td className="mono">{g.pattern}</td>
                    <td className="num mono" style={{ color: "var(--neg)" }}>
                      {bpsUsd(g.threshold_add_bps, notional)}
                    </td>
                    <td className="num mono">×{g.size_multiplier.toFixed(2)}</td>
                    <td style={{ color: "var(--text-dim)", fontSize: 12 }}>{g.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="footnote">
            A guardrail can only refuse a trade the rest of the pipeline would have taken. It
            is recomputed from recent trades every time, so it disappears on its own once the
            pattern behaves again — there is no penalty to reset by hand.
          </p>
        </Card>
      )}

      {mentor?.available && (mentor.proposals?.length || mentor.applied?.length) ? (
        <Card title="Mentor — proposed adjustments, validated by replay">
          <p style={{ marginTop: 0, fontSize: 12.5, color: "var(--text-dim)" }}>
            The Mentor only ever proposes <strong>tighter</strong> risk, and every proposal
            is validated by replaying the recorded trades under the proposed rule — the
            arithmetic decides, and a proposal the replay cannot justify is shown rejected.
            Nothing is applied without your explicit click.
          </p>
          {applyError && (
            <p style={{ color: "var(--neg)", fontSize: 12.5 }}>{applyError}</p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {(mentor.proposals ?? []).map((p) => (
              <div
                key={p.proposal_id}
                className="card"
                style={{
                  borderLeft: `3px solid var(--${p.status === "validated" ? "accent" : "border-strong"})`,
                }}
              >
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong style={{ fontSize: 13.5 }}>{p.title}</strong>
                  <div className="row" style={{ gap: 8 }}>
                    {p.applies === "next_session" && <Pill value="next session" />}
                    <Pill
                      value={p.status}
                      tone={p.status === "validated" ? "ok" : "bad"}
                    />
                  </div>
                </div>
                <p style={{ margin: "8px 0 0", fontSize: 12.5 }}>{p.rationale}</p>
                <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--text-dim)" }}>
                  <strong>Replay:</strong> {p.validation.detail}
                </p>
                {p.status === "validated" && p.in_effect && (
                  <p style={{ margin: "10px 0 0", fontSize: 12, color: "var(--text-faint)" }}>
                    Already in effect — the session is not taking new entries. Applying it
                    again would change nothing; lift the halt from Live Trading first.
                  </p>
                )}
                {p.status === "validated" && !p.in_effect && (
                  <div className="row" style={{ marginTop: 10 }}>
                    <button
                      className="btn small primary"
                      disabled={applying === p.proposal_id}
                      onClick={() => applyProposal(p.proposal_id)}
                    >
                      {applying === p.proposal_id ? "Applying…" : "Apply (tightens risk)"}
                    </button>
                    <span style={{ fontSize: 11.5, color: "var(--text-faint)" }}>
                      est. {bpsUsd(p.validation.delta_bps, notional)} per trade over{" "}
                      {p.validation.trades_affected} trades
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
          {(mentor.applied ?? []).length > 0 && (
            <p className="footnote" style={{ marginTop: 12 }}>
              Applied this session:{" "}
              {(mentor.applied ?? [])
                .map((a) => `${a.title} (${a.actor})`)
                .join(" · ")}
            </p>
          )}
        </Card>
      ) : mentor?.available ? (
        <Card title="Mentor — proposed adjustments, validated by replay">
          <Empty message="No proposals. The record does not currently justify tightening anything — that is the Mentor saying the system is behaving." />
        </Card>
      ) : null}

      <Card title="Recent lessons">
        {lessons.length === 0 ? (
          <Empty message="No closed trades yet. Lessons appear here as round trips close." />
        ) : (
          <div className="scroll tall">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Lesson</th>
                  <th>Verdict</th>
                  <th className="num">Expected</th>
                  <th className="num">Realised</th>
                  <th className="num">Miss</th>
                </tr>
              </thead>
              <tbody>
                {lessons.map((l) => (
                  <tr key={`${l.signal_id}-${l.closed_at}`}>
                    <td className="mono" style={{ whiteSpace: "nowrap" }}>{clock(l.closed_at)}</td>
                    <td>
                      {l.headline}
                      {l.cost_overrun && (
                        <span style={{ color: "var(--warn, #c90)", marginLeft: 6, fontSize: 11 }}>
                          · fees over budget
                        </span>
                      )}
                    </td>
                    <td>
                      <Pill
                        value={CATEGORY[l.category]?.label ?? l.category}
                        tone={CATEGORY[l.category]?.tone ?? ""}
                      />
                    </td>
                    <td className="num mono">{rowUsd(l.expected_net_bps, l.notional_usd)}</td>
                    <td className="num mono" style={{ color: l.is_win ? "var(--pos)" : "var(--neg)" }}>
                      {rowUsd(l.realised_net_bps, l.notional_usd)}
                    </td>
                    <td className="num mono" style={{ color: l.calibration_error_bps < 0 ? "var(--neg)" : "var(--text-dim)" }}>
                      {rowUsd(l.calibration_error_bps, l.notional_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {patterns.length > 0 && (
        <Card title="Every pattern seen — worst calibration first">
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Pattern</th>
                  <th className="num">Trades</th>
                  <th className="num">Win rate</th>
                  <th className="num">Mean miss</th>
                  <th>Last lesson</th>
                </tr>
              </thead>
              <tbody>
                {patterns.map((p) => (
                  <tr key={p.pattern}>
                    <td className="mono">{p.pattern}</td>
                    <td className="num mono">{p.reviews}</td>
                    <td className="num mono">{(p.win_rate * 100).toFixed(0)}%</td>
                    <td className="num mono" style={{ color: p.mean_error_bps < -3 ? "var(--neg)" : "var(--text-dim)" }}>
                      {bpsUsd(p.mean_error_bps, notional)}
                    </td>
                    <td style={{ color: "var(--text-dim)", fontSize: 12 }}>{p.last_headline}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <p className="footnote">{data.explanation}</p>
      <SimulationFootnote />
    </>
  );
}
