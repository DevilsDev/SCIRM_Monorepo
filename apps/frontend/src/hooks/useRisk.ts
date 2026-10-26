import { useEffect, useState } from 'react';
import { api, Risk, Recommendation } from '../services/api';

export function useRisk(id: string) {
  const [risk, setRisk] = useState<Risk | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;

    setLoading(true);
    setError(null);

    Promise.all([api.getRisk(id), api.getRecommendations(id)])
      .then(([riskData, recData]) => {
        setRisk(riskData);
        setRecommendations(recData.recommendations || []);
      })
      .catch((err) => {
        setError(err.message || 'Failed to fetch risk details');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id]);

  return { risk, recommendations, loading, error };
}
