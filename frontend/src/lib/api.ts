/**
 * The API client.
 *
 * Session lives in an HttpOnly cookie, so nothing here touches a token: `credentials:
 * "same-origin"` is the whole authentication story on this side. A 401 means the session
 * expired, and every caller treats that the same way — show the login screen — so it is
 * turned into one typed error rather than left for each call site to detect.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
  get isUnauthorized() {
    return this.status === 401;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* a non-JSON error body is still an error; the status carries the meaning */
    }
    throw new ApiError(String(detail), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export interface Capital {
  starting: number;
  equity: number;
  cash: number;
  invested: number;
  unrealized_pnl: number;
  realized_pnl: number;
  fees_paid?: number;
  total_pnl: number;
  return_pct: number;
  max_drawdown_pct: number;
  peak_equity?: number;
}

export interface RuntimeSnapshot {
  run_id: string | null;
  state: string;
  mode: string;
  simulated: boolean;
  scenario?: { id: string; title: string; demonstrates: string; expected_outcome: string };
  symbols?: string[];
  progress?: { bars_done: number; bars_total: number; percent: number };
  capital: Capital;
  risk?: {
    mode: string;
    kill_switch_reason: string;
    trades_today: number;
    new_trades_allowed: boolean;
    gross_exposure_pct: number;
    net_exposure_pct: number;
    limits: Record<string, number>;
  };
  ai?: {
    provider: string;
    enabled: boolean;
    assessments: number;
    neutral: number;
    rejections: number;
    budget: Record<string, unknown>;
  };
  counters: Record<string, number>;
  detail?: string;
  last_error?: string;
}

export interface Health {
  status: string;
  components: Record<string, string>;
  degraded: string[];
  uptime_seconds: number;
  version: string;
  simulated_only: boolean;
  live_runtime: {
    mode: string;
    state: string;
    heartbeat_age_seconds: number | null;
    market_data_age_seconds: number | null;
  } | null;
}

export interface Position {
  symbol: string;
  quantity: number;
  direction: string;
  average_price: number;
  last_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
  fees_paid: number;
  notional: number;
  opened_at: string | null;
}

export interface Decision {
  decision_id: string;
  symbol: string;
  decided_at: string;
  direction: string;
  base_confidence: number;
  confidence: number;
  verdict: string;
  approved_quantity: number;
  regime: string;
  data_quality_score: number;
  feature_hash: string;
  context_modifier: number;
  context_veto: boolean;
  context_used: boolean;
  context_reason: string;
  thesis: string;
  why_enter: string[];
  why_not_enter: string[];
  risk_checks: { name: string; passed: boolean; detail: string }[];
  features: Record<string, number>;
  snapshot: Record<string, unknown>;
  signal_id: string;
  correlation_id: string;
}

export interface Order {
  order_id: string;
  symbol: string;
  side: string;
  order_type: string;
  quantity: number;
  state: string;
  filled_quantity: number;
  average_fill_price: number;
  fees_paid: number;
  reject_reason: string;
  created_at: string;
  updated_at: string;
  signal_id: string;
}

export interface Fill {
  fill_id: string;
  order_id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  fee: number;
  slippage_bps: number;
  liquidity: string;
  filled_at: string;
}

export interface Assessment {
  assessment_id: string;
  symbol: string;
  created_at: string;
  expires_at: string;
  used: boolean;
  reason: string;
  provider: string;
  model_id: string;
  context_modifier: number;
  veto: boolean;
  leaning: string;
  confidence: number;
  thesis: string;
  supporting: string[];
  contradicting: string[];
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface Market {
  symbol: string;
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  change_pct: number;
  at: string;
  regime: string;
}

export interface NewsItem {
  news_id: string;
  published_at: string;
  source: string;
  headline: string;
  symbols: string[];
  sentiment: string;
  relevance: number;
  impact: string;
}

export interface LogLine {
  at: string;
  level: string;
  channel: string;
  component: string;
  message: string;
}

export interface Scenario {
  id: string;
  title: string;
  demonstrates: string;
  expected_outcome: string;
  bars: number;
  injects_data_faults: boolean;
  injects_llm_failure: boolean;
  tightens_risk_limits: boolean;
  news_items: number;
}

export interface Strategy {
  id: string;
  version: string;
  enabled: boolean;
  applicable_regimes: string[];
  description: string;
}

export interface Baseline {
  name: string;
  description: string;
  total_return_pct: number;
  max_drawdown_pct: number;
  sharpe: number | null;
  trades: number;
}

export interface Backtest {
  run_id: string;
  created_at: string;
  dataset: string;
  symbols: string[];
  timeframe: string;
  bars: number;
  verdict: string;
  total_return_pct: number;
  max_drawdown_pct: number;
  sharpe: number | null;
  trades: number;
  baselines: Baseline[];
  equity_curve: number[];
  evidence_statement: string;
  warnings: string[];
}

export interface RiskView {
  mode: string;
  kill_switch_reason: string;
  new_trades_allowed: boolean;
  gross_exposure_pct: number;
  net_exposure_pct: number;
  limits: Record<string, number>;
  blocked_by_check: Record<string, number>;
  rejected_total: number;
  approved_total: number;
  reconciliations: number;
  reconciliation_breaks: number;
}

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** A live order-book snapshot: `[price, quantity]` levels, bids descending, asks ascending.
 *
 * `available` is false when the venue could not be reached — the endpoint answers 200 with
 * an empty book and a reason rather than an error status, because the client polls it. */
export interface OrderBook {
  bids: [number, number][];
  asks: [number, number][];
  available?: boolean;
  reason?: string;
}

export interface StartOptions {
  scenario: string;
  symbols: string[];
  initial_capital: number;
  seed: number;
  bar_interval_seconds: number;
  strategies: string[];
  llm_enabled: boolean;
  news_enabled: boolean;
}

/** The itemised round-trip cost of a proposed trade, in basis points. */
export interface TradeCosts {
  fee_bps: number;
  spread_bps: number;
  slippage_bps: number;
  latency_bps: number;
  impact_bps: number;
  total_bps: number;
  total_currency: number;
  dominant: string;
}

export interface ExpectedValueRow {
  gross_edge_bps: number;
  net_edge_bps: number;
  net_edge_currency: number;
  threshold_bps: number;
  cost_ratio: number | null;
  tradeable: boolean;
  costs: TradeCosts;
  edge: {
    mean_bps: number;
    adjusted_bps: number;
    standard_error_bps: number;
    samples: number;
    regime: string;
    direction: string;
    confidence_band: number[];
  } | null;
  reason: string;
  explanation: string;
}

export interface RiskBudgetRow {
  state: string;
  profile: string;
  risk_currency: number;
  risk_pct: number;
  drawdown_multiplier: number;
  volatility_multiplier: number;
  streak_multiplier: number;
  total_multiplier: number;
  allows_new_trades: boolean;
  binding_constraint: string;
}

export interface Evaluation {
  symbol: string;
  at: string;
  signal_id: string;
  direction: string;
  confidence: number;
  price: number;
  budget: RiskBudgetRow;
  expected_value: ExpectedValueRow;
  tradeable: boolean;
}

export interface ClosedTrade {
  symbol: string;
  direction: string;
  regime: string;
  confidence: number;
  entry_price: number;
  exit_price: number;
  gross_bps: number;
  fees_bps: number;
  net_bps: number;
  expected_net_bps: number;
  closed_at: string;
  samples_now: number;
}

export interface Economics {
  available: boolean;
  reason?: string;
  profile?: Record<string, number | string>;
  budget?: RiskBudgetRow;
  consecutive_losses?: number;
  fees?: {
    maker_bps: number;
    taker_bps: number;
    round_trip_taker_bps: number;
    verified_at_source: boolean;
    source: string;
    requires_verification: boolean;
  };
  expected_value?: {
    enforcing: boolean;
    mode_explanation: string;
    threshold_bps: number;
    max_cost_ratio: number;
    evaluations: number;
    acceptance_rate: number;
    would_reject: number;
    rejected: number;
    no_evidence: number;
    min_samples: number;
    coverage: Record<string, number>;
    latest: Evaluation | null;
  };
  closed_trades?: {
    count: number;
    mean_net_bps: number | null;
    wins: number;
    losses: number;
    recent: ClosedTrade[];
  };
}

export interface Analytics {
  available: boolean;
  reason?: string;
  closed_trades?: number;
  ruin?: {
    probability_of_ruin: number;
    analytic_probability: number | null;
    median_max_drawdown_pct: number;
    worst_max_drawdown_pct: number;
    equity_5th_percentile: number;
    median_final_equity: number;
    longest_losing_streak: number;
    paths: number;
    horizon_trades: number;
    ruin_threshold: number;
    acceptable: boolean;
    seed: number;
  };
  explanation?: string;
  max_safe_risk_fraction?: number | null;
  max_safe_risk_note?: string;
  sample_warning?: string;
  profile?: Record<string, number | string>;
}

export interface CapitalView {
  simulated: boolean;
  currency: string;
  contributed: number;
  deposits: number;
  withdrawals: number;
  net_contributed: number;
  realized_pnl: number;
  unrealized_pnl: number;
  fees_paid: number;
  equity: number;
  cash: number;
  invested: number;
  trading_pnl: number;
  return_pct: number;
  max_drawdown_pct: number;
  peak_equity: number;
  live: {
    enabled: boolean;
    max_live_capital: number;
    allocated: number;
    note: string;
  };
  explanation: string;
}

export interface GateCheckRow {
  name: string;
  passed: boolean;
  reported: boolean;
  detail: string;
  remedy: string;
  rationale: string;
}

export interface GateReport {
  passed: boolean;
  evaluated_at: string;
  environment: string;
  total: number;
  failed: number;
  unreported: string[];
  checks: GateCheckRow[];
  explanation: string;
  live_enabled_in_config: boolean;
  max_live_capital: number;
  confirmation_phrase: string;
  ttl_seconds: number;
  venue_validation: Record<string, unknown> | null;
  custody_note: string;
}

export interface ActivationAttempt {
  attempt_id: string;
  attempted_at: string;
  operator: string;
  environment: string;
  passed: boolean;
  failed_checks: string[];
  configuration_fingerprint: string;
  runtime_started: boolean;
  runtime_state: string;
  detail: string;
}

export const api = {
  login: (username: string, password: string) =>
    post<{ username: string; role: string }>("/auth/login", { username, password }),
  logout: () => post<{ status: string }>("/auth/logout"),
  me: () => get<{ username: string; role: string }>("/auth/me"),

  health: () => get<Health>("/health"),
  runtime: () => get<RuntimeSnapshot>("/runtime"),
  portfolio: () =>
    get<RuntimeSnapshot & { equity_curve: { at: string; equity: number; drawdown_pct: number }[]; positions: Position[] }>(
      "/portfolio",
    ),
  positions: () => get<Position[]>("/positions"),
  orders: (limit = 100) => get<Order[]>(`/orders?limit=${limit}`),
  fills: (limit = 100) => get<Fill[]>(`/fills?limit=${limit}`),
  decisions: (limit = 60, actionableOnly = false) =>
    get<Decision[]>(`/decisions?limit=${limit}&actionable_only=${actionableOnly}`),
  assessments: (limit = 40) => get<Assessment[]>(`/assessments?limit=${limit}`),
  markets: () => get<Market[]>("/markets"),
  candles: (symbol: string, limit = 240) =>
    get<Candle[]>(`/markets/${encodeURIComponent(symbol)}/candles?limit=${limit}`),
  marketHistory: (symbol: string, timeframe = "1d", limit = 365) =>
    get<Candle[]>(
      `/markets/${encodeURIComponent(symbol)}/history?timeframe=${timeframe}&limit=${limit}`
    ),
  orderBook: (symbol: string, limit = 20) =>
    get<OrderBook>(`/markets/${encodeURIComponent(symbol)}/depth?limit=${limit}`),
  news: (limit = 40) => get<NewsItem[]>(`/news?limit=${limit}`),
  logs: (limit = 200, level?: string, channel?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (level) params.set("level", level);
    if (channel) params.set("channel", channel);
    return get<LogLine[]>(`/logs?${params}`);
  },
  risk: () => get<RiskView>("/risk"),
  strategies: () => get<Strategy[]>("/strategies"),
  economics: () => get<Economics>("/economics"),
  analytics: () => get<Analytics>("/analytics"),
  capital: () => get<CapitalView>("/capital"),
  liveGate: () => get<GateReport>("/live/gate"),
  armLive: (confirmation: string) =>
    post<{ armed: boolean; activation: Record<string, unknown> }>("/live/arm", { confirmation }),
  liveSnapshot: () => get<Record<string, unknown> & { active: boolean; state: string }>("/live"),
  liveHistory: () => get<ActivationAttempt[]>("/live/history"),
  liveStop: () => post<Record<string, unknown>>("/live/stop"),
  paperStart: () => post<Record<string, unknown>>("/live/paper-start"),
  liveKillSwitch: (reason: string) =>
    post<Record<string, unknown>>("/live/kill-switch", { reason }),
  changeRiskProfile: (profile: string) =>
    post<{ profile: string; previous: string; effective: string }>("/risk/profile", {
      profile,
      confirm: true,
    }),
  profileHistory: () =>
    get<{ at: string; actor: string; change: string }[]>("/risk/profile/history"),
  scenarios: () => get<Scenario[]>("/scenarios"),
  settings: () => get<Record<string, unknown>>("/settings"),
  systemStatus: () => get<Record<string, unknown>>("/system/status"),

  backtests: () => get<Backtest[]>("/backtests"),
  runBacktest: (body: { symbol: string; timeframe: string; bars: number; seed: number }) =>
    post<Backtest>("/backtests", body),

  start: (options: StartOptions) => post<RuntimeSnapshot>("/runtime/start", options),
  stop: () => post<RuntimeSnapshot>("/runtime/stop"),
  pause: () => post<RuntimeSnapshot>("/runtime/pause"),
  resume: () => post<RuntimeSnapshot>("/runtime/resume"),
  stopNewTrades: () => post<RuntimeSnapshot>("/runtime/stop-new-trades"),
  killSwitch: (reason: string) => post<RuntimeSnapshot>("/runtime/kill-switch", { reason }),
  releaseKillSwitch: (approvedBy: string) =>
    post<RuntimeSnapshot>("/runtime/release-kill-switch", { approved_by: approvedBy }),
  reset: (initialCapital: number) =>
    post<{ state: string; detail: string }>("/runtime/reset", {
      confirm: true,
      initial_capital: initialCapital,
    }),
};
