/**
 * The AI view.
 *
 * The design decision here is what to put first. Most "AI trading" dashboards lead with
 * the model's opinion, which invites the reader to treat it as the decision. This one
 * leads with the constraint: the model's output is clamped to a channel that can only
 * reduce risk, and the number shown next to every assessment is what it *cost* the
 * position, never what it added.
 *
 * The rejection rate is given equal billing with the assessments themselves. A model whose
 * output is discarded 40% of the time is a fact about the system that a success-only panel
 * would never show.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type Assessment, type Decision, type RuntimeSnapshot } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";
import { clock, titleCase } from "../lib/format";

export function AiView({
  runtime,
  subscribe,
}: {
  runtime: RuntimeSnapshot | null;
  subscribe: Subscribe;
}) {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [selected, setSelected] = useState<Decision | null>(null);

  const load = useCallback(() => {
    api.assessments(60).then(setAssessments).catch(() => undefined);
    api.decisions(60).then(setDecisions).catch(() => undefined);
  }, []);

  useEffect(load, [load, runtime?.run_id]);

  useStreamEvent(subscribe, "ai.context_assessed", (data) =>
    setAssessments((previous) => [data as Assessment, ...previous].slice(0, 60)),
  );
  useStreamEvent(subscribe, "decision.created", (data) =>
    setDecisions((previous) => [data as Decision, ...previous].slice(0, 60)),
  );

  const ai = runtime?.ai;
  const total = (ai?.assessments ?? 0) + (ai?.neutral ?? 0);
  const rejectionRate = total > 0 ? ((ai?.neutral ?? 0) / total) * 100 : 0;
  const budget = (ai?.budget ?? {}) as Record<string, string | number>;

  return (
    <>
      <h1>AI decisions</h1>
      <p className="section-note">
        The language model contributes exactly one number: a <strong>caution</strong> level,
        converted to a modifier clamped to <code>[-1, 0]</code>. It can shrink a position or
        veto it. There is no field in its response schema that can create a trade, enlarge
        one, choose a direction, or override a risk limit — so a hallucination, a poisoned
        news item or a prompt injection can only ever cost trades that would otherwise have
        been taken.
      </p>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <Stat label="Provider" value={ai?.provider ?? "—"}
            sub={ai?.enabled ? "enabled" : "disabled for this run"} />
        </div>
        <div className="card">
          <Stat label="Assessments used" value={ai?.assessments ?? 0}
            sub={`${ai?.neutral ?? 0} degraded to neutral`} />
        </div>
        <div className="card">
          <Stat
            label="Discarded"
            value={`${rejectionRate.toFixed(0)}%`}
            tone={rejectionRate > 30 ? "warn" : "flat"}
            sub={`${ai?.rejections ?? 0} failed validation`}
          />
        </div>
        <div className="card">
          <Stat label="Circuit breaker" value={titleCase(String(budget.breaker ?? "closed"))}
            tone={budget.breaker === "open" ? "warn" : "flat"}
            sub={`$${Number(budget.cost_usd_today ?? 0).toFixed(3)} today`} />
        </div>
      </div>

      <div className="grid cols-2">
        <Card title="Context assessments">
          {assessments.length === 0 ? (
            <Empty message="No assessments yet." />
          ) : (
            <div className="scroll tall">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th className="num">Effect</th>
                    <th>Status</th>
                    <th>Reason / thesis</th>
                  </tr>
                </thead>
                <tbody>
                  {assessments.map((assessment) => (
                    <tr key={assessment.assessment_id + assessment.created_at}>
                      <td className="faint">{clock(assessment.created_at)}</td>
                      <td>{assessment.symbol}</td>
                      <td className={`num ${assessment.context_modifier < 0 ? "warn" : "faint"}`}>
                        {assessment.context_modifier.toFixed(3)}
                      </td>
                      <td>
                        {assessment.veto ? (
                          <Pill value="veto" tone="bad" />
                        ) : assessment.used ? (
                          <Pill value="applied" tone="ok" />
                        ) : (
                          <Pill value="neutral" />
                        )}
                      </td>
                      <td
                        className="faint"
                        style={{ maxWidth: 320, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                        title={assessment.used ? assessment.thesis : assessment.reason}
                      >
                        {assessment.used ? assessment.thesis : assessment.reason || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Decisions — click one for the full reasoning">
          {decisions.length === 0 ? (
            <Empty message="No decisions yet." />
          ) : (
            <div className="scroll tall">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Direction</th>
                    <th className="num">Base</th>
                    <th className="num">Final</th>
                    <th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.map((decision) => (
                    <tr
                      key={decision.decision_id}
                      className="clickable"
                      onClick={() => setSelected(decision)}
                    >
                      <td className="faint">{clock(decision.decided_at)}</td>
                      <td
                        className={
                          decision.direction === "long"
                            ? "pos"
                            : decision.direction === "short"
                              ? "neg"
                              : "faint"
                        }
                      >
                        {decision.direction}
                      </td>
                      <td className="num faint">{decision.base_confidence.toFixed(3)}</td>
                      <td className="num">{decision.confidence.toFixed(3)}</td>
                      <td><Pill value={decision.verdict} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {selected && <DecisionDrawer decision={selected} onClose={() => setSelected(null)} />}
      <SimulationFootnote />
    </>
  );
}

/**
 * The trade journal entry and the event trace, in one panel.
 *
 * It exists to answer exactly one question — "why did the system do that?" — and it is
 * laid out in the order the pipeline actually ran, so the answer reads as a sequence
 * rather than a pile of fields.
 */
