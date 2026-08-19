/**
 * Macro & News — curated market intelligence, filter shown, garbage discarded.
 *
 * A short, fixed registry of sources: central-bank press feeds (the primary source for
 * international macro — rate decisions come from the institutions that make them) plus two
 * premier crypto newsrooms. Every headline is scored by readable rules and clickbait is
 * discarded outright; the terms that earned each item its place are displayed on it.
 *
 * Informational only, and the page says so: nothing here feeds the trading pipeline. A
 * headline is not measured edge, and this system only trades measured edge.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type IntelReport } from "../lib/api";
import { Card, Empty, Pill } from "../components/ui";

type KindFilter = "all" | "macro" | "crypto";

const KIND_TONE: Record<string, string> = { macro: "info", crypto: "ok", market: "", other: "" };

function age(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function Intel() {
  const [report, setReport] = useState<IntelReport | null>(null);
  const [filter, setFilter] = useState<KindFilter>("all");
  const [loading, setLoading] = useState(false);

  const load = useCallback((force = false) => {
    setLoading(true);
    api.intel(force)
      .then(setReport)
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => load(), [load]);

  const items = (report?.items ?? []).filter(
    (item) => filter === "all" || item.kind === filter,
  );
  const sources = report?.sources ?? [];
  const allDown = report?.available && (report.sources_ok ?? 0) === 0 && sources.length > 0;

  return (
    <>
      <h1>Macro &amp; News</h1>
      <p className="section-note">
        A fixed, curated registry — central-bank press feeds for international macro (Fed,
        ECB, Bank of England) plus premier crypto newsrooms — scored by a rules-based
        relevance filter that discards clickbait outright. Each item shows the terms that
        earned its place. <strong>Informational only:</strong> this page informs you and
        grounds the &ldquo;Ask the AI&rdquo; advisor; the trading pipeline does not act on
        headlines, because a headline is not measured edge.
      </p>

      <div className="row" style={{ marginBottom: 14, justifyContent: "space-between" }}>
        <div className="row" style={{ gap: 6 }}>
          {(["all", "macro", "crypto"] as const).map((kind) => (
            <button
              key={kind}
              className={`btn small ${filter === kind ? "primary" : ""}`}
              onClick={() => setFilter(kind)}
            >
              {kind === "all" ? "All" : kind === "macro" ? "Macro · long-term" : "Crypto"}
            </button>
          ))}
        </div>
        <div className="row" style={{ gap: 10 }}>
          {report?.available && (
            <span style={{ fontSize: 11.5, color: "var(--text-faint)" }}>
              {report.sources_ok}/{report.sources_total} sources ·{" "}
              {report.discarded ?? 0} discarded as garbage ·{" "}
              {report.filtered_irrelevant ?? 0} filtered as irrelevant
            </span>
          )}
          <button className="btn small" disabled={loading} onClick={() => load(true)}>
            {loading ? "Refreshing…" : "Refresh now"}
          </button>
        </div>
      </div>

      <Card title="Curated headlines">
        {items.length === 0 ? (
          <Empty
            message={
              allDown
                ? "No source could be reached from this server right now. The health panel below says which feed failed and how."
                : loading
                  ? "Fetching the curated feeds…"
                  : "Nothing relevant right now — the filter keeps this page empty rather than filling it with noise."
            }
          />
        ) : (
          <div className="scroll tall" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {items.map((item) => (
              <div key={item.item_id} className="intel-row">
                <div className="intel-score" title={`relevance ${item.relevance.toFixed(2)}`}>
                  <div
                    className="intel-score-fill"
                    style={{ height: `${Math.round(item.relevance * 100)}%` }}
                  />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 8, marginBottom: 3 }}>
                    <Pill value={item.kind} tone={KIND_TONE[item.kind] ?? ""} />
                    {item.horizon === "long" && <Pill value="long-term" tone="info" />}
                    {item.tier === "official" && <Pill value="primary source" tone="ok" />}
                    <span style={{ fontSize: 11, color: "var(--text-faint)" }}>
                      {item.source} · {age(item.published_at)}
                    </span>
                  </div>
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      style={{ color: "var(--text)", fontSize: 13.5, textDecoration: "none" }}
                    >
                      {item.headline}
                    </a>
                  ) : (
                    <span style={{ fontSize: 13.5 }}>{item.headline}</span>
                  )}
                  {item.matched.length > 0 && (
                    <div style={{ marginTop: 3, fontSize: 10.5, color: "var(--text-faint)" }}>
                      matched: {item.matched.slice(0, 6).join(", ")}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Source health — the whole registry, alive or not">
        <table>
          <thead>
            <tr>
              <th>Source</th>
              <th>Tier</th>
              <th>Region</th>
              <th>Status</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.source_id}>
                <td>{source.name}</td>
                <td><Pill value={source.tier} tone={source.tier === "official" ? "ok" : ""} /></td>
                <td className="mono" style={{ fontSize: 12 }}>{source.region}</td>
                <td>
                  <Pill
                    value={source.ok === null ? "not tried" : source.ok ? "ok" : "failed"}
                    tone={source.ok === null ? "" : source.ok ? "ok" : "bad"}
                  />
                </td>
                <td style={{ fontSize: 11.5, color: "var(--text-faint)" }}>{source.detail || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="footnote">
          The registry is code, not configuration — adding a source is a reviewed change.
          A feed that moves or dies shows up here as failed instead of silently vanishing.
        </p>
      </Card>
    </>
  );
}
