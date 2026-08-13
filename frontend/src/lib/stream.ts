/**
 * The Server-Sent Events hook.
 *
 * One connection for the whole app. Every view subscribes to the event types it cares
 * about; opening a stream per view would multiply connections for no benefit, since the
 * server pushes everything down one channel anyway.
 *
 * EventSource reconnects on its own, so there is no retry logic here — adding one would
 * fight the browser's. What is tracked is whether the connection is currently open, so
 * the header can say "live" or "reconnecting" honestly rather than showing stale numbers
 * as though they were current.
 */
import { useCallback, useEffect, useRef, useState } from "react";

type Handler = (data: unknown) => void;

const EVENT_TYPES = [
  "portfolio.updated",
  "decision.created",
  "order.state_changed",
  "order.fill_simulated",
  "ai.context_assessed",
  "news.received",
  "log",
  "runtime.started",
  "runtime.stopped",
  "runtime.finished",
  "runtime.error",
  "runtime.reset",
  "runtime.kill_switch",
  "system.reconciliation_completed",
  "backtest.completed",
] as const;

export type Subscribe = (type: string, handler: Handler) => () => void;

export function useEventStream(enabled: boolean) {
  const [connected, setConnected] = useState(false);
  const handlers = useRef(new Map<string, Set<Handler>>());

  useEffect(() => {
    if (!enabled) return;
    const source = new EventSource("/api/stream", { withCredentials: true });

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    const listeners: [string, EventListener][] = EVENT_TYPES.map((type) => {
      const listener: EventListener = (event) => {
        const message = event as MessageEvent<string>;
        let payload: unknown = message.data;
        try {
          payload = JSON.parse(message.data);
        } catch {
          /* a frame that is not JSON is still worth delivering as a string */
        }
        handlers.current.get(type)?.forEach((handler) => handler(payload));
      };
      source.addEventListener(type, listener);
      return [type, listener];
    });

    return () => {
      listeners.forEach(([type, listener]) => source.removeEventListener(type, listener));
      source.close();
      setConnected(false);
    };
  }, [enabled]);

  const subscribe = useCallback<Subscribe>((type, handler) => {
    const set = handlers.current.get(type) ?? new Set<Handler>();
    set.add(handler);
    handlers.current.set(type, set);
    return () => {
      set.delete(handler);
    };
  }, []);

  return { connected, subscribe };
}

/**
 * Subscribe for the lifetime of a component.
 *
 * The handler is held in a ref so a component can close over fresh state without
 * resubscribing on every render — resubscribing would drop events in the gap.
 */
export function useStreamEvent(subscribe: Subscribe, type: string, handler: Handler) {
  const stable = useRef(handler);
  stable.current = handler;
  useEffect(
    () => subscribe(type, (data) => stable.current(data)),
    [subscribe, type],
  );
}
