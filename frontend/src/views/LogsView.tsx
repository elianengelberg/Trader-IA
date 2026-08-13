import { useCallback, useEffect, useState } from "react";
import { api, type LogLine } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Card, Empty } from "../components/ui";
import { dateTime } from "../lib/format";

const LEVELS = ["", "INFO", "WARNING", "ERROR"];
const CHANNELS = ["", "runtime", "trading", "risk", "ai", "data"];

const LEVEL_CLASS: Record<string, string> = {
  ERROR: "neg",
  WARNING: "warn",
  INFO: "dim",
};

export function LogsView({ subscribe }: { subscribe: Subscribe }) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [level, setLevel] = useState("");
  const [channel, setChannel] = useState("");
  const [live, setLive] = useState(true);

  const load = useCallback(() => {
    api.logs(400, level || undefined, channel || undefined).then(setLines).catch(() => undefined);
  }, [level, channel]);

  useEffect(load, [load]);

  useStreamEvent(subscribe, "log", (data) => {
    if (!live) return;
    const line = data as LogLine;
    if (level && line.level !== level) return;
    if (channel && line.channel !== channel) return;
    setLines((previous) => [line, ...previous].slice(0, 400));
  });

  return (
    <>
      <h1>System log</h1>
      <p className="section-note">
        Streamed live from the runtime. Refusals are logged at the same volume as actions —
        a log that only records what happened cannot explain what did not.
      </p>

      <Card
        title={`Lines (${lines.length})`}
        actions={
          <div className="row">
            <select value={level} onChange={(e) => setLevel(e.target.value)}
              style={{ background: "var(--bg-input)", border: "1px solid var(--border-strong)", borderRadius: 7, padding: "4px 8px", fontSize: 12 }}>
              {LEVELS.map((value) => <option key={value} value={value}>{value || "All levels"}</option>)}
            </select>
            <select value={channel} onChange={(e) => setChannel(e.target.value)}
              style={{ background: "var(--bg-input)", border: "1px solid var(--border-strong)", borderRadius: 7, padding: "4px 8px", fontSize: 12 }}>
              {CHANNELS.map((value) => <option key={value} value={value}>{value || "All channels"}</option>)}
            </select>
            <label className="checkbox">
              <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
              Follow
            </label>
          </div>
        }
      >
        {lines.length === 0 ? (
          <Empty message="No log lines." />
        ) : (
          <div className="scroll tall">
            <table>
              <thead><tr><th>Time</th><th>Level</th><th>Channel</th><th>Component</th><th>Message</th></tr></thead>
              <tbody>
                {lines.map((line, index) => (
                  <tr key={`${line.at}-${index}`}>
                    <td className="faint">{dateTime(line.at)}</td>
                    <td className={LEVEL_CLASS[line.level] ?? ""}>{line.level}</td>
                    <td className="faint">{line.channel}</td>
                    <td className="faint">{line.component}</td>
                    <td style={{ fontFamily: "var(--sans)" }}>{line.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
