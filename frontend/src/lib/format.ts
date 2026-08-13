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
