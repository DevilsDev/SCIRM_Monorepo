import { useCallback, useEffect, useState } from 'react';
import { api, Risk } from '../services/api';

interface UseRisksParams {
  limit?: number;
  offset?: number;
  severity?: string;
}

export function useRisks(params: UseRisksParams = {}) {
  const [risks, setRisks] = useState<Risk[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRisks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getRisks(params);
      setRisks(data.risks || []);
      setTotalCount(data.total || 0);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch risks');
      setRisks([]);
    } finally {
      setLoading(false);
    }
  }, [params.limit, params.offset, params.severity]);

  useEffect(() => {
    fetchRisks();
  }, [fetchRisks]);

  return { risks, totalCount, loading, error, refetch: fetchRisks };
}
