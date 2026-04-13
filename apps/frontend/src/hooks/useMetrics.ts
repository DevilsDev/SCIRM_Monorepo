import { useEffect, useState } from 'react';
import { api } from '../services/api';

export function useMetrics() {
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getMetrics()
      .then(setMetrics)
      .catch((err) => setError(err.message || 'Failed to fetch metrics'))
      .finally(() => setLoading(false));
  }, []);

  return { metrics, loading, error };
}
