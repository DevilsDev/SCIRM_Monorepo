import { useParams, Link } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import SeverityBadge from '../components/SeverityBadge';
import { useRisk } from '../hooks/useRisk';

const priorityColors: Record<string, string> = {
  high: 'bg-red-100 text-red-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-green-100 text-green-800',
};

export default function RiskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { risk, recommendations, loading, error } = useRisk(id!);

  if (loading) {
    return <p className="text-sm text-gray-400">Loading risk details...</p>;
  }

  if (error || !risk) {
    return (
      <div className="space-y-4">
        <Link to="/risks" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
          <ArrowLeftIcon className="h-4 w-4" /> Back to risks
        </Link>
        <p className="text-sm text-red-500">{error || 'Risk not found'}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Link to="/risks" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
        <ArrowLeftIcon className="h-4 w-4" /> Back to risks
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{risk.title}</h1>
          <p className="text-sm text-gray-500 mt-1">
            Detected {new Date(risk.detected_at).toLocaleString()}
          </p>
        </div>
        <SeverityBadge severity={risk.severity} />
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Risk Details</h2>

          <p className="text-sm text-gray-700">{risk.description}</p>

          <div className="grid grid-cols-2 gap-4 pt-2">
            <div>
              <p className="text-xs text-gray-500">Probability</p>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 rounded-full h-2"
                    style={{ width: `${risk.probability * 100}%` }}
                  />
                </div>
                <span className="text-sm font-medium">{(risk.probability * 100).toFixed(0)}%</span>
              </div>
            </div>
            <div>
              <p className="text-xs text-gray-500">Impact Score</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{risk.impact_score.toFixed(1)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Category</p>
              <p className="text-sm font-medium text-gray-900 capitalize mt-1">{risk.risk_category}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Predicted Occurrence</p>
              <p className="text-sm text-gray-900 mt-1">{risk.predicted_occurrence || 'N/A'}</p>
            </div>
          </div>

          {/* Tags */}
          <div className="pt-2">
            <p className="text-xs text-gray-500 mb-2">Affected Entities</p>
            <div className="flex flex-wrap gap-1">
              {risk.affected_entities.length > 0 ? (
                risk.affected_entities.map((entity) => (
                  <span key={entity} className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs">
                    {entity}
                  </span>
                ))
              ) : (
                <span className="text-xs text-gray-400">None specified</span>
              )}
            </div>
          </div>

          <div className="pt-2">
            <p className="text-xs text-gray-500 mb-2">Data Sources</p>
            <div className="flex flex-wrap gap-1">
              {risk.data_sources.map((src) => (
                <span key={src} className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs">
                  {src}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Recommendations */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Recommendations ({recommendations.length})
          </h2>
          {recommendations.length === 0 ? (
            <p className="text-sm text-gray-400">No recommendations available for this risk.</p>
          ) : (
            <div className="space-y-4">
              {recommendations.map((rec) => (
                <div key={rec.id} className="border border-gray-100 rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <h3 className="text-sm font-medium text-gray-900">{rec.title}</h3>
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
                        priorityColors[rec.priority] || 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {rec.priority}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 mt-1">{rec.description}</p>
                  <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
                    {rec.estimated_cost != null && (
                      <span>${rec.estimated_cost.toLocaleString()}</span>
                    )}
                    {rec.timeline_days != null && <span>{rec.timeline_days}d</span>}
                    <span>{(rec.success_probability * 100).toFixed(0)}% success</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
