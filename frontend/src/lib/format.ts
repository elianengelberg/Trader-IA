/** Formatting helpers. Money is always labelled simulated somewhere on the page. */

export const money = (value: number, digits = 2) =>
  value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const signedMoney = (value: number) => `${value >= 0 ? "+" : ""}${money(value)}`;

export const pct = (value: number, digits = 2) => `${value >= 0 ? "" : ""}${value.toFixed(digits)}%`;

export const signedPct = (value: number, digits = 2) =>
  `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;

export const qty = (value: number) =>
  Math.abs(value) >= 1 ? value.toFixed(4) : value.toPrecision(4);

export const clock = (iso: string) => {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toISOString().slice(11, 19);
};

export const dateTime = (iso: string) => {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toISOString().replace("T", " ").slice(0, 19);
};

export const titleCase = (value: string) =>
  value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** Positive is good, negative is bad — used for P&L colouring, never for a prediction. */
export const toneOf = (value: number) => (value > 0 ? "pos" : value < 0 ? "neg" : "flat");

/**
 * A per-trade return in basis points, as the dollars it means at the given trade size —
 * or null when no trade size is known, because $0.00 would be a lie, not a conversion.
 * The engine keeps deciding in basis points (they compare trades of different sizes);
 * this is purely how the number is spoken to a person.
 */
export const bpsUsdValue = (bps: number, notionalUsd?: number | null) =>
  notionalUsd && notionalUsd > 0 ? (bps / 10_000) * notionalUsd : null;

/** The same conversion, rendered: "+$1.23" / "−$0.45", or "—" with no known trade size. */
export const bpsUsd = (
  bps: number,
  notionalUsd?: number | null,
  opts?: { signed?: boolean; digits?: number },
) => {
  const value = bpsUsdValue(bps, notionalUsd);
  if (value === null) return "—";
  const digits = opts?.digits ?? 2;
  const sign = opts?.signed === false ? "" : value >= 0 ? "+" : "−";
  return `${sign}$${money(Math.abs(value), digits)}`;
};

/** Median dollars-at-work of the rows that carry one — the page-local conversion factor. */
export const medianNotional = (rows: Array<{ entry_price?: number; quantity?: number }>) => {
  const notionals = rows
    .map((row) => (row.entry_price ?? 0) * (row.quantity ?? 0))
    .filter((value) => value > 0)
    .sort((a, b) => a - b);
  if (notionals.length === 0) return null;
  const mid = Math.floor(notionals.length / 2);
  return notionals.length % 2 ? notionals[mid] : (notionals[mid - 1] + notionals[mid]) / 2;
};
