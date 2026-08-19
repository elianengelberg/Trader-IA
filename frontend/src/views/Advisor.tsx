/**
 * Ask the AI — a read-only window into what the system is doing and why.
 *
 * You can ask it, in plain language, why it took a trade, what it has learned, whether it is
 * behaving. It answers from the system's own state, never from thin air. It has no button
 * that trades and no path to one: it explains, it cannot act. When a language model is
 * configured on the server the answers are in prose; without one, it returns the same
 * grounded briefing the model would reason over, so it is useful either way.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AdvisorAnswer, type AntiPatternReport } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Card, Empty, Pill, SimulationFootnote } from "../components/ui";

type Turn = { role: "you" | "advisor"; text: string; note?: string; grounded?: string[]; llm?: boolean };

const SUGGESTIONS = [
  "What are you doing right now, and why?",
  "Why are you not trading?",
  "What have you learned this session?",
  "Are you behaving, or drifting into bad habits?",
  "Explain your most recent decision.",
];

const SEV_TONE: Record<string, string> = { ok: "ok", watch: "warn", alert: "bad" };

export function Advisor({ subscribe }: { subscribe: Subscribe }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [audit, setAudit] = useState<AntiPatternReport | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const loadAudit = useCallback(() => {
    api.antipatterns().then(setAudit).catch(() => undefined);
  }, []);
  useEffect(loadAudit, [loadAudit]);
  useStreamEvent(subscribe, "trade.closed", loadAudit);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const ask = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setTurns((t) => [...t, { role: "you", text: q }]);
    setBusy(true);
    try {
      const answer: AdvisorAnswer = await api.advisorAsk(q);
      setTurns((t) => [
        ...t,
        {
          role: "advisor",
          text: answer.answer,
          note: answer.note,
          grounded: answer.grounded_on,
          llm: answer.used_llm,
        },
      ]);
    } catch {
      setTurns((t) => [
        ...t,
        { role: "advisor", text: "Couldn't reach the advisor just now. Try again in a moment." },
      ]);
    } finally {
      setBusy(false);
    }
  }, [busy]);

  const flagged = (audit?.checks ?? []).filter((c) => c.severity !== "ok");

  return (
    <>
      <h1>Ask the AI</h1>
      <p className="section-note">
        A read-only analyst you can question in plain language: why it took a trade, what it
        has learned, whether it is behaving. It answers only from the system&apos;s own state
        — it cannot place, size, or change anything, and it will say &ldquo;I don&apos;t have
        that&rdquo; rather than invent. When an AI key is set on the server the replies are in
        prose; otherwise it returns the grounded briefing the model would reason over.
      </p>

      <div className="grid" style={{ gridTemplateColumns: "1fr 300px", gap: 16, alignItems: "start" }}>
        <Card title="Conversation">
          <div ref={scroller} className="scroll tall" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {turns.length === 0 ? (
              <Empty message="Ask something about what the system is doing." />
            ) : (
              turns.map((turn, i) => (
                <div key={i} className={`chat-turn ${turn.role}`}>
                  <div className="chat-role">{turn.role === "you" ? "You" : "Advisor"}</div>
                  <div className="chat-body" style={{ whiteSpace: "pre-wrap" }}>{turn.text}</div>
                  {turn.role === "advisor" && (
                    <div className="chat-meta">
                      <Pill value={turn.llm ? "AI prose" : "system briefing"} tone={turn.llm ? "ok" : ""} />
                      {(turn.grounded ?? []).map((g) => (
                        <span key={g} className="chat-source">{g}</span>
                      ))}
                    </div>
                  )}
                  {turn.note && <div className="chat-note">{turn.note}</div>}
                </div>
              ))
            )}
            {busy && <div className="chat-turn advisor"><div className="chat-role">Advisor</div><div className="chat-body dim">thinking…</div></div>}
          </div>

          <form
            className="row"
            style={{ marginTop: 12, gap: 8 }}
            onSubmit={(e) => { e.preventDefault(); ask(input); }}
          >
            <input
              className="advisor-input"
              placeholder="Ask why it bought, what it learned, how it's thinking…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
            />
            <button className="btn primary" type="submit" disabled={busy || !input.trim()}>
              Ask
            </button>
          </form>

          <div className="row" style={{ marginTop: 10, gap: 6 }}>
            {SUGGESTIONS.map((s) => (
              <button key={s} className="btn small" onClick={() => ask(s)} disabled={busy}>
                {s}
              </button>
            ))}
          </div>
        </Card>

        <Card title="Behaviour audit">
          {!audit?.available ? (
            <Empty message={audit?.reason ?? "Start a session to audit its trading."} />
          ) : flagged.length === 0 ? (
            <div>
              <Pill value="all clear" tone="ok" />
              <p style={{ marginTop: 10, fontSize: 12, color: "var(--text-dim)" }}>
                No anti-patterns flagged in recent trading. The audit checks the system against
                documented ways accounts are emptied — overtrading, cost drag, revenge trading.
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {flagged.map((c) => (
                <div key={c.key}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <strong style={{ fontSize: 13 }}>{c.title}</strong>
                    <Pill value={c.severity} tone={SEV_TONE[c.severity] ?? ""} />
                  </div>
                  <p style={{ margin: "4px 0 0", fontSize: 12 }}>{c.detail}</p>
                  <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--text-faint)" }}>{c.principle}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <SimulationFootnote />
    </>
  );
}
