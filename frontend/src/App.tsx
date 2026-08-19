import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Health, type RuntimeSnapshot } from "./lib/api";
import { useEventStream } from "./lib/stream";
import { Login } from "./views/Login";
import { Dashboard } from "./views/Dashboard";
import { Markets } from "./views/Markets";
import { AiView } from "./views/AiView";
import { RiskView } from "./views/RiskView";
import { Portfolio } from "./views/Portfolio";
import { Orders } from "./views/Orders";
import { LogsView } from "./views/LogsView";
import { SystemView } from "./views/SystemView";
import { SettingsView } from "./views/SettingsView";
import { StrategyView } from "./views/StrategyView";
import { AnalyticsView } from "./views/AnalyticsView";
import { Learning } from "./views/Learning";
import { Advisor } from "./views/Advisor";
import { Intel } from "./views/Intel";
import { LiveView } from "./views/LiveView";
import { CapitalView } from "./views/CapitalView";
import { Pill } from "./components/ui";

type Tab =
  | "dashboard" | "markets" | "ai" | "risk" | "portfolio" | "orders"
  | "strategy" | "analytics" | "learning" | "advisor" | "intel" | "live" | "capital"
  | "logs" | "system" | "settings";

const NAV: { group: string; items: { id: Tab; label: string }[] }[] = [
  {
    group: "Operate",
    items: [
      { id: "dashboard", label: "Dashboard" },
      { id: "markets", label: "Markets" },
      { id: "portfolio", label: "Portfolio" },
      { id: "capital", label: "Capital" },
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
      { id: "learning", label: "Learning" },
      { id: "advisor", label: "Ask the AI" },
      { id: "intel", label: "Macro & News" },
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
  // The 24/7 session is the state that matters. The demo runtime being "stopped" is not
  // news — showing it as THE state while the real session runs read as a contradiction.
  const live = health?.live_runtime ?? null;
  const liveTone =
    live?.state === "running"
      ? "ok"
      : live?.state === "stopped"
        ? ""
        : live && ["safe_mode", "error"].includes(live.state)
          ? "bad"
          : "warn";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>Trader-IA</strong>
          <span>Paper Trading</span>
        </div>
        <span className="sim-badge">SIMULATED CAPITAL · NO REAL MONEY</span>
        {live ? (
          <>
            <span title="The 24/7 paper-live session — the state that matters">
              <Pill value={`24/7 · ${live.state}`} tone={liveTone} />
            </span>
            {(state === "running" || state === "paused") && (
              <span title="The synthetic demo run, separate from the 24/7 session">
                <Pill value={`demo · ${state}`} tone={state === "running" ? "ok" : "warn"} />
              </span>
            )}
          </>
        ) : (
          <Pill value={state} />
        )}
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
        {/* Stream connection status — NOT live trading. "Live" here read as
            "live trading", which is exactly what this platform is not; call it what
            it is: the event stream is connected or reconnecting. */}
        <span className={`pill ${connected ? "ok" : "warn"}`} title="Event-stream connection">
          <i className="dot" />
          {connected ? "Connected" : "Reconnecting"}
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
          {tab === "dashboard" && <Dashboard runtime={runtime} subscribe={subscribe} />}
          {tab === "markets" && <Markets subscribe={subscribe} />}
          {tab === "portfolio" && <Portfolio subscribe={subscribe} />}
          {tab === "orders" && <Orders subscribe={subscribe} />}
          {tab === "ai" && <AiView runtime={runtime} subscribe={subscribe} />}
          {tab === "strategy" && <StrategyView subscribe={subscribe} />}
          {tab === "risk" && <RiskView subscribe={subscribe} />}
          {tab === "analytics" && <AnalyticsView subscribe={subscribe} />}
          {tab === "learning" && <Learning subscribe={subscribe} />}
          {tab === "advisor" && <Advisor subscribe={subscribe} />}
          {tab === "intel" && <Intel />}
          {tab === "live" && <LiveView role={user.role} />}
          {tab === "capital" && <CapitalView subscribe={subscribe} />}
          {tab === "system" && <SystemView health={health} runtime={runtime} />}
          {tab === "logs" && <LogsView subscribe={subscribe} />}
          {tab === "settings" && <SettingsView />}
        </main>
      </div>
    </div>
  );
}
