import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Health, type RuntimeSnapshot } from "./lib/api";
import { useEventStream } from "./lib/stream";
import { Login } from "./views/Login";
import { Controls } from "./views/Controls";
import { Dashboard } from "./views/Dashboard";
import { Markets } from "./views/Markets";
import { AiView } from "./views/AiView";
import { RiskView } from "./views/RiskView";
import { Portfolio } from "./views/Portfolio";
import { Orders } from "./views/Orders";
import { Backtests } from "./views/Backtests";
import { NewsView } from "./views/NewsView";
import { LogsView } from "./views/LogsView";
import { SystemView } from "./views/SystemView";
import { SettingsView } from "./views/SettingsView";
import { StrategyView } from "./views/StrategyView";
import { AnalyticsView } from "./views/AnalyticsView";
import { LiveView } from "./views/LiveView";
import { Pill } from "./components/ui";

type Tab =
  | "dashboard" | "markets" | "ai" | "risk" | "portfolio" | "orders"
  | "strategy" | "analytics" | "live"
  | "backtests" | "news" | "logs" | "system" | "settings";

const NAV: { group: string; items: { id: Tab; label: string }[] }[] = [
  {
    group: "Operate",
    items: [
      { id: "dashboard", label: "Dashboard" },
      { id: "markets", label: "Markets" },
      { id: "portfolio", label: "Portfolio" },
      { id: "orders", label: "Orders & Fills" },
    ],
  },
  {
    group: "Understand",
    items: [
      { id: "strategy", label: "Strategy & Costs" },
      { id: "ai", label: "AI Decisions" },
      { id: "risk", label: "Risk" },
      { id: "analytics", label: "Ruin Analytics" },
      { id: "news", label: "News" },
      { id: "backtests", label: "Backtests" },
    ],
  },
  {
    group: "Inspect",
    items: [
      { id: "live", label: "Live Trading" },
      { id: "system", label: "System" },
      { id: "logs", label: "Logs" },
      { id: "settings", label: "Settings" },
    ],
  },
];

export default function App() {
  const [user, setUser] = useState<{ username: string; role: string } | null>(null);
  const [checking, setChecking] = useState(true);
  const [tab, setTab] = useState<Tab>("dashboard");
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  const { connected, subscribe } = useEventStream(user !== null);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  const refreshRuntime = useCallback(async () => {
    try {
      setRuntime(await api.runtime());
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) setUser(null);
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    refreshRuntime();
    api.health().then(setHealth).catch(() => undefined);

    // The only timer in the app. Everything else arrives on the stream; health is a
    // liveness question the stream cannot answer, because a dead server sends nothing.
    const timer = window.setInterval(() => {
      api.health().then(setHealth).catch(() => undefined);
      refreshRuntime();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [user, refreshRuntime]);

  if (checking) {
    return <div className="login-shell"><span className="dim">Loading…</span></div>;
  }

  if (!user) {
    return <Login onAuthenticated={setUser} />;
  }

  const state = runtime?.state ?? "stopped";
  const capital = runtime?.capital;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>Trader-IA</strong>
          <span>Paper Trading</span>
        </div>
        <span className="sim-badge">SIMULATED CAPITAL · NO REAL MONEY</span>
        <Pill value={state} />
        {capital && capital.starting > 0 && (
          <span className="mono dim" style={{ fontSize: 13 }}>
            ${capital.equity.toLocaleString("en-US", { maximumFractionDigits: 2 })}
            <span className={capital.total_pnl >= 0 ? "pos" : "neg"} style={{ marginLeft: 8 }}>
              {capital.total_pnl >= 0 ? "+" : ""}
              {capital.total_pnl.toFixed(2)} ({capital.return_pct >= 0 ? "+" : ""}
              {capital.return_pct.toFixed(2)}%)
            </span>
          </span>
        )}
        <div className="topbar-spacer" />
        <span className={`pill ${connected ? "ok" : "warn"}`}>
          <i className="dot" />
          {connected ? "Live" : "Reconnecting"}
        </span>
        {health && <Pill value={health.status} />}
        <span className="dim" style={{ fontSize: 12 }}>{user.username}</span>
        <button
          className="btn small"
          onClick={() => api.logout().then(() => setUser(null))}
        >
          Sign out
        </button>
      </header>

      <div className="body">
        <nav className="sidenav">
          {NAV.map((group) => (
            <div key={group.group}>
              <div className="nav-group">{group.group}</div>
              {group.items.map((item) => (
                <button
                  key={item.id}
                  className={tab === item.id ? "active" : ""}
                  onClick={() => setTab(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <main>
          <Controls runtime={runtime} onChanged={refreshRuntime} subscribe={subscribe} />

          {tab === "dashboard" && <Dashboard runtime={runtime} subscribe={subscribe} />}
          {tab === "markets" && <Markets subscribe={subscribe} />}
          {tab === "portfolio" && <Portfolio subscribe={subscribe} />}
          {tab === "orders" && <Orders subscribe={subscribe} />}
          {tab === "ai" && <AiView runtime={runtime} subscribe={subscribe} />}
          {tab === "strategy" && <StrategyView subscribe={subscribe} />}
          {tab === "risk" && <RiskView subscribe={subscribe} />}
          {tab === "analytics" && <AnalyticsView subscribe={subscribe} />}
          {tab === "live" && <LiveView role={user.role} />}
          {tab === "news" && <NewsView subscribe={subscribe} />}
          {tab === "backtests" && <Backtests />}
          {tab === "system" && <SystemView health={health} runtime={runtime} />}
          {tab === "logs" && <LogsView subscribe={subscribe} />}
          {tab === "settings" && <SettingsView />}
        </main>
      </div>
    </div>
  );
}
