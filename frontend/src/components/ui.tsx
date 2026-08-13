/** Small shared pieces. Nothing here knows about trading; they render values. */
import type { ReactNode } from "react";
import { money, signedMoney, signedPct, titleCase, toneOf } from "../lib/format";

export function Card({
  title,
  children,
  actions,
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="card">
      {title && (
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "pos" | "neg" | "flat" | "warn";
}) {
  return (
    <div className="stat">
      <span className="label">{label}</span>
      <span className={`value ${tone ?? ""}`}>{value}</span>
      {sub !== undefined && <span className="sub">{sub}</span>}
    </div>
  );
}

export function MoneyStat({
  label,
  value,
  signed = false,
  sub,
}: {
  label: string;
  value: number;
  signed?: boolean;
  sub?: ReactNode;
}) {
  return (
    <Stat
      label={label}
      value={signed ? signedMoney(value) : money(value)}
      tone={signed ? (toneOf(value) as "pos" | "neg" | "flat") : undefined}
      sub={sub}
    />
  );
}

export function PctStat({ label, value, sub }: { label: string; value: number; sub?: ReactNode }) {
  return (
    <Stat
      label={label}
      value={signedPct(value)}
      tone={toneOf(value) as "pos" | "neg" | "flat"}
      sub={sub}
    />
  );
}

const STATE_TONE: Record<string, string> = {
  online: "ok",
  running: "ok",
  ok: "ok",
  filled: "ok",
  approved: "ok",
  closed: "ok",
  degraded: "warn",
  paused: "warn",
  half_open: "warn",
  partially_filled: "warn",
  reduced_size: "warn",
  starting: "warn",
  offline: "bad",
  halted: "bad",
  rejected: "bad",
  failed: "bad",
  open: "bad",
  unknown: "",
  stopped: "",
  finished: "info",
  no_trade: "",
};

export function Pill({ value, tone }: { value: string; tone?: string }) {
  const resolved = tone ?? STATE_TONE[value?.toLowerCase?.() ?? ""] ?? "";
  return (
    <span className={`pill ${resolved}`}>
      <i className="dot" />
      {titleCase(value ?? "unknown")}
    </span>
  );
}

export function Empty({ message }: { message: string }) {
  return <div className="empty">{message}</div>;
}

export function Bar({ value, max, tone }: { value: number; max: number; tone?: string }) {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className={`bar ${tone ?? ""}`}>
      <div style={{ width: `${percent}%` }} />
    </div>
  );
}

/**
 * The disclaimer that appears on every page showing numbers.
 *
 * Not legal boilerplate: a dashboard full of equity curves and P&L reads as a brokerage
 * account unless it says otherwise, and it is not one.
 */
export function SimulationFootnote() {
  return (
    <p className="footnote">
      Every number on this page is simulated. This platform holds no money, connects to no
      broker and has no custody of any asset — the &ldquo;capital&rdquo; is a value in a
      simulation and the fills come from a bar-based matching engine, not a venue. Results
      describe what one configuration produced on one dataset under one cost model. They are
      not a prediction, not a recommendation, and not evidence that the same configuration
      would behave this way on data it has not seen.
    </p>
  );
}