export function DecisionDrawer({
  decision,
  onClose,
}: {
  decision: Decision;
  onClose: () => void;
}) {
  const failed = decision.risk_checks.filter((check) => !check.passed);
  const blocked = decision.verdict !== "approved" && decision.verdict !== "reduced_size";

  const steps = [
    {
      title: "Market data",
      state: "ok",
      detail: `${decision.symbol} @ ${String(decision.snapshot?.close ?? "—")} · quality ${decision.data_quality_score.toFixed(2)}`,
    },
    {
      title: "Features & regime",
      state: "ok",
      detail: `regime ${decision.regime} · feature hash ${decision.feature_hash?.slice(0, 12) ?? "—"}`,
    },
    {
      title: "Strategies & fusion",
      state: decision.direction === "no_trade" ? "skipped" : "ok",
      detail: `${decision.direction} at base confidence ${decision.base_confidence.toFixed(3)}`,
    },
    {
      title: "AI context",
      state: decision.context_veto ? "blocked" : decision.context_modifier < 0 ? "ok" : "skipped",
      detail: decision.context_used
        ? `modifier ${decision.context_modifier.toFixed(3)} → confidence ${decision.confidence.toFixed(3)}`
        : `no influence (${decision.context_reason || "neutral"})`,
    },
    {
      title: "Risk engine",
      state: blocked ? "blocked" : "ok",
      detail: blocked
        ? `${decision.verdict} — ${failed.map((c) => c.name).join(", ") || "no size approved"}`
        : `approved ${decision.approved_quantity.toFixed(6)}`,
    },
    {
      title: "Execution",
      state: blocked ? "skipped" : "ok",
      detail: blocked ? "no order was created" : "order intent submitted to the paper engine",
    },
  ];

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <h1 style={{ marginBottom: 2 }}>
              {decision.symbol} · {decision.direction}
            </h1>
            <span className="faint mono" style={{ fontSize: 12 }}>
              {decision.decided_at} · {decision.decision_id}
            </span>
          </div>
          <button className="btn small" onClick={onClose}>
            Close
          </button>
        </header>

        <h2>Why the system decided this</h2>
        <div className="trace">
          {steps.map((step) => (
            <div key={step.title} className={`trace-step ${step.state}`}>
              <div className="marker">
                <i />
                <span />
              </div>
              <div className="content">
                <strong>{step.title}</strong>
                <p>{step.detail}</p>
              </div>
            </div>
          ))}
        </div>

        {decision.why_enter.length > 0 && (
          <>
            <h2>Supporting</h2>
            <ul style={{ fontSize: 12.5, color: "var(--text-dim)", paddingLeft: 18 }}>
              {decision.why_enter.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </>
        )}

        {decision.why_not_enter.length > 0 && (
          <>
            <h2>Contradicting</h2>
            <ul style={{ fontSize: 12.5, color: "var(--warn)", paddingLeft: 18 }}>
              {decision.why_not_enter.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </>
        )}

        {decision.thesis && (
          <>
            <h2>AI thesis</h2>
            <p style={{ fontSize: 12.5, color: "var(--text-dim)" }}>{decision.thesis}</p>
          </>
        )}

        <h2>Risk checks</h2>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Check</th>
                <th>Result</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {decision.risk_checks.map((check) => (
                <tr key={check.name}>
                  <td>{check.name}</td>
                  <td className={check.passed ? "pos" : "neg"}>{check.passed ? "pass" : "fail"}</td>
                  <td className="faint">{check.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2>Features at decision time</h2>
        <dl className="kv">
          {Object.entries(decision.features)
            .slice(0, 18)
            .map(([key, value]) => (
              <div key={key} style={{ display: "contents" }}>
                <dt>{key}</dt>
                <dd>{typeof value === "number" ? value.toFixed(4) : String(value)}</dd>
              </div>
            ))}
        </dl>
      </div>
    </div>
  );
}
