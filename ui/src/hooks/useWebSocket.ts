import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { showToast } from "@/components/Toasts";

type ResourceEvent = {
  type: "resource_change";
  action: string;
  resource_id: string;
  provider_id: string;
};

/**
 * WebSocket hook that auto-invalidates React Query caches on resource changes.
 * Reconnects automatically with exponential backoff.
 */
export function useWebSocket() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      const ws = new WebSocket(`${protocol}//${host}/ws`);

      ws.onopen = () => {
        retryRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const data: ResourceEvent = JSON.parse(event.data as string);
          if (data.type === "resource_change") {
            queryClient.invalidateQueries({ queryKey: ["resources"] });
            queryClient.invalidateQueries({ queryKey: ["providers"] });
            queryClient.invalidateQueries({ queryKey: ["budget-status"] });
            showToast(`Resource ${data.resource_id}: ${data.action}`, "info");
          }
        } catch {
          // ignore non-JSON messages
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        const delay = Math.min(1000 * 2 ** retryRef.current, 30000);
        retryRef.current++;
        timerRef.current = setTimeout(connect, delay);
      };

      wsRef.current = ws;
    }

    connect();
    return () => {
      clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [queryClient]);
}
