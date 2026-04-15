import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, Risk, Recommendation } from '../services/api';
import PriorityMatrix from '../components/PriorityMatrix';
import SeverityBadge from '../components/SeverityBadge';

interface RiskWithRecs {
  risk: Risk;
  recommendations: Recommendation[];
}

export default function RecommendationsPage() {
  const [groups, setGroups] = useState<RiskWithRecs[]>([]);
  const [allRecs, setAllRecs] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { t } = useTranslation();

  useEffect(() => {
    (async () => {
      try {
        const risksData = await api.getRisks({ limit: 50 });
        const risks: Risk[] = risksData.risks || [];

        const results = await Promise.all(
          risks.map(async (risk) => {
            try {
              const recData = await api.getRecommendations(risk.id);
              return { risk, recommendations: recData.recommendations || [] };
            } catch {
              return { risk, recommendations: [] };
            }
          })
        );

        setGroups(results.filter((g) => g.recommendations.length > 0));
        setAllRecs(results.flatMap((g) => g.recommendations));
      } catch (err: any) {
        setError(err.message || 'Failed to load recommendations');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const totalCost = allRecs.reduce((sum, r) => sum + (r.estimated_cost || 0), 0);
  const avgTimeline = allRecs.length
    ? allRecs.reduce((sum, r) => sum + (r.timeline_days || 0), 0) / allRecs.length
    : 0;
  const highCount = allRecs.filter((r) => r.priority === 'high').length;
  const mediumCount = allRecs.filter((r) => r.priority === 'medium').length;
  const lowCount = allRecs.filter((r) => r.priority === 'low').length;

  if (loading) return <p className="text-sm text-gray-400">{t('common.loading', 'Loading...')}</p>;
  if (error) return <p className="text-sm text-red-500">{error}</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('recommendations.title', 'Recommendations')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('recommendations.subtitle', '{{count}} recommendations across {{risks}} risks', { count: allRecs.length, risks: groups.length })}</p>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
          <p className="text-2xl font-bold text-gray-900 dark:text-white">${(totalCost / 1000).toFixed(0)}k</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('recommendations.totalCost', 'Total Est. Cost')}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{avgTimeline.toFixed(0)}d</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('recommendations.avgTimeline', 'Avg Timeline')}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
          <p className="text-2xl font-bold text-red-600">{highCount}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('recommendations.highPriority', 'High Priority')}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
          <p className="text-2xl font-bold text-yellow-600">{mediumCount}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('recommendations.mediumPriority', 'Medium Priority')}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
          <p className="text-2xl font-bold text-green-600">{lowCount}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('recommendations.lowPriority', 'Low Priority')}</p>
        </div>
      </div>

      {/* Priority Matrix */}
      {allRecs.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('recommendations.priorityMatrix', 'Priority Matrix')}</h2>
          <PriorityMatrix recommendations={allRecs} />
        </div>
      )}

      {/* Grouped Recommendations */}
      {groups.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <p className="text-sm text-gray-400">{t('recommendations.noRecommendations', 'No recommendations available. Run an assessment first.')}</p>
        </div>
      ) : (
        groups.map(({ risk, recommendations }) => (
          <div key={risk.id} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <div className="flex items-center gap-3 mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{risk.title}</h2>
              <SeverityBadge severity={risk.severity} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {recommendations.map((rec) => (
                <div key={rec.id} className="border border-gray-100 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <h3 className="text-sm font-medium text-gray-900 dark:text-white">{rec.title}</h3>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-full capitalize">
                      {rec.action_type}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">{rec.description}</p>
                  <div className="flex items-center gap-3 mt-3 text-xs text-gray-500 dark:text-gray-400">
                    {rec.estimated_cost != null && <span>${rec.estimated_cost.toLocaleString()}</span>}
                    {rec.timeline_days != null && <span>{rec.timeline_days}d</span>}
                    <div className="flex-1">
                      <div className="bg-gray-200 rounded-full h-1.5">
                        <div
                          className="bg-blue-600 rounded-full h-1.5"
                          style={{ width: `${rec.success_probability * 100}%` }}
                        />
                      </div>
                    </div>
                    <span>{(rec.success_probability * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
