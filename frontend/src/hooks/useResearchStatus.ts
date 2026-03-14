import { useState, useCallback } from 'react';
import { useWebSocket } from './useWebSocket';
import type { ResearchSession, ResearchStatusMessage } from '../types/research';

export function useResearchStatus() {
  const [sessions, setSessions] = useState<ResearchSession[]>([]);

  const apiKey = localStorage.getItem('irt_api_key') || '';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = import.meta.env.VITE_WS_URL || `${protocol}//${window.location.host}`;
  const url = `${host}/api/research/status?api_key=${encodeURIComponent(apiKey)}`;

  const handleMessage = useCallback((data: unknown) => {
    const msg = data as ResearchStatusMessage;
    if (msg && Array.isArray(msg.sessions)) {
      setSessions((prev) => {
        if (prev.length === 0) {
          // Initial load from server — use as-is
          return msg.sessions;
        }
        // Merge: update existing sessions, add new ones
        const updated = [...prev];
        for (const incoming of msg.sessions) {
          const idx = updated.findIndex((s) => s.id === incoming.id);
          if (idx >= 0) {
            updated[idx] = incoming;
          } else {
            updated.push(incoming);
          }
        }
        return updated;
      });
    }
  }, []);

  const { isConnected } = useWebSocket({
    url,
    onMessage: handleMessage,
    enabled: !!apiKey,
  });

  return { sessions, isConnected };
}
