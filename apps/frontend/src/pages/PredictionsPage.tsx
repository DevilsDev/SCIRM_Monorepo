import { useEffect, useState } from 'react';
import { api } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';
import AnimatedBars from '../components/d3/AnimatedBars';
import GaugeChart from '../components/d3/GaugeChart';

interface Prediction {
  id: string;
  category: string;
  predicted_disruption_probability: number;
  severity: string;
  risk_count: number;
  average_impact: number;
  horizon_days: number;
  recommendation: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
};

export default function PredictionsPage() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api
      .getPredictions()
      .then((data) => setPredictions(data.predictions || []))
      .catch((err) => setError(err.message || 'Failed to load predictions'))
      .finally(() => setLoading(false));
  }, []);

  const barData = predictions.map((p) => ({
    name: p.category,
    value: Math.round(p.predicted_disruption_probability * 100),
    color: SEVERITY_COLORS[p.severity] || '#94a3b8',
  }));

  if (loading) return <p className="text-sm text-gray-400">Loading predictions...</p>;
  if (error) return <p className="text-sm text-red-500">{error}</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">7-Day Disruption Predictions</h1>
        <p className="text-sm text-gray-500 mt-1">
          {predictions.length} risk categories analyzed
        </p>
      </div>

      {predictions.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
          <p className="text-sm text-gray-400">No predictions available. Run an assessment first to generate risk data.</p>
        </div>
      ) : (
        <>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Disruption Probability by Category</h2>
            <AnimatedBars data={barData} height={predictions.length * 55 + 60} maxValue={100} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {predictions.map((p) => (
              <div key={p.id} className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-900 capitalize">{p.category}</h3>
                  <SeverityBadge severity={p.severity} />
                </div>
                <div className="flex items-center gap-4 mb-3">
                  <GaugeChart value={Math.round(p.predicted_disruption_probability * 100)} label="Disruption" size={100} />
                  <div className="flex-1 grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-2xl font-bold text-gray-900">{p.risk_count}</p>
                      <p className="text-xs text-gray-500">Active Risks</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-gray-900">{p.average_impact.toFixed(1)}</p>
                      <p className="text-xs text-gray-500">Avg Impact</p>
                    </div>
                  </div>
                </div>
                <p className="text-xs text-gray-600 bg-gray-50 rounded-lg p-3">{p.recommendation}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
