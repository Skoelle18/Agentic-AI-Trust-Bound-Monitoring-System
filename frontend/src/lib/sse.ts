import { useEffect, useMemo, useRef, useState } from "react";
import type { AuditEvent } from "./api";

type SSEState = {
  events: any[];
  connected: boolean;
};

export function useSSE(url: string, maxEvents = 500): SSEState {
  const [events, setEvents] = useState<any[]>([]);
  const [connected, setConnected] = useState(false);
  const backoffRef = useRef(500);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let stopped = false;

    const connect = () => {
      if (stopped) return;
      const es = new EventSource(url);
      esRef.current = es;

      es.onopen = () => {
        backoffRef.current = 500;
        setConnected(true);
      };

      es.onerror = () => {
        setConnected(false);
        try {
          es.close();
        } catch {}
        if (stopped) return;
        const wait = backoffRef.current;
        backoffRef.current = Math.min(15000, Math.round(backoffRef.current * 1.8));
        setTimeout(connect, wait);
      };

      es.addEventListener("audit", (evt) => {
        try {
          const data = JSON.parse((evt as MessageEvent).data) as AuditEvent;
          setEvents((prev) => {
            const next = [data, ...prev];
            return next.length > maxEvents ? next.slice(0, maxEvents) : next;
          });
        } catch {}
      });
    };

    connect();
    return () => {
      stopped = true;
      try {
        esRef.current?.close();
      } catch {}
    };
  }, [url, maxEvents]);

  return useMemo(() => ({ events, connected }), [events, connected]);
}

