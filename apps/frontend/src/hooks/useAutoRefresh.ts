import { useEffect, useRef } from 'react';

/**
 * Auto-refresh hook — calls a callback at a regular interval.
 * Pauses when the tab is not visible.
 */
export function useAutoRefresh(callback: () => void, intervalMs: number = 30000) {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') {
        savedCallback.current();
      }
    };

    const id = setInterval(tick, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}
