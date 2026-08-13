import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Card, Empty, Pill, SimulationFootnote } from "../components/ui";

export function SettingsView() {
  const [settings, setSettings] = useState<Record<string, any> | null>(null);

  useEffect(() => { api.settings().then(setSettings).catch(() => undefined); }, []);

  if (!settings) return <Card><Empty message="Loading settings…" /></Card>;

  const llm = settings.llm ?? {};
  const marketData = settings.market_data ?? {};
  const execution = settings.execution ?? {};
  const riskLimits = settings.risk_limits ?? {};

  return (
    <>
      <h1>Settings</h1>
      <p className="section-note">
        Configuration as the server sees it. Secrets are never returned by this endpoint —
        the LLM row shows <em>whether</em> a key is configured, never the key.
      </p>

      <div className="grid cols-2">
        <Card title="Environment">
          <dl className="kv">
            <dt>Environment</dt><dd>{settings.environment}</dd>
            <dt>Mode</dt><dd>{settings.mode}</dd>
            <dt>Simulated only</dt><dd><Pill value={settings.simulated_only ? "yes" : "no"} tone="ok" /></dd>
            <dt>Database</dt><dd>{settings.database}</dd>
          </dl>
        </Card>

        <Card title="AI context layer">
          <dl className="kv">
            <dt>Provider</dt><dd>{llm.provider}</dd>
            <dt>Model</dt><dd>{llm.model}</dd>
            <dt>Enabled</dt><dd>{String(llm.enabled)}</dd>
            <dt>API key configured</dt>
            <dd>
              <Pill value={llm.api_key_configured ? "yes" : "no — using the offline mock"}
                tone={llm.api_key_configured ? "ok" : ""} />
            </dd>
            <dt>Daily call cap</dt><dd>{llm.max_calls_per_day}</dd>
            <dt>Daily cost cap</dt><dd>${llm.max_cost_usd_per_day}</dd>
          </dl>
          <p className="footnote" style={{ marginTop: 12, paddingTop: 8 }}>
            To use Claude instead of the offline mock, set <code>TIA_ANTHROPIC_API_KEY</code>{" "}
            in your environment or <code>.env</code> file and set the provider to{" "}
            <code>anthropic</code>. The key is read by the server process only; it is never
            placed in a prompt, returned by an endpoint, or written to a log.
          </p>
        </Card>

        <Card title="Market data">
          <dl className="kv">
            <dt>Provider</dt><dd>{marketData.provider}</dd>
            <dt>Symbols</dt><dd>{(marketData.symbols ?? []).join(", ")}</dd>
            <dt>Timeframe</dt><dd>{marketData.timeframe}</dd>
          </dl>
        </Card>

        <Card title="Execution cost model">
          <dl className="kv">
            {Object.entries(execution).map(([key, value]) => (
              <div key={key} style={{ display: "contents" }}>
                <dt>{key.replace(/_/g, " ")}</dt><dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card title="Risk limits">
          <div className="banner warn">
            Not editable from this interface. {riskLimits.reason}
          </div>
          <div className="scroll">
            <table>
              <thead><tr><th>Limit</th><th className="num">Value</th></tr></thead>
              <tbody>
                {Object.entries(riskLimits.values ?? {}).map(([key, value]) => (
                  <tr key={key}>
                    <td className="faint">{key}</td>
                    <td className="num">{String(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
      <SimulationFootnote />
    </>
  );
}
