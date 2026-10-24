import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeftIcon, UserIcon, PlayIcon } from '@heroicons/react/24/outline';
import SeverityBadge from '../components/SeverityBadge';
import CommentsPanel from '../components/CommentsPanel';
import PlaybookRunner from '../components/PlaybookRunner';
import { Modal, Select } from '../components/ui';
import { useRisk } from '../hooks/useRisk';
import { api } from '../services/api';
import { useToast } from '../components/Toast';

const priorityColors: Record<string, string> = {
  high: 'bg-red-100 text-red-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-green-100 text-green-800',
};

const STATUS_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'mitigating', label: 'Mitigating' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'accepted', label: 'Accepted' },
];

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  investigating: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  mitigating: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  resolved: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  accepted: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

const TEAM_MEMBERS = [
  { value: '', label: 'Unassigned' },
  { value: 'sarah.chen', label: 'Sarah Chen (Risk Manager)' },
  { value: 'james.wilson', label: 'James Wilson (Analyst)' },
  { value: 'maria.garcia', label: 'Maria Garcia (Procurement)' },
  { value: 'david.kim', label: 'David Kim (IT Security)' },
  { value: 'anna.schmidt', label: 'Anna Schmidt (Compliance)' },
];

export default function RiskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { risk, recommendations, loading, error } = useRisk(id!);
  const { t } = useTranslation();
  const { addToast } = useToast();

  // Local state for owner and status (persisted in localStorage)
  const [owner, setOwner] = useState(() => localStorage.getItem(`scirm_risk_owner_${id}`) || '');
  const [status, setStatus] = useState(() => localStorage.getItem(`scirm_risk_status_${id}`) || 'open');
  const [showPlaybook, setShowPlaybook] = useState(false);

  const handleOwnerChange = async (newOwner: string) => {
    setOwner(newOwner);
    localStorage.setItem(`scirm_risk_owner_${id}`, newOwner);
    try {
      await api.updateRisk(id!, { owner: newOwner } as any);
    } catch { /* silent — localStorage is the fallback */ }
    const label = TEAM_MEMBERS.find((m) => m.value === newOwner)?.label || 'Unassigned';
    addToast('success', t('risks.ownerUpdated', 'Owner updated'), label);
  };

  const handleStatusChange = async (newStatus: string) => {
    setStatus(newStatus);
    localStorage.setItem(`scirm_risk_status_${id}`, newStatus);
    try {
      await api.updateRisk(id!, { status: newStatus } as any);
    } catch { /* silent */ }
    addToast('success', t('risks.statusUpdated', 'Status updated'), newStatus);
  };

  if (loading) {
    return <p className="text-sm text-gray-400">{t('risks.loadingDetails', 'Loading risk details...')}</p>;
  }

  if (error || !risk) {
    return (
      <div className="space-y-4">
        <Link to="/risks" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
          <ArrowLeftIcon className="h-4 w-4" /> {t('risks.backToRisks', 'Back to risks')}
        </Link>
        <p className="text-sm text-red-500">{error || t('risks.riskNotFound', 'Risk not found')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Link to="/risks" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
        <ArrowLeftIcon className="h-4 w-4" /> {t('risks.backToRisks', 'Back to risks')}
      </Link>

      {/* Header with actions */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{risk.title}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('risks.colDetected', 'Detected')} {new Date(risk.detected_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Status badge + changer */}
          <select
            value={status}
            onChange={(e) => handleStatusChange(e.target.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border-0 cursor-pointer ${STATUS_COLORS[status] || STATUS_COLORS.open}`}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <SeverityBadge severity={risk.severity} />
          <button
            onClick={() => setShowPlaybook(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 text-white rounded-lg text-xs font-medium hover:bg-purple-700 transition-colors"
          >
            <PlayIcon className="h-3.5 w-3.5" />
            {t('risks.runPlaybook', 'Run Playbook')}
          </button>
        </div>
      </div>

      {/* Owner assignment */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <UserIcon className="h-5 w-5 text-gray-400" />
        <span className="text-sm text-gray-500 dark:text-gray-400">{t('risks.assignedTo', 'Assigned to')}:</span>
        <select
          value={owner}
          onChange={(e) => handleOwnerChange(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
        >
          {TEAM_MEMBERS.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-6">
          {/* Risk Details */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('risks.riskDetails', 'Risk Details')}</h2>
            <p className="text-sm text-gray-700 dark:text-gray-300">{risk.description}</p>

            <div className="grid grid-cols-2 gap-4 pt-2">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">{t('risks.colProbability', 'Probability')}</p>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 bg-gray-200 rounded-full h-2">
                    <div className="bg-blue-600 rounded-full h-2" style={{ width: `${risk.probability * 100}%` }} />
                  </div>
                  <span className="text-sm font-medium">{(risk.probability * 100).toFixed(0)}%</span>
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">{t('risks.impactScore', 'Impact Score')}</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{risk.impact_score.toFixed(1)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">{t('risks.colCategory', 'Category')}</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white capitalize mt-1">{risk.risk_category}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">{t('risks.predictedOccurrence', 'Predicted Occurrence')}</p>
                <p className="text-sm text-gray-900 dark:text-white mt-1">{risk.predicted_occurrence || t('risks.na', 'N/A')}</p>
              </div>
            </div>

            {/* Tags */}
            <div className="pt-2">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('risks.affectedEntities', 'Affected Entities')}</p>
              <div className="flex flex-wrap gap-1">
                {risk.affected_entities.length > 0 ? (
                  risk.affected_entities.map((entity) => (
                    <span key={entity} className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded text-xs">{entity}</span>
                  ))
                ) : (
                  <span className="text-xs text-gray-400">{t('risks.noneSpecified', 'None specified')}</span>
                )}
              </div>
            </div>

            <div className="pt-2">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('risks.dataSources', 'Data Sources')}</p>
              <div className="flex flex-wrap gap-1">
                {risk.data_sources.map((src) => (
                  <span key={src} className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs">{src}</span>
                ))}
              </div>
            </div>
          </div>

          {/* Comments */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <CommentsPanel entityId={id!} entityType="risk" />
          </div>
        </div>

        {/* Recommendations */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {t('risks.recommendationsCount', 'Recommendations ({{count}})', { count: recommendations.length })}
          </h2>
          {recommendations.length === 0 ? (
            <p className="text-sm text-gray-400">{t('risks.noRecommendations', 'No recommendations available for this risk.')}</p>
          ) : (
            <div className="space-y-4">
              {recommendations.map((rec) => (
                <div key={rec.id} className="border border-gray-100 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <h3 className="text-sm font-medium text-gray-900 dark:text-white">{rec.title}</h3>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${priorityColors[rec.priority] || 'bg-gray-100 dark:bg-gray-700 text-gray-800'}`}>
                      {rec.priority}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">{rec.description}</p>
                  <div className="flex items-center gap-4 mt-3 text-xs text-gray-500 dark:text-gray-400">
                    {rec.estimated_cost != null && <span>${rec.estimated_cost.toLocaleString()}</span>}
                    {rec.timeline_days != null && <span>{rec.timeline_days}d</span>}
                    <span>{(rec.success_probability * 100).toFixed(0)}% {t('risks.success', 'success')}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Playbook Modal */}
      <Modal open={showPlaybook} onClose={() => setShowPlaybook(false)} title={t('playbooks.title', 'Incident Response Playbook')} description={risk.title} size="lg">
        <PlaybookRunner riskId={id} onClose={() => setShowPlaybook(false)} />
      </Modal>
    </div>
  );
}
