import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PlusIcon } from '@heroicons/react/24/outline';
import EntityForm, { EntityData } from '../components/EntityForm';
import GaugeChart from '../components/d3/GaugeChart';
import { api, RiskAssessmentResponse } from '../services/api';

function newEntity(): EntityData {
  return { id: crypto.randomUUID(), name: '', type: '', location: '' };
}

const PRIORITY_OPTIONS = [
  'supply_disruption',
  'regulatory',
  'financial',
  'environmental',
  'geopolitical',
];

export default function NewAssessmentPage() {
  const [entities, setEntities] = useState<EntityData[]>([newEntity()]);
  const [assessmentType, setAssessmentType] = useState('comprehensive');
  const [timeHorizon, setTimeHorizon] = useState(30);
  const [selectedPriorities, setSelectedPriorities] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<RiskAssessmentResponse | null>(null);

  const updateEntity = (index: number, entity: EntityData) => {
    const next = [...entities];
    next[index] = entity;
    setEntities(next);
  };

  const removeEntity = (index: number) => {
    setEntities(entities.filter((_, i) => i !== index));
  };

  const togglePriority = (p: string) => {
    setSelectedPriorities((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setResult(null);

    const validEntities = entities.filter((e) => e.name && e.type);
    if (validEntities.length === 0) {
      setError('At least one entity with name and type is required.');
      return;
    }

    setLoading(true);
    try {
      const response = await api.assessRisk({
        entities: validEntities.map((e) => ({
          id: e.id,
          name: e.name,
          type: e.type,
          location: e.location || undefined,
        })),
        assessment_type: assessmentType,
        time_horizon_days: timeHorizon,
        priority_factors: selectedPriorities.length > 0 ? selectedPriorities : undefined,
        context: { organization_id: 'a0000000-0000-0000-0000-000000000001' },
      });
      setResult(response);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Assessment failed. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">New Risk Assessment</h1>
        <p className="text-sm text-gray-500 mt-1">Configure and run a supply chain risk assessment</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Entities */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Entities to Assess</h2>
          <div className="space-y-3">
            {entities.map((entity, i) => (
              <EntityForm
                key={entity.id}
                entity={entity}
                onChange={(e) => updateEntity(i, e)}
                onRemove={() => removeEntity(i)}
                canRemove={entities.length > 1}
              />
            ))}
          </div>
          <button
            type="button"
            onClick={() => setEntities([...entities, newEntity()])}
            className="mt-3 inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800"
          >
            <PlusIcon className="h-4 w-4" /> Add Entity
          </button>
        </div>

        {/* Configuration */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Assessment Configuration</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Assessment Type</label>
              <select
                value={assessmentType}
                onChange={(e) => setAssessmentType(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value="comprehensive">Comprehensive</option>
                <option value="quick">Quick</option>
                <option value="targeted">Targeted</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Time Horizon (days)</label>
              <input
                type="number"
                min={1}
                max={365}
                value={timeHorizon}
                onChange={(e) => setTimeHorizon(Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
          </div>

          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">Priority Factors</label>
            <div className="flex flex-wrap gap-2">
              {PRIORITY_OPTIONS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => togglePriority(p)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                    selectedPriorities.includes(p)
                      ? 'bg-blue-100 text-blue-800 border-blue-300'
                      : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {p.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-4 py-3">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Assessing risks...' : 'Run Assessment'}
        </button>
      </form>

      {/* Results */}
      {result && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Assessment Complete</h2>
          <div className="flex items-center justify-around">
            <div className="text-center">
              <p className="text-3xl font-bold text-gray-900">{result.risks.length}</p>
              <p className="text-xs text-gray-500">Risks Identified</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold text-gray-900">{result.recommendations.length}</p>
              <p className="text-xs text-gray-500">Recommendations</p>
            </div>
            <GaugeChart value={Math.round(result.confidence_score * 100)} label="Confidence" size={120} />
          </div>

          {/* Reasoning Trail */}
          {result.reasoning_trail.length > 0 && (
            <div className="pt-4 border-t border-gray-200">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Agent Reasoning Trail</h3>
              <div className="space-y-3">
                {result.reasoning_trail.map((step, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 text-blue-800 flex items-center justify-center text-xs font-medium">
                      {i + 1}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900 capitalize">{step.agent}</p>
                      <p className="text-xs text-gray-600">{step.output || step.reasoning}</p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Confidence: {(step.confidence * 100).toFixed(0)}%
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <Link
            to="/risks"
            className="inline-block text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            View all risks &rarr;
          </Link>
        </div>
      )}
    </div>
  );
}
